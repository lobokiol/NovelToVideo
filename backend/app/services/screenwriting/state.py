"""剧本创作会话状态：进程内运行态缓存 + 数据库持久化。

每个（项目, 用户）唯一一份会话状态，包含三段工作区、对话消息、可恢复历史
快照与流程状态。运行态经会话级锁串行访问；数据库行是跨进程重启的事实源，
进程内缓存仅用于减少反序列化开销。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from time import time
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.harness.memory.short_term import InProcessShortTermMemory
from app.models.screenwriting import ScreenwritingSession
from app.schemas.screenwriting import (
    ScreenwritingChatTurn,
    ScreenwritingHistoryEntryRead,
    ScreenwritingStateResponse,
    ScreenwritingWorkspaceRead,
)
from app.services import project as project_service
from app.services.screenwriting.errors import ScreenwritingValidationError
from app.utils.time_tools import utc_now


ACTIVE_TABS: tuple[str, ...] = ("skeleton", "strategy", "script")
STAGE_LABELS: dict[str, str] = {
    "skeleton": "故事骨架",
    "strategy": "改编策略",
    "script": "剧本草案",
}
HISTORY_LIMIT = 20
DEFAULT_ASSISTANT_GREETING = (
    "你好，我是剧本创作助理。我会基于本项目已提取的小说事件，"
    "协助你完成故事骨架、改编策略与剧本。可以从右侧选择一个阶段，"
    "或直接告诉我你的创作目标。"
)


@dataclass(frozen=True)
class ScreenwritingWorkspace:
    """会话内三段工作区快照。"""

    skeleton: str = ""
    strategy: str = ""
    script: str = ""


@dataclass(frozen=True)
class ScreenwritingHistoryEntry:
    """可恢复的会话历史快照。"""

    id: str
    title: str
    created_at: datetime
    active_tab: str
    workspace: ScreenwritingWorkspace
    messages: list[ScreenwritingChatTurn] = field(default_factory=list)
    workflow: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenwritingSessionState:
    """单个会话隔离键的运行态。"""

    project_public_id: str
    user_public_id: str
    isolation_key: str
    conversation_id: str
    model_id: str
    active_tab: str = "skeleton"
    workspace: ScreenwritingWorkspace = field(default_factory=ScreenwritingWorkspace)
    messages: list[ScreenwritingChatTurn] = field(default_factory=list)
    history: list[ScreenwritingHistoryEntry] = field(default_factory=list)
    workflow: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utc_now)


class ScreenwritingStateStore:
    """进程内会话状态存储；底层存储与会话锁委托通用 InProcessShortTermMemory。"""

    def __init__(self) -> None:
        self._memory = InProcessShortTermMemory()

    async def session_lock(self, isolation_key: str):
        """返回会话隔离键对应的锁，保证同一会话操作串行。"""
        return await self._memory.session_lock(isolation_key)

    def get_or_create(
        self,
        *,
        project_public_id: str,
        user_public_id: str,
        isolation_key: str,
        model_id: str,
        active_tab: str = "skeleton",
    ) -> ScreenwritingSessionState:
        state = self._memory.load(isolation_key)
        if state is not None:
            state.model_id = model_id or state.model_id
            state.active_tab = normalize_active_tab(active_tab or state.active_tab)
            return state
        state = _new_session_state(
            project_public_id=project_public_id,
            user_public_id=user_public_id,
            isolation_key=isolation_key,
            model_id=model_id,
            active_tab=active_tab,
        )
        self._memory.save(isolation_key, state)
        return state

    def reset(
        self,
        *,
        project_public_id: str,
        user_public_id: str,
        isolation_key: str,
        model_id: str,
        active_tab: str = "skeleton",
    ) -> ScreenwritingSessionState:
        state = _new_session_state(
            project_public_id=project_public_id,
            user_public_id=user_public_id,
            isolation_key=isolation_key,
            model_id=model_id,
            active_tab=active_tab,
        )
        self._memory.save(isolation_key, state)
        return state


_STATE_STORE = ScreenwritingStateStore()


def get_state_store() -> ScreenwritingStateStore:
    """返回模块级会话状态存储单例。"""
    return _STATE_STORE


def build_session_isolation_key(project_public_id: str, user_public_id: str) -> str:
    """会话级隔离键：每个（项目, 用户）唯一。"""
    return f"screenwriting:{project_public_id}:{user_public_id}"


def normalize_active_tab(value: Any) -> str:
    tab = str(value or "skeleton").strip()
    return tab if tab in ACTIVE_TABS else "skeleton"


def stage_label(tab: str) -> str:
    return STAGE_LABELS.get(normalize_active_tab(tab), STAGE_LABELS["skeleton"])


def format_chat_time(now: datetime | None = None) -> str:
    try:
        tz = ZoneInfo(settings.tz)
    except ZoneInfoNotFoundError:
        tz = None
    current = now or datetime.now(tz)
    return current.strftime("%H:%M")


def new_conversation_id() -> str:
    return uuid4().hex


# ---------------------------------------------------------------------------
# 服务接口：状态读取 / 重置 / 历史恢复与删除 / 工作区编辑
# ---------------------------------------------------------------------------


async def get_screenwriting_state(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    *,
    store: ScreenwritingStateStore | None = None,
) -> ScreenwritingStateResponse:
    """读取（必要时初始化并水合）当前会话状态。"""
    current_store = store or _STATE_STORE
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    isolation_key = build_session_isolation_key(project_public_id, current_user_public_id)
    lock = await current_store.session_lock(isolation_key)
    async with lock:
        state = await _load_hydrated_state(
            session,
            current_store,
            project=project,
            project_public_id=project_public_id,
            user_public_id=current_user_public_id,
            isolation_key=isolation_key,
        )
        return to_state_response(state)


async def reset_screenwriting_state(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    *,
    store: ScreenwritingStateStore | None = None,
) -> ScreenwritingStateResponse:
    """重置会话：当前状态先归档进历史，再以全新对话开场。"""
    current_store = store or _STATE_STORE
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    isolation_key = build_session_isolation_key(project_public_id, current_user_public_id)
    lock = await current_store.session_lock(isolation_key)
    async with lock:
        previous = await _load_hydrated_state(
            session,
            current_store,
            project=project,
            project_public_id=project_public_id,
            user_public_id=current_user_public_id,
            isolation_key=isolation_key,
        )
        history = _archive_current_state(previous.history, previous)
        state = current_store.reset(
            project_public_id=project_public_id,
            user_public_id=current_user_public_id,
            isolation_key=isolation_key,
            model_id=str(getattr(project, "text_model", "") or "").strip(),
        )
        state.history = history
        await persist_session_state(session, project_id=int(project.id or 0), state=state)
        return to_state_response(state)


async def restore_screenwriting_history(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    history_id: str,
    *,
    store: ScreenwritingStateStore | None = None,
) -> ScreenwritingStateResponse:
    """恢复指定历史快照；恢复前先把当前状态归档进历史。"""
    current_store = store or _STATE_STORE
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    isolation_key = build_session_isolation_key(project_public_id, current_user_public_id)
    lock = await current_store.session_lock(isolation_key)
    async with lock:
        state = await _load_hydrated_state(
            session,
            current_store,
            project=project,
            project_public_id=project_public_id,
            user_public_id=current_user_public_id,
            isolation_key=isolation_key,
        )
        target_id = str(history_id or "").strip()
        entry = next((item for item in state.history if item.id == target_id), None)
        if entry is None:
            raise ScreenwritingValidationError("未找到指定创作历史")

        state.history = _archive_current_state(state.history, state)
        state.active_tab = normalize_active_tab(entry.active_tab)
        state.workspace = entry.workspace
        state.messages = list(entry.messages)
        state.workflow = dict(entry.workflow)
        state.conversation_id = new_conversation_id()
        state.messages.append(
            ScreenwritingChatTurn(
                role="assistant",
                content=f"已恢复创作历史：{stage_label(state.active_tab)}。",
                time=format_chat_time(),
            )
        )
        await persist_session_state(session, project_id=int(project.id or 0), state=state)
        return to_state_response(state)


async def delete_screenwriting_history(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    history_id: str,
    *,
    store: ScreenwritingStateStore | None = None,
) -> ScreenwritingStateResponse:
    """删除指定历史快照。"""
    current_store = store or _STATE_STORE
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    isolation_key = build_session_isolation_key(project_public_id, current_user_public_id)
    lock = await current_store.session_lock(isolation_key)
    async with lock:
        state = await _load_hydrated_state(
            session,
            current_store,
            project=project,
            project_public_id=project_public_id,
            user_public_id=current_user_public_id,
            isolation_key=isolation_key,
        )
        target_id = str(history_id or "").strip()
        next_history = [entry for entry in state.history if entry.id != target_id]
        if len(next_history) == len(state.history):
            raise ScreenwritingValidationError("未找到指定创作历史")
        state.history = next_history
        await persist_session_state(session, project_id=int(project.id or 0), state=state)
        return to_state_response(state)


async def update_screenwriting_workspace(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    *,
    active_tab: str,
    content: str,
    store: ScreenwritingStateStore | None = None,
) -> ScreenwritingStateResponse:
    """手动编辑保存指定阶段的工作区内容。"""
    current_store = store or _STATE_STORE
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    isolation_key = build_session_isolation_key(project_public_id, current_user_public_id)
    lock = await current_store.session_lock(isolation_key)
    async with lock:
        state = await _load_hydrated_state(
            session,
            current_store,
            project=project,
            project_public_id=project_public_id,
            user_public_id=current_user_public_id,
            isolation_key=isolation_key,
        )
        tab = normalize_active_tab(active_tab)
        state.active_tab = tab
        state.workspace = replace(state.workspace, **{tab: str(content or "").strip()})
        await persist_session_state(session, project_id=int(project.id or 0), state=state)
        return to_state_response(state)


async def set_screenwriting_config_draft(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    *,
    fields: dict[str, Any],
    store: ScreenwritingStateStore | None = None,
) -> ScreenwritingStateResponse:
    """保存结构化创作配置并立即锁定，随会话持久化。"""
    from app.services.screenwriting.project_config import apply_config_settings

    current_store = store or _STATE_STORE
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    isolation_key = build_session_isolation_key(project_public_id, current_user_public_id)
    lock = await current_store.session_lock(isolation_key)
    async with lock:
        state = await _load_hydrated_state(
            session,
            current_store,
            project=project,
            project_public_id=project_public_id,
            user_public_id=current_user_public_id,
            isolation_key=isolation_key,
        )
        apply_config_settings(
            state,
            total_episodes=fields.get("total_episodes"),
            episode_duration=fields.get("episode_duration"),
            source_start=fields.get("source_start"),
            source_end=fields.get("source_end"),
            platform_spec=fields.get("platform_spec"),
            style=fields.get("style"),
            paywall=fields.get("paywall"),
        )
        await persist_session_state(session, project_id=int(project.id or 0), state=state)
        return to_state_response(state)


# ---------------------------------------------------------------------------
# chat 集成接口：在持有会话锁的前提下读取/写回对话消息
# ---------------------------------------------------------------------------


async def acquire_session_lock(
    project_public_id: str,
    user_public_id: str,
    *,
    store: ScreenwritingStateStore | None = None,
):
    """返回会话锁；chat 流式生成期间应持有该锁以串行同一会话。"""
    current_store = store or _STATE_STORE
    isolation_key = build_session_isolation_key(project_public_id, user_public_id)
    return await current_store.session_lock(isolation_key)


async def load_chat_session_state(
    session: AsyncSession,
    project: Any,
    project_public_id: str,
    user_public_id: str,
    *,
    reset: bool = False,
    store: ScreenwritingStateStore | None = None,
) -> ScreenwritingSessionState:
    """加载（并水合）聊天可用的会话状态；reset 时归档当前状态并开启新对话。

    调用方必须已持有会话锁。
    """
    current_store = store or _STATE_STORE
    isolation_key = build_session_isolation_key(project_public_id, user_public_id)
    state = await _load_hydrated_state(
        session,
        current_store,
        project=project,
        project_public_id=project_public_id,
        user_public_id=user_public_id,
        isolation_key=isolation_key,
    )
    if reset:
        history = _archive_current_state(state.history, state)
        state = current_store.reset(
            project_public_id=project_public_id,
            user_public_id=user_public_id,
            isolation_key=isolation_key,
            model_id=str(getattr(project, "text_model", "") or "").strip(),
        )
        state.history = history
    return state


async def commit_chat_turns(
    session: AsyncSession,
    project: Any,
    state: ScreenwritingSessionState,
    *,
    user_content: str,
    assistant_content: str,
    active_tab: str,
) -> ScreenwritingSessionState:
    """把本轮用户输入与助理回复写入会话并持久化。

    调用方必须已持有会话锁。
    """
    state.active_tab = normalize_active_tab(active_tab)
    state.messages.append(
        ScreenwritingChatTurn(role="user", content=user_content, time=format_chat_time())
    )
    state.messages.append(
        ScreenwritingChatTurn(role="assistant", content=assistant_content, time=format_chat_time())
    )
    await persist_session_state(session, project_id=int(getattr(project, "id", 0) or 0), state=state)
    return state


async def commit_stage_output(
    session: AsyncSession,
    project: Any,
    state: ScreenwritingSessionState,
    *,
    stage: str,
    content: str,
    user_content: str,
    assistant_content: str,
) -> ScreenwritingSessionState:
    """把阶段生成产出写入工作区，连同本轮对话一并持久化。

    调用方必须已持有会话锁；活动选项卡切换为产出阶段。
    """
    tab = normalize_active_tab(stage)
    state.workspace = replace(state.workspace, **{tab: str(content or "").strip()})
    return await commit_chat_turns(
        session,
        project,
        state,
        user_content=user_content,
        assistant_content=assistant_content,
        active_tab=tab,
    )


# ---------------------------------------------------------------------------
# 持久化与序列化
# ---------------------------------------------------------------------------


async def get_persisted_session(
    session: AsyncSession,
    isolation_key: str,
) -> ScreenwritingSession | None:
    statement = select(ScreenwritingSession).where(
        ScreenwritingSession.isolation_key == isolation_key,
        ScreenwritingSession.disabled_at.is_(None),
    )
    result = await session.exec(statement)
    return result.first()


async def persist_session_state(
    session: AsyncSession,
    *,
    project_id: int,
    state: ScreenwritingSessionState,
) -> ScreenwritingSession:
    persisted = await get_persisted_session(session, state.isolation_key)
    if persisted is None:
        persisted = ScreenwritingSession(
            project_id=project_id,
            user_public_id=state.user_public_id,
            isolation_key=state.isolation_key,
        )
    persisted.project_id = project_id
    persisted.user_public_id = state.user_public_id
    persisted.conversation_id = state.conversation_id
    persisted.model_id = state.model_id
    persisted.active_tab = state.active_tab
    persisted.skeleton = state.workspace.skeleton
    persisted.strategy = state.workspace.strategy
    persisted.script = state.workspace.script
    persisted.messages = _serialize_chat_turns(state.messages)
    persisted.history = _serialize_history_entries(state.history)
    persisted.workflow = _serialize_workflow(state.workflow)
    persisted.updated_at = utc_now()
    state.updated_at = persisted.updated_at
    session.add(persisted)
    await session.commit()
    return persisted


def hydrate_state_from_persisted(
    state: ScreenwritingSessionState,
    persisted: ScreenwritingSession,
) -> None:
    state.model_id = persisted.model_id or state.model_id
    state.conversation_id = persisted.conversation_id or state.conversation_id
    state.active_tab = normalize_active_tab(persisted.active_tab)
    state.workspace = ScreenwritingWorkspace(
        skeleton=persisted.skeleton or "",
        strategy=persisted.strategy or "",
        script=persisted.script or "",
    )
    messages = _deserialize_chat_turns(persisted.messages)
    if messages:
        state.messages = messages
    state.history = _deserialize_history_entries(persisted.history)
    workflow = _deserialize_workflow(persisted.workflow)
    if workflow:
        state.workflow = workflow
    state.updated_at = persisted.updated_at


async def _load_hydrated_state(
    session: AsyncSession,
    store: ScreenwritingStateStore,
    *,
    project: Any,
    project_public_id: str,
    user_public_id: str,
    isolation_key: str,
) -> ScreenwritingSessionState:
    state = store.get_or_create(
        project_public_id=project_public_id,
        user_public_id=user_public_id,
        isolation_key=isolation_key,
        model_id=str(project.text_model or "").strip(),
    )
    persisted = await get_persisted_session(session, isolation_key)
    if persisted is not None:
        hydrate_state_from_persisted(state, persisted)
    return state


def _new_session_state(
    *,
    project_public_id: str,
    user_public_id: str,
    isolation_key: str,
    model_id: str,
    active_tab: str = "skeleton",
) -> ScreenwritingSessionState:
    return ScreenwritingSessionState(
        project_public_id=project_public_id,
        user_public_id=user_public_id,
        isolation_key=isolation_key,
        conversation_id=new_conversation_id(),
        model_id=model_id,
        active_tab=normalize_active_tab(active_tab),
        messages=[
            ScreenwritingChatTurn(
                role="assistant",
                content=DEFAULT_ASSISTANT_GREETING,
                time=format_chat_time(),
            )
        ],
    )


def _serialize_chat_turns(messages: list[ScreenwritingChatTurn]) -> str:
    return json.dumps(
        [
            {"role": turn.role, "content": turn.content, "time": turn.time}
            for turn in messages
            if turn.role in {"user", "assistant"} and turn.content.strip()
        ],
        ensure_ascii=False,
    )


def _deserialize_chat_turns(raw: str) -> list[ScreenwritingChatTurn]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    messages: list[ScreenwritingChatTurn] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        turn_time = str(item.get("time") or "").strip() or format_chat_time()
        if role in {"user", "assistant"} and content:
            messages.append(ScreenwritingChatTurn(role=role, content=content, time=turn_time))
    return messages


def _serialize_history_entries(history: list[ScreenwritingHistoryEntry]) -> str:
    return json.dumps(
        [
            {
                "id": entry.id,
                "title": entry.title,
                "created_at": entry.created_at.isoformat(),
                "active_tab": entry.active_tab,
                "workspace": {
                    "skeleton": entry.workspace.skeleton,
                    "strategy": entry.workspace.strategy,
                    "script": entry.workspace.script,
                },
                "messages": [
                    {"role": turn.role, "content": turn.content, "time": turn.time}
                    for turn in entry.messages
                    if turn.role in {"user", "assistant"} and turn.content.strip()
                ],
                "workflow": entry.workflow,
            }
            for entry in history
        ],
        ensure_ascii=False,
        default=str,
    )


def _deserialize_history_entries(raw: str) -> list[ScreenwritingHistoryEntry]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    entries: list[ScreenwritingHistoryEntry] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        workspace_payload = item.get("workspace")
        if not isinstance(workspace_payload, dict):
            workspace_payload = {}
        created_at = _parse_history_datetime(item.get("created_at") or item.get("createdAt"))
        entry_id = str(item.get("id") or "").strip() or _new_history_id(created_at)
        active_tab = normalize_active_tab(item.get("active_tab") or item.get("activeTab"))
        workspace = ScreenwritingWorkspace(
            skeleton=str(workspace_payload.get("skeleton") or ""),
            strategy=str(workspace_payload.get("strategy") or ""),
            script=str(workspace_payload.get("script") or ""),
        )
        raw_messages = item.get("messages")
        try:
            messages = _deserialize_chat_turns(
                json.dumps(raw_messages if isinstance(raw_messages, list) else [], ensure_ascii=False)
            )
        except TypeError:
            messages = []
        workflow = item.get("workflow")
        entries.append(
            ScreenwritingHistoryEntry(
                id=entry_id,
                title=str(item.get("title") or "").strip()
                or _history_title(workspace, active_tab),
                created_at=created_at,
                active_tab=active_tab,
                workspace=workspace,
                messages=messages,
                workflow=dict(workflow) if isinstance(workflow, dict) else {},
            )
        )
    return entries


def _serialize_workflow(workflow: dict[str, Any]) -> str:
    return json.dumps(workflow, ensure_ascii=False, default=str)


def _deserialize_workflow(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_history_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if text:
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return utc_now()


# ---------------------------------------------------------------------------
# 历史归档
# ---------------------------------------------------------------------------


def _archive_current_state(
    history: list[ScreenwritingHistoryEntry],
    state: ScreenwritingSessionState,
) -> list[ScreenwritingHistoryEntry]:
    entry = _history_entry_from_state(state)
    entries = [entry] if entry is not None else []
    entries.extend(history)
    return _dedupe_history_entries(entries)


def _history_entry_from_state(state: ScreenwritingSessionState) -> ScreenwritingHistoryEntry | None:
    if not _has_restorable_content(state):
        return None
    created_at = utc_now()
    return ScreenwritingHistoryEntry(
        id=_new_history_id(created_at),
        title=_history_title(state.workspace, state.active_tab),
        created_at=created_at,
        active_tab=normalize_active_tab(state.active_tab),
        workspace=state.workspace,
        messages=list(state.messages),
        workflow=dict(state.workflow),
    )


def _has_restorable_content(state: ScreenwritingSessionState) -> bool:
    workspace = state.workspace
    if workspace.skeleton.strip() or workspace.strategy.strip() or workspace.script.strip():
        return True
    return any(turn.role == "user" and turn.content.strip() for turn in state.messages)


def _dedupe_history_entries(
    entries: list[ScreenwritingHistoryEntry],
    *,
    limit: int = HISTORY_LIMIT,
) -> list[ScreenwritingHistoryEntry]:
    deduped: list[ScreenwritingHistoryEntry] = []
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            continue
        seen.add(entry.id)
        deduped.append(entry)
        if len(deduped) >= limit:
            break
    return deduped


def _new_history_id(created_at: datetime | None = None) -> str:
    current = created_at or utc_now()
    return f"history-{current.strftime('%Y%m%d%H%M%S%f')}-{int(time() * 1000) % 1000:03d}"


def _history_title(workspace: ScreenwritingWorkspace, active_tab: str) -> str:
    tab = normalize_active_tab(active_tab)
    contents = {
        "skeleton": workspace.skeleton,
        "strategy": workspace.strategy,
        "script": workspace.script,
    }
    content = contents.get(tab, "").strip()
    if not content:
        for key in ACTIVE_TABS:
            if contents[key].strip():
                tab = key
                content = contents[key].strip()
                break
    heading = _first_markdown_heading(content)
    if heading:
        return heading[:80]
    return stage_label(tab)


def _first_markdown_heading(content: str) -> str:
    for line in content.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line.strip())
        if match:
            return match.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# 读模型转换
# ---------------------------------------------------------------------------


def to_state_response(state: ScreenwritingSessionState) -> ScreenwritingStateResponse:
    return ScreenwritingStateResponse(
        project_public_id=state.project_public_id,
        isolation_key=state.isolation_key,
        conversation_id=state.conversation_id,
        model_id=state.model_id,
        active_tab=normalize_active_tab(state.active_tab),
        workspace=ScreenwritingWorkspaceRead(
            skeleton=state.workspace.skeleton,
            strategy=state.workspace.strategy,
            script=state.workspace.script,
        ),
        messages=list(state.messages),
        history=[
            ScreenwritingHistoryEntryRead(
                id=entry.id,
                title=entry.title,
                created_at=entry.created_at,
                active_tab=normalize_active_tab(entry.active_tab),
                workspace=ScreenwritingWorkspaceRead(
                    skeleton=entry.workspace.skeleton,
                    strategy=entry.workspace.strategy,
                    script=entry.workspace.script,
                ),
                messages=list(entry.messages),
            )
            for entry in state.history
        ],
        workflow=dict(state.workflow),
        updated_at=state.updated_at,
    )