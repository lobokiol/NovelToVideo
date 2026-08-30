from __future__ import annotations

"""镜头视频生成服务。

以镜头分镜图（shot.reference_media_public_id）为首帧做图生视频：技能文件
模板拼接运动提示词（画面动作 + 镜头运动 + 台词情绪），并注入项目固定的
导演叙事提示词约束运镜与节奏；生成参数按项目画幅比例与镜头时长收敛，
产出视频媒体挂靠镜头（scope=shot）。每镜可多次生成形成候选，首个成功
候选自动设为选定（media_role=final），后续候选由用户在工作台择优切换。
"""

import json
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.tasks.engine import default_async_task_engine
from app.models.media import (
    MEDIA_ROLE_FINAL,
    MEDIA_ROLE_GENERATED,
    MEDIA_SCOPE_SHOT,
    MEDIA_STATUS_READY,
    MEDIA_TYPE_VIDEO,
    MediaAsset,
)
from app.models.project import ProjectVideoMode
from app.models.storyboard import STORYBOARD_STATUS_LOCKED, StoryboardShot
from app.schemas.tasks import TaskItemCreate, TaskJobCreate, TaskJobDetail
from app.services import media as media_service
from app.services import project as project_service
from app.services import storyboard as storyboard_service
from app.services import style_prompt as style_prompt_service
from app.services.prompt_registry import PromptRegistry, PromptRegistryError
from app.services.video_generation_spec import (
    clamp_seedance_duration,
    find_seedance_spec_by_dimensions,
    is_seedance_2_model,
    supported_seedance_resolutions,
)


SHOT_VIDEO_TASK_TYPE = "storyboard.shot_video"

# 镜头时长收敛区间：主流图生视频模型支持 3-12 秒。
SHOT_DURATION_MIN = 3
SHOT_DURATION_MAX = 12
SHOT_DURATION_DEFAULT = 5

DEFAULT_RESOLUTION = "720p"

_PROMPT_ACTION_MAX_CHARS = 10000
_PROMPT_DIALOGUE_MAX_CHARS = 160

# data/skills 提示词文件缺失时的内置回退模板，与技能文件保持同等约束。
_FALLBACK_SHOT_VIDEO_PROMPT = (
    "你正在为一个电影镜头生成图生视频：首帧图已经给定（该镜头的分镜首帧画面），"
    "你的任务是让画面从首帧自然动起来，完成这一镜的表演与运镜。\n\n"
    "以首帧图为唯一起点自然延展运动：人物形象、服饰、场景结构、光线方向与整体调色"
    "必须与首帧完全连续，禁止人物变形、换脸、换装或场景跳变。\n\n"
    "运动服从镜头信息：主体动作按画面动作描述连续推进，机位按镜头运动描述平滑执行，"
    "景别保持与首帧构图一致的演进逻辑；动作与运镜节奏均匀，画面稳定无闪烁、无残影。\n\n"
    "台词只用于指导人物的表情、口型与肢体情绪，禁止在画面中出现任何文字、字幕或水印。"
)


class ShotVideoServiceError(storyboard_service.StoryboardServiceError):
    """镜头视频服务错误，沿用分镜服务错误族便于路由统一映射。"""


def load_shot_video_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取镜头视频生成提示词模板，缺失时回退内置模板。"""

    prompt_name = settings.shot_video_prompt_name.strip()
    if not prompt_name:
        return _FALLBACK_SHOT_VIDEO_PROMPT
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(prompt_name)
    except PromptRegistryError:
        return _FALLBACK_SHOT_VIDEO_PROMPT


def clamp_shot_duration(duration_seconds: int | None, *, model_id: str = "") -> int:
    """把镜头时长收敛到视频模型支持区间，未填时用默认值。"""

    if is_seedance_2_model(model_id):
        return clamp_seedance_duration(duration_seconds)
    value = int(duration_seconds or 0)
    if value <= 0:
        return SHOT_DURATION_DEFAULT
    return max(SHOT_DURATION_MIN, min(SHOT_DURATION_MAX, value))


def resolve_shot_video_inputs(
    mode: ProjectVideoMode,
    *,
    storyboard_frame_media_public_id: str,
    last_frame_media_public_id: str = "",
) -> dict[str, object]:
    """按项目视频模式把分镜图和独立尾帧映射为供应商输入角色。"""

    frame_id = (storyboard_frame_media_public_id or "").strip()
    tail_id = (last_frame_media_public_id or "").strip()
    if not frame_id:
        raise ShotVideoServiceError("该镜头尚无分镜图，请先生成分镜图", retryable=False)

    try:
        resolved_mode = mode if isinstance(mode, ProjectVideoMode) else ProjectVideoMode(str(mode))
    except ValueError as exc:
        raise ShotVideoServiceError("项目视频生成模式无效", retryable=False) from exc

    if resolved_mode == ProjectVideoMode.TEXT:
        raise ShotVideoServiceError("纯文本模式不能使用当前分镜图生成视频", retryable=False)
    if resolved_mode == ProjectVideoMode.SINGLE_IMAGE:
        first_frame_id = frame_id
        reference_ids: list[str] = []
    elif resolved_mode == ProjectVideoMode.MULTI_REFERENCE:
        first_frame_id = ""
        reference_ids = [frame_id]
    elif resolved_mode in (ProjectVideoMode.START_END_REQUIRED, ProjectVideoMode.END_FRAME_OPTIONAL):
        first_frame_id = frame_id
        reference_ids = []
    elif resolved_mode == ProjectVideoMode.START_FRAME_OPTIONAL:
        first_frame_id = ""
        reference_ids = [frame_id]
    else:  # pragma: no cover - exhaustive enum guard
        raise ShotVideoServiceError("项目视频生成模式无效", retryable=False)

    supports_tail = resolved_mode in (
        ProjectVideoMode.START_END_REQUIRED,
        ProjectVideoMode.END_FRAME_OPTIONAL,
        ProjectVideoMode.START_FRAME_OPTIONAL,
    )
    resolved_tail_id = tail_id if supports_tail else ""
    if resolved_tail_id and resolved_tail_id == frame_id:
        raise ShotVideoServiceError("必须使用独立尾帧图片，不能复用当前分镜图", retryable=False)
    if resolved_mode in (ProjectVideoMode.START_END_REQUIRED, ProjectVideoMode.START_FRAME_OPTIONAL) and not resolved_tail_id:
        raise ShotVideoServiceError("当前视频生成模式要求提供独立尾帧", retryable=False)

    return {
        "first_frame_media_public_id": first_frame_id,
        "last_frame_media_public_id": resolved_tail_id,
        "reference_media_public_ids": reference_ids,
    }


def build_shot_video_prompt(
    shot: StoryboardShot,
    *,
    director_style_prompt: str = "",
    model_id: str = "",
    mode: ProjectVideoMode = ProjectVideoMode.SINGLE_IMAGE,
    has_last_frame: bool = False,
    duration_seconds: int | None = None,
) -> str:
    """拼接图生视频运动提示词：技能模板 + 镜头运动信息 + 项目固定叙事提示词。"""

    action = (shot.action or "").strip()
    if len(action) > _PROMPT_ACTION_MAX_CHARS:
        action = action[:_PROMPT_ACTION_MAX_CHARS] + "…"
    dialogue = (shot.dialogue or "").strip().replace("\n", " / ")
    if len(dialogue) > _PROMPT_DIALOGUE_MAX_CHARS:
        dialogue = dialogue[:_PROMPT_DIALOGUE_MAX_CHARS] + "…"

    resolved_duration = clamp_shot_duration(
        shot.duration_seconds if duration_seconds is None else duration_seconds,
        model_id=model_id,
    )
    motion_bits = [f"镜头时长：约 {resolved_duration} 秒"]
    if action:
        motion_bits.append(f"画面动作：{action}")
    if (shot.camera or "").strip():
        motion_bits.append(f"镜头运动：{shot.camera.strip()}")
    if (shot.shot_size or "").strip():
        motion_bits.append(f"景别保持：{shot.shot_size.strip()}，与首帧构图一致")
    if dialogue:
        motion_bits.append(f"台词情绪参考（不出现文字与字幕）：{dialogue}")

    if mode in (ProjectVideoMode.SINGLE_IMAGE, ProjectVideoMode.END_FRAME_OPTIONAL):
        material_instruction = "图片1是当前正式分镜图，并严格作为首帧"
        if has_last_frame:
            material_instruction = "图片1是当前正式分镜图并作为首帧；图片2是独立尾帧"
    elif mode == ProjectVideoMode.MULTI_REFERENCE:
        material_instruction = "图片1是当前正式分镜图，并作为核心参考图"
    elif mode == ProjectVideoMode.START_END_REQUIRED:
        material_instruction = "图片1是当前正式分镜图并作为首帧；图片2是独立尾帧"
    elif mode == ProjectVideoMode.START_FRAME_OPTIONAL:
        material_instruction = "图片1是当前正式分镜图并作为核心参考图；图片2是独立尾帧"
    else:
        material_instruction = "严格使用请求中的当前正式分镜图"

    sections = [
        f"## 素材使用规则（最高优先级）\n{material_instruction}",
        load_shot_video_prompt(),
        "## 运动信息\n" + "\n".join(motion_bits),
    ]
    narrative = (director_style_prompt or "").strip()
    if narrative:
        sections.append(f"## 导演叙事提示词\n{narrative}")
    return "\n\n".join(sections)


async def _selected_video_shot_ids(
    session: AsyncSession, *, shot_public_ids: list[str]
) -> set[str]:
    """查询已存在选定视频（scope=shot & video & final & ready）的镜头集合。"""

    if not shot_public_ids:
        return set()
    rows = (
        await session.exec(
            select(MediaAsset.scope_public_id).where(
                MediaAsset.scope_type == MEDIA_SCOPE_SHOT,
                MediaAsset.scope_public_id.in_(shot_public_ids),
                MediaAsset.media_type == MEDIA_TYPE_VIDEO,
                MediaAsset.media_role == MEDIA_ROLE_FINAL,
                MediaAsset.status == MEDIA_STATUS_READY,
                MediaAsset.disabled_at.is_(None),
            )
        )
    ).all()
    return {str(value) for value in rows}


async def generate_shot_video(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    shot_public_id: str,
    model_id: str = "",
    generate_audio: bool = False,
    resolution: str = "",
    ratio: str = "",
    duration_seconds: int | None = None,
    allow_auto_select: bool = True,
    task_job_public_id: str = "",
    task_item_public_id: str = "",
    gateway: Any | None = None,
) -> dict[str, Any]:
    """为单个镜头生成一段候选视频；首个成功候选自动设为选定final。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    bound_model_id = str(project.video_model or "").strip()
    if not bound_model_id:
        raise ShotVideoServiceError(
            "项目未绑定视频模型，请先在项目设置中选择视频模型",
            retryable=False,
        )
    requested_model_id = str(model_id or "").strip()
    if requested_model_id and requested_model_id != bound_model_id:
        raise ShotVideoServiceError(
            "请求的视频模型与项目绑定模型不一致，请刷新项目后重试",
            retryable=False,
        )

    shot = await storyboard_service.load_shot_or_raise(
        session, int(project.id), user_public_id, shot_public_id
    )
    frame_media_public_id = (shot.reference_media_public_id or "").strip()
    video_inputs = resolve_shot_video_inputs(
        project.mode,
        storyboard_frame_media_public_id=frame_media_public_id,
        last_frame_media_public_id=shot.last_frame_media_public_id,
    )

    try:
        source_width, source_height = await media_service.get_image_media_dimensions(
            session,
            project_public_id,
            user_public_id,
            media_public_id=frame_media_public_id,
        )
    except media_service.MediaServiceError as exc:
        raise ShotVideoServiceError(str(exc), result=exc.result, retryable=False) from exc

    requested_resolution = (resolution or "").strip().lower()
    requested_ratio = (ratio or "").strip()
    # 比例/分辨率优先取请求覆写（镜头详情自定义），否则回落项目设置 / 默认档。
    resolved_ratio = requested_ratio or str(project.video_ratio or "9:16").strip() or "9:16"
    resolved_resolution = requested_resolution or DEFAULT_RESOLUTION
    if is_seedance_2_model(bound_model_id):
        # Seedance 2.0 输出规格由分镜图像素锁定，覆写仅作参考、最终以分镜图规格为准。
        seedance_spec = find_seedance_spec_by_dimensions(source_width, source_height)
        if seedance_spec is None:
            raise ShotVideoServiceError(
                "当前正式分镜图不符合 Seedance 2.0 官方像素规格，请重新生成分镜图",
                retryable=False,
            )
        resolved_resolution, frame_ratio = seedance_spec
        if resolved_resolution not in supported_seedance_resolutions(bound_model_id):
            raise ShotVideoServiceError(
                "当前正式分镜图分辨率不受项目绑定的 Seedance 模型支持",
                retryable=False,
            )
        resolved_ratio = frame_ratio

    duration = clamp_shot_duration(
        shot.duration_seconds if duration_seconds is None else duration_seconds,
        model_id=bound_model_id,
    )
    _, director_style_prompt = await style_prompt_service.ensure_project_style_prompts(session, project)
    prompt = build_shot_video_prompt(
        shot,
        director_style_prompt=director_style_prompt,
        model_id=bound_model_id,
        mode=project.mode,
        has_last_frame=bool(video_inputs["last_frame_media_public_id"]),
        duration_seconds=duration,
    )
    params: dict[str, Any] = {
        "ratio": "adaptive" if is_seedance_2_model(bound_model_id) else resolved_ratio,
        "duration": duration,
        "resolution": resolved_resolution,
        "generate_audio": bool(generate_audio),
    }
    if not is_seedance_2_model(bound_model_id) and (shot.seed or "").strip():
        params["seed"] = shot.seed.strip()

    try:
        result = await media_service.generate_video_media(
            session,
            project_public_id,
            user_public_id,
            model_id=bound_model_id,
            prompt=prompt,
            params=params,
            first_frame_media_public_id=str(video_inputs["first_frame_media_public_id"]),
            last_frame_media_public_id=str(video_inputs["last_frame_media_public_id"]),
            reference_media_public_ids=list(video_inputs["reference_media_public_ids"]),
            expected_width=source_width,
            expected_height=source_height,
            generation_mode=project.mode.value,
            scope_type=MEDIA_SCOPE_SHOT,
            scope_public_id=shot.public_id,
            media_role=MEDIA_ROLE_GENERATED,
            task_job_public_id=task_job_public_id,
            task_item_public_id=task_item_public_id,
            gateway=gateway,
        )
    except media_service.MediaServiceError as exc:
        raise ShotVideoServiceError(
            str(exc),
            result={**exc.result, "shot_public_id": shot.public_id},
        ) from exc

    media: MediaAsset = result["media"]
    auto_selected = False
    if allow_auto_select:
        selected = await _selected_video_shot_ids(session, shot_public_ids=[shot.public_id])
        if shot.public_id not in selected:
            media.media_role = MEDIA_ROLE_FINAL
            session.add(media)
            await session.flush()
            auto_selected = True

    output_summary = {
        "media_public_id": media.public_id,
        "url": media.url,
        "shot_public_id": shot.public_id,
        "episode_public_id": shot.episode_public_id,
        "shot_index": shot.shot_index,
        "duration": duration,
        "auto_selected": auto_selected,
        "generate_audio": generate_audio,
    }
    output_text = json.dumps(output_summary, ensure_ascii=False)
    return {
        **result,
        "shot_public_id": shot.public_id,
        "episode_public_id": shot.episode_public_id,
        "shot_index": shot.shot_index,
        "auto_selected": auto_selected,
        "duration": duration,
        "resolution": resolved_resolution,
        "ratio": resolved_ratio,
        "width": source_width,
        "height": source_height,
        "generation_mode": project.mode.value,
        "prompt": prompt,
        "raw_output": output_text,
        "output_text": output_text,
    }


async def build_shot_video_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    episode_public_ids: list[str] | None = None,
    shot_public_ids: list[str] | None = None,
    only_missing: bool = True,
    generate_audio: bool = False,
    resolution: str = "",
    ratio: str = "",
    model_id: str = "",
    duration_seconds: int | None = None,
    quantity: int = 1,
) -> list[TaskItemCreate]:
    """构造镜头视频生成子项：每镜一个或多个候选；默认仅补缺。

    仅接受已有分镜图的未锁定镜头。
    """

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    resolved_model_id = str(project.video_model or "").strip()
    if not resolved_model_id:
        raise ShotVideoServiceError("项目未绑定视频模型，请先在项目设置中选择视频模型")
    requested_model_id = str(model_id or "").strip()
    if requested_model_id and requested_model_id != resolved_model_id:
        raise ShotVideoServiceError(
            "请求的视频模型与项目绑定模型不一致，请刷新项目后重试",
            retryable=False,
        )

    selected_shot_ids = set(storyboard_service._dedupe_public_ids(shot_public_ids))
    selected_episode_ids = set(storyboard_service._dedupe_public_ids(episode_public_ids))
    shots = await storyboard_service.list_storyboard_shots(session, project_public_id, user_public_id)
    candidates: list[StoryboardShot] = []
    skipped_no_frame = 0
    for shot in shots:
        if selected_shot_ids and shot.public_id not in selected_shot_ids:
            continue
        if selected_episode_ids and shot.episode_public_id not in selected_episode_ids:
            continue
        if shot.status == STORYBOARD_STATUS_LOCKED:
            continue
        if not (shot.reference_media_public_id or "").strip():
            skipped_no_frame += 1
            continue
        resolve_shot_video_inputs(
            project.mode,
            storyboard_frame_media_public_id=shot.reference_media_public_id,
            last_frame_media_public_id=shot.last_frame_media_public_id,
        )
        candidates.append(shot)

    if only_missing and candidates:
        selected = await _selected_video_shot_ids(
            session, shot_public_ids=[shot.public_id for shot in candidates]
        )
        candidates = [shot for shot in candidates if shot.public_id not in selected]
    if not candidates:
        if skipped_no_frame:
            raise ShotVideoServiceError("所选镜头均无分镜图或已有选定视频，请先生成分镜图")
        raise ShotVideoServiceError("没有待生成视频的镜头")

    normalized_quantity = max(1, min(4, int(quantity or 1)))
    items: list[TaskItemCreate] = []
    for shot in candidates:
        for candidate_index in range(1, normalized_quantity + 1):
            items.append(
                TaskItemCreate(
                    item_type=SHOT_VIDEO_TASK_TYPE,
                    item_key=f"shot-video:{shot.public_id}:{candidate_index}",
                    payload={
                        "project_public_id": project_public_id,
                        "current_user_public_id": user_public_id,
                        "model_id": resolved_model_id,
                        "shot_public_id": shot.public_id,
                        "episode_public_id": shot.episode_public_id,
                        "shot_index": shot.shot_index,
                        "candidate_index": candidate_index,
                        "quantity": normalized_quantity,
                        "duration_seconds": duration_seconds,
                        "generate_audio": generate_audio,
                        "resolution": (resolution or "").strip(),
                        "ratio": (ratio or "").strip(),
                    },
                )
            )
    return items


async def submit_shot_video_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    episode_public_ids: list[str] | None = None,
    shot_public_ids: list[str] | None = None,
    only_missing: bool = True,
    generate_audio: bool = False,
    resolution: str = "",
    ratio: str = "",
    model_id: str = "",
    duration_seconds: int | None = None,
    quantity: int = 1,
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交镜头视频生成异步任务；每条候选独立执行与计费。"""

    items = await build_shot_video_task_items(
        session,
        project_public_id,
        user_public_id,
        episode_public_ids=episode_public_ids,
        shot_public_ids=shot_public_ids,
        only_missing=only_missing,
        generate_audio=generate_audio,
        resolution=resolution,
        ratio=ratio,
        model_id=model_id,
        duration_seconds=duration_seconds,
        quantity=quantity,
    )
    resolved_engine = engine or default_async_task_engine
    shot_count = len({str(item.payload.get("shot_public_id") or "") for item in items})
    candidate_count = len(items)
    if shot_count == 1:
        job_name = "镜头视频生成" if candidate_count == 1 else f"镜头视频生成：{candidate_count} 条候选"
    else:
        job_name = f"镜头视频批量生成：{shot_count} 镜"
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=SHOT_VIDEO_TASK_TYPE,
            queue_name=storyboard_service.STORYBOARD_QUEUE_NAME,
            name=job_name,
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": str(items[0].payload.get("model_id") or ""),
                "shot_count": shot_count,
                "candidate_count": candidate_count,
                "quantity": max(1, min(4, int(quantity or 1))),
                "duration_seconds": duration_seconds,
                "only_missing": only_missing,
                "generate_audio": generate_audio,
                "resolution": (resolution or "").strip(),
                "ratio": (ratio or "").strip(),
            },
            items=items,
        ),
    )