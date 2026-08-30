from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.tasks.engine import AsyncTaskEngine
from app.models.tasks import TaskStatus, utc_now
from app.schemas.tasks import TaskStreamRecord
from app.services import tasks as task_service


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OrphanScavengeResult:
    """OrphanScavenger 单次扫描结果。"""

    stale_running_recovered: int = 0
    pending_enqueued: int = 0
    redis_pending_claimed: int = 0
    redis_pending_acked: int = 0


class OrphanScavenger:
    """恢复 pending 孤儿、running 僵尸和 Redis PEL 滞留消息。"""

    def __init__(
        self,
        task_engine: AsyncTaskEngine,
        *,
        consumer_name: str,
        session_maker: Any,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
        limit: int = 100,
    ) -> None:
        self.task_engine = task_engine
        self.consumer_name = f"{consumer_name}-scavenger"
        self.session_maker = session_maker
        self.redis_client = redis_client
        self.stream_name = stream_name
        self.group_name = group_name
        self.limit = max(limit, 1)

    async def run_once(self) -> OrphanScavengeResult:
        """执行一次孤儿任务恢复。"""
        stale_running_recovered = 0
        pending_enqueued = 0
        redis_pending_claimed = 0
        redis_pending_acked = 0

        async with self.session_maker() as session:
            stale_running_recovered = await self.task_engine.recover_stale_running_task_items(
                session,
                limit=self.limit,
            )

        claimed_records = await self._claim_stale_redis_pending_records()
        redis_pending_claimed = len(claimed_records)
        for record in claimed_records:
            if await self._recover_redis_pending_record(record):
                redis_pending_acked += 1

        async with self.session_maker() as session:
            pending_enqueued = await self.task_engine.enqueue_due_pending_task_items(
                session,
                limit=self.limit,
                redis_client=self.redis_client,
                stream_name=self.stream_name,
                group_name=self.group_name,
            )

        return OrphanScavengeResult(
            stale_running_recovered=stale_running_recovered,
            pending_enqueued=pending_enqueued,
            redis_pending_claimed=redis_pending_claimed,
            redis_pending_acked=redis_pending_acked,
        )

    async def _claim_stale_redis_pending_records(self) -> list[TaskStreamRecord]:
        import app.core.tasks.stream as task_stream

        config = self.task_engine.config
        try:
            return await task_stream.claim_stale_task_stream_records(
                self.consumer_name,
                min_idle_ms=int(max(config.stale_running_timeout_seconds, 0) * 1000),
                redis_client=self.redis_client,
                stream_name=self.stream_name or config.stream_name,
                group_name=self.group_name or config.consumer_group,
                count=self.limit,
            )
        except Exception:
            logger.exception("OrphanScavenger 认领 Redis pending 消息失败")
            return []

    async def _recover_redis_pending_record(self, record: TaskStreamRecord) -> bool:
        message = record.message
        should_ack = False
        async with self.session_maker() as session:
            try:
                item = await task_service.get_task_item(session, message.item_public_id)
            except task_service.TaskItemNotFoundError:
                should_ack = True
            else:
                should_ack = await self._recover_existing_item(session, record, item.status)

        if not should_ack:
            return False
        await self._ack(record.stream_id)
        return True

    async def _recover_existing_item(
        self,
        session: AsyncSession,
        record: TaskStreamRecord,
        status: TaskStatus,
    ) -> bool:
        message = record.message
        if status in {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PARTIAL,
            TaskStatus.PAUSED,
        }:
            return True
        if status == TaskStatus.QUEUED:
            try:
                await task_service.recover_queued_task_item_to_pending(session, message.item_public_id)
            except task_service.TaskServiceError:
                await session.rollback()
                return False
            return True
        if status == TaskStatus.PENDING:
            return True
        if status == TaskStatus.RUNNING:
            item = await task_service.get_task_item(session, message.item_public_id)
            if item.heartbeat_at is not None:
                cutoff = utc_now() - timedelta(seconds=max(self.task_engine.config.stale_running_timeout_seconds, 0))
                if item.heartbeat_at > cutoff:
                    return False
            try:
                await task_service.record_task_item_failure(
                    session,
                    message.item_public_id,
                    "task_redis_pending_stale",
                    "Redis pending 消息超时，已由 OrphanScavenger 恢复",
                    item.worker_id,
                    retry_backoff_seconds=self.task_engine.config.worker_retry_backoff_seconds,
                    stream_id=record.stream_id,
                    stage="redis_pending_scavenger",
                )
            except task_service.TaskServiceError:
                await session.rollback()
                return False
            return True
        return False

    async def _ack(self, stream_id: str) -> None:
        try:
            await self.task_engine.ack_task_stream_record(
                stream_id,
                redis_client=self.redis_client,
                stream_name=self.stream_name,
                group_name=self.group_name,
            )
        except Exception:
            logger.exception("OrphanScavenger ACK Redis pending 消息失败：stream_id=%s", stream_id)
