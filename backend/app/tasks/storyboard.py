from __future__ import annotations

from typing import Any

from app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure
from app.services import shot_video as shot_video_service
from app.services import storyboard as storyboard_service
from app.services import storyboard_image as storyboard_image_service


async def generate_storyboard_task(context: Any) -> dict[str, Any]:
    """Storyboard generation task item handler."""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    episode_public_id = str(payload.get("episode_public_id") or "").strip()
    art_style = str(payload.get("art_style") or "").strip()
    director_style = str(payload.get("director_style") or "").strip()
    shot_public_ids = [
        str(item or "").strip()
        for item in (payload.get("shot_public_ids") or [])
        if str(item or "").strip()
    ]
    if not project_public_id or not current_user_public_id or not model_id or not episode_public_id:
        raise ValueError("分镜生成任务参数不完整")

    try:
        result = await storyboard_service.generate_storyboard(
            context.session,
            project_public_id,
            current_user_public_id,
            episode_public_id,
            model_id=model_id,
            art_style=art_style,
            director_style=director_style,
            shot_public_ids=shot_public_ids,
        )
        await context.session.commit()
    except storyboard_service.StoryboardServiceError as exc:
        await context.session.rollback()
        raise TaskHandlerFailure(
            str(exc),
            error_code="storyboard_generation_failed",
            result={**exc.result, "episode_public_id": episode_public_id},
            retryable=exc.retryable,
        ) from exc

    shots = result["shots"]
    return {
        "created": int(result["created"]),
        "updated": int(result["updated"]),
        "shot_public_ids": [shot.public_id for shot in shots],
        "regenerated_shot_public_ids": shot_public_ids,
        "episode_public_id": episode_public_id,
        "episode_index": result.get("episode_index"),
        "model_id": result.get("model_id") or model_id,
        "art_style": result.get("art_style") or art_style,
        "director_style": result.get("director_style") or director_style,
        "parse_status": result.get("parse_status") or "",
        "storyboard_timing": result.get("storyboard_timing") or {},
        "messages": result.get("messages") or [],
        "composed_prompt": str(result.get("composed_prompt") or ""),
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
    }


async def grid_image_storyboard_task(context: Any) -> dict[str, Any]:
    """宫格分镜图生成子任务处理器：每个子项对应一组镜头的一张宫格图。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    grid_size = int(payload.get("grid_size") or 0)
    image_size = str(payload.get("image_size") or "").strip()
    shot_public_ids = [
        str(item or "").strip()
        for item in (payload.get("shot_public_ids") or [])
        if str(item or "").strip()
    ]
    if not project_public_id or not current_user_public_id or not grid_size or not shot_public_ids:
        raise ValueError("宫格分镜图任务参数不完整")

    try:
        result = await storyboard_image_service.generate_storyboard_grid_image(
            context.session,
            project_public_id,
            current_user_public_id,
            shot_public_ids=shot_public_ids,
            grid_size=grid_size,
            image_size=image_size,
            model_id=model_id,
            task_job_public_id=context.message.job_public_id,
            task_item_public_id=context.message.item_public_id,
        )
        await context.session.commit()
    except storyboard_service.StoryboardServiceError as exc:
        await context.session.rollback()
        raise TaskHandlerFailure(
            str(exc),
            error_code="storyboard_grid_image_failed",
            result={**exc.result, "shot_public_ids": shot_public_ids, "grid_size": grid_size},
            retryable=exc.retryable,
        ) from exc

    return {
        "grid_media_public_id": str(result.get("grid_media_public_id") or ""),
        "url": str(result.get("grid_url") or ""),
        "episode_public_id": str(result.get("episode_public_id") or ""),
        "shot_public_ids": list(result.get("shot_public_ids") or shot_public_ids),
        "shot_public_id": str(result.get("shot_public_id") or shot_public_ids[0]),
        "shot_indexes": list(result.get("shot_indexes") or []),
        "shot_index": int(result.get("shot_index") or 0),
        "frame_media_public_ids": list(result.get("frame_media_public_ids") or []),
        "frame_media_public_id": str(result.get("frame_media_public_id") or ""),
        "grid_size": grid_size,
        "image_size": image_size,
        "model_id": str(result.get("model_id") or model_id),
        "prompt": str(result.get("prompt") or ""),
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
        "storyboard_timing": result.get("storyboard_timing") or {},
    }


async def shot_video_storyboard_task(context: Any) -> dict[str, Any]:
    """镜头视频生成子任务处理器：每个子项对应一个镜头的一段候选视频。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    shot_public_id = str(payload.get("shot_public_id") or "").strip()
    generate_audio = bool(payload.get("generate_audio"))
    resolution = str(payload.get("resolution") or "").strip()
    ratio = str(payload.get("ratio") or "").strip()
    raw_duration = payload.get("duration_seconds")
    duration_seconds = int(raw_duration) if raw_duration not in (None, "") else None
    candidate_index = max(1, int(payload.get("candidate_index") or 1))
    if not project_public_id or not current_user_public_id or not shot_public_id:
        raise ValueError("镜头视频任务参数不完整")

    try:
        result = await shot_video_service.generate_shot_video(
            context.session,
            project_public_id,
            current_user_public_id,
            shot_public_id=shot_public_id,
            model_id=model_id,
            generate_audio=generate_audio,
            resolution=resolution,
            ratio=ratio,
            duration_seconds=duration_seconds,
            allow_auto_select=candidate_index == 1,
            task_job_public_id=context.message.job_public_id,
            task_item_public_id=context.message.item_public_id,
        )
        await context.session.commit()
    except storyboard_service.StoryboardServiceError as exc:
        await context.session.rollback()
        raise TaskHandlerFailure(
            str(exc),
            error_code="storyboard_shot_video_failed",
            result={**exc.result, "shot_public_id": shot_public_id},
            retryable=exc.retryable,
        ) from exc

    media = result.get("media")
    return {
        "media_public_id": str(getattr(media, "public_id", "") or ""),
        "url": str(getattr(media, "url", "") or ""),
        "shot_public_id": str(result.get("shot_public_id") or shot_public_id),
        "episode_public_id": str(result.get("episode_public_id") or ""),
        "shot_index": int(result.get("shot_index") or 0),
        "candidate_index": candidate_index,
        "auto_selected": bool(result.get("auto_selected")),
        "generate_audio": generate_audio,
        "resolution": resolution,
        "ratio": str(result.get("ratio") or ratio),
        "duration": int(result.get("duration") or duration_seconds or 0),
        "model_id": str(result.get("model_id") or model_id),
        "prompt": str(result.get("prompt") or ""),
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
        "media_timing": result.get("media_timing") or {},
    }


ASYNC_TASKS = (
    AsyncTaskDefinition(storyboard_service.STORYBOARD_GENERATE_TASK_TYPE, generate_storyboard_task),
    AsyncTaskDefinition(storyboard_image_service.STORYBOARD_GRID_IMAGE_TASK_TYPE, grid_image_storyboard_task),
    AsyncTaskDefinition(shot_video_service.SHOT_VIDEO_TASK_TYPE, shot_video_storyboard_task),
)