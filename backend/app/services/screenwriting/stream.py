from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def normalize_stream_event(event: Any) -> dict[str, Any]:
    """把服务层流式事件归一化为可 JSON 序列化字典。"""
    if isinstance(event, BaseModel):
        return event.model_dump(by_alias=True, mode="json")
    if isinstance(event, dict):
        return dict(event)
    return {"type": "message.delta", "content": str(event or "")}


def format_ndjson_event(event: Any) -> str:
    """把单个流式事件格式化为 NDJSON 行。"""
    return json.dumps(normalize_stream_event(event), ensure_ascii=False) + "\n"