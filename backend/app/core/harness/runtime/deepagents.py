"""基于 deepagents 的 Harness Agent 运行时。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from langchain_core.messages import BaseMessage

from app.core.harness.memory.scope import HarnessMemoryScope
from app.core.harness.profiles import register_screenwriting_harness_profile
from app.core.harness.runtime.agent import HarnessAgentError, ScriptAgentEvent, ScriptAgentInput
from app.core.harness.tools.adapter import ModelGatewayAdapter
from app.core.harness.tools.chat_model import ProviderGatewayChatModel


class DeepAgentsRuntime:
    """基于 deepagents 的主 Agent 运行时。"""

    def __init__(
        self,
        *,
        adapter: ModelGatewayAdapter,
        model_id: str | None = None,
        tools: Sequence[Any] | None = None,
        system_prompt: str | None = None,
        memory_scope: HarnessMemoryScope | None = None,
        agent_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.adapter = adapter
        self.model_id = (model_id or "").strip()
        self.tools = list(tools or [])
        self.system_prompt = system_prompt
        self.memory_scope = memory_scope or HarnessMemoryScope()
        self.agent_factory = agent_factory or self._default_agent_factory

    def _default_agent_factory(self, **kwargs: Any) -> Any:
        try:
            from deepagents import create_deep_agent
        except ImportError as exc:
            raise HarnessAgentError("deepagents 依赖未安装，无法启动 Harness Agent") from exc
        return create_deep_agent(**kwargs)

    def _build_agent(self, model_id: str | None, isolation_key: str) -> Any:
        register_screenwriting_harness_profile()
        return self.agent_factory(
            model=ProviderGatewayChatModel(
                adapter=self.adapter,
                model_id=(model_id or self.model_id) or None,
            ),
            tools=self.tools,
            system_prompt=self.system_prompt,
            memory=self.memory_scope.memory_sources(isolation_key),
        )

    async def stream_chat(self, request: ScriptAgentInput) -> AsyncIterator[ScriptAgentEvent]:
        agent = self._build_agent(request.model_id, request.isolation_key)
        stream = agent.astream(
            {"messages": request.messages},
            stream_mode="messages",
            config={"configurable": {"thread_id": request.isolation_key}} if request.isolation_key else None,
        )
        async for chunk in stream:
            event = self._chunk_to_event(chunk)
            if event is not None:
                yield event

    def _chunk_to_event(self, chunk: Any) -> ScriptAgentEvent | None:
        if isinstance(chunk, ScriptAgentEvent):
            return chunk
        if isinstance(chunk, BaseMessage):
            return ScriptAgentEvent(type="message.delta", content=self._message_content_to_text(chunk.content))
        if isinstance(chunk, tuple) and chunk:
            return self._chunk_to_event(chunk[0])
        if isinstance(chunk, dict):
            if "type" in chunk:
                data = chunk.get("data")
                return ScriptAgentEvent(
                    type=str(chunk.get("type") or "runtime.event"),
                    content=self._message_content_to_text(chunk.get("content")),
                    data=dict(data) if isinstance(data, dict) else {},
                )
            messages = chunk.get("messages")
            if isinstance(messages, list) and messages:
                return self._chunk_to_event(messages[-1])
        return None

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, list):
            return "".join(str(item) for item in content if item is not None)
        return str(content)
