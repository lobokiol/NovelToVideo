"""RAG 通用文档结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RagDocument:
    """可被 RAG 索引与检索消费的统一文档。"""

    source_id: str
    source_type: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
