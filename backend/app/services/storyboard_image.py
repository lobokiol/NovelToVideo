from __future__ import annotations

"""宫格分镜图生成服务。

为一组分镜镜头生成一张 N×N 宫格分镜图：每个画格对应一个不同镜头，按分镜
顺序组成 storyboard contact sheet，画格位置与镜头顺序一一对应（画面中不
标注编号）。流程：确定性模板拼接多镜头宫格提示词 → 注入组内引用资产的
封面参考图与资产详情（角色/场景/风格一致性）→ 调图像网关生成宫格大图 →
Pillow 按画格裁切 → 大图入媒体中枢，裁切格分别回写到对应
shot.reference_media_public_id。

grid_size=1 时退化为单帧模式：直接生成镜头首帧单图（提示词换用单帧模板，
不含宫格布局话术），媒体链路不变（大图与首帧图仍双入库）。

宫格提示词为确定性模板拼接（不经文本模型），每格画面说明沿用分镜表生成
阶段写入的 shot.prompt；提示词中的 @资产名 引用会展开为资产详情说明；
美术/导演风格手册截断注入，由图像模型按合成流程指令自行提取关键约束。
"""

import asyncio
import json
import re
from dataclasses import dataclass
from io import BytesIO
from time import perf_counter
from typing import Any

from PIL import Image, ImageOps
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.tasks.engine import default_async_task_engine
from app.models.asset import Asset
from app.models.media import (
    MEDIA_ROLE_FINAL,
    MEDIA_ROLE_GRID,
    MEDIA_SCOPE_EPISODE,
    MEDIA_SCOPE_PROJECT,
    MEDIA_SCOPE_SHOT,
    MEDIA_SOURCE_GENERATION,
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_TYPE_IMAGE,
    MediaAsset,
)
from app.models.storyboard import STORYBOARD_STATUS_LOCKED, StoryboardShot
from app.schemas.tasks import TaskItemCreate, TaskJobCreate, TaskJobDetail
from app.services import media as media_service
from app.services import project as project_service
from app.services import storyboard as storyboard_service
from app.services import style_prompt as style_prompt_service
from app.services.agent_gateway import ProviderModelGatewayError
from app.services.media_storage import get_media_storage
from app.services.prompt_registry import PromptRegistry, PromptRegistryError
from app.services.video_generation_spec import (
    VideoGenerationSpecError,
    seedance_dimensions,
    storyboard_image_size_to_resolution,
)
from app.utils.time_tools import utc_now


STORYBOARD_GRID_IMAGE_TASK_TYPE = "storyboard.grid_image"

# 宫格规格：格数 → (行, 列)；1 宫格退化为直接绘制镜头首帧单图。
GRID_LAYOUTS: dict[int, tuple[int, int]] = {1: (1, 1), 4: (2, 2), 9: (3, 3), 16: (4, 4), 25: (5, 5)}

# 分辨率档位 → 允许的宫格规格：格数越多要求分辨率越高，保证首帧格裁切后仍可作视频首帧。
GRID_SIZES_BY_IMAGE_SIZE: dict[str, tuple[int, ...]] = {
    "1K": (1, 4),
    "2K": (1, 4, 9, 16),
    "4K": (1, 4, 9, 16, 25),
}
DEFAULT_GRID_IMAGE_SIZE = "4K"

_GRID_REFERENCE_MAX_COUNT = 8
_GRID_REFERENCE_PER_ASSET = 2
_SHOT_PROMPT_MAX_CHARS = 2000
_ASSET_SUMMARY_MAX_CHARS = 500

# 提示词中的 @资产名 引用；名称段落到空白或常见中英文标点为止。
_MENTION_RE = re.compile(r"@([^\s@，。；、！？…,;.!?()（）【】\[\]{}<>：:\"'`]{1,60})")

_ASSET_TYPE_LABELS = {"role": "角色", "faction": "势力", "prop": "道具", "scene": "场景"}

# data/skills 提示词文件缺失时的内置回退模板，与技能文件保持同等约束。
_FALLBACK_GRID_IMAGE_PROMPT = (
    "你正在绘制一张 N×N 宫格电影分镜图（Storyboard Contact Sheet）："
    "每个画格对应一个不同分镜镜头，按故事顺序从左到右、从上到下排布，"
    "共同呈现一段连续剧情。\n\n"
    "生成一张 {rows} 行 × {cols} 列的宫格分镜图，共 {grid_size} 个画格。"
    "每个画格都是独立取景、独立构图的电影画面，不是同一张大场景被网格切开。"
    "画格之间用极细纯白分隔线等分整图。画格位置与给定镜头顺序一一对应，"
    "整张图不得出现任何编号、文字、水印、签名、标题或额外装饰。\n\n"
    "绘制前先做故事板规划：把给定的分镜镜头按顺序逐一放入对应画格，确保每个画格有"
    "不同景别、机位、动作或情绪任务；相邻画格在剧情上连续，但画面不能雷同。\n\n"
    "一致性铁律：所有画格共享同一人物设定、服装细节、场景规则、光线方向、"
    "整体调色和美术风格。仅允许根据各分镜要求改变动作、表情、机位、构图、"
    "景别和景深；禁止换脸、换服装、换场景规则或加入分镜外的新角色。"
    "附带参考图时，参考图中的角色与场景形象是强约束。\n\n"
    "镜头多样性铁律：整张图必须体现环境交代远景、人物情绪近景/特写、"
    "细节或道具特写、低角度或高角度表现力镜头等变化；远景用深景深，"
    "中景用中景深，特写用浅景深。\n\n"
    "台词与情绪只用于指导表情、视线和肢体语言；不要在画面中绘制字幕、对白、"
    "气泡或任何可读文字。\n\n"
    "以下是本次任务的画幅比例、美术风格、导演风格、分镜画面要求与引用资产详情，"
    "请综合全部信息完成整张宫格图。"
)

# grid_size=1（单帧模式）时技能文件缺失的内置回退模板，与技能文件保持同等约束。
_FALLBACK_FRAME_IMAGE_PROMPT = (
    "你正在为一个电影镜头绘制首帧画面：一幅构图完整、可直接用作该镜头视频首帧的"
    "单幅电影画面，定格镜头起幅瞬间的表演与取景。\n\n"
    "画面为镜头起幅：构图完整稳定、主体清晰，并在人物视线与动作展开方向预留空间，"
    "作为视频首帧能自然启动整个镜头的后续表演与运镜。"
    "整张图不得出现编号文字、水印、边框装饰、标题或宫格分隔线。\n\n"
    "一致性铁律：角色的五官、发型、年龄感、身高体型、服饰与随身武器道具必须与参考图"
    "及资产设定完全一致，参考图是对应形象的唯一权威来源，禁止再创作，"
    "禁止添加设定之外的角色、服饰部件或武器道具；场景空间结构与光源方向符合镜头信息描述。\n\n"
    "台词与情绪只用于指导起幅瞬间的表情与肢体语言，不要在画面中绘制文字或气泡。\n\n"
    "以下是本次任务的画幅比例、美术风格、导演风格、镜头信息与引用资产详情，"
    "请综合全部信息完成这幅首帧画面。"
)


class StoryboardImageServiceError(storyboard_service.StoryboardServiceError):
    """宫格分镜图服务错误，沿用分镜服务错误族便于路由统一映射。"""


@dataclass(frozen=True)
class StoryboardReferenceImage:
    image: dict[str, Any]
    asset_public_id: str
    asset_name: str
    media_public_id: str

    def audit_payload(self) -> dict[str, str]:
        return {
            "asset_public_id": self.asset_public_id,
            "asset_name": self.asset_name,
            "media_public_id": self.media_public_id,
        }


def resolve_grid_spec(grid_size: int, image_size: str) -> tuple[str, tuple[int, int]]:
    """校验分辨率与宫格规格的组合，返回归一化分辨率与 (行, 列)。"""

    resolved_size = (image_size or "").strip().upper() or DEFAULT_GRID_IMAGE_SIZE
    if resolved_size not in GRID_SIZES_BY_IMAGE_SIZE:
        raise StoryboardImageServiceError("分镜图分辨率仅支持 1K/2K/4K")
    if grid_size not in GRID_LAYOUTS:
        raise StoryboardImageServiceError("宫格规格仅支持 1/4/9/16/25 格")
    if grid_size not in GRID_SIZES_BY_IMAGE_SIZE[resolved_size]:
        allowed = "/".join(str(item) for item in GRID_SIZES_BY_IMAGE_SIZE[resolved_size])
        raise StoryboardImageServiceError(f"{resolved_size} 分辨率仅支持 {allowed} 宫格")
    return resolved_size, GRID_LAYOUTS[grid_size]


def load_grid_image_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取宫格分镜图生成提示词模板，缺失时回退内置模板。"""

    prompt_name = settings.storyboard_grid_image_prompt_name.strip()
    if not prompt_name:
        return _FALLBACK_GRID_IMAGE_PROMPT
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(prompt_name)
    except PromptRegistryError:
        return _FALLBACK_GRID_IMAGE_PROMPT


def load_frame_image_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取单帧分镜图生成提示词模板，缺失时回退内置模板。"""

    prompt_name = settings.storyboard_frame_image_prompt_name.strip()
    if not prompt_name:
        return _FALLBACK_FRAME_IMAGE_PROMPT
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(prompt_name)
    except PromptRegistryError:
        return _FALLBACK_FRAME_IMAGE_PROMPT


def extract_prompt_mentions(prompt: str) -> list[str]:
    """提取提示词中 @资产名 引用的名称列表（保序去重）。"""

    names: list[str] = []
    for match in _MENTION_RE.finditer(prompt):
        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)
    return names


def format_asset_details(assets: list[Asset], prompt: str) -> list[str]:
    """把镜头引用资产整理为提示词可读的详情行，@引用的资产置前并标注。"""

    mentioned = set(extract_prompt_mentions(prompt))
    ordered = sorted(assets, key=lambda item: (item.name or "") not in mentioned)
    lines: list[str] = []
    for asset in ordered:
        name = (asset.name or "").strip()
        if not name:
            continue
        summary = (asset.summary or asset.description or "").strip().replace("\n", " ")
        if len(summary) > _ASSET_SUMMARY_MAX_CHARS:
            summary = summary[:_ASSET_SUMMARY_MAX_CHARS] + "…"
        bits = [f"{_ASSET_TYPE_LABELS.get(asset.asset_type or '', '资产')}「{name}」"]
        if (asset.keyword or "").strip():
            bits.append(f"关键词：{asset.keyword.strip()}")
        if (asset.colors or "").strip():
            bits.append(f"主配色：{asset.colors.strip()}")
        if summary:
            bits.append(f"设定：{summary}")
        prefix = "【提示词@引用】" if name in mentioned else ""
        lines.append(f"- {prefix}{'；'.join(bits)}")
    return lines


def group_storyboard_shots_for_grid(
    shots: list[StoryboardShot],
    *,
    grid_size: int,
) -> list[list[StoryboardShot]]:
    """按分集与镜头顺序把分镜切成宫格图任务组。"""

    ordered = sorted(shots, key=lambda item: (item.episode_index, item.episode_public_id, item.shot_index, item.id or 0))
    groups: list[list[StoryboardShot]] = []
    current_episode = ""
    current: list[StoryboardShot] = []
    for shot in ordered:
        episode_key = shot.episode_public_id or f"episode-index:{shot.episode_index}"
        if current and (episode_key != current_episode or len(current) >= grid_size):
            groups.append(current)
            current = []
        current_episode = episode_key
        current.append(shot)
    if current:
        groups.append(current)
    return groups


def _common_episode_public_id(shots: list[StoryboardShot]) -> str:
    ids = {shot.episode_public_id for shot in shots if shot.episode_public_id}
    return next(iter(ids)) if len(ids) == 1 else ""


def _trim_text(value: str, max_chars: int) -> str:
    text = (value or "").strip().replace("\n", " / ")
    return text if len(text) <= max_chars else text[:max_chars] + "…"


def _format_grid_shot_line(shot: StoryboardShot, slot_index: int) -> str:
    prompt = _trim_text((shot.prompt or "").strip() or (shot.action or "").strip(), _SHOT_PROMPT_MAX_CHARS)
    dialogue = _trim_text(shot.dialogue or "", 160)
    parts = [
        f"第 {slot_index} 格（镜头 #{shot.shot_index}）",
        f"场号：{shot.scene_number or '未指定'}",
        f"景别：{shot.shot_size or '未指定'}",
        f"机位与运镜：{shot.camera or '未指定'}",
        f"时长：约 {shot.duration_seconds or 0} 秒",
        f"生图提示词：{prompt or '（无描述）'}",
    ]
    if dialogue:
        parts.append(f"台词情绪参考：{dialogue}")
    return "；".join(parts)


def build_grid_image_prompt(
    *,
    shots: list[StoryboardShot],
    grid_size: int,
    rows: int,
    cols: int,
    video_ratio: str,
    art_style_key: str,
    art_style_prompt: str,
    director_style_key: str,
    director_style_prompt: str,
    reference_asset_names: list[str],
    asset_details: list[str],
) -> str:
    """确定性拼接一组镜头的宫格分镜图生成提示词；grid_size=1 时使用单帧模板。

    组成：分镜脚本逐镜画面要求 + 项目固定的美术风格提示词 + 项目固定的导演
    叙事提示词 + 镜头用语（技能文件内景别与视角标准）+ 参考图说明 + 资产详情。
    """

    if grid_size == 1:
        header = load_frame_image_prompt()
    else:
        header = (
            load_grid_image_prompt()
            .replace("{rows}", str(rows))
            .replace("{cols}", str(cols))
            .replace("{grid_size}", str(grid_size))
        )

    ratio = video_ratio or "9:16"
    ratio_section = (
        f"## 画幅比例\n画面宽高比为 {ratio}。"
        if grid_size == 1
        else f"## 画幅比例\n整图与每个画格的宽高比均为 {ratio}。"
    )
    sections = [header, ratio_section]
    sections.append(
        "## 分镜图提示词合成流程\n"
        f"先根据下方各镜头的生图提示词，为本次 {rows}x{cols} 宫格组织完整画面；"
        "每个画格只对应自己镜头的生图提示词，不得改写镜头顺序、不得新增剧情。\n"
        "再结合随 prompt 发送的资产参考图附件，以及下方引用资产详情中的外观描述，锁定角色、场景、道具的外观一致性。\n"
        "美术风格提示词控制全图的质感、色彩、光影、材质与整体视觉统一；"
        "导演叙事提示词控制每格的运镜、镜头调度与叙事节奏。\n"
        "最后按上述要求绘制完整分镜图。"
    )
    if grid_size > 1:
        sections.append(
            "## 宫格语义\n"
            f"每个画格对应一个不同分镜镜头。本组共 {len(shots)} 个有效镜头，"
            f"按第 1 格到第 {len(shots)} 格的位置顺序从左到右、从上到下绘制，"
            "画格位置与镜头顺序一一对应。这些画格共同组成一张 "
            f"{rows}x{cols} Storyboard Contact Sheet 式分镜图，不是单镜头关键帧拆解。"
        )
        if len(shots) < grid_size:
            sections.append(
                "## 未使用画格\n"
                f"本组少于 {grid_size} 个镜头时，只绘制前 {len(shots)} 个画格；"
                "剩余画格保持干净空白或极简占位，不得补写新剧情、新人物或新场景。"
            )
    if reference_asset_names:
        sections.append(
            "## 参考图说明\n随本提示词附带的参考图是以下资产的定妆图，"
            "是对应角色/场景形象的唯一权威来源，必须 100% 保留其五官、发型、年龄感、"
            "身高体型、服饰与随身武器道具的原貌，禁止再创作或替换设定："
            f"{'、'.join(reference_asset_names)}。"
            "同一资产的多张参考图为该形象的不同角度，均以其为准。"
        )
    art_style_text = (art_style_prompt or "").strip()
    director_style_text = (director_style_prompt or "").strip()
    sections.append(
        f"## 美术风格提示词\nstyleKey: {art_style_key or '未指定'}\n{art_style_text or '（未提炼美术风格提示词）'}"
    )
    if director_style_key or director_style_text:
        sections.append(
            f"## 导演叙事提示词\ndirectorKey: {director_style_key or '未指定'}\n"
            f"{director_style_text or '（未提炼导演叙事提示词）'}"
        )
    if grid_size == 1:
        sections.append("## 镜头信息\n" + _format_grid_shot_line(shots[0], 1))
    else:
        sections.append(
            "## 分镜画面要求\n"
            "严格按下列画格顺序绘制，画格位置与镜头一一对应，不要在画面中标注任何编号或文字：\n"
            + "\n".join(_format_grid_shot_line(shot, index) for index, shot in enumerate(shots, start=1))
        )
    if asset_details:
        sections.append(
            "## 引用资产详情\n画面内容中以 @资产名 引用的资产以下列设定为准，"
            "并与参考图一一对应：\n" + "\n".join(asset_details)
        )
    return "\n\n".join(sections)


def _crop_grid_cells(data: bytes, *, rows: int, cols: int, count: int) -> list[bytes]:
    """把宫格大图等分裁切为前 count 个画格的 PNG 字节。"""

    with Image.open(BytesIO(data)) as image:
        converted = image.convert("RGB")
        width, height = converted.size
        cell_width = width / cols
        cell_height = height / rows
        results: list[bytes] = []
        for index in range(count):
            row, col = divmod(index, cols)
            box = (
                round(col * cell_width),
                round(row * cell_height),
                round((col + 1) * cell_width),
                round((row + 1) * cell_height),
            )
            buffer = BytesIO()
            converted.crop(box).save(buffer, format="PNG")
            results.append(buffer.getvalue())
        return results


def _normalize_storyboard_frame(
    data: bytes,
    *,
    target_size: tuple[int, int] | None,
) -> tuple[bytes, int, int, int, int]:
    """Read real dimensions and optionally center-fit a formal frame to video pixels."""

    with Image.open(BytesIO(data)) as image:
        converted = image.convert("RGB")
        source_width, source_height = converted.size
        if target_size is None:
            return data, source_width, source_height, source_width, source_height
        normalized = ImageOps.fit(
            converted,
            target_size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        buffer = BytesIO()
        normalized.save(buffer, format="PNG")
        width, height = normalized.size
        return buffer.getvalue(), width, height, source_width, source_height


def _allocate_reference_slots(
    ordered_asset_ids: list[str],
    media_ids_by_asset: dict[str, list[str]],
) -> list[tuple[str, str]]:
    """按轮询分配参考图额度：先保证每资产一张封面，余量内再逐资产补多角度图。"""

    selected: list[tuple[str, str]] = []
    for round_index in range(_GRID_REFERENCE_PER_ASSET):
        for asset_id in ordered_asset_ids:
            if len(selected) >= _GRID_REFERENCE_MAX_COUNT:
                return selected
            media_ids = media_ids_by_asset.get(asset_id, [])
            if round_index < len(media_ids):
                selected.append((asset_id, media_ids[round_index]))
    return selected


async def _collect_reference_images(
    session: AsyncSession,
    *,
    project_id: int,
    user_public_id: str,
    shots: list[StoryboardShot],
) -> tuple[list[StoryboardReferenceImage], list[Asset]]:
    """按镜头引用资产收集参考图与资产记录（跨镜头保序去重），无图资产自动跳过。

    每资产最多 _GRID_REFERENCE_PER_ASSET 张（封面优先，其次最新多角度图），
    整组上限 _GRID_REFERENCE_MAX_COUNT 张：先保证每个资产有一张，余量再补第二张。
    """

    asset_ids: list[str] = []
    for shot in shots:
        for asset_public_id in [item.strip() for item in (shot.asset_public_ids or "").split(",") if item.strip()]:
            if asset_public_id not in asset_ids:
                asset_ids.append(asset_public_id)
    if not asset_ids:
        return [], []

    assets = (
        await session.exec(
            select(Asset).where(
                Asset.project_id == project_id,
                Asset.user_public_id == user_public_id,
                Asset.public_id.in_(asset_ids),
                Asset.disabled_at.is_(None),
            )
        )
    ).all()
    assets_by_public_id = {asset.public_id: asset for asset in assets}
    ordered_assets = [assets_by_public_id[asset_id] for asset_id in asset_ids if asset_id in assets_by_public_id]

    media_ids_by_asset: dict[str, list[str]] = {}
    for asset in ordered_assets:
        media_ids_by_asset[asset.public_id] = await media_service._latest_asset_image_media_public_ids(
            session,
            project_id=project_id,
            user_public_id=user_public_id,
            asset_public_id=asset.public_id,
            limit=_GRID_REFERENCE_PER_ASSET,
        )

    selected = _allocate_reference_slots([asset.public_id for asset in ordered_assets], media_ids_by_asset)
    if not selected:
        return [], ordered_assets

    payloads = await media_service._load_reference_media_files(
        session,
        project_id=project_id,
        user_public_id=user_public_id,
        media_public_ids=[media_id for _, media_id in selected],
    )
    payloads_by_media_id = {str(payload["media_public_id"]).strip(): payload for payload in payloads}
    references = [
        StoryboardReferenceImage(
            image=payloads_by_media_id[media_id],
            asset_public_id=asset_id,
            asset_name=assets_by_public_id[asset_id].name.strip(),
            media_public_id=media_id,
        )
        for asset_id, media_id in selected
        if media_id in payloads_by_media_id
    ]
    return references, ordered_assets


async def _load_shots_by_public_ids(
    session: AsyncSession,
    *,
    project_id: int,
    user_public_id: str,
    shot_public_ids: list[str],
) -> list[StoryboardShot]:
    """按公开 ID 批量加载分镜镜头，按输入顺序返回（已删除镜头自动跳过）。"""

    ids = storyboard_service._dedupe_public_ids(shot_public_ids)
    statement = select(StoryboardShot).where(
        StoryboardShot.project_id == project_id,
        StoryboardShot.user_public_id == user_public_id,
        StoryboardShot.public_id.in_(ids),
        StoryboardShot.disabled_at.is_(None),
    )
    loaded = {shot.public_id: shot for shot in (await session.exec(statement)).all()}
    return [loaded[shot_id] for shot_id in ids if shot_id in loaded]


async def generate_storyboard_grid_image(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    shot_public_ids: list[str],
    grid_size: int,
    image_size: str = "",
    model_id: str = "",
    task_job_public_id: str = "",
    task_item_public_id: str = "",
    gateway: Any | None = None,
) -> dict[str, Any]:
    """为一组镜头生成一张宫格分镜图，并裁切画格回写到对应镜头。"""

    resolved_image_size, (rows, cols) = resolve_grid_spec(grid_size, image_size)

    timing = storyboard_service._StoryboardTiming()
    stage_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    resolved_model_id = (model_id or project.image_model or "").strip()
    shots = await _load_shots_by_public_ids(
        session,
        project_id=int(project.id),
        user_public_id=user_public_id,
        shot_public_ids=shot_public_ids,
    )
    timing.mark("shots_lookup", stage_started_at)

    stage_started_at = perf_counter()
    reference_items, shot_assets = await _collect_reference_images(
        session,
        project_id=int(project.id),
        user_public_id=user_public_id,
        shots=shots,
    )
    reference_images = [item.image for item in reference_items]
    reference_asset_public_ids = [item.asset_public_id for item in reference_items]
    reference_asset_names = [item.asset_name for item in reference_items]
    reference_media_public_ids = [item.media_public_id for item in reference_items]
    reference_image_mappings = [item.audit_payload() for item in reference_items]
    # 同一资产可能附带多张角度参考图，提示词中的资产名单按首次出现去重。
    prompt_reference_names = list(dict.fromkeys(reference_asset_names))
    timing.mark("reference_media", stage_started_at)

    stage_started_at = perf_counter()
    first_shot = shots[0]
    art_style_key = (first_shot.art_style_key or str(project.art_style or "")).strip()
    director_style_key = (first_shot.director_style_key or str(project.director_manual or "")).strip()
    art_style_prompt, director_style_prompt = await style_prompt_service.ensure_project_style_prompts(
        session, project
    )
    video_ratio = str(project.video_ratio or "9:16").strip() or "9:16"
    try:
        video_resolution = storyboard_image_size_to_resolution(
            str(project.video_model or ""), resolved_image_size
        )
        target_frame_size = (
            seedance_dimensions(video_resolution, video_ratio)
            if video_resolution is not None
            else None
        )
    except VideoGenerationSpecError as exc:
        raise StoryboardImageServiceError(str(exc)) from exc
    prompt = build_grid_image_prompt(
        shots=shots,
        grid_size=grid_size,
        rows=rows,
        cols=cols,
        video_ratio=video_ratio,
        art_style_key=art_style_key,
        art_style_prompt=art_style_prompt,
        director_style_key=director_style_key,
        director_style_prompt=director_style_prompt,
        reference_asset_names=prompt_reference_names,
        asset_details=format_asset_details(shot_assets, "\n".join(shot.prompt or "" for shot in shots)),
    )
    timing.mark("prompt_build", stage_started_at)

    episode_public_id = _common_episode_public_id(shots)
    scope_type = MEDIA_SCOPE_EPISODE if episode_public_id else MEDIA_SCOPE_PROJECT
    scope_public_id = episode_public_id or project_public_id
    shot_ids = [shot.public_id for shot in shots]
    shot_indexes = [int(shot.shot_index) for shot in shots]
    grid_params = {
        "grid_size": grid_size,
        "image_size": resolved_image_size,
        "rows": rows,
        "cols": cols,
        "shot_public_ids": shot_ids,
        "shot_indexes": shot_indexes,
        "episode_public_id": episode_public_id,
        "aspect_ratio": video_ratio,
        "video_resolution": video_resolution or "",
        "reference_asset_names": reference_asset_names,
        "reference_asset_public_ids": reference_asset_public_ids,
        "reference_media_public_ids": reference_media_public_ids,
        "reference_images": reference_image_mappings,
        "mode": "edit" if reference_images else "generate",
    }
    grid_media = MediaAsset(
        project_id=int(project.id),
        user_public_id=user_public_id,
        media_type=MEDIA_TYPE_IMAGE,
        source=MEDIA_SOURCE_GENERATION,
        status=MEDIA_STATUS_PROCESSING,
        scope_type=scope_type,
        scope_public_id=scope_public_id,
        media_role=MEDIA_ROLE_GRID,
        model_id=resolved_model_id,
        prompt=prompt,
        params=media_service._dump_params(grid_params),
        task_job_public_id=task_job_public_id,
        task_item_public_id=task_item_public_id,
    )
    session.add(grid_media)
    await session.flush()

    resolved_gateway = gateway or media_service.build_media_gateway(MEDIA_TYPE_IMAGE)
    edit_parameters = media_service._image_edit_parameters_for_model(resolved_model_id) if reference_images else {}
    gen_kwargs: dict[str, Any] = {
        "aspect_ratio": video_ratio,
        "image_size": resolved_image_size,
    }
    storage = get_media_storage()
    try:
        stage_started_at = perf_counter()
        # 判断是否有引用资产相关推按，有则调用图生图，没有则调用文生图
        if reference_images:
            output = await resolved_gateway.edit_image(
                model_id=resolved_model_id,
                prompt=prompt,
                images=reference_images,
                **edit_parameters,
                **gen_kwargs,
            )
        else:
            output = await resolved_gateway.generate_image(
                model_id=resolved_model_id, prompt=prompt, **gen_kwargs
            )
        timing.mark("image_model", stage_started_at)
        stage_started_at = perf_counter()
        data = await media_service._resolve_media_bytes(
            output, timeout=settings.image_generation_timeout_seconds
        )
        timing.mark("media_bytes", stage_started_at)

        grid_media.mime_type = output.mime_type.strip().lower() or "image/png"
        grid_media.width = output.width
        grid_media.height = output.height
        grid_media.seed = output.seed
        grid_media.usage = json.dumps({"usage": output.usage, "cost": output.cost}, ensure_ascii=False)
        grid_media.cost_tokens = media_service._cost_tokens_from_usage(output.usage)
        stage_started_at = perf_counter()
        await media_service._store_media_bytes(
            storage,
            grid_media,
            project_public_id=project_public_id,
            data=data,
            ext=media_service._ext_for(MEDIA_TYPE_IMAGE, grid_media.mime_type, output.url),
        )
        grid_media.status = MEDIA_STATUS_READY
        session.add(grid_media)
        await session.flush()
        timing.mark("grid_media_write", stage_started_at)
    except (ProviderModelGatewayError, media_service.MediaServiceError) as exc:
        grid_media.status = MEDIA_STATUS_FAILED
        grid_media.error_message = str(exc)
        session.add(grid_media)
        await session.flush()
        raise StoryboardImageServiceError(
            f"宫格分镜图生成失败：{exc}",
            result={
                "grid_media_public_id": grid_media.public_id,
                "shot_public_ids": shot_ids,
                "model_id": resolved_model_id,
                "storyboard_timing": timing.payload(),
            },
        ) from exc

    stage_started_at = perf_counter()
    frame_cells = await asyncio.to_thread(_crop_grid_cells, data, rows=rows, cols=cols, count=len(shots))
    timing.mark("grid_crop", stage_started_at)

    stage_started_at = perf_counter()
    frame_media_ids: list[str] = []
    for cell_index, (shot, frame_data) in enumerate(zip(shots, frame_cells, strict=True)):
        row, col = divmod(cell_index, cols)
        frame_data, frame_width, frame_height, source_width, source_height = await asyncio.to_thread(
            _normalize_storyboard_frame,
            frame_data,
            target_size=target_frame_size,
        )
        frame_media = MediaAsset(
            project_id=int(project.id),
            user_public_id=user_public_id,
            media_type=MEDIA_TYPE_IMAGE,
            source=MEDIA_SOURCE_GENERATION,
            status=MEDIA_STATUS_PROCESSING,
            scope_type=MEDIA_SCOPE_SHOT,
            scope_public_id=shot.public_id,
            media_role=MEDIA_ROLE_FINAL,
            model_id=resolved_model_id,
            prompt=(shot.prompt or "").strip(),
            params=media_service._dump_params(
                {
                    "grid_media_public_id": grid_media.public_id,
                    "cell_index": cell_index,
                    "row": row,
                    "col": col,
                    "grid_size": grid_size,
                    "image_size": resolved_image_size,
                    "video_resolution": video_resolution or "",
                    "video_ratio": video_ratio,
                    "source_width": source_width,
                    "source_height": source_height,
                }
            ),
            mime_type="image/png",
            width=frame_width,
            height=frame_height,
            task_job_public_id=task_job_public_id,
            task_item_public_id=task_item_public_id,
        )
        session.add(frame_media)
        await session.flush()
        await media_service._store_media_bytes(
            storage,
            frame_media,
            project_public_id=project_public_id,
            data=frame_data,
            ext="png",
        )
        frame_media.status = MEDIA_STATUS_READY
        session.add(frame_media)
        frame_media_ids.append(frame_media.public_id)

        shot.reference_media_public_id = frame_media.public_id
        shot.updated_at = utc_now()
        session.add(shot)
    await session.flush()
    timing.mark("cell_media_write", stage_started_at)

    output_summary = {
        "grid_media_public_id": grid_media.public_id,
        "grid_url": grid_media.url,
        "grid_size": grid_size,
        "image_size": resolved_image_size,
        "rows": rows,
        "cols": cols,
        "episode_public_id": episode_public_id,
        "shot_public_ids": shot_ids,
        "shot_indexes": shot_indexes,
        "frame_media_public_ids": frame_media_ids,
        "reference_asset_names": reference_asset_names,
        "reference_asset_public_ids": reference_asset_public_ids,
        "reference_media_public_ids": reference_media_public_ids,
        "reference_images": reference_image_mappings,
        "mode": grid_params["mode"],
    }
    output_text = json.dumps(output_summary, ensure_ascii=False)
    return {
        "grid_media": grid_media,
        "grid_media_public_id": grid_media.public_id,
        "grid_url": grid_media.url,
        "frame_media_public_ids": frame_media_ids,
        "frame_media_public_id": frame_media_ids[0] if frame_media_ids else "",
        "shot_public_ids": shot_ids,
        "shot_public_id": shot_ids[0] if shot_ids else "",
        "shot_indexes": shot_indexes,
        "shot_index": shot_indexes[0] if shot_indexes else 0,
        "episode_public_id": episode_public_id,
        "model_id": resolved_model_id,
        "reference_asset_names": reference_asset_names,
        "reference_asset_public_ids": reference_asset_public_ids,
        "reference_media_public_ids": reference_media_public_ids,
        "reference_images": reference_image_mappings,
        "prompt": prompt,
        "raw_output": output_text,
        "output_text": output_text,
        "storyboard_timing": timing.payload(),
    }


async def build_grid_image_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    grid_size: int,
    image_size: str = "",
    episode_public_ids: list[str] | None = None,
    shot_public_ids: list[str] | None = None,
    only_missing: bool = False,
    model_id: str = "",
) -> list[TaskItemCreate]:
    """把待生成镜头按宫格规格分组构造任务子项（每组一张宫格图）。"""

    resolved_image_size, _layout = resolve_grid_spec(grid_size, image_size)
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    resolved_model_id = (model_id or project.image_model or "").strip()
    if not resolved_model_id:
        raise StoryboardImageServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")

    selected_shot_ids = set(storyboard_service._dedupe_public_ids(shot_public_ids))
    selected_episode_ids = set(storyboard_service._dedupe_public_ids(episode_public_ids))
    shots = await storyboard_service.list_storyboard_shots(
        session, project_public_id, user_public_id
    )
    candidates: list[StoryboardShot] = []
    for shot in shots:
        if selected_shot_ids and shot.public_id not in selected_shot_ids:
            continue
        if selected_episode_ids and shot.episode_public_id not in selected_episode_ids:
            continue
        if only_missing and shot.reference_media_public_id.strip():
            continue
        if shot.status == STORYBOARD_STATUS_LOCKED:
            continue
        candidates.append(shot)
    if not candidates:
        raise StoryboardImageServiceError("没有待生成分镜图的镜头")
    groups = group_storyboard_shots_for_grid(candidates, grid_size=grid_size)

    items: list[TaskItemCreate] = []
    for group in groups:
        first = group[0]
        last = group[-1]
        items.append(
            TaskItemCreate(
                item_type=STORYBOARD_GRID_IMAGE_TASK_TYPE,
                item_key=f"storyboard-grid:{first.episode_public_id}:{first.shot_index}-{last.shot_index}",
                payload={
                    "project_public_id": project_public_id,
                    "current_user_public_id": user_public_id,
                    "model_id": resolved_model_id,
                    "grid_size": grid_size,
                    "image_size": resolved_image_size,
                    "episode_public_id": _common_episode_public_id(group),
                    "episode_index": first.episode_index,
                    "shot_public_ids": [shot.public_id for shot in group],
                    "shot_indexes": [int(shot.shot_index) for shot in group],
                    "shot_count": len(group),
                },
            )
        )
    return items


async def submit_grid_image_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    grid_size: int,
    image_size: str = "",
    episode_public_ids: list[str] | None = None,
    shot_public_ids: list[str] | None = None,
    only_missing: bool = False,
    model_id: str = "",
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交宫格分镜图生成异步任务；每组镜头一个子项、一张宫格图。"""

    items = await build_grid_image_task_items(
        session,
        project_public_id,
        user_public_id,
        grid_size=grid_size,
        image_size=image_size,
        episode_public_ids=episode_public_ids,
        shot_public_ids=shot_public_ids,
        only_missing=only_missing,
        model_id=model_id,
    )
    resolved_engine = engine or default_async_task_engine
    resolved_image_size = str(items[0].payload.get("image_size") or "")
    spec_label = (
        f"单帧 · {resolved_image_size}" if grid_size == 1 else f"{grid_size} 格 · {resolved_image_size}"
    )
    shot_count = sum(int(item.payload.get("shot_count") or 0) for item in items)
    job_name = (
        f"分镜图生成（{spec_label}）"
        if len(items) == 1
        else f"分镜图批量生成：{shot_count} 镜 / {len(items)} 张（{spec_label}）"
    )
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=STORYBOARD_GRID_IMAGE_TASK_TYPE,
            queue_name=storyboard_service.STORYBOARD_QUEUE_NAME,
            name=job_name,
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": str(items[0].payload.get("model_id") or ""),
                "grid_size": grid_size,
                "image_size": resolved_image_size,
                "shot_count": shot_count,
                "grid_count": len(items),
                "only_missing": only_missing,
            },
            items=items,
        ),
    )