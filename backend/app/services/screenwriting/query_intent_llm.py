"""剧本创作 RAG 查询意图的 LLM 解析器。"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.services.agent_gateway import ProviderModelGateway
from app.services.screenwriting.query_intent import (
    ChapterRangeIntent,
    ChapterTailIntent,
    EventSelector,
    RetrievalToolCall,
    RetrievalToolPlan,
    ScreenwritingQueryIntent,
    fallback_tool_plan,
    parse_screenwriting_query_intent,
)


_JSON_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_ALLOWED_TOOL_NAMES = {
    "metadata_lookup",
    "event_json_search",
    "event_vector_search",
    "chapter_vector_search",
    "chapter_text_lookup",
    "lexical_fallback",
}
_ALLOWED_FIELD_SOURCE_TYPES = {
    "project",
    "novel",
    "chapter",
    "art_style",
    "director_manual",
    "event",
}


async def parse_screenwriting_query_intent_with_llm(
    query: str,
    *,
    model_id: str,
    gateway: Any | None = None,
    timeout_seconds: float | None = None,
) -> ScreenwritingQueryIntent:
    """使用模型解析检索意图，失败时回退到本地确定性解析。"""
    fallback_intent = parse_screenwriting_query_intent(query)
    resolved_model_id = str(model_id or "").strip()
    if not resolved_model_id:
        return _fallback_with_failure(fallback_intent, "intent parser skipped: model_id is empty")

    resolved_timeout = float(timeout_seconds if timeout_seconds is not None else 2.0)
    resolved_gateway = gateway or ProviderModelGateway(timeout=resolved_timeout)
    try:
        raw_text = await asyncio.wait_for(
            resolved_gateway.generate_text(
                model_id=resolved_model_id,
                messages=_intent_parser_messages(query),
                temperature=0,
            ),
            timeout=resolved_timeout,
        )
        payload = _load_json_object(raw_text)
        return _intent_from_payload(query, payload, fallback_intent)
    except Exception as exc:
        return _fallback_with_failure(fallback_intent, str(exc))


def _intent_parser_messages(query: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是剧本创作 RAG 的查询意图解析器。只输出一个 JSON 对象，不要输出解释。"
                "可用工具: metadata_lookup, event_json_search, event_vector_search, "
                "chapter_vector_search, chapter_text_lookup, lexical_fallback。"
                "章节选择器支持: absolute_range(start,end), tail(count)。"
                "当用户问最后几章、最新几章、结尾几章时，使用 chapter_tail 或 "
                "chapter_selector={\"type\":\"tail\",\"count\":N}。"
                "当用户询问角色、地点、组织、冲突、结果、高潮等事件要素时，使用 event_selector。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请把用户问题解析为如下 JSON 字段："
                "answer_focus, confidence, chapter_range, chapter_tail, field_lookups, "
                "event_selector, lookup_terms, tools。\n"
                "chapter_range 示例: {\"start_index\":1,\"end_index\":3}。\n"
                "chapter_tail 示例: {\"count\":5}。\n"
                "field_lookups 示例: [{\"source_type\":\"novel\",\"document_markers\":[\"作者\"]}]。\n"
                "field_lookups 的 source_type 只能取: project, novel, chapter, art_style, director_manual, event。\n"
                "event_selector 示例: {\"characters\":[\"张小凡\"],\"scenes\":[\"草庙村\"],"
                "\"event_types\":[\"冲突\"],\"focus\":[\"conflict\",\"outcome\"]}。\n"
                "tools 示例: [{\"tool\":\"metadata_lookup\",\"args\":{},\"priority\":1}]。\n\n"
                f"用户问题: {query}"
            ),
        },
    ]


def _load_json_object(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    fence_match = _JSON_CODE_FENCE_RE.match(text)
    if fence_match:
        text = fence_match.group(1).strip()
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("intent parser output must be a JSON object")
    return loaded


def _intent_from_payload(
    query: str,
    payload: dict[str, Any],
    fallback_intent: ScreenwritingQueryIntent,
) -> ScreenwritingQueryIntent:
    lookup_terms = _string_tuple(payload.get("lookup_terms")) or fallback_intent.lookup_terms
    chapter_range = _chapter_range_from_payload(payload.get("chapter_range")) or fallback_intent.chapter_range
    chapter_tail = _chapter_tail_from_payload(payload) or fallback_intent.chapter_tail
    field_lookups = _field_lookups_from_payload(payload.get("field_lookups")) or fallback_intent.field_lookups
    event_selector = _event_selector_from_payload(payload.get("event_selector")) or fallback_intent.event_selector
    tool_plan = _ensure_required_tools(
        _tool_plan_from_payload(payload, lookup_terms=lookup_terms),
        has_metadata_lookup=chapter_range is not None or chapter_tail is not None or bool(field_lookups),
        has_event_lookup=event_selector is not None,
    )
    return fallback_intent.with_updates(
        lookup_terms=lookup_terms,
        chapter_range=chapter_range,
        chapter_tail=chapter_tail,
        field_lookups=field_lookups,
        event_selector=event_selector,
        tool_plan=tool_plan,
        diagnostics={
            **fallback_intent.diagnostics,
            "intentParser": "llm",
        },
    )


def _tool_plan_from_payload(payload: dict[str, Any], *, lookup_terms: tuple[str, ...]) -> RetrievalToolPlan:
    tools = _tool_calls_from_payload(payload.get("tools"))
    if not tools:
        tools = fallback_tool_plan(
            has_metadata_lookup=bool(payload.get("chapter_range") or payload.get("chapter_tail") or payload.get("field_lookups")),
            has_event_lookup=bool(payload.get("event_selector")),
            lookup_terms=lookup_terms,
        ).tools
    confidence = _float_value(payload.get("confidence"), default=0.0)
    return RetrievalToolPlan(
        tools=tuple(sorted(tools, key=lambda tool: tool.priority)),
        answer_focus=str(payload.get("answer_focus") or "").strip(),
        confidence=max(0.0, min(1.0, confidence)),
        source="llm",
    )


def _ensure_required_tools(
    tool_plan: RetrievalToolPlan,
    *,
    has_metadata_lookup: bool,
    has_event_lookup: bool,
) -> RetrievalToolPlan:
    tools = list(tool_plan.tools)
    tool_names = {tool.tool for tool in tools}
    if has_metadata_lookup and "metadata_lookup" not in tool_names:
        tools.append(RetrievalToolCall(tool="metadata_lookup", priority=0))
    if has_event_lookup and "event_json_search" not in tool_names:
        tools.append(RetrievalToolCall(tool="event_json_search", priority=20))
    return RetrievalToolPlan(
        tools=tuple(sorted(tools, key=lambda tool: tool.priority)),
        answer_focus=tool_plan.answer_focus,
        confidence=tool_plan.confidence,
        source=tool_plan.source,
    )


def _tool_calls_from_payload(value: Any) -> tuple[RetrievalToolCall, ...]:
    if not isinstance(value, list):
        return ()
    calls: list[RetrievalToolCall] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool") or "").strip()
        if tool_name not in _ALLOWED_TOOL_NAMES:
            continue
        args = item.get("args")
        calls.append(
            RetrievalToolCall(
                tool=tool_name,
                args=dict(args) if isinstance(args, dict) else {},
                priority=_int_value(item.get("priority"), default=index),
            )
        )
    return tuple(calls)


def _chapter_range_from_payload(value: Any) -> ChapterRangeIntent | None:
    if not isinstance(value, dict):
        return None
    start_index = _positive_int(value.get("start_index") or value.get("start"))
    end_index = _positive_int(value.get("end_index") or value.get("end"))
    if start_index is None or end_index is None:
        return None
    return ChapterRangeIntent(start_index=start_index, end_index=end_index)


def _chapter_tail_from_payload(payload: dict[str, Any]) -> ChapterTailIntent | None:
    direct = payload.get("chapter_tail")
    if isinstance(direct, dict):
        count = _positive_int(direct.get("count"))
        if count is not None:
            return ChapterTailIntent(count=count)

    for call in _tool_calls_from_payload(payload.get("tools")):
        selector = call.args.get("chapter_selector")
        if isinstance(selector, dict) and selector.get("type") == "tail":
            count = _positive_int(selector.get("count"))
            if count is not None:
                return ChapterTailIntent(count=count)
    return None


def _field_lookups_from_payload(value: Any):
    from app.services.screenwriting.query_intent import FieldLookupIntent

    if not isinstance(value, list):
        return ()
    lookups: list[FieldLookupIntent] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("source_type") or "").strip()
        markers = _string_tuple(item.get("document_markers"))
        if source_type in _ALLOWED_FIELD_SOURCE_TYPES and markers:
            lookups.append(FieldLookupIntent(source_type=source_type, document_markers=markers))
    return tuple(lookups)


def _event_selector_from_payload(value: Any) -> EventSelector | None:
    if not isinstance(value, dict):
        return None
    selector = EventSelector(
        characters=_string_tuple(value.get("characters")),
        scenes=_string_tuple(value.get("scenes")),
        organizations=_string_tuple(value.get("organizations")),
        event_types=_string_tuple(value.get("event_types") or value.get("types")),
        focus=_string_tuple(value.get("focus")),
    )
    if not any(
        (
            selector.characters,
            selector.scenes,
            selector.organizations,
            selector.event_types,
            selector.focus,
        )
    ):
        return None
    return selector


def _fallback_with_failure(intent: ScreenwritingQueryIntent, failure_reason: str) -> ScreenwritingQueryIntent:
    return intent.with_updates(
        tool_plan=fallback_tool_plan(
            has_metadata_lookup=intent.chapter_range is not None or intent.chapter_tail is not None or bool(intent.field_lookups),
            has_event_lookup=intent.event_selector is not None,
            lookup_terms=intent.lookup_terms,
            diagnostics={"intentParserFailure": failure_reason},
        ),
        diagnostics={
            **intent.diagnostics,
            "intentParser": "fallback",
            "intentParserFailure": failure_reason,
        },
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item or "").strip())


def _positive_int(value: Any) -> int | None:
    number = _int_value(value, default=0)
    return number if number > 0 else None


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
