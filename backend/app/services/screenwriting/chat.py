from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from time import perf_counter, time
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.harness import HarnessAgent, ScriptAgentEvent, ScriptAgentInput
from app.core.harness.runtime.crewai import CrewAIStageRuntime
from app.core.harness.runtime.deepagents import DeepAgentsRuntime
from app.core.harness.tools.adapter import ModelGatewayAdapter
from app.models.novel import NovelChapter
from app.schemas.screenwriting import (
    ScreenwritingActiveTab,
    ScreenwritingAssessPayload,
    ScreenwritingChatPayload,
    ScreenwritingChatResponse,
    ScreenwritingRagWarmupResponse,
    ScreenwritingStreamEvent,
)
from app.services import project as project_service
from app.services.screenwriting.agent_tools import build_screenwriting_agent_tools
from app.services.screenwriting.assessment import (
    StageAssessment,
    load_cached_assessment,
    save_assessment_cache,
    stage_content_fingerprint,
    stream_stage_assessment,
)
from app.services.screenwriting.errors import (
    ScreenwritingServiceError,
    ScreenwritingValidationError,
)
from app.services.screenwriting.project_config import (
    ensure_project_config,
    format_project_config,
    message_contains_project_config_hint,
    resolve_project_config_dialog,
)
from app.services.screenwriting.prompts import build_guide_system_prompt
from app.services.screenwriting.query_intent import normalize_lookup_text, parse_screenwriting_query_intent
from app.services.screenwriting.rag_index import ScreenwritingRagContext
from app.services.screenwriting.rag_runtime import (
    ScreenwritingRagPreparation,
    build_system_prompt_with_rag,
    empty_rag_context,
    prepare_rag_context,
    rag_runtime_payload,
    schedule_rag_index_warmup,
)
from app.services.screenwriting.quality import ensure_stage_output_quality
from app.services.screenwriting.stage_generation import (
    StageGenerationPlan,
    build_stage_repair_message,
    build_stage_system_prompt,
    clean_stage_output,
    clear_pending_script_repair,
    configured_episode_duration_minutes,
    mark_stage_completed,
    merge_script_episode_blocks,
    resolve_script_repair_dialog,
    resolve_stage_generation,
    save_pending_script_repair,
    script_block_matches_episode,
    script_episode_message,
    script_repair_confirmation_prompt,
    stage_completion_reply,
)
from app.services.screenwriting.constants import (
    STAGE_SELF_REPAIR_MAX_ATTEMPTS,
    WORKFLOW_BASIC_INFO_CONFIRMED,
)
from app.services.screenwriting.state import (
    ScreenwritingSessionState,
    acquire_session_lock,
    commit_chat_turns,
    commit_stage_output,
    load_chat_session_state,
    persist_session_state,
    stage_label,
)


MAX_HISTORY_MESSAGES = 40

__all__ = [
    "ScreenwritingServiceError",
    "ScreenwritingValidationError",
    "chat_screenwriting",
    "build_screenwriting_chat_stream",
    "warmup_screenwriting_rag_index",
]


ScreenwritingAgentFactory = Callable[..., HarnessAgent]


@dataclass
class ScreenwritingServerTimings:
    """单次请求在服务端的阶段耗时。"""

    started_at: float
    server_started_at_ms: int
    client_request_started_at_ms: int | None = None
    stages: list[dict[str, int | str]] = field(default_factory=list)

    @classmethod
    def start(cls, client_request_started_at_ms: int | None = None) -> "ScreenwritingServerTimings":
        return cls(
            started_at=perf_counter(),
            server_started_at_ms=int(time() * 1000),
            client_request_started_at_ms=client_request_started_at_ms,
        )

    def mark(self, name: str, started_at: float, ended_at: float | None = None) -> None:
        ended_at = ended_at if ended_at is not None else perf_counter()
        self.stages.append(
            {
                "name": name,
                "durationMs": _duration_ms(started_at, ended_at),
                "startedAtMs": _duration_ms(self.started_at, started_at),
                "endedAtMs": _duration_ms(self.started_at, ended_at),
            }
        )

    def payload(self) -> dict[str, Any]:
        client_to_server_ms = None
        if self.client_request_started_at_ms is not None:
            client_to_server_ms = max(0, self.server_started_at_ms - self.client_request_started_at_ms)
        return {
            "totalMs": _duration_ms(self.started_at, perf_counter()),
            "clientToServerMs": client_to_server_ms,
            "stages": [dict(stage) for stage in self.stages],
        }


@dataclass(frozen=True)
class ScreenwritingChatContext:
    """单次剧本创作对话上下文。"""

    project_public_id: str
    user_public_id: str
    conversation_id: str
    isolation_key: str
    model_id: str
    active_tab: ScreenwritingActiveTab
    messages: list[dict[str, str]]
    payload: ScreenwritingChatPayload
    rag_context: ScreenwritingRagContext
    rag_document_count: int
    thinking_started_at: float
    server_timings: ScreenwritingServerTimings
    agent: HarnessAgent
    db_session: AsyncSession
    project: Any
    session_state: ScreenwritingSessionState
    stage_plan: StageGenerationPlan | None = None
    chapter_events: list[dict[str, Any]] = field(default_factory=list)
    stage_agent_builder: Callable[..., HarnessAgent] | None = None

    def build_stage_agent(self, stage_message: str, *, repair: bool = False) -> HarnessAgent:
        """为阶段生成/修复轮构建子 Agent（系统提示词随消息重建）。

        repair=True 表示质量校验失败后的修复轮：CrewAI 团队路径换用单员
        修复团队，不重跑完整团队链路。
        """
        assert self.stage_agent_builder is not None
        return self.stage_agent_builder(stage_message, repair=repair)

    def stage_agent_input(self, agent: HarnessAgent, stage_message: str) -> ScriptAgentInput:
        """阶段子 Agent 的单次调用输入（不携带对话历史）。"""
        del agent
        rag_runtime = rag_runtime_payload(self.rag_context, document_count=self.rag_document_count)
        return ScriptAgentInput(
            project_public_id=self.project_public_id,
            user_public_id=self.user_public_id,
            isolation_key=self.isolation_key,
            messages=[{"role": "user", "content": stage_message}],
            model_id=self.model_id,
            metadata={
                "conversation_id": self.conversation_id,
                "active_tab": self.active_tab,
                "rag": rag_runtime,
            },
        )

    def agent_input(self) -> ScriptAgentInput:
        """转换为 Harness Agent 单次调用输入。"""
        rag_runtime = rag_runtime_payload(self.rag_context, document_count=self.rag_document_count)
        return ScriptAgentInput(
            project_public_id=self.project_public_id,
            user_public_id=self.user_public_id,
            isolation_key=self.isolation_key,
            messages=self.messages,
            model_id=self.model_id,
            metadata={
                "conversation_id": self.conversation_id,
                "active_tab": self.active_tab,
                "rag": rag_runtime,
            },
        )


@dataclass(frozen=True)
class _PreparedChatTurn:
    """单轮对话准备结果：配置链路直答或完整 Agent 上下文（二选一）。"""

    project: Any
    state: ScreenwritingSessionState
    model_id: str
    config_reply: str = ""
    context: ScreenwritingChatContext | None = None


async def chat_screenwriting(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    agent_factory: ScreenwritingAgentFactory | None = None,
) -> ScreenwritingChatResponse:
    """执行一次剧本创作多轮对话，并返回聚合响应。"""
    context: ScreenwritingChatContext | None = None
    status = "error"
    lock = await acquire_session_lock(project_public_id, current_user_public_id)
    async with lock:
        try:
            server_timings = ScreenwritingServerTimings.start(payload.client_request_started_at_ms)
            turn = await _prepare_chat_turn(
                session,
                project_public_id,
                current_user_public_id,
                payload,
                server_timings=server_timings,
                agent_factory=agent_factory,
            )
            if turn.config_reply:
                state = await commit_chat_turns(
                    session,
                    turn.project,
                    turn.state,
                    user_content=payload.message,
                    assistant_content=turn.config_reply,
                    active_tab=payload.active_tab,
                )
                status = "completed"
                return ScreenwritingChatResponse(
                    conversation_id=turn.state.conversation_id,
                    isolation_key=_build_isolation_key(
                        project_public_id, current_user_public_id, turn.state.conversation_id
                    ),
                    model_id=turn.model_id,
                    active_tab=payload.active_tab,
                    content=turn.config_reply,
                    messages=list(state.messages),
                    runtime={
                        "agent": "project_config",
                        "conversation": "multi_turn",
                        "directAnswer": True,
                        "thinkingElapsedMs": _elapsed_ms_since(server_timings.started_at),
                        "serverTimings": server_timings.payload(),
                    },
                )

            context = turn.context
            assert context is not None
            if context.stage_plan is not None:
                response = await _run_stage_generation(context)
                status = "completed"
                return response
            direct_answer_started_at = perf_counter()
            direct_answer = _metadata_direct_answer(context)
            if direct_answer:
                context.server_timings.mark("directAnswer", direct_answer_started_at)
                state = await commit_chat_turns(
                    session,
                    context.project,
                    context.session_state,
                    user_content=payload.message,
                    assistant_content=direct_answer,
                    active_tab=payload.active_tab,
                )
                response = ScreenwritingChatResponse(
                    conversation_id=context.conversation_id,
                    isolation_key=context.isolation_key,
                    model_id=context.model_id,
                    active_tab=context.active_tab,
                    content=direct_answer,
                    messages=list(state.messages),
                    runtime={
                        "agent": "metadata_direct",
                        "conversation": "multi_turn",
                        "rag": rag_runtime_payload(context.rag_context, document_count=context.rag_document_count),
                        "directAnswer": True,
                        "thinkingElapsedMs": _thinking_elapsed_ms(context),
                        "serverTimings": context.server_timings.payload(),
                    },
                )
                status = "completed"
                return response

            agent_run_started_at = perf_counter()
            try:
                result = await context.agent.run_chat(context.agent_input())
            finally:
                context.server_timings.mark("agentRun", agent_run_started_at)
            content = result.content.strip()
            if not content:
                status = "empty_response"
                raise ScreenwritingServiceError("模型未返回可用对话内容")

            state = await commit_chat_turns(
                session,
                context.project,
                context.session_state,
                user_content=payload.message,
                assistant_content=content,
                active_tab=payload.active_tab,
            )
            response = ScreenwritingChatResponse(
                conversation_id=context.conversation_id,
                isolation_key=context.isolation_key,
                model_id=context.model_id,
                active_tab=context.active_tab,
                content=content,
                messages=list(state.messages),
                runtime={
                    "agent": "harness",
                    "conversation": "multi_turn",
                    "rag": rag_runtime_payload(context.rag_context, document_count=context.rag_document_count),
                    "thinkingElapsedMs": _thinking_elapsed_ms(context),
                    "serverTimings": context.server_timings.payload(),
                },
            )
            status = "completed"
            return response
        finally:
            if context is not None:
                _print_server_timing_log(context, operation="chat", status=status)


async def build_screenwriting_chat_stream(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    agent_factory: ScreenwritingAgentFactory | None = None,
) -> AsyncIterator[ScreenwritingStreamEvent]:
    """构建剧本创作多轮对话流式事件。

    本函数是异步生成器：首个 start(preparing) 事件在项目加载与 RAG 准备
    开始前即发出，保证客户端立即获得服务端反馈；准备阶段的任何异常都
    转换为 error 事件而不是 HTTP 异常。整个生成期间持有会话锁，使同一
    会话的流式对话串行执行。
    """
    server_timings = ScreenwritingServerTimings.start(payload.client_request_started_at_ms)
    yield ScreenwritingStreamEvent(
        type="start",
        content="",
        conversation_id="",
        isolation_key="",
        model_id="",
        active_tab=payload.active_tab,
        data={
            "phase": "preparing",
            "thinkingElapsedMs": _elapsed_ms_since(server_timings.started_at),
            "serverTimings": server_timings.payload(),
        },
    )
    lock = await acquire_session_lock(project_public_id, current_user_public_id)
    async with lock:
        try:
            turn = await _prepare_chat_turn(
                session,
                project_public_id,
                current_user_public_id,
                payload,
                server_timings=server_timings,
                agent_factory=agent_factory,
            )
            if turn.config_reply:
                await commit_chat_turns(
                    session,
                    turn.project,
                    turn.state,
                    user_content=payload.message,
                    assistant_content=turn.config_reply,
                    active_tab=payload.active_tab,
                )
        except Exception as exc:
            yield ScreenwritingStreamEvent(
                type="error",
                content="",
                conversation_id="",
                isolation_key="",
                model_id="",
                active_tab=payload.active_tab,
                data={
                    "detail": _exception_detail(exc),
                    "errorType": exc.__class__.__name__,
                    "thinkingElapsedMs": _elapsed_ms_since(server_timings.started_at),
                    "serverTimings": server_timings.payload(),
                },
            )
            return
        if turn.config_reply:
            yield ScreenwritingStreamEvent(
                type="done",
                content=turn.config_reply,
                conversation_id=turn.state.conversation_id,
                isolation_key=_build_isolation_key(
                    project_public_id, current_user_public_id, turn.state.conversation_id
                ),
                model_id=turn.model_id,
                active_tab=payload.active_tab,
                data={
                    "directAnswer": True,
                    "agent": "project_config",
                    "assistantMessage": turn.config_reply,
                    "messages": _state_message_payload(turn.state),
                    "thinkingElapsedMs": _elapsed_ms_since(server_timings.started_at),
                    "serverTimings": server_timings.payload(),
                },
            )
            return
        assert turn.context is not None
        if turn.context.stage_plan is not None:
            async for event in _stream_stage_generation(turn.context):
                yield event
            return
        async for event in _stream_prepared_chat(turn.context):
            yield event


async def warmup_screenwriting_rag_index(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
) -> ScreenwritingRagWarmupResponse:
    """校验项目访问权限后异步调度剧本创作 RAG 向量索引预热。"""
    await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    schedule = schedule_rag_index_warmup(project_public_id, current_user_public_id)
    return ScreenwritingRagWarmupResponse(
        status=schedule.status,
        rag_isolation_key=schedule.rag_isolation_key,
    )


async def build_screenwriting_assessment_stream(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingAssessPayload,
) -> AsyncIterator[ScreenwritingStreamEvent]:
    """构建阶段质量评估流式事件。

    评估为只读操作：不写会话状态、不持会话锁，不阻塞聊天与工作区功能；
    准备阶段异常转换为 error 事件。
    """
    stage = payload.active_tab
    conversation_id = ""
    model_id = ""
    try:
        project, model_id = await _load_chat_project(
            session,
            project_public_id,
            current_user_public_id,
            ScreenwritingServerTimings.start(None),
        )
        state = await load_chat_session_state(
            session,
            project,
            project_public_id,
            current_user_public_id,
        )
        conversation_id = state.conversation_id
        chapter_events = await _load_chapter_events(session, project)
    except Exception as exc:
        yield ScreenwritingStreamEvent(
            type="error",
            content="",
            conversation_id=conversation_id,
            isolation_key="",
            model_id=model_id,
            active_tab=stage,
            data={"detail": _exception_detail(exc), "errorType": exc.__class__.__name__},
        )
        return

    yield ScreenwritingStreamEvent(
        type="start",
        content="",
        conversation_id=conversation_id,
        isolation_key="",
        model_id=model_id,
        active_tab=stage,
        data={"phase": "assessing", "stage": stage},
    )

    cached = load_cached_assessment(state, stage)
    if cached is not None:
        # 内容未变化：直接复用缓存报告，零模型调用。
        yield ScreenwritingStreamEvent(
            type="done",
            content=cached.report,
            conversation_id=conversation_id,
            isolation_key="",
            model_id=model_id,
            active_tab=stage,
            data={
                "stage": stage,
                "scores": dict(cached.scores),
                "report": cached.report,
                "improvementPrompt": cached.improvement_prompt,
                "cached": True,
            },
        )
        return

    # 指纹取评估开始时刻的内容：评估期间内容被修改时，缓存自然失效。
    assessed_fingerprint = stage_content_fingerprint(str(getattr(state.workspace, stage, "") or ""))
    async for event in stream_stage_assessment(
        state,
        stage,
        chapter_events,
        model_id=model_id,
    ):
        if str(event.get("type") or "") == "done":
            data = dict(event.get("data") or {})
            data["cached"] = False
            assessment = StageAssessment(
                stage=stage,
                report=str(data.get("report") or ""),
                scores=dict(data.get("scores") or {}),
                improvement_prompt=str(data.get("improvementPrompt") or ""),
            )
            save_assessment_cache(state, assessment, fingerprint=assessed_fingerprint)
            # 写缓存需短暂持锁持久化；评估过程本身不持锁，不阻塞其他功能。
            lock = await acquire_session_lock(project_public_id, current_user_public_id)
            async with lock:
                await persist_session_state(
                    session,
                    project_id=int(getattr(project, "id", 0) or 0),
                    state=state,
                )
            yield ScreenwritingStreamEvent(
                type="done",
                content=str(event.get("content") or ""),
                conversation_id=conversation_id,
                isolation_key="",
                model_id=model_id,
                active_tab=stage,
                data=data,
            )
            continue
        yield ScreenwritingStreamEvent(
            type=str(event.get("type") or "message.delta"),
            content=str(event.get("content") or ""),
            conversation_id=conversation_id,
            isolation_key="",
            model_id=model_id,
            active_tab=stage,
            data=dict(event.get("data") or ({"detail": event.get("detail")} if event.get("detail") else {})),
        )


async def _stream_prepared_chat(context: ScreenwritingChatContext) -> AsyncIterator[ScreenwritingStreamEvent]:
    status = "cancelled"
    content = ""
    model_stream_started_at: float | None = None
    model_stream_marked = False

    def mark_model_stream() -> None:
        nonlocal model_stream_marked
        if model_stream_marked or model_stream_started_at is None:
            return
        context.server_timings.mark("modelStream", model_stream_started_at)
        model_stream_marked = True

    try:
        direct_answer_started_at = perf_counter()
        direct_answer = _metadata_direct_answer(context)
        if direct_answer:
            context.server_timings.mark("directAnswer", direct_answer_started_at)
            status = "completed"
            state = await commit_chat_turns(
                context.db_session,
                context.project,
                context.session_state,
                user_content=context.payload.message,
                assistant_content=direct_answer,
                active_tab=context.payload.active_tab,
            )
            yield _stream_event(
                context,
                "done",
                content=direct_answer,
                data={
                    "directAnswer": True,
                    "assistantMessage": direct_answer,
                    "messages": _state_message_payload(state),
                },
            )
            return

        model_stream_started_at = perf_counter()
        try:
            async for event in context.agent.stream_chat(context.agent_input()):
                if event.type == "message.delta":
                    delta = _normalize_agent_delta(content, event.content)
                    if not delta:
                        continue
                    content += delta
                    yield _stream_event(context, event.type, content=delta, data=event.data)
                    continue
                if event.type == "done":
                    final_content = _agent_final_content(event)
                    if final_content:
                        content += _normalize_agent_delta(content, final_content)
                    break
                if event.type == "error":
                    mark_model_stream()
                    status = "error"
                    yield _agent_error_event(context, event)
                    return
                yield _event_from_agent_event(context, event)
        except Exception as exc:
            mark_model_stream()
            status = "error"
            yield _stream_event(
                context,
                "error",
                data={"detail": _exception_detail(exc), "errorType": exc.__class__.__name__},
            )
            return

        mark_model_stream()
        final_content = content.strip()
        if not final_content:
            status = "empty_response"
            yield _stream_event(
                context,
                "error",
                data={"detail": "模型未返回可用对话内容", "errorType": "ScreenwritingServiceError"},
            )
            return

        status = "completed"
        state = await commit_chat_turns(
            context.db_session,
            context.project,
            context.session_state,
            user_content=context.payload.message,
            assistant_content=final_content,
            active_tab=context.payload.active_tab,
        )
        yield _stream_event(
            context,
            "done",
            content=final_content,
            data={
                "assistantMessage": final_content,
                "messages": _state_message_payload(state),
            },
        )
    finally:
        mark_model_stream()
        _print_server_timing_log(context, operation="chat.stream", status=status)


async def _run_stage_generation(context: ScreenwritingChatContext) -> ScreenwritingChatResponse:
    """聚合路径执行阶段生成：质量校验 + 自修复循环；script 阶段逐集生成。"""
    plan = context.stage_plan
    assert plan is not None
    agent_run_started_at = perf_counter()
    pending_prompt = ""
    if plan.stage == "script":
        stage_content, quality_warnings, pending_prompt = await _run_script_episodes_aggregate(context, plan)
    else:
        stage_content, quality_warnings = await _run_single_stage_aggregate(context, plan)
    context.server_timings.mark("agentRun", agent_run_started_at)

    state = context.session_state
    if pending_prompt:
        # 单集修复预算耗尽：状态与回滚稿已落库，把确认请求作为本轮回复返回。
        return ScreenwritingChatResponse(
            conversation_id=context.conversation_id,
            isolation_key=context.isolation_key,
            model_id=context.model_id,
            active_tab="script",
            content=pending_prompt,
            messages=list(state.messages),
            runtime={
                "agent": "stage_generation",
                "stage": plan.stage,
                "requestedStage": plan.requested_stage,
                "pendingScriptRepair": True,
                "conversation": "multi_turn",
                "rag": rag_runtime_payload(context.rag_context, document_count=context.rag_document_count),
                "workspace": _workspace_payload(state),
                "thinkingElapsedMs": _thinking_elapsed_ms(context),
                "serverTimings": context.server_timings.payload(),
            },
        )

    assistant_content = f"{plan.dispatch_reply}\n\n{stage_completion_reply(plan)}"
    mark_stage_completed(context.session_state, plan.stage)
    state = await commit_stage_output(
        context.db_session,
        context.project,
        context.session_state,
        stage=plan.stage,
        content=stage_content,
        user_content=context.payload.message,
        assistant_content=assistant_content,
    )
    return ScreenwritingChatResponse(
        conversation_id=context.conversation_id,
        isolation_key=context.isolation_key,
        model_id=context.model_id,
        active_tab=plan.stage,  # type: ignore[arg-type]
        content=assistant_content,
        messages=list(state.messages),
        runtime={
            "agent": "stage_generation",
            "stage": plan.stage,
            "requestedStage": plan.requested_stage,
            "blockedStage": plan.blocked_stage,
            "qualityWarnings": quality_warnings,
            "conversation": "multi_turn",
            "rag": rag_runtime_payload(context.rag_context, document_count=context.rag_document_count),
            "workspace": _workspace_payload(state),
            "thinkingElapsedMs": _thinking_elapsed_ms(context),
            "serverTimings": context.server_timings.payload(),
        },
    )


async def _run_single_stage_aggregate(
    context: ScreenwritingChatContext,
    plan: StageGenerationPlan,
) -> tuple[str, list[str]]:
    """聚合路径生成 skeleton/strategy：质量失败时自修复重试。"""
    stage_message = plan.stage_message
    last_error: ScreenwritingServiceError | None = None
    for attempt in range(STAGE_SELF_REPAIR_MAX_ATTEMPTS + 1):
        agent = context.build_stage_agent(stage_message, repair=attempt > 0)
        try:
            result = await agent.run_chat(context.stage_agent_input(agent, stage_message))
        except Exception as exc:
            raise ScreenwritingServiceError(f"阶段生成失败：{exc}") from exc
        content = clean_stage_output(_agent_result_text(result))
        try:
            warnings = ensure_stage_output_quality(
                plan.stage,
                content,
                chapter_events=context.chapter_events,
            )
            return content, warnings
        except ScreenwritingServiceError as exc:
            last_error = exc
            if attempt >= STAGE_SELF_REPAIR_MAX_ATTEMPTS:
                raise
            stage_message = build_stage_repair_message(
                plan.stage,
                stage_message=plan.stage_message,
                failure_reason=str(exc),
                failed_output=content,
            )
    raise last_error or ScreenwritingServiceError("阶段生成失败")


async def _run_script_episodes_aggregate(
    context: ScreenwritingChatContext,
    plan: StageGenerationPlan,
) -> tuple[str, list[str], str]:
    """聚合路径逐集生成剧本；单集修复预算耗尽时落库 pending 并返回确认文案。"""
    state = context.session_state
    duration_minutes = configured_episode_duration_minutes(state)
    generated_script = state.workspace.script
    quality_warnings: list[str] = []
    episode_numbers = plan.episode_numbers or (1,)

    for index, episode_no in enumerate(episode_numbers):
        base_message = script_episode_message(
            plan.stage_message, episode_no, duration_minutes=duration_minutes
        )
        if plan.repair and index == 0:
            base_message = build_stage_repair_message(
                "script",
                stage_message=base_message,
                failure_reason=plan.repair_failure,
                failed_output=plan.repair_failed_output,
            )
        current_message = base_message
        last_failure = ""
        last_output = ""
        for attempt in range(STAGE_SELF_REPAIR_MAX_ATTEMPTS + 1):
            agent = context.build_stage_agent(
                current_message,
                repair=plan.repair or attempt > 0,
            )
            try:
                result = await agent.run_chat(context.stage_agent_input(agent, current_message))
            except Exception as exc:
                raise ScreenwritingServiceError(f"剧本生成失败：{exc}") from exc
            content = clean_stage_output(_agent_result_text(result))
            last_output = content
            try:
                _ensure_script_episode_output(content, episode_no, context, duration_minutes, quality_warnings)
                generated_script = merge_script_episode_blocks(
                    generated_script, content, target_episode_numbers=(episode_no,)
                )
                last_failure = ""
                break
            except ScreenwritingServiceError as exc:
                last_failure = str(exc)
                if attempt >= STAGE_SELF_REPAIR_MAX_ATTEMPTS:
                    break
                current_message = build_stage_repair_message(
                    "script",
                    stage_message=base_message,
                    failure_reason=last_failure,
                    failed_output=content,
                )
        if last_failure:
            rollback_script = _script_rollback_content(generated_script, last_output, episode_no)
            save_pending_script_repair(
                state,
                failure_reason=last_failure,
                failed_output=last_output,
                stage_message=plan.stage_message,
                episode_no=episode_no,
                remaining_episode_numbers=tuple(episode_numbers[index + 1 :]),
            )
            confirmation_prompt = script_repair_confirmation_prompt(last_failure, episode_no)
            await commit_stage_output(
                context.db_session,
                context.project,
                state,
                stage="script",
                content=rollback_script,
                user_content=context.payload.message,
                assistant_content=confirmation_prompt,
            )
            return rollback_script, quality_warnings, confirmation_prompt

    if plan.repair:
        clear_pending_script_repair(state)
    return generated_script, quality_warnings, ""


def _ensure_script_episode_output(
    content: str,
    episode_no: int,
    context: ScreenwritingChatContext,
    duration_minutes: int,
    quality_warnings: list[str],
) -> None:
    """单集产出校验：集号匹配 + 剧本质量规则；软警告累积进 quality_warnings。"""
    if not script_block_matches_episode(content, episode_no):
        raise ScreenwritingServiceError(
            f"剧本输出未以 EP{episode_no:02d} 标题开头，疑似串集或缺少分集标题"
        )
    quality_warnings.extend(
        ensure_stage_output_quality(
            "script",
            content,
            chapter_events=context.chapter_events,
            target_duration_minutes=duration_minutes,
        )
    )


def _script_rollback_content(generated_script: str, failed_output: str, episode_no: int) -> str:
    """回滚剧本 = 已通过校验的集 + 本集失败尝试稿（可解析时并入，便于人工查看）。"""
    if failed_output and script_block_matches_episode(failed_output, episode_no):
        return merge_script_episode_blocks(
            generated_script, failed_output, target_episode_numbers=(episode_no,)
        )
    return generated_script


async def _stream_stage_generation(context: ScreenwritingChatContext) -> AsyncIterator[ScreenwritingStreamEvent]:
    """流式路径执行阶段生成。

    对话区只承载调度与收尾文案；阶段正文经 workspace.delta（targetTab 定向、
    携带累计全文）写入右侧工作区；质量校验失败触发自修复（stage.repair 事件），
    script 阶段逐集生成（script.episode.start 事件），单集预算耗尽转入
    "回滚 + 人工确认补全"闭环。
    """
    plan = context.stage_plan
    assert plan is not None
    state = context.session_state
    status = "cancelled"
    model_stream_started_at: float | None = None
    model_stream_marked = False

    def mark_model_stream() -> None:
        nonlocal model_stream_marked
        if model_stream_marked or model_stream_started_at is None:
            return
        context.server_timings.mark("modelStream", model_stream_started_at)
        model_stream_marked = True

    try:
        yield _stream_event(
            context,
            "agent.action",
            data={
                "phase": "stage.repair.confirmed" if plan.repair else "request.received",
                "message": "用户已确认补全剧本单集" if plan.repair else "已接收创作需求",
                "detail": plan.repair_failure if plan.repair else context.payload.message,
                "targetTab": plan.stage,
            },
        )
        yield _stream_event(context, "message.delta", content=plan.dispatch_reply)
        yield _stream_event(
            context,
            "agent.action",
            data={
                "phase": "subagent.dispatch",
                "message": f"调用{stage_label(plan.stage)}助理",
                "detail": f"{stage_label(plan.stage)}助理会把结果实时写入右侧工作区。",
                "targetTab": plan.stage,
                "agentName": f"screenwriting-{plan.stage}-agent",
            },
        )

        model_stream_started_at = perf_counter()
        duration_minutes = configured_episode_duration_minutes(state)
        quality_warnings: list[str] = []

        if plan.stage == "script":
            generated_script = state.workspace.script
            episode_numbers = plan.episode_numbers or (1,)
            for index, episode_no in enumerate(episode_numbers):
                yield _stream_event(
                    context,
                    "agent.action",
                    data={
                        "phase": "script.episode.start",
                        "message": f"开始生成 EP{episode_no:02d}",
                        "detail": f"EP{episode_no:02d}",
                        "targetTab": "script",
                        "agentName": "screenwriting-script-agent",
                    },
                )
                base_message = script_episode_message(
                    plan.stage_message, episode_no, duration_minutes=duration_minutes
                )
                if plan.repair and index == 0:
                    base_message = build_stage_repair_message(
                        "script",
                        stage_message=base_message,
                        failure_reason=plan.repair_failure,
                        failed_output=plan.repair_failed_output,
                    )
                current_message = base_message
                last_failure = ""
                last_output = ""
                for attempt in range(STAGE_SELF_REPAIR_MAX_ATTEMPTS + 1):
                    agent = context.build_stage_agent(
                        current_message,
                        repair=plan.repair or attempt > 0,
                    )
                    attempt_content = ""
                    try:
                        async for event in agent.stream_chat(
                            context.stage_agent_input(agent, current_message)
                        ):
                            if event.type == "message.delta":
                                delta = _normalize_agent_delta(attempt_content, event.content)
                                if not delta:
                                    continue
                                attempt_content += delta
                                preview = (
                                    f"{generated_script}\n\n---\n\n{attempt_content}"
                                    if generated_script
                                    else attempt_content
                                )
                                yield _stream_event(
                                    context,
                                    "workspace.delta",
                                    content=delta,
                                    data={"targetTab": "script", "workspaceContent": preview},
                                )
                                continue
                            if event.type == "structured_response":
                                # 团队运行时在流末补发整稿；以整稿为准，避免流式过滤缺漏。
                                final_text = str(event.content or "").strip()
                                if final_text:
                                    attempt_content = final_text
                                continue
                            if event.type == "done":
                                final_content = _agent_final_content(event)
                                if final_content:
                                    attempt_content += _normalize_agent_delta(attempt_content, final_content)
                                break
                            if event.type == "error":
                                mark_model_stream()
                                status = "error"
                                yield _agent_error_event(context, event)
                                return
                            yield _event_from_agent_event(context, event)
                    except Exception as exc:
                        mark_model_stream()
                        status = "error"
                        yield _stream_event(
                            context,
                            "error",
                            data={"detail": _exception_detail(exc), "errorType": exc.__class__.__name__},
                        )
                        return
                    content = clean_stage_output(attempt_content)
                    last_output = content
                    try:
                        _ensure_script_episode_output(
                            content, episode_no, context, duration_minutes, quality_warnings
                        )
                        generated_script = merge_script_episode_blocks(
                            generated_script, content, target_episode_numbers=(episode_no,)
                        )
                        last_failure = ""
                        break
                    except ScreenwritingServiceError as exc:
                        last_failure = str(exc)
                        if attempt >= STAGE_SELF_REPAIR_MAX_ATTEMPTS:
                            break
                        current_message = build_stage_repair_message(
                            "script",
                            stage_message=base_message,
                            failure_reason=last_failure,
                            failed_output=content,
                        )
                        yield _stream_event(
                            context,
                            "agent.action",
                            data={
                                "phase": "stage.repair",
                                "message": f"EP{episode_no:02d} 质量校验未通过，正在触发助理自我修复",
                                "detail": last_failure,
                                "targetTab": "script",
                                "agentName": "screenwriting-script-agent",
                            },
                        )
                if last_failure:
                    mark_model_stream()
                    rollback_script = _script_rollback_content(generated_script, last_output, episode_no)
                    save_pending_script_repair(
                        state,
                        failure_reason=last_failure,
                        failed_output=last_output,
                        stage_message=plan.stage_message,
                        episode_no=episode_no,
                        remaining_episode_numbers=tuple(episode_numbers[index + 1 :]),
                    )
                    confirmation_prompt = script_repair_confirmation_prompt(last_failure, episode_no)
                    committed = await commit_stage_output(
                        context.db_session,
                        context.project,
                        state,
                        stage="script",
                        content=rollback_script,
                        user_content=context.payload.message,
                        assistant_content=confirmation_prompt,
                    )
                    status = "pending_repair_confirmation"
                    yield _stream_event(
                        context,
                        "workspace.delta",
                        content=rollback_script,
                        data={
                            "targetTab": "script",
                            "workspaceContent": rollback_script,
                            "workspace": _workspace_payload(committed),
                        },
                    )
                    yield _stream_event(
                        context,
                        "agent.action",
                        data={
                            "phase": "stage.repair.confirmation_required",
                            "message": f"EP{episode_no:02d} 自动修复未通过，需要确认是否继续补全",
                            "detail": last_failure,
                            "targetTab": "script",
                        },
                    )
                    yield _stream_event(context, "message.delta", content=f"\n\n{confirmation_prompt}")
                    yield _stream_event(
                        context,
                        "done",
                        content=f"{plan.dispatch_reply}\n\n{confirmation_prompt}",
                        data={
                            "assistantMessage": confirmation_prompt,
                            "messages": _state_message_payload(committed),
                            "workspace": _workspace_payload(committed),
                            "stage": "script",
                            "pendingScriptRepair": True,
                        },
                    )
                    return
                yield _stream_event(
                    context,
                    "workspace.delta",
                    content=generated_script,
                    data={"targetTab": "script", "workspaceContent": generated_script},
                )
            if plan.repair:
                clear_pending_script_repair(state)
            stage_content = generated_script
        else:
            stage_message = plan.stage_message
            stage_content = ""
            for attempt in range(STAGE_SELF_REPAIR_MAX_ATTEMPTS + 1):
                agent = context.build_stage_agent(stage_message, repair=attempt > 0)
                attempt_content = ""
                try:
                    async for event in agent.stream_chat(
                        context.stage_agent_input(agent, stage_message)
                    ):
                        if event.type == "message.delta":
                            delta = _normalize_agent_delta(attempt_content, event.content)
                            if not delta:
                                continue
                            attempt_content += delta
                            yield _stream_event(
                                context,
                                "workspace.delta",
                                content=delta,
                                data={"targetTab": plan.stage, "workspaceContent": attempt_content},
                            )
                            continue
                        if event.type == "structured_response":
                            # 团队运行时在流末补发整稿；以整稿为准，避免流式过滤缺漏。
                            final_text = str(event.content or "").strip()
                            if final_text:
                                attempt_content = final_text
                            continue
                        if event.type == "done":
                            final_content = _agent_final_content(event)
                            if final_content:
                                attempt_content += _normalize_agent_delta(attempt_content, final_content)
                            break
                        if event.type == "error":
                            mark_model_stream()
                            status = "error"
                            yield _agent_error_event(context, event)
                            return
                        yield _event_from_agent_event(context, event)
                except Exception as exc:
                    mark_model_stream()
                    status = "error"
                    yield _stream_event(
                        context,
                        "error",
                        data={"detail": _exception_detail(exc), "errorType": exc.__class__.__name__},
                    )
                    return
                content = clean_stage_output(attempt_content)
                try:
                    quality_warnings = ensure_stage_output_quality(
                        plan.stage,
                        content,
                        chapter_events=context.chapter_events,
                    )
                    stage_content = content
                    break
                except ScreenwritingServiceError as exc:
                    if attempt >= STAGE_SELF_REPAIR_MAX_ATTEMPTS:
                        mark_model_stream()
                        status = "quality_failed"
                        yield _stream_event(
                            context,
                            "error",
                            data={"detail": str(exc), "errorType": "ScreenwritingServiceError"},
                        )
                        return
                    stage_message = build_stage_repair_message(
                        plan.stage,
                        stage_message=plan.stage_message,
                        failure_reason=str(exc),
                        failed_output=content,
                    )
                    yield _stream_event(
                        context,
                        "agent.action",
                        data={
                            "phase": "stage.repair",
                            "message": f"{stage_label(plan.stage)}质量校验未通过，正在触发助理自我修复",
                            "detail": str(exc),
                            "targetTab": plan.stage,
                            "agentName": f"screenwriting-{plan.stage}-agent",
                        },
                    )

        mark_model_stream()
        if not stage_content:
            status = "empty_response"
            yield _stream_event(
                context,
                "error",
                data={"detail": "模型未返回可用阶段内容", "errorType": "ScreenwritingServiceError"},
            )
            return

        status = "completed"
        completion_reply = stage_completion_reply(plan)
        assistant_content = f"{plan.dispatch_reply}\n\n{completion_reply}"
        mark_stage_completed(context.session_state, plan.stage)
        committed = await commit_stage_output(
            context.db_session,
            context.project,
            context.session_state,
            stage=plan.stage,
            content=stage_content,
            user_content=context.payload.message,
            assistant_content=assistant_content,
        )
        for warning in quality_warnings:
            yield _stream_event(
                context,
                "agent.action",
                data={
                    "phase": "quality.warning",
                    "message": f"{stage_label(plan.stage)}已生成，但存在需要补强的质量提示",
                    "detail": warning,
                    "targetTab": plan.stage,
                },
            )
        yield _stream_event(
            context,
            "agent.action",
            data={
                "phase": "workspace.sync",
                "message": f"{stage_label(plan.stage)}已同步到右侧工作区",
                "detail": stage_label(plan.stage),
                "targetTab": plan.stage,
            },
        )
        yield _stream_event(
            context,
            "workspace.delta",
            content=stage_content,
            data={
                "targetTab": plan.stage,
                "workspaceContent": stage_content,
                "workspace": _workspace_payload(committed),
            },
        )
        yield _stream_event(context, "message.delta", content=f"\n\n{completion_reply}")
        yield _stream_event(
            context,
            "done",
            content=assistant_content,
            data={
                "assistantMessage": assistant_content,
                "messages": _state_message_payload(committed),
                "workspace": _workspace_payload(committed),
                "stage": plan.stage,
                "requestedStage": plan.requested_stage,
                "blockedStage": plan.blocked_stage,
                "qualityWarnings": quality_warnings,
            },
        )
    finally:
        mark_model_stream()
        _print_server_timing_log(context, operation="chat.stage_stream", status=status)


def _workspace_payload(state: ScreenwritingSessionState) -> dict[str, str]:
    return {
        "skeleton": state.workspace.skeleton,
        "strategy": state.workspace.strategy,
        "script": state.workspace.script,
    }


def _agent_result_text(result: Any) -> str:
    """取聚合结果文本：团队运行时的整稿（structured_response）优先于流式拼接。"""
    structured = getattr(result, "structured_response", None)
    if isinstance(structured, str) and structured.strip():
        return structured
    return str(getattr(result, "content", "") or "")


async def _prepare_chat_turn(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    server_timings: ScreenwritingServerTimings,
    agent_factory: ScreenwritingAgentFactory | None,
) -> _PreparedChatTurn:
    """准备单轮对话：先走创作配置链路分流，未命中再构建完整 Agent 上下文。

    调用方必须已持有会话锁。
    """
    project, model_id = await _load_chat_project(
        session,
        project_public_id,
        current_user_public_id,
        server_timings,
    )
    state = await load_chat_session_state(
        session,
        project,
        project_public_id,
        current_user_public_id,
        reset=payload.reset,
    )
    config_started_at = perf_counter()
    chapter_events = await _load_chapter_events(session, project)
    chapter_index_range = _chapter_index_bounds(chapter_events)

    # 剧本单集修复确认优先于配置链路（"确认"一词两个状态机都识别）。
    repair_dialog = resolve_script_repair_dialog(state, payload.message)
    if isinstance(repair_dialog, str):
        server_timings.mark("configDialog", config_started_at)
        return _PreparedChatTurn(
            project=project,
            state=state,
            model_id=model_id,
            config_reply=repair_dialog,
        )
    if isinstance(repair_dialog, StageGenerationPlan):
        server_timings.mark("configDialog", config_started_at)
        context = await _build_chat_context(
            session,
            project,
            project_public_id,
            current_user_public_id,
            payload,
            model_id=model_id,
            state=state,
            agent_message=payload.message,
            chapter_events=chapter_events,
            chapter_index_range=chapter_index_range,
            stage_plan=repair_dialog,
            server_timings=server_timings,
            agent_factory=agent_factory,
        )
        return _PreparedChatTurn(project=project, state=state, model_id=model_id, context=context)

    dialog = resolve_project_config_dialog(state, payload.message, chapter_index_range)
    server_timings.mark("configDialog", config_started_at)
    if dialog is not None and dialog.reply:
        return _PreparedChatTurn(
            project=project,
            state=state,
            model_id=model_id,
            config_reply=dialog.reply,
        )

    agent_message = dialog.proceed_message if dialog is not None and dialog.proceed_message else payload.message
    stage_plan = resolve_stage_generation(state, agent_message)
    if (
        stage_plan is not None
        and stage_plan.stage == "script"
        and not stage_plan.repair
        and not stage_plan.episode_numbers
    ):
        # 已有集绝不静默覆盖：配置范围内无缺失集时引导用户显式指定目标集。
        return _PreparedChatTurn(
            project=project,
            state=state,
            model_id=model_id,
            config_reply=(
                "创作配置范围内的剧本集已全部生成，本次未执行生成——已有集不会被静默覆盖。"
                "如需重写某集，请明确指定集数，例如「重写EP2」或「重新生成第2-3集剧本」。"
            ),
        )
    context = await _build_chat_context(
        session,
        project,
        project_public_id,
        current_user_public_id,
        payload,
        model_id=model_id,
        state=state,
        agent_message=agent_message,
        chapter_events=chapter_events,
        chapter_index_range=chapter_index_range,
        stage_plan=stage_plan,
        server_timings=server_timings,
        agent_factory=agent_factory,
    )
    return _PreparedChatTurn(
        project=project,
        state=state,
        model_id=model_id,
        context=context,
    )


async def _load_chapter_events(session: AsyncSession, project: Any) -> list[dict[str, Any]]:
    """加载项目内事件提取就绪的章节事件，供 Agent 工具与配置草拟使用。"""
    project_id = getattr(project, "id", None)
    if not project_id:
        return []
    statement = (
        select(NovelChapter)
        .where(
            NovelChapter.project_id == project_id,
            NovelChapter.event_state == 1,
        )
        .order_by(NovelChapter.chapter_index, NovelChapter.id)
    )
    result = await session.exec(statement)
    return [
        {
            "chapterIndex": int(chapter.chapter_index or 0),
            "chapterTitle": chapter.chapter,
            "reel": chapter.reel,
            "event": chapter.event.strip(),
        }
        for chapter in result.all()
        if str(chapter.event or "").strip()
    ]


def _chapter_index_bounds(chapter_events: list[dict[str, Any]]) -> tuple[int, int] | None:
    indexes = [int(event.get("chapterIndex", 0) or 0) for event in chapter_events]
    indexes = [index for index in indexes if index > 0]
    if not indexes:
        return None
    return min(indexes), max(indexes)


async def _load_chat_project(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    server_timings: ScreenwritingServerTimings,
) -> tuple[Any, str]:
    """加载项目并校验文本模型配置；访问类异常在此抛出以映射为 HTTP 错误。"""
    project_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    model_id = str(project.text_model or "").strip()
    if not model_id:
        raise ScreenwritingValidationError("项目尚未配置文本模型，请先在项目设置中选择文本模型")
    server_timings.mark("project", project_started_at)
    return project, model_id


_CHAPTER_RETRIEVAL_KEYWORDS: tuple[str, ...] = (
    "章", "回", "卷", "人物", "角色", "主角", "主人公", "反派", "配角", "boss",
    "剧情", "情节", "故事", "事件", "场景", "设定", "世界观", "背景", "关系",
    "结局", "原著", "小说", "为什么", "为何", "怎么", "如何", "发生", "谁",
    "经历", "冲突", "线索", "伏笔", "细节",
)
_BASIC_CONFIG_LOOKUP_KEYWORDS: tuple[str, ...] = (
    "基本配置",
    "创作配置",
    "项目配置",
    "剧本基本信息",
    "配置是否完整",
    "检查配置",
    "确认配置",
    "当前配置",
    "已确认配置",
    "集数",
    "单集时长",
    "原著范围",
    "章节范围",
    "平台规格",
    "风格定位",
    "付费策略",
)
_CONTENT_RETRIEVAL_STRONG_KEYWORDS: tuple[str, ...] = (
    "章", "回", "卷", "人物", "角色", "主角", "主人公", "反派", "配角", "boss",
    "剧情", "情节", "事件", "场景", "设定", "世界观", "背景", "关系",
    "结局", "原著", "小说", "发生", "经历", "冲突", "线索", "伏笔", "细节",
)
_QUESTION_RETRIEVAL_KEYWORDS: tuple[str, ...] = ("为什么", "为何", "怎么", "如何", "谁")


def _should_retrieve_chapters(stage_plan: StageGenerationPlan | None, message: str) -> bool:
    """判断本轮是否需要章节向量检索。

    阶段生成（骨架/策略/剧本）依赖原著内容，必须检索；普通对话中，设置创作配置
    与不涉及原著内容的基本问答无需检索，仅当消息问及章节、人物、剧情等内容时才检索。
    """
    if stage_plan is not None:
        return True
    text = (message or "").strip()
    if not text:
        return False
    if message_contains_project_config_hint(text):
        return False
    if _is_basic_config_lookup_message(text):
        return False
    if parse_screenwriting_query_intent(text).field_lookups:
        return True
    return any(keyword in text for keyword in _CONTENT_RETRIEVAL_STRONG_KEYWORDS) or (
        any(keyword in text for keyword in _QUESTION_RETRIEVAL_KEYWORDS)
        and any(keyword in text for keyword in _CONTENT_RETRIEVAL_STRONG_KEYWORDS)
    )


def _is_basic_config_lookup_message(message: str) -> bool:
    """识别只检查项目创作配置的普通问答，不触发章节内容检索。"""
    text = (message or "").strip()
    if not text:
        return False
    return any(keyword in text for keyword in _BASIC_CONFIG_LOOKUP_KEYWORDS)


async def _build_chat_context(
    session: AsyncSession,
    project: Any,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    model_id: str,
    state: ScreenwritingSessionState,
    agent_message: str,
    chapter_events: list[dict[str, Any]],
    chapter_index_range: tuple[int, int] | None,
    server_timings: ScreenwritingServerTimings,
    agent_factory: ScreenwritingAgentFactory | None,
    stage_plan: StageGenerationPlan | None = None,
) -> ScreenwritingChatContext:
    active_tab = payload.active_tab
    conversation_id = state.conversation_id
    isolation_key = _build_isolation_key(project_public_id, current_user_public_id, conversation_id)
    rag_started_at = perf_counter()
    if _should_retrieve_chapters(stage_plan, agent_message):
        rag_preparation = await prepare_rag_context(
            session,
            project,
            project_public_id,
            current_user_public_id,
            agent_message,
        )
    else:
        # 基本问答、设置创作配置等不依赖原著内容的轮次跳过章节向量检索。
        rag_preparation = ScreenwritingRagPreparation(context=empty_rag_context(), document_count=0)
    server_timings.mark("rag", rag_started_at)
    agent_setup_started_at = perf_counter()
    tools = build_screenwriting_agent_tools(
        rag_preparation.context,
        state,
        chapter_events,
        chapter_index_range,
    )
    resolved_factory = agent_factory or _default_agent_factory
    stage_agent_builder: Callable[[str], HarnessAgent] | None = None
    if stage_plan is not None:
        rag_text = rag_preparation.context.text

        def _build_stage_agent(stage_message: str, *, repair: bool = False) -> HarnessAgent:
            # 阶段子 Agent 为纯文本生成：数据已注入提示词，不绑定工具，
            # 避免模型发起工具调用导致流式通道零文本产出。
            system_prompt = build_stage_system_prompt(
                stage_plan.stage,
                state,
                stage_message=stage_message,
                rag_text=rag_text,
                chapter_events=chapter_events,
            )
            if agent_factory is None and settings.screenwriting_stage_team_enabled:
                return _build_stage_team_agent(
                    model_id=model_id,
                    system_prompt=system_prompt,
                    stage=stage_plan.stage,
                    repair=repair,
                )
            return resolved_factory(
                model_id=model_id,
                system_prompt=system_prompt,
                tools=[],
            )

        stage_agent_builder = _build_stage_agent
        agent = stage_agent_builder(stage_plan.stage_message)
        agent_messages = [{"role": "user", "content": stage_plan.stage_message}]
    else:
        base_prompt = build_guide_system_prompt(
            active_tab,
            project_config_block=format_project_config(ensure_project_config(state, chapter_index_range)),
            workspace_overview=_workspace_overview(state),
            config_confirmed=state.workflow.get(WORKFLOW_BASIC_INFO_CONFIRMED) is True,
        )
        system_prompt = build_system_prompt_with_rag(base_prompt, rag_preparation.context)
        agent_messages = _agent_messages(state, agent_message)
        agent = resolved_factory(
            model_id=model_id,
            system_prompt=system_prompt,
            tools=tools,
        )
    server_timings.mark("agentSetup", agent_setup_started_at)
    return ScreenwritingChatContext(
        project_public_id=project_public_id,
        user_public_id=current_user_public_id,
        conversation_id=conversation_id,
        isolation_key=isolation_key,
        model_id=model_id,
        active_tab=active_tab,
        messages=agent_messages,
        payload=payload,
        rag_context=rag_preparation.context,
        rag_document_count=rag_preparation.document_count,
        thinking_started_at=server_timings.started_at,
        server_timings=server_timings,
        agent=agent,
        db_session=session,
        project=project,
        session_state=state,
        stage_plan=stage_plan,
        chapter_events=chapter_events,
        stage_agent_builder=stage_agent_builder,
    )


def _workspace_overview(state: ScreenwritingSessionState) -> str:
    """生成三阶段工作区概览（标题与字数），全文由 get_workspace 工具按需读取。"""
    labels = (("故事骨架", state.workspace.skeleton), ("改编策略", state.workspace.strategy), ("剧本草案", state.workspace.script))
    lines = []
    for label, content in labels:
        text = content.strip()
        if not text:
            lines.append(f"- {label}：（空）")
            continue
        heading = next(
            (line.lstrip("#").strip() for line in text.splitlines() if line.strip().startswith("#")),
            "",
        )
        summary = f"约{len(text)}字" + (f"，标题「{heading}」" if heading else "")
        lines.append(f"- {label}：{summary}")
    return "\n".join(lines)


def _default_agent_factory(
    *,
    model_id: str,
    system_prompt: str,
    tools: list[Callable[..., Any]] | None = None,
) -> HarnessAgent:
    runtime = DeepAgentsRuntime(
        adapter=ModelGatewayAdapter(default_model_id=model_id),
        model_id=model_id,
        tools=tools,
        system_prompt=system_prompt,
    )
    return HarnessAgent(runtime=runtime)


def _build_stage_team_agent(
    *,
    model_id: str,
    system_prompt: str,
    stage: str,
    repair: bool,
) -> HarnessAgent:
    """构建 CrewAI 阶段团队 Agent；修复轮换用单员修复团队，不重跑完整链路。"""
    from app.services.screenwriting.team import (
        screenwriting_stage_team_members,
        stage_repair_team_members,
    )

    team_members = stage_repair_team_members(stage) if repair else screenwriting_stage_team_members(stage)
    runtime = CrewAIStageRuntime(
        adapter=ModelGatewayAdapter(default_model_id=model_id),
        model_id=model_id,
        system_prompt=system_prompt,
        stage=stage,
        team_members=team_members,
        name=f"screenwriting-{stage}-agent",
    )
    return HarnessAgent(runtime=runtime)


def _agent_messages(state: ScreenwritingSessionState, agent_message: str) -> list[dict[str, str]]:
    """从服务端会话状态构造 Agent 输入消息（截取最近若干轮 + 本轮输入）。"""
    messages = [
        {"role": turn.role, "content": turn.content}
        for turn in state.messages[-MAX_HISTORY_MESSAGES:]
        if turn.content.strip()
    ]
    messages.append({"role": "user", "content": agent_message.strip()})
    return messages


def _state_message_payload(state: ScreenwritingSessionState) -> list[dict[str, str]]:
    return [message.model_dump(by_alias=True, mode="json") for message in state.messages]


def _metadata_direct_answer(context: ScreenwritingChatContext) -> str:
    """对确定性的 metadata 字段查询直接返回命中字段，避免简单问题等待模型生成。"""
    rag_context = context.rag_context
    runtime = rag_context.runtime
    if runtime.get("retrievalMode") != "metadata":
        return ""
    if runtime.get("retrievalStrategy") != "field_lookup_exact":
        return ""

    lookup_specs = _runtime_field_lookup_specs(runtime)
    if not lookup_specs:
        return ""

    answer_lines: list[str] = []
    for hit in rag_context.hits:
        markers = [
            marker
            for source_type, source_markers in lookup_specs
            if source_type == hit.document.source_type
            for marker in source_markers
        ]
        if not markers:
            continue
        answer_lines.extend(_matching_field_lines(hit.chunk_text, markers))

    return "\n".join(_dedupe_preserve_order(answer_lines[:5]))


def _runtime_field_lookup_specs(runtime: dict[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    raw_specs = runtime.get("intentFieldLookups")
    if not isinstance(raw_specs, list):
        return []
    specs: list[tuple[str, tuple[str, ...]]] = []
    for raw_spec in raw_specs:
        if not isinstance(raw_spec, dict):
            continue
        source_type = str(raw_spec.get("sourceType") or raw_spec.get("source_type") or "").strip()
        raw_markers = raw_spec.get("documentMarkers") or raw_spec.get("document_markers")
        if not source_type or not isinstance(raw_markers, list):
            continue
        markers = tuple(str(marker).strip() for marker in raw_markers if str(marker).strip())
        if markers:
            specs.append((source_type, markers))
    return specs


def _matching_field_lines(text: str, markers: list[str]) -> list[str]:
    normalized_markers = tuple(normalize_lookup_text(marker) for marker in markers)
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        label, value = _split_field_line(raw_line)
        if not label or not value:
            continue
        normalized_label = normalize_lookup_text(label)
        if not any(marker and marker in normalized_label for marker in normalized_markers):
            continue
        lines.append(f"{label.strip()}: {value.strip()}")
    return lines


def _split_field_line(line: str) -> tuple[str, str]:
    text = str(line or "").strip()
    for delimiter in ("：", ":"):
        if delimiter in text:
            label, value = text.split(delimiter, 1)
            return label.strip(), value.strip()
    return "", ""


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_agent_delta(current_content: str, incoming_content: str) -> str:
    """把运行时可能返回的累计内容转换为客户端可直接追加的增量。"""
    if not incoming_content:
        return ""
    if not current_content:
        return incoming_content
    if len(incoming_content) > len(current_content) and incoming_content.startswith(current_content):
        return incoming_content[len(current_content) :]
    return incoming_content


_RUNTIME_AGENT_ACTION_EVENTS = frozenset(
    {
        "tool.start",
        "tool.result",
        "tool.end",
        "tool.error",
        "stage.team.plan",
        "stage.member.progress",
        "stage.member.complete",
        "stage.team.complete",
    }
)


def _event_from_agent_event(context: ScreenwritingChatContext, event: ScriptAgentEvent) -> ScreenwritingStreamEvent:
    """把运行时事件转换为流式协议事件。

    团队/工具类进度事件归一为 agent.action（前端执行过程面板），
    其余事件原样透传。
    """
    if event.type in _RUNTIME_AGENT_ACTION_EVENTS:
        data = event.data or {}
        message = str(data.get("summary") or data.get("message") or event.content or "正在处理工作流").strip()
        action_data: dict[str, Any] = {
            "phase": event.type,
            "message": message,
        }
        detail = str(data.get("goal") or data.get("detail") or "").strip()
        if detail:
            action_data["detail"] = detail
        if context.stage_plan is not None:
            action_data["targetTab"] = context.stage_plan.stage
        agent_name = str(data.get("name") or "").strip()
        if agent_name:
            action_data["agentName"] = agent_name
        return _stream_event(context, "agent.action", data=action_data)
    return _stream_event(
        context,
        event.type,
        content=event.content,
        data=event.data,
    )


def _agent_error_event(context: ScreenwritingChatContext, event: ScriptAgentEvent) -> ScreenwritingStreamEvent:
    data = dict(event.data)
    data["detail"] = _agent_error_detail(event)
    data.setdefault("errorType", "AgentRuntimeError")
    return _stream_event(context, "error", content=event.content, data=data)


def _agent_error_detail(event: ScriptAgentEvent) -> str:
    for key in ("detail", "message", "errorMessage", "error", "reason"):
        value = event.data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if event.content.strip():
        return event.content.strip()
    return "Agent 运行时返回错误事件"


def _agent_final_content(event: ScriptAgentEvent) -> str:
    if event.content.strip():
        return event.content.strip()
    for key in ("assistantMessage", "content", "message", "text", "answer"):
        value = event.data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = event.data.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            value = message.get("content")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _exception_detail(exc: Exception) -> str:
    detail = str(exc).strip()
    return detail or exc.__class__.__name__


def _stream_event(
    context: ScreenwritingChatContext,
    event_type: str,
    *,
    content: str = "",
    data: dict[str, Any] | None = None,
) -> ScreenwritingStreamEvent:
    event_data = dict(data or {})
    event_data.setdefault("thinkingElapsedMs", _thinking_elapsed_ms(context))
    event_data.setdefault("serverTimings", context.server_timings.payload())
    if event_type in {"start", "done", "error"}:
        event_data.setdefault(
            "rag",
            rag_runtime_payload(context.rag_context, document_count=context.rag_document_count),
        )
    return ScreenwritingStreamEvent(
        type=event_type,
        content=content,
        conversation_id=context.conversation_id,
        isolation_key=context.isolation_key,
        model_id=context.model_id,
        active_tab=context.active_tab,
        data=event_data,
    )


def _elapsed_ms_since(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _thinking_elapsed_ms(context: ScreenwritingChatContext) -> int:
    return max(0, int((perf_counter() - context.thinking_started_at) * 1000))


def _print_server_timing_log(context: ScreenwritingChatContext, *, operation: str, status: str) -> None:
    print(_format_server_timing_log(context, operation=operation, status=status), flush=True)


def _format_server_timing_log(context: ScreenwritingChatContext, *, operation: str, status: str) -> str:
    timings = context.server_timings.payload()
    stages = ", ".join(_format_timing_stage(stage) for stage in timings["stages"]) or "-"
    return (
        "Screenwriting server timings: "
        f"operation={operation} "
        f"status={status} "
        f"project_public_id={context.project_public_id} "
        f"conversation_id={context.conversation_id} "
        f"active_tab={context.active_tab} "
        f"model_id={context.model_id} "
        f"total_ms={timings['totalMs']} "
        f"client_to_server_ms={_format_optional_ms(timings['clientToServerMs'])} "
        f"rag_mode={context.rag_context.runtime.get('retrievalMode', '-')} "
        f"rag_hits={len(context.rag_context.hits)} "
        f"rag_documents={context.rag_document_count} "
        f"stages=[{stages}]"
    )


def _format_timing_stage(stage: dict[str, int | str]) -> str:
    return (
        f"{stage['name']}={stage['durationMs']}ms"
        f"(+{stage['startedAtMs']}..+{stage['endedAtMs']}ms)"
    )


def _format_optional_ms(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value}ms"


def _duration_ms(started_at: float, ended_at: float) -> int:
    return max(0, int((ended_at - started_at) * 1000))


def _build_isolation_key(project_public_id: str, user_public_id: str, conversation_id: str) -> str:
    return f"screenwriting:{project_public_id}:{user_public_id}:{conversation_id}"