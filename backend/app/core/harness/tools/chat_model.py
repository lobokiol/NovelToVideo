"""LangChain ChatModel 适配器。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.utils import convert_to_openai_messages
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field as PydanticField

from app.core.harness.runtime.agent import HarnessAgentError
from app.core.harness.tools.adapter import ModelGatewayAdapter


class ProviderGatewayChatModel(BaseChatModel):
    """把项目 ProviderModelGateway 包装为 LangChain ChatModel。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    adapter: ModelGatewayAdapter = PydanticField(exclude=True)
    model_id: str | None = None
    provider_key: str | None = None
    input_values: dict[str, str] | None = None

    @property
    def _llm_type(self) -> str:
        return "provider-gateway"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider_key": self.provider_key,
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """把 LangChain 工具绑定转换为 OpenAI-compatible tools 参数。"""
        request_kwargs = {
            **kwargs,
            "tools": [convert_to_openai_tool(tool) for tool in tools],
        }
        if tool_choice is not None:
            request_kwargs["tool_choice"] = _normalize_tool_choice(tool_choice)
        return self.bind(**request_kwargs)

    def _convert_messages(self, messages: list[BaseMessage]) -> list[dict[str, Any]]:
        return convert_to_openai_messages(messages)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        request_kwargs = self._request_kwargs(stop=stop, kwargs=kwargs)
        raw_response = await self.adapter.generate_response(
            messages=self._convert_messages(messages),
            model_id=self.model_id,
            provider_key=self.provider_key,
            input_values=self.input_values,
            **request_kwargs,
        )
        return ChatResult(
            generations=[ChatGeneration(message=self._response_to_ai_message(raw_response))],
            llm_output={"raw_response": raw_response},
        )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        request_kwargs = self._request_kwargs(stop=stop, kwargs=kwargs)
        produced = False
        async for chunk in self.adapter.generate_stream(
            messages=self._convert_messages(messages),
            model_id=self.model_id,
            provider_key=self.provider_key,
            input_values=self.input_values,
            **request_kwargs,
        ):
            produced = True
            yield ChatGenerationChunk(message=AIMessageChunk(content=chunk))
        if not produced:
            # 流式通道零产出（如模型整轮只输出工具调用增量、网关只透传文本）时，
            # 回退非流式调用，避免 LangChain 抛 "No generations found in stream"。
            result = await self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            message = result.generations[0].message
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=message.content,
                    additional_kwargs=dict(message.additional_kwargs),
                    response_metadata=dict(message.response_metadata),
                )
            )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs))
        raise HarnessAgentError("ProviderGatewayChatModel 同步调用不支持在运行中的事件循环内执行")

    @staticmethod
    def _request_kwargs(*, stop: list[str] | None, kwargs: dict[str, Any]) -> dict[str, Any]:
        request_kwargs = dict(kwargs)
        if stop is not None:
            request_kwargs["stop"] = stop
        return request_kwargs

    @staticmethod
    def _response_to_ai_message(raw_response: Any) -> AIMessage:
        if isinstance(raw_response, AIMessage):
            return raw_response
        if isinstance(raw_response, str):
            return AIMessage(content=raw_response)
        if isinstance(raw_response, dict):
            content = ProviderGatewayChatModel._extract_response_content(raw_response)
            return AIMessage(content=content, response_metadata={"raw_response": raw_response})
        return AIMessage(content=str(raw_response))

    @staticmethod
    def _extract_response_content(raw_response: dict[str, Any]) -> str:
        for key in ("output_text", "text"):
            value = raw_response.get(key)
            if isinstance(value, str):
                return value
        choices = raw_response.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                for key in ("message", "delta"):
                    message = choice.get(key)
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str):
                            return content
                text = choice.get("text")
                if isinstance(text, str):
                    return text
        return ""


def _normalize_tool_choice(tool_choice: str) -> str | dict[str, dict[str, str] | str]:
    normalized = tool_choice.strip()
    if normalized == "any":
        return "required"
    if normalized in {"auto", "none", "required"}:
        return normalized
    return {"type": "function", "function": {"name": normalized}}