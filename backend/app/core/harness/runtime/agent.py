"""Harness Agent 运行底座与可替换运行时协议。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


class HarnessAgentError(Exception):
    """Harness Agent 执行失败。"""


@dataclass(frozen=True)
class ScriptAgentInput:
    """主 Agent 单次调用输入。"""

    project_public_id: str
    user_public_id: str
    isolation_key: str
    messages: list[dict[str, str]]
    model_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScriptAgentEvent:
    """主 Agent 流式事件。"""

    type: str
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScriptAgentResult:
    """主 Agent 聚合结果。"""

    content: str
    events: list[ScriptAgentEvent]
    structured_response: Any | None = None


class ScriptAgentRuntime(Protocol):
    """主 Agent 可替换运行时协议。"""

    def stream_chat(self, request: ScriptAgentInput) -> AsyncIterator[ScriptAgentEvent]:
        """按事件流执行一次对话。"""


def _structured_response_to_text(structured_response: Any | None) -> str:
    """把结构化响应归一化为可展示文本。"""
    if structured_response is None:
        return ""
    model_dump = getattr(structured_response, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except TypeError:
            dumped = model_dump()
        return _structured_response_to_text(dumped)
    if isinstance(structured_response, str):
        text = structured_response.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                return _structured_response_to_text(json.loads(text))
            except json.JSONDecodeError:
                return text
        return text
    if isinstance(structured_response, dict):
        for key in ("content", "markdown", "text", "output", "answer"):
            value = structured_response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(structured_response, list):
        parts = [_structured_response_to_text(item) for item in structured_response]
        return "\n".join(part for part in parts if part)
    return str(structured_response).strip()


def _event_final_content(event: ScriptAgentEvent) -> str:
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


def _merge_final_content(current_content: str, final_content: str) -> str:
    if not final_content:
        return current_content
    if not current_content:
        return final_content
    if final_content.startswith(current_content):
        return final_content
    if current_content.startswith(final_content):
        return current_content
    return f"{current_content}{final_content}"


class HarnessAgent:
    """主 Agent 门面，向业务层隐藏具体运行时。"""

    def __init__(self, *, runtime: ScriptAgentRuntime) -> None:
        self.runtime = runtime

    def stream_chat(self, request: ScriptAgentInput) -> AsyncIterator[ScriptAgentEvent]:
        return self.runtime.stream_chat(request)

    async def run_chat(self, request: ScriptAgentInput) -> ScriptAgentResult:
        events: list[ScriptAgentEvent] = []
        content_parts: list[str] = []
        structured_response: Any | None = None
        async for event in self.stream_chat(request):
            events.append(event)
            if event.type == "message.delta" and event.content:
                content_parts.append(event.content)
            if event.type == "done":
                final_content = _event_final_content(event)
                if final_content:
                    content_parts = [_merge_final_content("".join(content_parts), final_content)]
                break
            if event.type == "structured_response":
                structured_response = event.data.get("structured_response", event.content or event.data)
                if not content_parts:
                    text = _structured_response_to_text(structured_response)
                    if text:
                        content_parts.append(text)
        return ScriptAgentResult(
            content="".join(content_parts),
            events=events,
            structured_response=structured_response,
        )
