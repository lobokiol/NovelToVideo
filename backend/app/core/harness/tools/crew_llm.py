"""CrewAI LLM 适配器：把项目模型网关接入 CrewAI 团队成员。

CrewAI 是可选运行时依赖：导入失败时 ProviderGatewayCrewLLM 为 None，
真正的硬依赖校验推迟到团队构建时（runtime/crewai.py）。
"""

from __future__ import annotations

import asyncio
import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from pydantic import ConfigDict, Field as PydanticField

from app.core.harness.runtime.agent import HarnessAgentError
from app.core.harness.tools.adapter import ModelGatewayAdapter
from app.core.harness.tools.chat_model import ProviderGatewayChatModel

try:  # CrewAI 为剧本创作阶段团队的可选运行时依赖。
    from crewai.llms.base_llm import BaseLLM as CrewAIBaseLLM, llm_call_context as crewai_llm_call_context
except ImportError:  # pragma: no cover - 运行环境导入守卫。
    CrewAIBaseLLM = None  # type: ignore[assignment,misc]
    crewai_llm_call_context = None  # type: ignore[assignment]


@dataclass
class _CrewAIStageAbortContext:
    """阶段团队熔断上下文：任一成员模型调用失败后阻断后续成员调用。"""

    error: BaseException | None = None


_CREWAI_STAGE_ABORT_CONTEXT: ContextVar[_CrewAIStageAbortContext | None] = ContextVar(
    "crewai_stage_abort_context",
    default=None,
)


if CrewAIBaseLLM is not None:

    class ProviderGatewayCrewLLM(CrewAIBaseLLM):  # type: ignore[misc,valid-type]
        """基于项目模型网关的 CrewAI LLM 适配器。

        stream=True 时逐增量经基类 _emit_stream_chunk_event 发布到 CrewAI
        事件总线（供 crew 流式输出消费），返回值仍为拼接后的完整文本
        （CrewAI 任务链需要完整结果）。
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        adapter: ModelGatewayAdapter = PydanticField(exclude=True)
        stream: bool = False
        request_options: dict[str, Any] = PydanticField(default_factory=dict)

        async def acall(
            self,
            messages: str | list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            callbacks: list[Any] | None = None,
            available_functions: dict[str, Any] | None = None,
            from_task: Any | None = None,
            from_agent: Any | None = None,
            response_model: type[Any] | None = None,
        ) -> str | Any:
            abort_context = _CREWAI_STAGE_ABORT_CONTEXT.get()
            if abort_context is not None and abort_context.error is not None:
                raise HarnessAgentError(
                    "模型调用已失败，本轮阶段生成已停止，请确认后重新发送。"
                ) from abort_context.error
            try:
                call_context = crewai_llm_call_context if crewai_llm_call_context is not None else contextlib.nullcontext
                with call_context():
                    request_options = dict(self.request_options or {})
                    if getattr(self, "stream", False):
                        content_parts: list[str] = []
                        async for chunk in self.adapter.generate_stream(
                            model_id=self.model,
                            messages=self._normalize_messages(messages),
                            **request_options,
                        ):
                            text = str(chunk or "")
                            if not text:
                                continue
                            content_parts.append(text)
                            self._emit_stream_chunk_event(
                                text,
                                from_task=from_task,
                                from_agent=from_agent,
                            )
                        return "".join(content_parts)
                    raw_response = await self.adapter.generate_response(
                        model_id=self.model,
                        messages=self._normalize_messages(messages),
                        **request_options,
                    )
                    if isinstance(raw_response, str):
                        return raw_response
                    if isinstance(raw_response, dict):
                        return ProviderGatewayChatModel._extract_response_content(raw_response)
                    return str(raw_response or "")
            except Exception as exc:
                if abort_context is not None and abort_context.error is None:
                    abort_context.error = exc
                raise

        def call(
            self,
            messages: str | list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            callbacks: list[Any] | None = None,
            available_functions: dict[str, Any] | None = None,
            from_task: Any | None = None,
            from_agent: Any | None = None,
            response_model: type[Any] | None = None,
        ) -> str | Any:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(
                    self.acall(
                        messages,
                        tools=tools,
                        callbacks=callbacks,
                        available_functions=available_functions,
                        from_task=from_task,
                        from_agent=from_agent,
                        response_model=response_model,
                    )
                )
            raise HarnessAgentError("ProviderGatewayCrewLLM 同步调用不支持在运行中的事件循环内执行")

        @staticmethod
        def _normalize_messages(messages: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
            if isinstance(messages, str):
                return [{"role": "user", "content": messages}]
            normalized: list[dict[str, Any]] = []
            for message in messages:
                role = str(message.get("role") or "user")
                content = message.get("content") or ""
                normalized.append({"role": role, "content": str(content)})
            return normalized

else:  # pragma: no cover - 仅用于导入保护。
    ProviderGatewayCrewLLM = None  # type: ignore[assignment,misc]