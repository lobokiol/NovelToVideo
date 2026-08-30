from __future__ import annotations

"""为ProductionAgent的生产工作台提供的故事板服务"""

import json
import math
import re
from time import perf_counter
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.tasks.engine import default_async_task_engine
from app.models.asset import Asset, AssetEpisode
from app.models.script import ScriptEpisode
from app.models.storyboard import (
    STORYBOARD_STATUS_DRAFT,
    STORYBOARD_STATUS_LOCKED,
    StoryboardShot,
)
from app.schemas.tasks import TaskItemCreate, TaskJobCreate, TaskJobDetail
from app.services import project as project_service
from app.services import script as script_service
from app.services import style_prompt as style_prompt_service
from app.services.agent_gateway import ProviderModelGateway, ProviderModelGatewayError
from app.services.prompt_registry import PromptRegistry, PromptRegistryError
from app.utils.time_tools import utc_now


STORYBOARD_GENERATE_TASK_TYPE = "storyboard.generate"
STORYBOARD_QUEUE_NAME = "storyboard"
STORYBOARD_TABLE_PROMPT_NAME = settings.storyboard_table_prompt_name or "storyboard_table_generation"
SHOT_STATUS_VALUES = {STORYBOARD_STATUS_DRAFT, STORYBOARD_STATUS_LOCKED}

EPISODE_CONTEXT_MAX_CHARS = 9000
ASSET_CONTEXT_MAX_ITEMS = 120
FALLBACK_MAX_SHOTS = 80

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")
_SCRIPT_SCENE_HEADING_RE = re.compile(r"^(?:#{1,4}\s*)?(\d+\s*[-－]\s*\d+)\s+(.+?)\s*$")
_SCRIPT_DIALOGUE_RE = re.compile(r"^([^：:\n]{1,40})[：:](.+)$")
_FALLBACK_STORYBOARD_TABLE_PROMPT = (
    "你是 ProductionAgent 的分镜表执行 Agent。"
    "只返回 JSON 数组。每个条目必须包含 sequence、description、scene、"
    "associateAssetsNames、duration、shotSize、cameraMove、action、emotion、lighting、"
    "lines、sound 和 associateAssetsIds。"
)


class StoryboardServiceError(Exception):
    """分镜服务基础异常。

    retryable=False 表示确定性失败（参数/前置状态问题），任务系统不应重试。
    """

    def __init__(self, message: str, *, result: dict[str, Any] | None = None, retryable: bool = True) -> None:
        super().__init__(message)
        self.result = result or {}
        self.retryable = bool(retryable)


class StoryboardShotNotFoundError(StoryboardServiceError):
    """分镜镜头不存在或无权访问。"""


class _StoryboardTiming:
    def __init__(self) -> None:
        self.started_at = perf_counter()
        self.stages: list[dict[str, int | str]] = []

    def mark(self, name: str, started_at: float) -> None:
        ended_at = perf_counter()
        self.stages.append(
            {
                "name": name,
                "durationMs": _duration_ms(started_at, ended_at),
                "startedAtMs": _duration_ms(self.started_at, started_at),
                "endedAtMs": _duration_ms(self.started_at, ended_at),
            }
        )

    def payload(self) -> dict[str, Any]:
        return {
            "totalMs": _duration_ms(self.started_at, perf_counter()),
            "stages": [dict(stage) for stage in self.stages],
        }


def _duration_ms(started_at: float, ended_at: float) -> int:
    return max(0, int((ended_at - started_at) * 1000))


def build_storyboard_gateway() -> ProviderModelGateway:
    return ProviderModelGateway(timeout=settings.model_request_timeout_seconds)


def load_storyboard_table_prompt(registry: PromptRegistry | None = None) -> str:
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(STORYBOARD_TABLE_PROMPT_NAME)
    except PromptRegistryError:
        return _FALLBACK_STORYBOARD_TABLE_PROMPT


async def generate_storyboard(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_id: str,
    *,
    model_id: str,
    art_style: str = "",
    director_style: str = "",
    shot_public_ids: list[str] | None = None,
    gateway: Any | None = None,
) -> dict[str, Any]:
    """为单个剧本分集生成并持久化分镜镜头。

    指定 shot_public_ids 时进入按镜头重生成模式：仍以整集上下文调用模型保证
    行间连贯，但只持久化所选镜头对应的行，其余镜头保持原样。
    """

    model_id = model_id.strip()
    if not model_id:
        raise StoryboardServiceError("缺少分镜生成所用文本模型 ID")

    timing = _StoryboardTiming()
    stage_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    episode, _plan = await script_service.get_episode_or_raise(
        session,
        project_public_id,
        user_public_id,
        episode_public_id,
    )
    target_indexes: set[int] = set()
    for shot_public_id in _dedupe_public_ids(shot_public_ids):
        shot = await load_shot_or_raise(session, int(project.id), user_public_id, shot_public_id)
        if shot.episode_public_id != episode.public_id:
            raise StoryboardServiceError(f"镜头 {shot.shot_index} 不属于目标分集，无法按镜头重生成")
        target_indexes.add(int(shot.shot_index))
    timing.mark("project_and_episode_lookup", stage_started_at)

    stage_started_at = perf_counter()
    asset_context, asset_lookup = await build_asset_context(
        session,
        int(project.id),
        user_public_id,
        episode,
    )
    timing.mark("asset_context", stage_started_at)

    stage_started_at = perf_counter()
    resolved_art_style = art_style.strip() or str(project.art_style or "").strip()
    resolved_director_style = director_style.strip() or str(project.director_manual or "").strip()
    resolved_gateway = gateway or build_storyboard_gateway()
    art_style_prompt, director_style_prompt = await style_prompt_service.ensure_project_style_prompts(
        session,
        project,
        model_id=model_id,
        gateway=resolved_gateway,
    )
    timing.mark("style_prompt", stage_started_at)

    stage_started_at = perf_counter()
    messages = build_storyboard_messages(
        episode=episode,
        asset_context=asset_context,
        art_style=resolved_art_style,
        art_style_prompt=art_style_prompt,
        director_style=resolved_director_style,
        director_style_prompt=director_style_prompt,
    )
    prompt_trace = _model_prompt_trace(model_id=model_id, messages=messages)
    timing.mark("prompt_build", stage_started_at)

    raw = ""
    try:
        stage_started_at = perf_counter()
        raw = await _generate_full_text(resolved_gateway, model_id=model_id, messages=messages)
        timing.mark("storyboard_model", stage_started_at)
    except ProviderModelGatewayError as exc:
        timing.mark("storyboard_model", stage_started_at)
        prompt_trace["storyboard_timing"] = timing.payload()
        raise StoryboardServiceError(f"分镜生成失败：{exc}", result=prompt_trace) from exc

    prompt_trace["raw_output"] = raw
    prompt_trace["output_text"] = raw

    stage_started_at = perf_counter()
    parsed = parse_storyboard_table(raw, asset_lookup)
    parse_status = "model_json"
    if not parsed:
        parsed = fallback_storyboard_rows(episode, asset_lookup)
        parse_status = "fallback_script_parse"
    if not parsed:
        prompt_trace["storyboard_timing"] = timing.payload()
        raise StoryboardServiceError("未能生成有效分镜，请检查剧本内容或模型输出", result=prompt_trace)
    if target_indexes:
        parsed = [row for row in parsed if int(row.get("shot_index") or 0) in target_indexes]
        if not parsed:
            prompt_trace["storyboard_timing"] = timing.payload()
            raise StoryboardServiceError(
                "模型输出未覆盖所选镜头，请重试或改用整集生成", result=prompt_trace
            )
    timing.mark("parse_output", stage_started_at)

    stage_started_at = perf_counter()
    result = await persist_storyboard_rows(
        session,
        project_id=int(project.id),
        user_public_id=user_public_id,
        episode=episode,
        rows=parsed,
        art_style=resolved_art_style,
        director_style=resolved_director_style,
        model_id=model_id,
        partial=bool(target_indexes),
    )
    timing.mark("write_storyboard", stage_started_at)

    return {
        **result,
        **prompt_trace,
        "parse_status": parse_status,
        "storyboard_timing": timing.payload(),
        "episode_public_id": episode.public_id,
        "episode_index": episode.episode_index,
        "art_style": resolved_art_style,
        "director_style": resolved_director_style,
    }


async def _generate_full_text(gateway: Any, *, model_id: str, messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    async for chunk in gateway.generate_stream(model_id=model_id, messages=messages):
        text = str(chunk or "")
        if text:
            parts.append(text)
    return "".join(parts).strip()


def build_storyboard_messages(
    *,
    episode: ScriptEpisode,
    asset_context: str,
    art_style: str,
    art_style_prompt: str,
    director_style: str,
    director_style_prompt: str,
) -> list[dict[str, str]]:
    system = load_storyboard_table_prompt()
    episode_body = (episode.body or "").strip()
    if len(episode_body) > EPISODE_CONTEXT_MAX_CHARS:
        episode_body = episode_body[:EPISODE_CONTEXT_MAX_CHARS] + "\n...（剧本已截断）"
    user = "\n\n".join(
        [
            f"## 分集\nEP{episode.episode_index:02d} {episode.title or ''}".strip(),
            f"## 分集剧本正文\n{episode_body or '（无正文）'}",
            f"## 项目资产清单\n{asset_context or '（暂无资产）'}",
            f"## 美术风格提示词\nstyleKey: {art_style or '未指定'}\n{art_style_prompt or '（未提炼美术风格提示词）'}",
            f"## 导演叙事提示词\ndirectorKey: {director_style or '未指定'}\n{director_style_prompt or '（未提炼导演叙事提示词）'}",
            "请只输出合法 JSON 数组。",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def build_asset_context(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    episode: ScriptEpisode,
) -> tuple[str, dict[str, dict[str, str]]]:
    statement = (
        select(Asset)
        .where(
            Asset.project_id == project_id,
            Asset.user_public_id == user_public_id,
            Asset.disabled_at.is_(None),
            Asset.main_asset.is_(True),
        )
        .order_by(Asset.asset_type, Asset.name, Asset.id)
        .limit(ASSET_CONTEXT_MAX_ITEMS)
    )
    assets = list((await session.exec(statement)).all())
    if episode.id is not None:
        episode_statement = (
            select(Asset)
            .join(AssetEpisode, AssetEpisode.asset_id == Asset.id)
            .where(
                AssetEpisode.project_id == project_id,
                AssetEpisode.user_public_id == user_public_id,
                AssetEpisode.episode_id == int(episode.id),
                Asset.disabled_at.is_(None),
                Asset.main_asset.is_(True),
            )
            .order_by(Asset.asset_type, Asset.name, Asset.id)
        )
        episode_assets = list((await session.exec(episode_statement)).all())
        assets = _merge_assets(episode_assets + assets)[:ASSET_CONTEXT_MAX_ITEMS]

    lines: list[str] = []
    lookup: dict[str, dict[str, str]] = {}
    for index, asset in enumerate(assets, start=1):
        summary = str(asset.summary or "").strip().replace("\n", " ")
        if len(summary) > 180:
            summary = summary[:180] + "..."
        record = {
            "index": str(index),
            "public_id": asset.public_id,
            "name": asset.name or "",
            "asset_type": asset.asset_type or "",
        }
        if asset.id is not None:
            lookup[str(asset.id)] = record
        lookup[str(index)] = record
        if asset.public_id:
            lookup[asset.public_id] = record
        if asset.name:
            lookup[asset.name] = record
        lines.append(
            f"- id:{index} publicId:{asset.public_id} type:{asset.asset_type} "
            f"name:{asset.name} variant:{asset.variant_label or '-'} summary:{summary or '-'}"
        )
    return "\n".join(lines), lookup


def _merge_assets(assets: list[Asset]) -> list[Asset]:
    seen: set[str] = set()
    result: list[Asset] = []
    for asset in assets:
        key = asset.public_id
        if key in seen:
            continue
        seen.add(key)
        result.append(asset)
    return result


def parse_storyboard_table(raw: str, asset_lookup: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return []
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fenced:
        text = fenced.group(1).strip()
    else:
        matched = _JSON_ARRAY_RE.search(text)
        if matched:
            text = matched.group(0)

    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    if isinstance(data, dict):
        for key in ("shots", "items", "storyboard"):
            value = data.get(key)
            if isinstance(value, list):
                data = value
                break
    if not isinstance(data, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        row = normalize_storyboard_row(item, len(normalized) + 1, asset_lookup or {})
        if row:
            normalized.append(row)
    return normalized


def normalize_storyboard_row(
    item: dict[str, Any],
    fallback_sequence: int,
    asset_lookup: dict[str, dict[str, str]],
) -> dict[str, Any] | None:
    action = _first_text(item.get("action"), item.get("description"), item.get("画面动作"))
    description = _first_text(item.get("description"), item.get("画面描述"), action)
    if not action and not description:
        return None
    sequence = _positive_int(item.get("sequence") or item.get("shotIndex") or item.get("镜头序号"), fallback_sequence)
    lines = _normalize_lines(item.get("lines"))
    dialogue = "\n".join(
        f"{line['character']}：{line['dialogue']}" if line["character"] else line["dialogue"]
        for line in lines
        if line.get("dialogue")
    )
    asset_names = _text_list(item.get("associateAssetsNames") or item.get("assetNames") or item.get("assets"))
    asset_public_ids = _asset_ids_from_row(
        item.get("associateAssetsIds") or item.get("assetPublicIds") or item.get("assetIds"),
        asset_names,
        asset_lookup,
    )
    return {
        "shot_index": sequence,
        "scene_number": _first_text(item.get("scene"), item.get("sceneNumber"), item.get("场号"))[:40],
        "shot_size": _first_text(item.get("shotSize"), item.get("shot_size"), item.get("景别"))[:40],
        "camera": _first_text(item.get("cameraMove"), item.get("camera"), item.get("运镜"))[:120],
        "action": action or description,
        "dialogue": dialogue,
        "duration_seconds": _positive_int(item.get("duration") or item.get("durationSeconds"), 4),
        "asset_public_ids": ",".join(asset_public_ids)[:400],
        "asset_names": ",".join(asset_names)[:400],
        "prompt": build_shot_prompt(description, item, asset_names),
        "negative_prompt": "",
    }


def _asset_ids_from_row(
    raw_ids: Any,
    asset_names: list[str],
    asset_lookup: dict[str, dict[str, str]],
) -> list[str]:
    result: list[str] = []
    for value in _text_list(raw_ids):
        record = asset_lookup.get(value)
        public_id = record["public_id"] if record else value
        if public_id and public_id not in result:
            result.append(public_id)
    for name in asset_names:
        record = asset_lookup.get(name)
        if record and record["public_id"] not in result:
            result.append(record["public_id"])
    return result


def build_shot_prompt(description: str, item: dict[str, Any], asset_names: list[str]) -> str:
    """拼接镜头生图提示词；资产以 @资产名 内联引用，正文已 @ 过的不再重复补引。"""
    parts = [
        description,
        _first_text(item.get("action")),
        _first_text(item.get("shotSize")),
        _first_text(item.get("cameraMove")),
        _first_text(item.get("lighting")),
    ]
    prompt = "；".join(part for part in parts if part)
    missing = [name for name in asset_names if name and f"@{name}" not in prompt]
    if missing:
        supplement = f"画面可见 {'、'.join(f'@{name}' for name in missing)}"
        prompt = f"{prompt}；{supplement}" if prompt else supplement
    return prompt


def _normalize_lines(value: Any) -> list[dict[str, str]]:
    if isinstance(value, str):
        return [{"character": "", "dialogue": value.strip()}] if value.strip() else []
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append({"character": "", "dialogue": text})
            continue
        if not isinstance(item, dict):
            continue
        dialogue = _first_text(item.get("dialogue"), item.get("line"), item.get("text"))
        if not dialogue:
            continue
        result.append({"character": _first_text(item.get("character"), item.get("name")), "dialogue": dialogue})
    return result


def fallback_storyboard_rows(
    episode: ScriptEpisode,
    asset_lookup: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_scene = ""
    pending_scene = ""
    pending_action = ""
    pending_lines: list[str] = []

    def flush_pending() -> None:
        nonlocal pending_action, pending_scene, pending_lines
        if not pending_action:
            return
        rows.append(_fallback_row(len(rows) + 1, pending_scene, pending_action, pending_lines, asset_lookup or {}))
        pending_action = ""
        pending_scene = ""
        pending_lines = []

    for raw_line in (episode.body or "").splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            continue
        heading = _SCRIPT_SCENE_HEADING_RE.match(line)
        if heading:
            flush_pending()
            current_scene = heading.group(1).replace(" ", "")
            continue
        if line.startswith("△"):
            flush_pending()
            action = line.lstrip("△").strip()
            pending_scene = current_scene
            pending_action = action
            pending_lines = []
            continue
        dialogue = _SCRIPT_DIALOGUE_RE.match(line)
        if dialogue and pending_action:
            pending_lines.append(f"{dialogue.group(1).strip()}：{dialogue.group(2).strip()}")
    flush_pending()
    if not rows and (episode.summary or episode.body):
        text = (episode.summary or episode.body or "").strip().replace("\n", " ")
        for index, segment in enumerate(_split_fallback_segments(text), start=1):
            rows.append(_fallback_row(index, current_scene or f"EP{episode.episode_index:02d}", segment, [], asset_lookup or {}))
    return rows[:FALLBACK_MAX_SHOTS]


def _fallback_row(
    sequence: int,
    scene: str,
    action: str,
    dialogue_lines: list[str],
    asset_lookup: dict[str, dict[str, str]],
) -> dict[str, Any]:
    names = [name for name in asset_lookup if name and name in action and not re.match(r"^[0-9a-f-]{8,}$", name)]
    public_ids = [asset_lookup[name]["public_id"] for name in names if name in asset_lookup]
    duration = max(4, min(12, math.ceil(sum(len(line) for line in dialogue_lines) / 3) + 1))
    return {
        "shot_index": sequence,
        "scene_number": scene[:40],
        "shot_size": "中景" if sequence > 1 else "全景",
        "camera": "静止" if dialogue_lines else "从环境全景缓推至主体动作中景",
        "action": action[:2000],
        "dialogue": "\n".join(dialogue_lines),
        "duration_seconds": duration,
        "asset_public_ids": ",".join(dict.fromkeys(public_ids))[:400],
        "asset_names": ",".join(dict.fromkeys(names))[:400],
        "prompt": action[:2000],
        "negative_prompt": "",
    }


def _split_fallback_segments(text: str) -> list[str]:
    chunks = re.split(r"[。！？!?]\s*", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()][:FALLBACK_MAX_SHOTS]


async def persist_storyboard_rows(
    session: AsyncSession,
    *,
    project_id: int,
    user_public_id: str,
    episode: ScriptEpisode,
    rows: list[dict[str, Any]],
    art_style: str,
    director_style: str,
    model_id: str,
    partial: bool = False,
) -> dict[str, Any]:
    """按镜头序号 upsert 分镜行；partial 模式只更新给到的行，不禁用缺席镜头。"""
    existing_statement = select(StoryboardShot).where(
        StoryboardShot.project_id == project_id,
        StoryboardShot.user_public_id == user_public_id,
        StoryboardShot.episode_public_id == episode.public_id,
    )
    existing = list((await session.exec(existing_statement)).all())
    by_index = {int(shot.shot_index): shot for shot in existing}
    incoming_indexes: set[int] = set()
    created = 0
    updated = 0
    result_shots: list[StoryboardShot] = []
    now = utc_now()

    for row in rows:
        shot_index = max(1, int(row.get("shot_index") or len(incoming_indexes) + 1))
        incoming_indexes.add(shot_index)
        shot = by_index.get(shot_index)
        if shot is not None and shot.status == STORYBOARD_STATUS_LOCKED:
            result_shots.append(shot)
            continue
        values = {
            "scene_number": str(row.get("scene_number") or "")[:40],
            "shot_size": str(row.get("shot_size") or "")[:40],
            "camera": str(row.get("camera") or "")[:120],
            "action": str(row.get("action") or ""),
            "dialogue": str(row.get("dialogue") or ""),
            "duration_seconds": max(0, int(row.get("duration_seconds") or 0)),
            "asset_public_ids": str(row.get("asset_public_ids") or "")[:400],
            "asset_names": str(row.get("asset_names") or "")[:400],
            "art_style_key": art_style[:120],
            "director_style_key": director_style[:120],
            "model_id": model_id[:120],
            "prompt": str(row.get("prompt") or ""),
            "negative_prompt": str(row.get("negative_prompt") or ""),
        }
        if shot is None:
            shot = StoryboardShot(
                project_id=project_id,
                user_public_id=user_public_id,
                episode_public_id=episode.public_id,
                episode_index=episode.episode_index,
                shot_index=shot_index,
                sort_order=shot_index,
                **values,
            )
            created += 1
        else:
            for key, value in values.items():
                setattr(shot, key, value)
            shot.episode_index = episode.episode_index
            shot.sort_order = shot_index
            shot.disabled_at = None
            shot.updated_at = now
            updated += 1
        session.add(shot)
        result_shots.append(shot)

    if not partial:
        for shot in existing:
            if shot.shot_index in incoming_indexes or shot.status == STORYBOARD_STATUS_LOCKED:
                continue
            shot.disabled_at = now
            shot.updated_at = now
            session.add(shot)

    await session.flush()
    result_shots.sort(key=lambda item: (item.episode_index, item.shot_index, item.id or 0))
    return {"created": created, "updated": updated, "shots": result_shots}


async def submit_storyboard_generation_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    episode_public_ids: list[str] | None = None,
    shot_public_ids: list[str] | None = None,
    art_style: str = "",
    director_style: str = "",
    engine: Any | None = None,
) -> TaskJobDetail:
    model_id = model_id.strip()
    if not model_id:
        raise StoryboardServiceError("缺少分镜生成所用文本模型 ID")
    await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    items = await build_storyboard_task_items(
        session,
        project_public_id,
        user_public_id,
        model_id=model_id,
        episode_public_ids=episode_public_ids,
        shot_public_ids=shot_public_ids,
        art_style=art_style,
        director_style=director_style,
    )
    if not items:
        raise StoryboardServiceError("没有可用于分镜生成的剧本分集")

    selected_shot_count = sum(len(item.payload.get("shot_public_ids") or []) for item in items)
    if selected_shot_count:
        job_name = f"分镜脚本重生成：{selected_shot_count} 镜"
    else:
        job_name = "分镜表生成" if len(items) == 1 else f"分镜表批量生成：{len(items)} 集"
    resolved_engine = engine or default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=STORYBOARD_GENERATE_TASK_TYPE,
            queue_name=STORYBOARD_QUEUE_NAME,
            name=job_name,
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": model_id,
                "episode_public_ids": [item.payload["episode_public_id"] for item in items],
                "shot_count": selected_shot_count,
                "art_style": art_style,
                "director_style": director_style,
            },
            items=items,
        ),
    )


async def build_storyboard_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    episode_public_ids: list[str] | None = None,
    shot_public_ids: list[str] | None = None,
    art_style: str = "",
    director_style: str = "",
) -> list[TaskItemCreate]:
    # 按镜头重生成：把所选镜头按分集分组，每个分集一个子项、只重写选中的行。
    shots_by_episode: dict[str, list[str]] = {}
    resolved_shot_ids = _dedupe_public_ids(shot_public_ids)
    if resolved_shot_ids:
        selected_episode_ids = set(_dedupe_public_ids(episode_public_ids))
        all_shots = await list_storyboard_shots(session, project_public_id, user_public_id)
        by_public_id = {shot.public_id: shot for shot in all_shots}
        for shot_public_id in resolved_shot_ids:
            shot = by_public_id.get(shot_public_id)
            if shot is None:
                raise StoryboardShotNotFoundError(f"分镜镜头不存在：{shot_public_id}")
            if selected_episode_ids and shot.episode_public_id not in selected_episode_ids:
                continue
            shots_by_episode.setdefault(shot.episode_public_id, []).append(shot.public_id)
        if not shots_by_episode:
            raise StoryboardServiceError("所选镜头不在目标分集内")
        episode_ids = list(shots_by_episode.keys())
    else:
        episode_ids = _dedupe_public_ids(episode_public_ids)
        if not episode_ids:
            plans = await script_service.list_plans(session, project_public_id, user_public_id)
            if not plans:
                return []
            _, episodes = await script_service.get_plan_detail(session, project_public_id, user_public_id, plans[0].public_id)
            episode_ids = [episode.public_id for episode in episodes if episode.public_id]

    items: list[TaskItemCreate] = []
    for episode_public_id in episode_ids:
        episode, _plan = await script_service.get_episode_or_raise(
            session,
            project_public_id,
            user_public_id,
            episode_public_id,
        )
        items.append(
            TaskItemCreate(
                item_type=STORYBOARD_GENERATE_TASK_TYPE,
                item_key=f"storyboard:{episode_public_id}",
                payload={
                    "project_public_id": project_public_id,
                    "current_user_public_id": user_public_id,
                    "model_id": model_id,
                    "episode_public_id": episode_public_id,
                    "episode_index": episode.episode_index,
                    "episode_title": episode.title,
                    "shot_public_ids": shots_by_episode.get(episode_public_id, []),
                    "art_style": art_style,
                    "director_style": director_style,
                },
            )
        )
    return items


async def list_storyboard_shots(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    episode_public_id: str = "",
) -> list[StoryboardShot]:
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    statement = select(StoryboardShot).where(
        StoryboardShot.project_id == project.id,
        StoryboardShot.user_public_id == user_public_id,
        StoryboardShot.disabled_at.is_(None),
    )
    if episode_public_id.strip():
        statement = statement.where(StoryboardShot.episode_public_id == episode_public_id.strip())
    statement = statement.order_by(StoryboardShot.episode_index, StoryboardShot.shot_index, StoryboardShot.id)
    return list((await session.exec(statement)).all())


async def update_storyboard_shot(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    shot_public_id: str,
    *,
    fields: dict[str, Any],
) -> StoryboardShot:
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    shot = await load_shot_or_raise(session, int(project.id), user_public_id, shot_public_id)
    if shot.status == STORYBOARD_STATUS_LOCKED:
        raise StoryboardServiceError("分镜已锁定，请先解锁再编辑")
    editable = {
        "scene_number",
        "shot_size",
        "camera",
        "action",
        "dialogue",
        "duration_seconds",
        "asset_public_ids",
        "asset_names",
        "art_style_key",
        "director_style_key",
        "model_id",
        "prompt",
        "negative_prompt",
        "reference_media_public_id",
        "last_frame_media_public_id",
        "seed",
    }
    for key, value in fields.items():
        if key not in editable or value is None:
            continue
        setattr(shot, key, value)
    shot.updated_at = utc_now()
    session.add(shot)
    await session.flush()
    return shot


async def set_storyboard_shot_lock(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    shot_public_id: str,
    *,
    locked: bool,
) -> StoryboardShot:
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    shot = await load_shot_or_raise(session, int(project.id), user_public_id, shot_public_id)
    shot.status = STORYBOARD_STATUS_LOCKED if locked else STORYBOARD_STATUS_DRAFT
    shot.updated_at = utc_now()
    session.add(shot)
    await session.flush()
    return shot


async def delete_storyboard_shot(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    shot_public_id: str,
) -> None:
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    shot = await load_shot_or_raise(session, int(project.id), user_public_id, shot_public_id)
    if shot.status == STORYBOARD_STATUS_LOCKED:
        raise StoryboardServiceError("分镜已锁定，请先解锁再删除")
    shot.disabled_at = utc_now()
    shot.updated_at = utc_now()
    session.add(shot)
    await session.flush()


async def load_shot_or_raise(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    shot_public_id: str,
) -> StoryboardShot:
    statement = select(StoryboardShot).where(
        StoryboardShot.project_id == project_id,
        StoryboardShot.user_public_id == user_public_id,
        StoryboardShot.public_id == shot_public_id,
        StoryboardShot.disabled_at.is_(None),
    )
    shot = (await session.exec(statement)).first()
    if shot is None:
        raise StoryboardShotNotFoundError("分镜镜头不存在或无权访问")
    return shot


def _model_prompt_trace(*, model_id: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    return {"model_id": model_id, "messages": messages, "composed_prompt": _format_model_messages(messages)}


def _format_model_messages(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = str(message.get("role") or f"message_{index}").strip()
        content = str(message.get("content") or "").strip()
        if content:
            parts.append(f"{role}：\n{content}")
    return "\n\n".join(parts)


def _dedupe_public_ids(values: list[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,，、\n]+", value)
    elif isinstance(value, list):
        parts = value
    else:
        parts = [value]
    result: list[str] = []
    for item in parts:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            try:
                text = json.dumps(value, ensure_ascii=False)
            except TypeError:
                text = str(value)
        else:
            text = str(value)
        text = text.strip()
        if text:
            return text
    return ""


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default