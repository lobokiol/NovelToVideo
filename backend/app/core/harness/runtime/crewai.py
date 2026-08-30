"""基于 CrewAI 的阶段助理团队运行时。

多角色顺序协作生成阶段正文：每成员独立 LLM 参数，只有最后一个成员
（终稿审校）的 token 流作为正文增量对外发布；非文本进度经
stage.team.plan / stage.member.progress / stage.member.complete /
stage.team.complete 事件暴露。CrewAI 为可选依赖，缺失时构建即抛
HarnessAgentError，由业务层回退单 Agent 路径。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.core.harness.runtime.agent import (
    HarnessAgentError,
    ScriptAgentEvent,
    ScriptAgentInput,
    _structured_response_to_text,
)
from app.core.harness.tools.adapter import ModelGatewayAdapter
from app.core.harness.tools.crew_llm import (
    _CREWAI_STAGE_ABORT_CONTEXT,
    _CrewAIStageAbortContext,
    ProviderGatewayCrewLLM,
)


@dataclass(frozen=True)
class _CrewAIStageProgressMember:
    role: str
    member_index: int
    total_members: int


@dataclass(frozen=True)
class _CrewAIStageProgressContext:
    stage_name: str
    members_by_role: dict[str, _CrewAIStageProgressMember]
    event_callback: Callable[[ScriptAgentEvent], None]


_CREWAI_STAGE_PROGRESS_CONTEXT: ContextVar[_CrewAIStageProgressContext | None] = ContextVar(
    "crewai_stage_progress_context",
    default=None,
)


def _emit_crewai_stage_task_complete(output: Any) -> None:
    """模块级 CrewAI 任务完成回调（Task callback 须可被 Pydantic 序列化）。"""
    context = _CREWAI_STAGE_PROGRESS_CONTEXT.get()
    if context is None:
        return
    role = str(getattr(output, "agent", "") or "")
    member = context.members_by_role.get(role)
    if member is None:
        return
    context.event_callback(
        ScriptAgentEvent(
            type="stage.member.complete",
            data={
                "name": context.stage_name,
                "role": member.role,
                "memberIndex": member.member_index,
                "totalMembers": member.total_members,
                "summary": f"第 {member.member_index}/{member.total_members} 个角色已完成：{member.role}",
            },
        )
    )


@dataclass(frozen=True)
class CrewAIStageTeamMember:
    """阶段助理团队成员定义。

    业务层据此声明角色协作行为，运行时按成员配置执行：
    generation_options 为该成员的模型生成参数（如 temperature）；
    context_task_mode 取 "all"（承接全部前序任务）或 "last"（仅承接上一任务）。
    """

    role: str
    goal: str
    backstory: str
    task: str
    expected_output: str
    generation_options: dict[str, Any] = field(default_factory=dict)
    context_task_mode: str = "all"


class CrewAIStageRuntime:
    """基于 CrewAI 的阶段助理团队运行时，生成固定工作区内容。"""

    def __init__(
        self,
        *,
        adapter: ModelGatewayAdapter,
        model_id: str | None = None,
        tools: Sequence[Any] | None = None,
        system_prompt: str | None = None,
        name: str | None = None,
        stage: str = "stage",
        crew_factory: Callable[..., Any] | None = None,
        agent_factory: Callable[..., Any] | None = None,
        task_factory: Callable[..., Any] | None = None,
        team_members: Sequence[CrewAIStageTeamMember | Mapping[str, str]] | None = None,
        chunk_size: int = 240,
        progress_interval_seconds: float = 15.0,
        **_: Any,
    ) -> None:
        self.adapter = adapter
        self.model_id = (model_id or "").strip()
        self.tools = list(tools or [])
        self.system_prompt = system_prompt or ""
        self.name = name or f"screenwriting-{stage}-agent"
        self.stage = stage
        self.crew_factory = crew_factory
        self.agent_factory = agent_factory
        self.task_factory = task_factory
        self.team_members = (
            self._coerce_team_members(team_members)
            if team_members is not None
            else self._default_team_members(self.stage)
        )
        self.chunk_size = max(1, chunk_size)
        self.progress_interval_seconds = max(0.1, float(progress_interval_seconds))

    async def stream_chat(self, request: ScriptAgentInput) -> AsyncIterator[ScriptAgentEvent]:
        yield ScriptAgentEvent(
            type="tool.start",
            data={
                "name": self.name,
                "summary": "阶段创作团队开始编排创作内容",
                "team": [member.role for member in self.team_members],
            },
        )
        yield self._team_plan_event()
        progress_queue: asyncio.Queue[ScriptAgentEvent] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit_progress(event: ScriptAgentEvent) -> None:
            loop.call_soon_threadsafe(progress_queue.put_nowait, event)

        crew = self._build_crew(request, emit_task_progress=True)
        result = None
        streamed_content = False
        async for event in self._run_crew_with_progress(
            crew,
            progress_queue,
            event_callback=emit_progress,
        ):
            if event.type == "stage.result":
                result = event.data.get("result")
                continue
            if event.type == "message.delta" and event.content:
                streamed_content = True
            yield event
        yield ScriptAgentEvent(
            type="stage.team.complete",
            data={
                "name": self.name,
                "summary": f"{self._stage_label()}团队已完成，正在整理最终输出。",
                "totalMembers": len(self.team_members),
            },
        )
        if result is None:
            raise HarnessAgentError(f"{self._stage_label()}团队未返回可用结果")
        content = self._normalize_crew_output(result)
        if streamed_content:
            if content:
                yield ScriptAgentEvent(
                    type="structured_response",
                    content=content,
                    data={"structured_response": content},
                )
            return
        for chunk in self._iter_text_chunks(content):
            yield ScriptAgentEvent(type="message.delta", content=chunk)

    def _build_crew(
        self,
        request: ScriptAgentInput,
        *,
        emit_task_progress: bool = False,
    ) -> Any:
        if ProviderGatewayCrewLLM is None:
            raise HarnessAgentError("阶段创作团队依赖未就绪，请检查运行环境")

        agent_factory, task_factory, crew_factory, process = self._resolve_crewai_factories()
        agents: list[Any] = []
        tasks: list[Any] = []
        for member in self.team_members:
            llm = ProviderGatewayCrewLLM(
                adapter=self.adapter,
                model=request.model_id or self.model_id,
                stream=True,
                request_options=member.generation_options,
            )
            agent = agent_factory(
                role=member.role,
                goal=member.goal,
                backstory=self._build_member_backstory(member),
                llm=llm,
                tools=[],
                allow_delegation=False,
                verbose=False,
                max_iter=1,
                max_retry_limit=0,
            )
            task_kwargs: dict[str, Any] = {
                "description": f"{member.task}\n\n{self._build_task_description(request)}",
                "expected_output": member.expected_output,
                "agent": agent,
            }
            if emit_task_progress:
                task_kwargs["callback"] = _emit_crewai_stage_task_complete
            context_tasks = tasks[-1:] if member.context_task_mode == "last" else list(tasks)
            if context_tasks:
                task_kwargs["context"] = context_tasks
            task = task_factory(**task_kwargs)
            agents.append(agent)
            tasks.append(task)
        return crew_factory(
            agents=agents,
            tasks=tasks,
            process=process.sequential,
            stream=True,
            verbose=False,
        )

    def _team_plan_event(self) -> ScriptAgentEvent:
        return ScriptAgentEvent(
            type="stage.team.plan",
            data={
                "name": self.name,
                "summary": f"{self._stage_label()}团队已拆分为 {len(self.team_members)} 个角色顺序协作。",
                "totalMembers": len(self.team_members),
                "team": [
                    {
                        "memberIndex": index,
                        "role": member.role,
                        "goal": member.goal,
                        "expectedOutput": member.expected_output,
                    }
                    for index, member in enumerate(self.team_members, start=1)
                ],
            },
        )

    async def _run_crew_with_progress(
        self,
        crew: Any,
        progress_queue: asyncio.Queue[ScriptAgentEvent],
        *,
        event_callback: Callable[[ScriptAgentEvent], None],
    ) -> AsyncIterator[ScriptAgentEvent]:
        progress_context = _CrewAIStageProgressContext(
            stage_name=self.name,
            members_by_role={
                member.role: _CrewAIStageProgressMember(
                    role=member.role,
                    member_index=index,
                    total_members=len(self.team_members),
                )
                for index, member in enumerate(self.team_members, start=1)
            },
            event_callback=event_callback,
        )
        progress_token = _CREWAI_STAGE_PROGRESS_CONTEXT.set(progress_context)
        abort_token = _CREWAI_STAGE_ABORT_CONTEXT.set(_CrewAIStageAbortContext())
        kickoff_task = asyncio.create_task(crew.akickoff())
        started_at = time.monotonic()
        current_member_index = 1
        last_progress_key: tuple[int, int] | None = None
        try:
            while not kickoff_task.done():
                async for event in self._drain_progress_queue(progress_queue):
                    if event.type == "stage.member.complete":
                        completed_index = int(event.data.get("memberIndex") or current_member_index)
                        current_member_index = min(completed_index + 1, max(len(self.team_members), 1))
                    yield event

                elapsed_seconds = int(time.monotonic() - started_at)
                interval = max(1, int(self.progress_interval_seconds))
                progress_key = (current_member_index, elapsed_seconds // interval)
                if progress_key != last_progress_key:
                    last_progress_key = progress_key
                    yield self._member_progress_event(
                        member_index=current_member_index,
                        elapsed_seconds=elapsed_seconds,
                    )

                done, _ = await asyncio.wait({kickoff_task}, timeout=self.progress_interval_seconds)
                if done:
                    break

            async for event in self._drain_progress_queue(progress_queue):
                yield event
            kickoff_result = await kickoff_task
            if self._is_streaming_output(kickoff_result):
                async for event in self._stream_crew_output_with_progress(
                    kickoff_result,
                    progress_queue,
                    started_at=started_at,
                ):
                    yield event
                kickoff_result = self._streaming_output_result(kickoff_result)
            async for event in self._drain_progress_queue(progress_queue):
                yield event
            yield ScriptAgentEvent(type="stage.result", data={"result": kickoff_result})
        except Exception as exc:
            yield ScriptAgentEvent(
                type="tool.error",
                data={
                    "name": self.name,
                    "summary": f"{self._stage_label()}团队执行失败：{exc}",
                },
            )
            raise
        finally:
            _CREWAI_STAGE_PROGRESS_CONTEXT.reset(progress_token)
            _CREWAI_STAGE_ABORT_CONTEXT.reset(abort_token)
            if not kickoff_task.done():
                kickoff_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await kickoff_task

    async def _stream_crew_output_with_progress(
        self,
        streaming_output: Any,
        progress_queue: asyncio.Queue[ScriptAgentEvent],
        *,
        started_at: float,
    ) -> AsyncIterator[ScriptAgentEvent]:
        stream_done = object()
        stream_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def consume_stream() -> None:
            try:
                async for chunk in streaming_output:
                    await stream_queue.put(chunk)
            except Exception as exc:
                await stream_queue.put(exc)
            finally:
                await stream_queue.put(stream_done)

        stream_task = asyncio.create_task(consume_stream())
        current_member_index = 1
        last_progress_key: tuple[int, int] | None = None
        try:
            while True:
                async for event in self._drain_progress_queue(progress_queue):
                    if event.type == "stage.member.complete":
                        completed_index = int(event.data.get("memberIndex") or current_member_index)
                        current_member_index = min(completed_index + 1, max(len(self.team_members), 1))
                    yield event

                try:
                    item = await asyncio.wait_for(
                        stream_queue.get(),
                        timeout=self.progress_interval_seconds,
                    )
                except TimeoutError:
                    elapsed_seconds = int(time.monotonic() - started_at)
                    interval = max(1, int(self.progress_interval_seconds))
                    progress_key = (current_member_index, elapsed_seconds // interval)
                    if progress_key != last_progress_key:
                        last_progress_key = progress_key
                        yield self._member_progress_event(
                            member_index=current_member_index,
                            elapsed_seconds=elapsed_seconds,
                        )
                    continue

                if item is stream_done:
                    break
                if isinstance(item, BaseException):
                    raise item
                if not self._is_final_stage_output_chunk(item):
                    continue
                text = self._stream_chunk_to_text(item)
                if text:
                    yield ScriptAgentEvent(type="message.delta", content=text)

            async for event in self._drain_progress_queue(progress_queue):
                yield event
        finally:
            if not stream_task.done():
                stream_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stream_task

    @staticmethod
    def _is_streaming_output(value: Any) -> bool:
        return hasattr(value, "__aiter__")

    @staticmethod
    def _streaming_output_result(streaming_output: Any) -> Any:
        try:
            return getattr(streaming_output, "result")
        except Exception:
            return streaming_output

    def _is_final_stage_output_chunk(self, chunk: Any) -> bool:
        """只放行最后一个任务（终稿审校角色）的 token 作为正文增量。"""
        if not self.team_members:
            return True
        final_task_index = len(self.team_members) - 1
        task_index = chunk.get("task_index") if isinstance(chunk, dict) else getattr(chunk, "task_index", None)
        if task_index is not None:
            try:
                return int(task_index) == final_task_index
            except (TypeError, ValueError):
                return False
        agent_role = chunk.get("agent_role") if isinstance(chunk, dict) else getattr(chunk, "agent_role", None)
        if agent_role:
            return str(agent_role) == self.team_members[-1].role
        return True

    @staticmethod
    def _stream_chunk_to_text(chunk: Any) -> str:
        chunk_type = getattr(chunk, "chunk_type", None)
        chunk_type_value = getattr(chunk_type, "value", chunk_type)
        if str(chunk_type_value or "").lower() == "tool_call":
            return ""
        if isinstance(chunk, dict):
            value = chunk.get("content")
        else:
            value = getattr(chunk, "content", None)
        if value is None:
            return str(chunk or "")
        return str(value or "")

    async def _drain_progress_queue(
        self,
        progress_queue: asyncio.Queue[ScriptAgentEvent],
    ) -> AsyncIterator[ScriptAgentEvent]:
        while True:
            try:
                yield progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    def _member_progress_event(self, *, member_index: int, elapsed_seconds: int) -> ScriptAgentEvent:
        if not self.team_members:
            role = "阶段执行 Agent"
            goal = "完成当前阶段任务"
            total_members = 1
        else:
            total_members = len(self.team_members)
            bounded_index = min(max(member_index, 1), total_members)
            member = self.team_members[bounded_index - 1]
            role = member.role
            goal = member.goal
            member_index = bounded_index
        return ScriptAgentEvent(
            type="stage.member.progress",
            data={
                "name": self.name,
                "role": role,
                "goal": goal,
                "memberIndex": member_index,
                "totalMembers": total_members,
                "elapsedSeconds": elapsed_seconds,
                "summary": f"第 {member_index}/{total_members} 个角色处理中：{role}",
            },
        )

    def _build_member_backstory(self, member: CrewAIStageTeamMember) -> str:
        return (
            f"{member.backstory}\n\n"
            "你属于主 Agent 派发的阶段创作团队，只处理当前阶段任务。\n"
            "阶段技能提示词与运行时约束如下：\n"
            f"{self.system_prompt or '无额外阶段提示词。'}\n\n"
            "运行模式：创作配置与章节事件已注入上方运行时上下文，"
            "禁止输出 Thought、Action、Action Input、Observation 或任何工具调用语法。"
        )

    def _build_task_description(self, request: ScriptAgentInput) -> str:
        messages = self._normalize_messages(request.messages)
        latest_user_message = next(
            (message["content"] for message in reversed(messages) if message["role"] == "user"),
            "",
        )
        history = "\n".join(f"{message['role']}: {message['content']}" for message in messages[-6:])
        return (
            f"阶段：{self._stage_label()}\n"
            f"用户需求：{latest_user_message}\n\n"
            f"近轮上下文：\n{history}\n\n"
            "只输出阶段正文。不得输出主 Agent 对话、工具调用说明、执行日志或隐藏推理。"
        )

    @staticmethod
    def _normalize_messages(messages: Sequence[Any]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in messages:
            if isinstance(message, dict):
                normalized.append(
                    {"role": str(message.get("role") or "user"), "content": str(message.get("content") or "")}
                )
            else:
                normalized.append({"role": "user", "content": str(message)})
        return normalized

    def _resolve_crewai_factories(self) -> tuple[Callable[..., Any], Callable[..., Any], Callable[..., Any], Any]:
        if self.agent_factory is not None and self.task_factory is not None and self.crew_factory is not None:
            try:
                from crewai import Process
            except ImportError:  # pragma: no cover - 运行环境导入守卫。
                process = type("Process", (), {"sequential": "sequential"})
                return self.agent_factory, self.task_factory, self.crew_factory, process
            return self.agent_factory, self.task_factory, self.crew_factory, Process

        try:
            from crewai import Agent, Crew, Process, Task
        except ImportError as exc:  # pragma: no cover - 运行环境导入守卫。
            raise HarnessAgentError("阶段创作团队依赖未就绪，请检查运行环境") from exc
        return (
            self.agent_factory or Agent,
            self.task_factory or Task,
            self.crew_factory or Crew,
            Process,
        )

    @staticmethod
    def _coerce_team_members(
        team_members: Sequence[CrewAIStageTeamMember | Mapping[str, str]],
    ) -> list[CrewAIStageTeamMember]:
        normalized: list[CrewAIStageTeamMember] = []
        for member in team_members:
            if isinstance(member, CrewAIStageTeamMember):
                normalized.append(member)
                continue
            normalized.append(
                CrewAIStageTeamMember(
                    role=str(member.get("role") or "阶段执行 Agent"),
                    goal=str(member.get("goal") or "完成当前阶段任务"),
                    backstory=str(member.get("backstory") or "你是商业短剧改编团队成员。"),
                    task=str(member.get("task") or "完成当前阶段内容生成。"),
                    expected_output=str(member.get("expected_output") or "阶段 Markdown 正文。"),
                )
            )
        return normalized or CrewAIStageRuntime._default_team_members("stage")

    @staticmethod
    def _default_team_members(stage: str) -> list[CrewAIStageTeamMember]:
        """未注入 team_members 时的通用单员兜底（业务团队定义在 services 层）。"""
        return [
            CrewAIStageTeamMember(
                role="阶段执行 Agent",
                goal="生成可直接写入右侧工作区的专业 Markdown 正文。",
                backstory="你是商业短剧改编团队的阶段执行 Agent。",
                task="完成当前阶段内容生成。",
                expected_output="完整的阶段 Markdown 正文，不包含主 Agent 对话或调度说明。",
            )
        ]

    @staticmethod
    def _normalize_crew_output(result: Any) -> str:
        for attr in ("raw", "content", "text"):
            value = getattr(result, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if isinstance(result, str):
            return result.strip()
        model_dump = getattr(result, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump(mode="json")
            except TypeError:
                dumped = model_dump()
            return _structured_response_to_text(dumped)
        return _structured_response_to_text(result)

    def _iter_text_chunks(self, content: str) -> list[str]:
        if not content:
            return []
        chunks: list[str] = []
        current = ""
        for part in content.splitlines(keepends=True):
            if current and len(current) + len(part) > self.chunk_size:
                chunks.append(current)
                current = ""
            current += part
        if current:
            chunks.append(current)
        return chunks or [content]

    def _stage_label(self) -> str:
        return {
            "skeleton": "故事骨架",
            "strategy": "改编策略",
            "script": "剧本",
        }.get(self.stage, "阶段内容")