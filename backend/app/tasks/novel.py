from __future__ import annotations

from typing import Any

from app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure
from app.services import novel as novel_service


async def clean_chapter_event_task(context: Any) -> dict[str, Any]:
    """批量章节事件清洗子任务处理器。"""
    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    chapter_id = _payload_int(payload.get("chapter_id"))
    if not project_public_id or not current_user_public_id or chapter_id <= 0:
        raise ValueError("批量清洗章节事件任务参数不完整")

    result = await novel_service.clean_chapter_for_task(
        context.session,
        project_public_id,
        chapter_id,
        current_user_public_id,
        model_id=model_id,
    )
    if result.get("event_state") == -1:
        raise TaskHandlerFailure(
            str(result.get("error_reason") or "章节事件清洗失败"),
            error_code="novel_chapter_clean_failed",
            result=result,
        )
    return result


def _payload_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


ASYNC_TASKS = (
    AsyncTaskDefinition(novel_service.NOVEL_CHAPTER_CLEAN_TASK_TYPE, clean_chapter_event_task),
)
