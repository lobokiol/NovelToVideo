"""剧本创作结构化章节事件抽取。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.agent_gateway import ProviderModelGateway


_JSON_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_LIST_SEPARATOR_RE = re.compile(r"[,，、/|；;]+")


@dataclass(frozen=True)
class StructuredEvent:
    """单个章节事件的结构化表示。"""

    summary: str
    characters: tuple[str, ...] = ()
    scenes: tuple[str, ...] = ()
    organizations: tuple[str, ...] = ()
    event_type: str = ""
    conflict: str = ""
    outcome: str = ""
    sequence: int = 1

    def to_dict(self) -> dict[str, Any]:
        """转换为可持久化的 JSON 对象。"""
        return {
            "summary": self.summary,
            "characters": list(self.characters),
            "scenes": list(self.scenes),
            "organizations": list(self.organizations),
            "event_type": self.event_type,
            "conflict": self.conflict,
            "outcome": self.outcome,
            "sequence": self.sequence,
        }


async def extract_chapter_events(
    chapter_text: str,
    *,
    model_id: str,
    gateway: Any | None = None,
    timeout_seconds: float = 2.0,
) -> tuple[StructuredEvent, ...]:
    """调用模型抽取结构化章节事件；失败时返回空元组。"""
    content = str(chapter_text or "").strip()
    resolved_model_id = str(model_id or "").strip()
    if not content or not resolved_model_id:
        return ()

    resolved_timeout = max(0.1, float(timeout_seconds))
    resolved_gateway = gateway or ProviderModelGateway(timeout=resolved_timeout)
    try:
        raw_text = await asyncio.wait_for(
            resolved_gateway.generate_text(
                model_id=resolved_model_id,
                messages=_event_extraction_messages(content),
                temperature=0,
            ),
            timeout=resolved_timeout,
        )
        return parse_chapter_events(raw_text)
    except Exception:
        return ()


def parse_chapter_events(raw_events: Any) -> tuple[StructuredEvent, ...]:
    """解析并校验模型输出的结构化事件 JSON。"""
    payload = _load_event_payload(raw_events)
    raw_items = payload.get("events")
    if not isinstance(raw_items, list):
        raise ValueError("event payload must contain an events array")

    events: list[StructuredEvent] = []
    for fallback_sequence, item in enumerate(raw_items, start=1):
        if not isinstance(item, Mapping):
            continue
        event = _structured_event_from_mapping(item, fallback_sequence=fallback_sequence)
        if event is not None:
            events.append(event)
    return tuple(events)


def events_to_json(events: Sequence[StructuredEvent]) -> str:
    """把结构化事件序列化为稳定 JSON。"""
    return json.dumps({"events": [event.to_dict() for event in events]}, ensure_ascii=False, indent=2)


def _event_extraction_messages(chapter_text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是章节事件结构化抽取器。只输出 JSON 对象，格式为 "
                "{\"events\":[{\"summary\":\"\",\"characters\":[],\"scenes\":[],"
                "\"organizations\":[],\"event_type\":\"\",\"conflict\":\"\","
                "\"outcome\":\"\",\"sequence\":1}]}。不要输出解释。"
            ),
        },
        {"role": "user", "content": chapter_text},
    ]


def _load_event_payload(raw_events: Any) -> dict[str, Any]:
    if isinstance(raw_events, Mapping):
        return dict(raw_events)
    if isinstance(raw_events, list):
        return {"events": raw_events}
    text = str(raw_events or "").strip()
    fence_match = _JSON_CODE_FENCE_RE.match(text)
    if fence_match:
        text = fence_match.group(1).strip()
    payload = json.loads(text)
    if isinstance(payload, list):
        return {"events": payload}
    if not isinstance(payload, dict):
        raise ValueError("event payload must be a JSON object")
    return payload


def _structured_event_from_mapping(
    item: Mapping[str, Any],
    *,
    fallback_sequence: int,
) -> StructuredEvent | None:
    summary = _text_value(item.get("summary") or item.get("title") or item.get("event"))
    conflict = _text_value(item.get("conflict"))
    outcome = _text_value(item.get("outcome") or item.get("result"))
    characters = _string_tuple(item.get("characters") or item.get("roles"))
    scenes = _string_tuple(item.get("scenes") or item.get("locations"))
    organizations = _string_tuple(item.get("organizations") or item.get("orgs"))
    event_type = _text_value(item.get("event_type") or item.get("type"))
    sequence = _positive_int(item.get("sequence") or item.get("index")) or fallback_sequence

    if not any((summary, conflict, outcome, characters, scenes, organizations, event_type)):
        return None
    return StructuredEvent(
        summary=summary or conflict or outcome or event_type,
        characters=characters,
        scenes=scenes,
        organizations=organizations,
        event_type=event_type,
        conflict=conflict,
        outcome=outcome,
        sequence=sequence,
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_items: Sequence[Any] = _LIST_SEPARATOR_RE.split(value)
    elif isinstance(value, Sequence):
        raw_items = value
    else:
        return ()
    items = []
    for item in raw_items:
        text = _text_value(item)
        if text:
            items.append(text)
    return tuple(dict.fromkeys(items))


def _text_value(value: Any) -> str:
    return str(value or "").strip()


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
