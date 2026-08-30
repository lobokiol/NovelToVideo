"""剧本管理服务：把剧本创作工作台的剧本草案解析并同步落库。

解析规则与前端 utils/screenwritingScript.ts 同构（EP 标题、场号 slug、日夜内外），
保证两端分集一致。同步幂等：同一来源会话更新同一份计划，已锁定集不被覆盖。
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.asset import Asset, AssetEpisode
from app.models.script import ScriptEpisode, ScriptPlan
from app.services import project as project_service
from app.services.screenwriting.constants import WORKFLOW_PROJECT_CONFIG
from app.services.screenwriting.quality import iter_episode_blocks
from app.services.screenwriting.state import (
    acquire_session_lock,
    build_session_isolation_key,
    load_chat_session_state,
)
from app.utils.time_tools import utc_now


class ScriptServiceError(Exception):
    """剧本管理服务失败。"""


class ScriptPlanNotFoundError(ScriptServiceError):
    """剧本计划不存在或无权访问。"""


class ScriptEpisodeNotFoundError(ScriptServiceError):
    """剧本分集不存在或无权访问。"""


@dataclass(frozen=True)
class ExportedScriptZip:
    """剧本分集导出的 ZIP 文件内容。"""

    filename: str
    content: bytes
    episode_count: int


_SCENE_SLUG_RE = re.compile(r"^(\d+\s*[-－]\s*\d+)\s+(.+)$")
_SCENE_TIME_RE = re.compile(r"(日|夜|晨|清晨|上午|中午|午后|下午|傍晚|黄昏|深夜|连续)")
_SCENE_PLACE_RE = re.compile(r"(内|外)")
_EP_TITLE_TAIL_RE = re.compile(r"\bEP\s*0?\d+\s*[：:\-\s]*(.*)$", re.IGNORECASE)
_CN_TITLE_RE = re.compile(r"第\s*\d+\s*集\s*(.*)$")
_UNSAFE_ZIP_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass(frozen=True)
class ParsedScene:
    number: str
    title: str
    location: str
    day_night: str
    interior_exterior: str


@dataclass(frozen=True)
class ParsedEpisode:
    episode_index: int
    title: str
    summary: str
    body: str
    scenes: list[ParsedScene]


def parse_script_episodes(content: str) -> list[ParsedEpisode]:
    """把剧本 Markdown 解析为分集结构。"""
    episodes: list[ParsedEpisode] = []
    for episode_no, block in iter_episode_blocks(content):
        lines = block.splitlines()
        title = _parse_episode_title(lines[0] if lines else "", episode_no)
        episodes.append(
            ParsedEpisode(
                episode_index=episode_no,
                title=title,
                summary=_extract_summary(block),
                body=block.strip(),
                scenes=_parse_scenes(block),
            )
        )
    return episodes


def _parse_episode_title(heading: str, episode_no: int) -> str:
    text = heading.strip().lstrip("#").strip()
    ep_match = _EP_TITLE_TAIL_RE.search(text)
    if ep_match and ep_match.group(1).strip():
        return ep_match.group(1).strip()
    cn_match = _CN_TITLE_RE.search(text)
    if cn_match and cn_match.group(1).strip():
        return cn_match.group(1).strip()
    return f"第{episode_no}集"


def _extract_summary(block: str) -> str:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^#{1,6}\s*剧情梗概\s*$", line.strip()):
            collected: list[str] = []
            for tail in lines[index + 1 :]:
                trimmed = tail.strip()
                if not trimmed:
                    continue
                if trimmed == "---" or _parse_scene_heading(trimmed) is not None or trimmed.startswith("#"):
                    break
                collected.append(trimmed)
            if collected:
                return "".join(collected)
    for line in lines:
        trimmed = line.strip()
        if (
            len(trimmed) >= 24
            and not trimmed.startswith("#")
            and trimmed != "---"
            and _parse_scene_heading(trimmed) is None
            and not trimmed.startswith("人物：")
            and not trimmed.startswith("△")
        ):
            return trimmed
    return ""


def _parse_scene_heading(line: str) -> tuple[str, str] | None:
    text = line.strip()
    slug = _SCENE_SLUG_RE.match(text)
    if slug and _SCENE_TIME_RE.search(slug.group(2)) and _SCENE_PLACE_RE.search(slug.group(2)):
        return slug.group(1).replace(" ", ""), slug.group(2).strip()
    markdown = re.match(r"^#{1,6}\s*(场景[一二三四五六七八九十\d]+)[：:]\s*(.+)$", text)
    if markdown:
        return markdown.group(1), markdown.group(2).strip()
    return None


def _parse_scenes(block: str) -> list[ParsedScene]:
    scenes: list[ParsedScene] = []
    for line in block.splitlines():
        heading = _parse_scene_heading(line)
        if heading is None:
            continue
        number, title = heading
        day_match = _SCENE_TIME_RE.search(title)
        place_match = _SCENE_PLACE_RE.search(title)
        location = re.split(r"\s+", title)[0] if title else ""
        scenes.append(
            ParsedScene(
                number=number,
                title=title,
                location=location,
                day_night=day_match.group(1) if day_match else "",
                interior_exterior=place_match.group(1) if place_match else "",
            )
        )
    return scenes


def _scenes_to_json(scenes: list[ParsedScene]) -> str:
    return json.dumps(
        [
            {
                "number": scene.number,
                "title": scene.title,
                "location": scene.location,
                "dayNight": scene.day_night,
                "interiorExterior": scene.interior_exterior,
            }
            for scene in scenes
        ],
        ensure_ascii=False,
    )


async def sync_current_workspace(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    title: str = "",
) -> ScriptPlan:
    """加载当前剧本创作会话，把剧本工作区同步为剧本计划。

    标题缺省时依次取：用户传入 > 项目名称 > 「未命名剧本」。
    """
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    lock = await acquire_session_lock(project_public_id, user_public_id)
    async with lock:
        state = await load_chat_session_state(session, project, project_public_id, user_public_id)
    config = state.workflow.get(WORKFLOW_PROJECT_CONFIG)
    config = dict(config) if isinstance(config, dict) else {}
    resolved_title = title.strip() or str(getattr(project, "name", "") or "").strip() or "未命名剧本"
    return await sync_workspace_to_plan(
        session,
        project_public_id,
        user_public_id,
        script_content=state.workspace.script,
        title=resolved_title,
        config=config,
    )


async def sync_workspace_to_plan(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    script_content: str,
    title: str,
    config: dict[str, Any] | None = None,
) -> ScriptPlan:
    """把剧本工作区正文同步为剧本计划与分集（幂等：同源会话更新同一计划）。

    已锁定（is_locked）的分集保留不覆盖；正文实质变化的分集 version 递增；
    本次正文中不再存在的非锁定分集会被移除。
    """
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    episodes = parse_script_episodes(script_content)
    if not episodes:
        raise ScriptServiceError("当前剧本工作区没有可同步的分集内容，请先生成剧本草案")

    isolation_key = build_session_isolation_key(project_public_id, user_public_id)
    config = config or {}
    plan = await _get_or_create_plan(session, project, user_public_id, isolation_key)
    plan.title = title.strip() or plan.title or "未命名剧本"
    plan.total_episodes = str(config.get("totalEpisodes", "") or "")
    plan.episode_duration = str(config.get("episodeDuration", "") or "")
    plan.source_range = str(config.get("sourceRange", "") or "")
    plan.platform_spec = str(config.get("platformSpec", "") or "")
    plan.style = str(config.get("style", "") or "")
    plan.paywall = str(config.get("paywall", "") or "")
    plan.status = "synced"
    plan.updated_at = utc_now()
    session.add(plan)
    await session.flush()

    existing = await _load_plan_episodes(session, plan.id)
    existing_by_index = {episode.episode_index: episode for episode in existing}
    incoming_indexes = {episode.episode_index for episode in episodes}

    for parsed in episodes:
        current = existing_by_index.get(parsed.episode_index)
        if current is not None and current.is_locked:
            continue  # 人工锁定集不被同步覆盖。
        scenes_json = _scenes_to_json(parsed.scenes)
        if current is None:
            session.add(
                ScriptEpisode(
                    plan_id=plan.id,
                    episode_index=parsed.episode_index,
                    title=parsed.title,
                    summary=parsed.summary,
                    body=parsed.body,
                    scenes=scenes_json,
                    version=1,
                )
            )
            continue
        if current.body != parsed.body:
            current.version += 1
        current.title = parsed.title
        current.summary = parsed.summary
        current.body = parsed.body
        current.scenes = scenes_json
        current.updated_at = utc_now()
        session.add(current)

    # 移除本次正文中不再存在、且未锁定的分集。
    for episode in existing:
        if episode.episode_index not in incoming_indexes and not episode.is_locked:
            await session.delete(episode)

    await session.flush()
    return plan


async def get_plan_detail(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    plan_public_id: str,
) -> tuple[ScriptPlan, list[ScriptEpisode]]:
    """读取剧本计划详情与分集（校验归属当前用户与项目）。"""
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    plan = await _get_plan_or_raise(session, project, user_public_id, plan_public_id)
    episodes = await _load_plan_episodes(session, plan.id)
    return plan, episodes


async def list_plans(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
) -> list[ScriptPlan]:
    """列出项目下当前用户的剧本计划（按更新时间倒序）。"""
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    statement = (
        select(ScriptPlan)
        .where(
            ScriptPlan.project_id == project.id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
        )
        .order_by(ScriptPlan.updated_at.desc())
    )
    return list((await session.exec(statement)).all())


async def _get_or_create_plan(
    session: AsyncSession,
    project: Any,
    user_public_id: str,
    isolation_key: str,
) -> ScriptPlan:
    statement = select(ScriptPlan).where(
        ScriptPlan.source_isolation_key == isolation_key,
        ScriptPlan.disabled_at.is_(None),
    )
    plan = (await session.exec(statement)).first()
    if plan is not None:
        return plan
    return ScriptPlan(
        project_id=project.id,
        user_public_id=user_public_id,
        source_isolation_key=isolation_key,
    )


async def _load_plan_episodes(session: AsyncSession, plan_id: int) -> list[ScriptEpisode]:
    statement = (
        select(ScriptEpisode)
        .where(ScriptEpisode.plan_id == plan_id, ScriptEpisode.disabled_at.is_(None))
        .order_by(ScriptEpisode.episode_index)
    )
    return list((await session.exec(statement)).all())


async def _get_plan_or_raise(
    session: AsyncSession,
    project: Any,
    user_public_id: str,
    plan_public_id: str,
) -> ScriptPlan:
    """按公开 ID 获取剧本计划，不存在或不归属当前项目/用户时抛业务异常。"""
    statement = select(ScriptPlan).where(
        ScriptPlan.public_id == plan_public_id,
        ScriptPlan.project_id == project.id,
        ScriptPlan.user_public_id == user_public_id,
        ScriptPlan.disabled_at.is_(None),
    )
    plan = (await session.exec(statement)).first()
    if plan is None:
        raise ScriptPlanNotFoundError("剧本计划不存在或无权访问")
    return plan


async def create_plan_from_content(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    title: str,
    content: str,
) -> ScriptPlan:
    """把整段剧本 Markdown 解析为分集并落库为一份新的剧本计划（手动新建/导入）。

    每次调用都创建一份独立计划，来源隔离键以 manual: 前缀加随机串保证唯一；
    解析不出任何分集时报错。
    """
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    episodes = parse_script_episodes(content)
    if not episodes:
        raise ScriptServiceError("未能从内容中解析出分集，请检查剧本格式（需含分集标题）")

    resolved_title = title.strip() or str(getattr(project, "name", "") or "").strip() or "未命名剧本"
    plan = ScriptPlan(
        project_id=project.id,
        user_public_id=user_public_id,
        source_isolation_key=f"manual:{uuid4()}",
        title=resolved_title,
        status="manual",
    )
    session.add(plan)
    await session.flush()

    for parsed in episodes:
        session.add(
            ScriptEpisode(
                plan_id=plan.id,
                episode_index=parsed.episode_index,
                title=parsed.title,
                summary=parsed.summary,
                body=parsed.body,
                scenes=_scenes_to_json(parsed.scenes),
                version=1,
            )
        )
    await session.flush()
    return plan


async def list_project_episodes(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
) -> list[tuple[ScriptEpisode, str, str, list[Asset]]]:
    """平铺列出项目下当前用户的全部分集，每项携带所属计划的公开 ID 与标题。"""
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    statement = (
        select(ScriptEpisode, ScriptPlan.public_id, ScriptPlan.title)
        .join(ScriptPlan, ScriptEpisode.plan_id == ScriptPlan.id)
        .where(
            ScriptPlan.project_id == project.id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
            ScriptEpisode.disabled_at.is_(None),
        )
        .order_by(ScriptPlan.updated_at.desc(), ScriptPlan.id, ScriptEpisode.episode_index)
    )
    result = await session.exec(statement)
    rows = [(episode, plan_public_id, plan_title) for episode, plan_public_id, plan_title in result.all()]
    if not rows:
        return []

    episode_ids = [int(episode.id) for episode, _, _ in rows if episode.id is not None]
    assets_by_episode_id: dict[int, list[Asset]] = {episode_id: [] for episode_id in episode_ids}
    if episode_ids:
        asset_statement = (
            select(AssetEpisode.episode_id, Asset)
            .join(Asset, AssetEpisode.asset_id == Asset.id)
            .where(
                AssetEpisode.project_id == project.id,
                AssetEpisode.user_public_id == user_public_id,
                AssetEpisode.episode_id.in_(episode_ids),
                Asset.disabled_at.is_(None),
                Asset.main_asset.is_(True),
            )
            .order_by(Asset.asset_type, Asset.name, Asset.id)
        )
        asset_rows = list((await session.exec(asset_statement)).all())
        seen_by_episode: dict[int, set[int]] = {}
        for episode_id, asset in asset_rows:
            asset_id = int(asset.id)
            seen = seen_by_episode.setdefault(int(episode_id), set())
            if asset_id in seen:
                continue
            seen.add(asset_id)
            assets_by_episode_id.setdefault(int(episode_id), []).append(asset)

    return [
        (episode, plan_public_id, plan_title, assets_by_episode_id.get(int(episode.id), []))
        for episode, plan_public_id, plan_title in rows
    ]



async def export_episodes_zip(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    episode_public_ids: list[str],
) -> ExportedScriptZip:
    """把选中的分集导出为 ZIP，每个分集一个 Markdown 文件。"""
    if not episode_public_ids:
        raise ScriptServiceError("请选择要导出的剧本分集")

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    requested_ids = list(dict.fromkeys(episode_public_ids))
    statement = (
        select(ScriptEpisode, ScriptPlan)
        .join(ScriptPlan, ScriptEpisode.plan_id == ScriptPlan.id)
        .where(
            ScriptEpisode.public_id.in_(requested_ids),
            ScriptEpisode.disabled_at.is_(None),
            ScriptPlan.project_id == project.id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
        )
        .order_by(ScriptPlan.title, ScriptPlan.id, ScriptEpisode.episode_index)
    )
    rows = list((await session.exec(statement)).all())
    if not rows:
        raise ScriptEpisodeNotFoundError("未找到可导出的剧本分集")

    buffer = io.BytesIO()
    used_paths: set[str] = set()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for episode, plan in rows:
            relative_path = _unique_zip_path(
                used_paths,
                f"{_safe_zip_name(plan.title or '未命名剧本')}/"
                f"EP{episode.episode_index:02d}-{_safe_zip_name(episode.title or '未命名分集')}.md",
            )
            archive.writestr(relative_path, _format_episode_export(plan, episode).encode("utf-8"))

    timestamp = utc_now().strftime("%Y%m%d-%H%M")
    return ExportedScriptZip(
        filename=f"scripts-{timestamp}.zip",
        content=buffer.getvalue(),
        episode_count=len(rows),
    )


def _safe_zip_name(value: str) -> str:
    name = _UNSAFE_ZIP_NAME_RE.sub("_", value.strip()).strip(". ")
    return name or "未命名"


def _unique_zip_path(used_paths: set[str], relative_path: str) -> str:
    if relative_path not in used_paths:
        used_paths.add(relative_path)
        return relative_path

    stem, suffix = relative_path.rsplit(".", 1) if "." in relative_path else (relative_path, "")
    counter = 2
    while True:
        candidate = f"{stem}-{counter}.{suffix}" if suffix else f"{stem}-{counter}"
        if candidate not in used_paths:
            used_paths.add(candidate)
            return candidate
        counter += 1


def _format_episode_export(plan: ScriptPlan, episode: ScriptEpisode) -> str:
    return episode.body


async def update_plan(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    plan_public_id: str,
    *,
    title: str,
) -> ScriptPlan:
    """更新剧本计划元信息（当前支持剧名）。"""
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    plan = await _get_plan_or_raise(session, project, user_public_id, plan_public_id)
    plan.title = title.strip() or plan.title
    plan.updated_at = utc_now()
    session.add(plan)
    await session.flush()
    return plan


async def delete_plan(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    plan_public_id: str,
) -> None:
    """删除整部剧本计划及其全部分集。"""
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    plan = await _get_plan_or_raise(session, project, user_public_id, plan_public_id)
    for episode in await _load_plan_episodes(session, plan.id):
        await session.delete(episode)
    await session.delete(plan)
    await session.flush()


async def get_episode_or_raise(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_id: str,
) -> tuple[ScriptEpisode, ScriptPlan]:
    """按公开 ID 获取分集及其所属计划，校验归属当前项目与用户。"""
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    statement = (
        select(ScriptEpisode, ScriptPlan)
        .join(ScriptPlan, ScriptEpisode.plan_id == ScriptPlan.id)
        .where(
            ScriptEpisode.public_id == episode_public_id,
            ScriptEpisode.disabled_at.is_(None),
            ScriptPlan.project_id == project.id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
        )
    )
    row = (await session.exec(statement)).first()
    if row is None:
        raise ScriptEpisodeNotFoundError("分集不存在或无权访问")
    episode, plan = row
    return episode, plan


async def update_episode(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_id: str,
    *,
    title: str | None = None,
    summary: str | None = None,
    body: str | None = None,
) -> tuple[ScriptEpisode, ScriptPlan]:
    """编辑分集：仅更新提交的字段；正文变更时重解析场次并递增版本。"""
    episode, plan = await get_episode_or_raise(
        session, project_public_id, user_public_id, episode_public_id
    )
    if title is not None:
        episode.title = title
    if summary is not None:
        episode.summary = summary
    if body is not None and body != episode.body:
        episode.body = body
        episode.scenes = _scenes_to_json(_parse_scenes(body))
        episode.version += 1
    episode.updated_at = utc_now()
    plan.updated_at = utc_now()
    session.add(episode)
    session.add(plan)
    await session.flush()
    return episode, plan


async def set_episode_lock(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_id: str,
    *,
    locked: bool,
) -> tuple[ScriptEpisode, ScriptPlan]:
    """设置或解除分集的人工锁定。"""
    episode, plan = await get_episode_or_raise(
        session, project_public_id, user_public_id, episode_public_id
    )
    episode.is_locked = 1 if locked else 0
    episode.updated_at = utc_now()
    session.add(episode)
    await session.flush()
    return episode, plan


async def delete_episode(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_id: str,
) -> None:
    """删除单个分集。"""
    episode, plan = await get_episode_or_raise(
        session, project_public_id, user_public_id, episode_public_id
    )
    await session.delete(episode)
    plan.updated_at = utc_now()
    session.add(plan)
    await session.flush()
