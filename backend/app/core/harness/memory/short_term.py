"""记忆与知识层 · 短期记忆协议与进程内通用实现。

ShortTermMemory 定义会话级运行态的读写与清理抽象；InProcessShortTermMemory 是其
进程内通用实现（isolation_key → 运行态 + 会话级并发锁）。仅在单进程单事件循环内
有效，多 worker 部署需迁移至数据库事实源（行锁/乐观锁）。
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class ShortTermMemory(Protocol):
    """短期（会话）记忆协议。"""

    def load(self, isolation_key: str) -> Any | None:
        """读取会话运行态（不存在返回 None）。"""

    def save(self, isolation_key: str, state: Any) -> None:
        """写入或替换会话运行态。"""

    def reset(self, isolation_key: str) -> None:
        """清空指定会话的运行态。"""


class InProcessShortTermMemory:
    """ShortTermMemory 的进程内实现：会话运行态字典 + 会话级 asyncio 锁。

    会话锁保证同一 isolation_key 的状态操作在事件循环内串行，消除对同一
    运行态的并发读改竞态。
    """

    def __init__(self) -> None:
        self._states: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def session_lock(self, isolation_key: str) -> asyncio.Lock:
        """返回该会话隔离键对应的锁，不存在则惰性创建（创建过程由注册锁保护）。"""
        async with self._registry_lock:
            lock = self._locks.get(isolation_key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[isolation_key] = lock
            return lock

    def load(self, isolation_key: str) -> Any | None:
        """读取会话运行态，不存在返回 None。"""
        return self._states.get(isolation_key)

    def save(self, isolation_key: str, state: Any) -> None:
        """写入或替换会话运行态。"""
        self._states[isolation_key] = state

    def reset(self, isolation_key: str) -> None:
        """清空指定会话的运行态。"""
        self._states.pop(isolation_key, None)