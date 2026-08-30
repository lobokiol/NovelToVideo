"""Harness Agent 记忆隔离命名工具。"""

from __future__ import annotations

import hashlib
import re


_UNSAFE_MEMORY_PART_RE = re.compile(r"[^a-zA-Z0-9_-]+")


class HarnessMemoryScope:
    """按 isolation_key 生成 deepagents 记忆文档路径。"""

    def __init__(self, *, memory_root: str = "/memory/harness") -> None:
        self.memory_root = memory_root.strip().rstrip("/") or "/memory/harness"

    def memory_sources(self, isolation_key: str) -> list[str]:
        """返回当前会话隔离的 AGENTS.md 记忆文档路径。"""
        key = isolation_key.strip()
        if not key:
            return []
        return [f"{self.memory_root}/{self._safe_scope_name(key)}/AGENTS.md"]

    @staticmethod
    def _safe_scope_name(isolation_key: str) -> str:
        slug = _UNSAFE_MEMORY_PART_RE.sub("-", isolation_key).strip("-").lower()
        digest = hashlib.sha256(isolation_key.encode("utf-8")).hexdigest()[:12]
        if not slug:
            return digest
        return f"{slug[:80]}-{digest}"
