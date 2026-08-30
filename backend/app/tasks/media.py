from __future__ import annotations

from typing import Any

from app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure
from app.services import media as media_service


async def video_generation_media_task(context: Any) -> dict[str, Any]:
    """通用视频生成子任务处理器：调用媒体服务执行生成并回写媒体行。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    prompt = str(payload.get("prompt") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    first_frame_media_public_id = str(payload.get("first_frame_media_public_id") or "").strip()
    last_frame_media_public_id = str(payload.get("last_frame_media_public_id") or "").strip()
    reference_media_public_ids = _payload_str_list(payload.get("reference_media_public_ids"))
    scope_type = str(payload.get("scope_type") or "").strip()
    scope_public_id = str(payload.get("scope_public_id") or "").strip()
    if not project_public_id or not current_user_public_id or not model_id or not prompt.strip():
        raise ValueError("视频生成任务参数不完整")

    try:
        result = await media_service.generate_video_media(
            context.session,
            project_public_id,
            current_user_public_id,
            model_id=model_id,
            prompt=prompt,
            params=params,
            first_frame_media_public_id=first_frame_media_public_id,
            last_frame_media_public_id=last_frame_media_public_id,
            reference_media_public_ids=reference_media_public_ids,
            scope_type=scope_type,
            scope_public_id=scope_public_id,
            task_job_public_id=context.message.job_public_id,
            task_item_public_id=context.message.item_public_id,
        )
        await context.session.commit()
    except media_service.MediaServiceError as exc:
        await context.session.rollback()
        # 与资产生图链路同语义：事务回滚不留半行媒体，失败详情由任务子项结果承载。
        failure_result = {**exc.result, "scope_type": scope_type, "scope_public_id": scope_public_id}
        raise TaskHandlerFailure(
            str(exc),
            error_code="media_video_generation_failed",
            result=failure_result,
            retryable=exc.retryable,
        ) from exc

    media = result["media"]
    return {
        "media_public_id": media.public_id,
        "url": media.url,
        "model_id": media.model_id or model_id,
        "prompt": str(result.get("prompt") or ""),
        "scope_type": scope_type,
        "scope_public_id": scope_public_id,
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
        "media_timing": result.get("media_timing") or {},
    }


def _payload_str_list(value: Any) -> list[str]:
    """把任务 payload 中的列表值清理为字符串列表。"""

    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


ASYNC_TASKS = (
    AsyncTaskDefinition(media_service.MEDIA_VIDEO_GENERATION_TASK_TYPE, video_generation_media_task),
)
