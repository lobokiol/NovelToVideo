from __future__ import annotations

"""在线剪辑台工程服务：工程获取/保存与时间线 JSON 约束校验。"""

import json
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.editor import EditorProject
from app.services import project as project_service
from app.utils.time_tools import utc_now


# 时间线 JSON 最大字节数：限制异常前端把巨型 payload 灌进文本列。
_TIMELINE_MAX_BYTES = 2 * 1024 * 1024


class EditorServiceError(Exception):
    """剪辑台服务业务错误。"""


async def get_or_create_editor_project(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
) -> EditorProject:
    """取项目的剪辑工程；不存在则创建一份空工程（画幅跟随项目设置）。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    existing = (
        await session.exec(
            select(EditorProject).where(
                EditorProject.project_id == int(project.id),
                EditorProject.disabled_at.is_(None),
            )
        )
    ).first()
    if existing is not None:
        return existing
    editor_project = EditorProject(
        project_id=int(project.id),
        user_public_id=user_public_id,
        ratio=str(project.video_ratio or "").strip(),
    )
    session.add(editor_project)
    await session.flush()
    return editor_project


def _validate_timeline(timeline: str) -> str:
    """校验时间线为合法 JSON 对象并限制尺寸，返回规整后的紧凑 JSON。"""

    text = (timeline or "").strip() or "{}"
    if len(text.encode("utf-8")) > _TIMELINE_MAX_BYTES:
        raise EditorServiceError("时间线工程过大，请精简后再保存")
    try:
        value = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise EditorServiceError("时间线工程不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise EditorServiceError("时间线工程必须是 JSON 对象")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


async def save_editor_project(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    timeline: str,
    duration_ms: int = 0,
    ratio: str = "",
    name: str = "",
) -> EditorProject:
    """保存剪辑工程时间线与元信息。"""

    editor_project = await get_or_create_editor_project(session, project_public_id, user_public_id)
    editor_project.timeline = _validate_timeline(timeline)
    editor_project.duration_ms = max(0, int(duration_ms or 0))
    if ratio.strip():
        editor_project.ratio = ratio.strip()
    if name.strip():
        editor_project.name = name.strip()[:120]
    editor_project.user_public_id = user_public_id
    editor_project.updated_at = utc_now()
    session.add(editor_project)
    await session.flush()
    return editor_project


def timeline_payload(editor_project: EditorProject) -> dict[str, Any]:
    """把工程行的时间线 JSON 解析为对象（损坏时回退空对象）。"""

    try:
        value = json.loads(editor_project.timeline or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}