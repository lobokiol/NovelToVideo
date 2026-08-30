from __future__ import annotations

import asyncio
import inspect
import logging
import os
import socket
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.tasks.engine import (
    AsyncTaskEngine,
    TaskHandler,
    TaskHandlerFailure,
    TaskHandlerRegistry,
    TaskHandlerResult,
    default_async_task_engine,
    default_task_handler_registry,
)
from app.core.tasks.scavenger import OrphanScavenger
from app.models.tasks import TaskItem, TaskJob, TaskStatus
from app.schemas.tasks import TaskStreamMessage, TaskStreamRecord


logger = logging.getLogger(__name__)


TASK_STATUS_LABELS: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "待处理",
    TaskStatus.QUEUED: "已入队",
    TaskStatus.RUNNING: "运行中",
    TaskStatus.SUCCEEDED: "成功",
    TaskStatus.FAILED: "失败",
    TaskStatus.CANCELLED: "已取消",
    TaskStatus.PARTIAL: "部分成功",
    TaskStatus.PAUSED: "已暂停",
}


class TaskWorkerServiceError(Exception):
    """异步任务 Worker 服务层基础异常。"""


@dataclass(frozen=True)
class TaskWorkerContext:
    """异步任务处理器上下文。"""

    session: AsyncSession
    record: TaskStreamRecord
    worker_id: str

    @property
    def message(self) -> TaskStreamMessage:
        """返回当前 Redis Stream 消息。"""
        return self.record.message


class TaskWorker:
    """通用异步任务 Worker。"""

    def __init__(
        self,
        *,
        consumer_name: str | None = None,
        registry: TaskHandlerRegistry | None = None,
        session_maker: Any | None = None,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
        batch_size: int = 1,
        block_ms: int | None = 5000,
        idle_sleep_seconds: float = 0.5,
        max_concurrency: int = 1,
        task_timeout_seconds: float | None = None,
        task_log_enabled: bool = True,
        orphan_scavenger_interval_seconds: float = 30.0,
        task_engine: Any | None = None,
    ) -> None:
        self.consumer_name = consumer_name or _default_consumer_name()
        self.registry = registry or default_task_handler_registry
        self.session_maker = session_maker
        self.redis_client = redis_client
        self.stream_name = stream_name
        self.group_name = group_name
        self.batch_size = max(batch_size, 1)
        self.block_ms = block_ms
        self.idle_sleep_seconds = max(idle_sleep_seconds, 0)
        self.max_concurrency = max(max_concurrency, 1)
        self.task_timeout_seconds = task_timeout_seconds
        self.task_log_enabled = task_log_enabled
        self.orphan_scavenger_interval_seconds = max(orphan_scavenger_interval_seconds, 0)
        self._last_orphan_scavenge_at = 0.0
        self._orphan_scavenger: OrphanScavenger | None = None
        if task_engine is None:
            raise TaskWorkerServiceError("TaskWorker 必须传入 task_engine")
        self.task_engine = task_engine

    async def process_once(self) -> int:
        """读取并处理一批异步任务消息。"""
        await self._maybe_scavenge_orphans()
        records = await self.task_engine.read_task_stream_records(
            self.consumer_name,
            redis_client=self.redis_client,
            stream_name=self.stream_name,
            group_name=self.group_name,
            count=self.batch_size,
            block_ms=self.block_ms,
        )
        if self.max_concurrency == 1:
            for record in records:
                await self.process_record(record)
            return len(records)
        semaphore = asyncio.Semaphore(self.max_concurrency)
        await asyncio.gather(*(self._process_record_with_limit(record, semaphore) for record in records))
        return len(records)

    async def process_record(self, record: TaskStreamRecord) -> None:
        """处理单条 Redis Stream 任务消息。"""
        started_at = time.perf_counter()
        message = record.message
        handler = self.registry.get(message.task_type, message.item_type)
        self._log_task_event(
            logging.INFO,
            "收到任务消息",
            "message_received",
            record,
            message,
        )
        async with self._open_session() as session:
            if handler is None:
                started = await self.task_engine.mark_task_item_running(
                    session,
                    message.item_public_id,
                    self.consumer_name,
                )
                if not started:
                    acked = await self._ack(record.stream_id)
                    self._log_task_event(
                        logging.INFO,
                        "任务跳过：抢占失败或任务不可执行",
                        "claim_skipped",
                        record,
                        message,
                        started_at=started_at,
                        extra_fields=[("ACK", "ack", acked)],
                    )
                    return
                acked = await self._mark_item_failed_and_ack(
                    session,
                    record,
                    "task_handler_not_found",
                    f"未注册任务处理器：{message.item_type or message.task_type}",
                    stage="handler_lookup",
                )
                self._log_task_event(
                    logging.WARNING,
                    "任务处理失败：未注册处理器",
                    "handler_not_found",
                    record,
                    message,
                    started_at=started_at,
                    extra_fields=[
                        ("处理器", "handler", message.item_type or message.task_type),
                        ("ACK", "ack", acked),
                    ],
                )
                return

            started = await self.task_engine.mark_task_item_running(
                session,
                message.item_public_id,
                self.consumer_name,
            )
            if not started:
                acked = await self._ack(record.stream_id)
                self._log_task_event(
                    logging.INFO,
                    "任务跳过：抢占失败或任务不可执行",
                    "claim_skipped",
                    record,
                    message,
                    started_at=started_at,
                    extra_fields=[("ACK", "ack", acked)],
                )
                return
            self._log_task_event(
                logging.INFO,
                "任务开始执行",
                "task_started",
                record,
                message,
                extra_fields=[("处理器", "handler", _handler_name(handler))],
            )

            context = TaskWorkerContext(
                session=session,
                record=record,
                worker_id=self.consumer_name,
            )
            heartbeat_task = self._start_heartbeat(message.item_public_id)
            try:
                result = await _run_handler(handler, context, timeout_seconds=self.task_timeout_seconds)
            except asyncio.TimeoutError:
                await session.rollback()
                await self._stop_heartbeat(heartbeat_task)
                acked = await self._mark_item_failed_and_ack(
                    session,
                    record,
                    "task_handler_timeout",
                    f"任务处理超时：{self.task_timeout_seconds}秒",
                    stage="handler_timeout",
                )
                self._log_task_event(
                    logging.ERROR,
                    "任务执行超时",
                    "task_timeout",
                    record,
                    message,
                    started_at=started_at,
                    exc_info=True,
                    extra_fields=[
                        ("超时时间", "timeout", f"{self.task_timeout_seconds}s"),
                        ("错误码", "error_code", "task_handler_timeout"),
                        ("ACK", "ack", acked),
                    ],
                )
                return
            except TaskHandlerFailure as exc:
                await session.rollback()
                await self._stop_heartbeat(heartbeat_task)
                acked = await self._mark_item_failed_and_ack(
                    session,
                    record,
                    exc.error_code,
                    exc.error_message,
                    stage="handler_failure",
                    result=exc.result,
                    retryable=exc.retryable,
                )
                self._log_task_event(
                    logging.WARNING,
                    "任务处理器声明业务失败",
                    "task_handler_failure",
                    record,
                    message,
                    started_at=started_at,
                    exc_info=True,
                    extra_fields=[
                        ("错误", "error", exc.error_message),
                        ("错误码", "error_code", exc.error_code),
                        ("ACK", "ack", acked),
                    ],
                )
                return
            except Exception as exc:
                await session.rollback()
                await self._stop_heartbeat(heartbeat_task)
                acked = await self._mark_item_failed_and_ack(
                    session,
                    record,
                    "task_handler_error",
                    str(exc),
                    stage="handler_error",
                )
                self._log_task_event(
                    logging.ERROR,
                    "任务执行异常",
                    "task_error",
                    record,
                    message,
                    started_at=started_at,
                    exc_info=True,
                    extra_fields=[
                        ("错误", "error", str(exc)),
                        ("错误码", "error_code", "task_handler_error"),
                        ("ACK", "ack", acked),
                    ],
                )
                return

            await self._stop_heartbeat(heartbeat_task)
            try:
                await self.task_engine.mark_task_item_succeeded(
                    session,
                    message.item_public_id,
                    result or {},
                    self.consumer_name,
                )
            except Exception as exc:
                await session.rollback()
                await self._create_writeback_dead_letter(
                    record,
                    stage="writeback_success",
                    error_code="task_success_writeback_error",
                    error_message=str(exc),
                    result=result or {},
                )
                logger.exception(
                    "任务成功结果写回失败，已尝试写入死信记录：stream_id=%s item_public_id=%s",
                    record.stream_id,
                    message.item_public_id,
                )
                return
            acked = await self._ack(record.stream_id)
            self._log_task_event(
                logging.INFO,
                "任务执行成功",
                "task_succeeded",
                record,
                message,
                started_at=started_at,
                extra_fields=[
                    ("ACK", "ack", acked),
                    ("结果", "result", _result_summary(result)),
                ],
            )

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """持续消费异步任务消息。"""
        in_flight: set[asyncio.Task[None]] = set()
        try:
            while stop_event is None or not stop_event.is_set() or in_flight:
                self._discard_done_tasks(in_flight)
                if stop_event is not None and stop_event.is_set():
                    if in_flight:
                        await self._wait_for_any_record(in_flight)
                    continue

                if len(in_flight) < self.max_concurrency:
                    started = await self._start_available_records(in_flight)
                    if started > 0:
                        continue
                    if self.idle_sleep_seconds > 0:
                        await asyncio.sleep(self.idle_sleep_seconds)
                    continue

                await self._maybe_scavenge_orphans()
                await self._wait_for_any_record(in_flight)
        except asyncio.CancelledError:
            for task in in_flight:
                task.cancel()
            if in_flight:
                await asyncio.gather(*in_flight, return_exceptions=True)
            raise

    async def _process_record_with_limit(
        self,
        record: TaskStreamRecord,
        semaphore: asyncio.Semaphore,
    ) -> None:
        async with semaphore:
            await self.process_record(record)

    async def _start_available_records(self, in_flight: set[asyncio.Task[None]]) -> int:
        """按空闲并发槽位读取并启动任务消息。"""
        capacity = max(0, self.max_concurrency - len(in_flight))
        if capacity <= 0:
            return 0
        await self._maybe_scavenge_orphans()
        records = await self.task_engine.read_task_stream_records(
            self.consumer_name,
            redis_client=self.redis_client,
            stream_name=self.stream_name,
            group_name=self.group_name,
            count=min(self.batch_size, capacity),
            block_ms=self.block_ms,
        )
        for record in records:
            in_flight.add(asyncio.create_task(self._process_record_background(record)))
        return len(records)

    async def _process_record_background(self, record: TaskStreamRecord) -> None:
        """后台处理任务消息，避免单条异常终止 Worker 主循环。"""
        try:
            await self.process_record(record)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("任务后台处理异常：stream_id=%s", record.stream_id)

    async def _wait_for_any_record(self, in_flight: set[asyncio.Task[None]]) -> None:
        if not in_flight:
            return
        done, _ = await asyncio.wait(in_flight, return_when=asyncio.FIRST_COMPLETED)
        in_flight.difference_update(done)

    def _discard_done_tasks(self, in_flight: set[asyncio.Task[None]]) -> None:
        done = {task for task in in_flight if task.done()}
        in_flight.difference_update(done)

    def _start_heartbeat(self, item_public_id: str) -> asyncio.Task[None] | None:
        interval = self.task_engine.config.worker_heartbeat_interval_seconds
        if interval <= 0:
            return None
        return asyncio.create_task(self._run_heartbeat(item_public_id))

    async def _run_heartbeat(self, item_public_id: str) -> None:
        interval = self.task_engine.config.worker_heartbeat_interval_seconds
        while interval > 0:
            await asyncio.sleep(interval)
            try:
                async with self._open_session() as session:
                    alive = await self.task_engine.heartbeat_task_item(
                        session,
                        item_public_id,
                        self.consumer_name,
                    )
            except Exception:
                logger.exception("任务心跳刷新失败：item_public_id=%s", item_public_id)
                return
            if not alive:
                logger.warning("任务心跳停止：任务已不再由当前 Worker 运行，item_public_id=%s", item_public_id)
                return

    async def _stop_heartbeat(self, heartbeat_task: asyncio.Task[None] | None) -> None:
        if heartbeat_task is None:
            return
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            return

    async def _maybe_scavenge_orphans(self) -> None:
        if self.orphan_scavenger_interval_seconds <= 0:
            return
        now = time.monotonic()
        if now - self._last_orphan_scavenge_at < self.orphan_scavenger_interval_seconds:
            return
        self._last_orphan_scavenge_at = now
        if self._orphan_scavenger is None:
            self._orphan_scavenger = OrphanScavenger(
                self.task_engine,
                consumer_name=self.consumer_name,
                session_maker=self._session_maker(),
                redis_client=self.redis_client,
                stream_name=self.stream_name,
                group_name=self.group_name,
                limit=max(self.batch_size, 100),
            )
        try:
            result = await self._orphan_scavenger.run_once()
        except Exception:
            logger.exception("OrphanScavenger 扫描失败")
            return
        logger.info(
            "OrphanScavenger 扫描完成：stale_running=%s pending_enqueued=%s redis_claimed=%s redis_acked=%s",
            result.stale_running_recovered,
            result.pending_enqueued,
            result.redis_pending_claimed,
            result.redis_pending_acked,
        )

    async def _mark_item_failed_and_ack(
        self,
        session: AsyncSession,
        record: TaskStreamRecord,
        error_code: str,
        error_message: str,
        *,
        stage: str,
        result: dict[str, Any] | None = None,
        retryable: bool = True,
    ) -> int | None:
        try:
            await self._mark_item_failed(
                session,
                record.message.item_public_id,
                error_code,
                error_message,
                stream_id=record.stream_id,
                stage=stage,
                result=result,
                retryable=retryable,
            )
        except Exception as exc:
            await session.rollback()
            await self._create_writeback_dead_letter(
                record,
                stage=f"writeback_{stage}",
                error_code="task_failure_writeback_error",
                error_message=str(exc),
                result=result,
            )
            logger.exception(
                "任务失败状态写回失败，已尝试写入死信记录：stream_id=%s item_public_id=%s",
                record.stream_id,
                record.message.item_public_id,
            )
            return None
        return await self._ack(record.stream_id)

    async def _create_writeback_dead_letter(
        self,
        record: TaskStreamRecord,
        *,
        stage: str,
        error_code: str,
        error_message: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        message = record.message
        try:
            async with self._open_session() as session:
                await self.task_engine.create_task_dead_letter(
                    session,
                    job_public_id=message.job_public_id,
                    item_public_id=message.item_public_id,
                    task_type=message.task_type,
                    item_type=message.item_type,
                    queue_name=message.queue_name,
                    stream_id=record.stream_id,
                    stage=stage,
                    worker_id=self.consumer_name,
                    error_code=error_code,
                    error_message=error_message,
                    payload=message.payload,
                    result=result or {},
                )
        except Exception:
            logger.exception(
                "任务写回异常的死信记录创建失败：stream_id=%s item_public_id=%s",
                record.stream_id,
                message.item_public_id,
            )

    async def _mark_item_failed(
        self,
        session: AsyncSession,
        item_public_id: str,
        error_code: str,
        error_message: str,
        *,
        stream_id: str = "",
        stage: str = "handler",
        result: dict[str, Any] | None = None,
        retryable: bool = True,
    ) -> None:
        await self.task_engine.mark_task_item_failed(
            session,
            item_public_id,
            error_code,
            error_message,
            self.consumer_name,
            stream_id=stream_id,
            stage=stage,
            result=result,
            retryable=retryable,
        )

    async def _ack(self, stream_id: str) -> int:
        return await self.task_engine.ack_task_stream_record(
            stream_id,
            redis_client=self.redis_client,
            stream_name=self.stream_name,
            group_name=self.group_name,
        )

    def _session_maker(self) -> Any:
        if self.session_maker is None:
            self.session_maker = _default_session_maker()
        return self.session_maker

    def _open_session(self) -> Any:
        return self._session_maker()()

    def _log_task_event(
        self,
        level: int,
        event: str,
        event_code: str,
        record: TaskStreamRecord,
        message: TaskStreamMessage,
        *,
        started_at: float | None = None,
        extra_fields: list[tuple[str, str, Any]] | None = None,
        exc_info: bool = False,
    ) -> None:
        if not self.task_log_enabled:
            return
        logger.log(
            level,
            _format_task_log_event(
                event,
                event_code,
                record,
                message,
                self.consumer_name,
                started_at=started_at,
                extra_fields=extra_fields,
            ),
            exc_info=exc_info,
        )


def create_task_worker(
    task_engine: AsyncTaskEngine | None = None,
    *,
    consumer_name: str | None = None,
    session_maker: Any | None = None,
    redis_client: Any | None = None,
    stream_name: str | None = None,
    group_name: str | None = None,
    batch_size: int | None = None,
    block_ms: int | None = None,
    idle_sleep_seconds: float | None = None,
    max_concurrency: int | None = None,
    task_timeout_seconds: float | None = None,
    task_log_enabled: bool | None = None,
    orphan_scavenger_interval_seconds: float | None = None,
) -> TaskWorker:
    """基于异步任务引擎创建通用 Worker。"""
    engine = task_engine or default_async_task_engine
    config = engine.config
    return TaskWorker(
        consumer_name=consumer_name or config.worker_consumer_name,
        registry=engine.registry,
        session_maker=_coalesce(session_maker, engine.session_maker),
        redis_client=_coalesce(redis_client, engine.redis_client),
        stream_name=_coalesce(stream_name, config.stream_name),
        group_name=_coalesce(group_name, config.consumer_group),
        batch_size=batch_size if batch_size is not None else config.worker_batch_size,
        block_ms=block_ms if block_ms is not None else config.worker_block_ms,
        idle_sleep_seconds=(
            idle_sleep_seconds
            if idle_sleep_seconds is not None
            else config.worker_idle_sleep_seconds
        ),
        max_concurrency=max_concurrency if max_concurrency is not None else config.worker_max_concurrency,
        task_timeout_seconds=(
            task_timeout_seconds
            if task_timeout_seconds is not None
            else config.worker_task_timeout_seconds
        ),
        task_log_enabled=(
            task_log_enabled
            if task_log_enabled is not None
            else config.worker_log_enabled
        ),
        orphan_scavenger_interval_seconds=(
            orphan_scavenger_interval_seconds
            if orphan_scavenger_interval_seconds is not None
            else config.orphan_scavenger_interval_seconds
        ),
        task_engine=engine,
    )


async def format_task_worker_status(worker: TaskWorker) -> str:
    """生成类似 Celery 启动面板的 Worker 运行状态文本。"""
    config = worker.task_engine.config
    stream_name = worker.stream_name or config.stream_name
    group_name = worker.group_name or config.consumer_group
    registered_tasks = worker.registry.keys()
    task_modules = list(config.modules)

    lines = [
        "",
        "================= 异步任务 Worker(Async Task Worker) =================",
        f"Worker 标识(worker):        {worker.consumer_name}",
        f"进程 ID(pid):               {os.getpid()}",
        f"主机名(hostname):           {socket.gethostname()}",
        f"Stream(stream):             {stream_name}",
        f"消费组(group):              {group_name}",
        f"并发数(concurrency):        {worker.max_concurrency}",
        f"批量读取数(batch_size):     {worker.batch_size}",
        f"阻塞读取(block_ms):         {_format_optional(worker.block_ms, suffix='ms')}",
        f"空闲休眠(idle_sleep):       {worker.idle_sleep_seconds}s",
        f"任务超时(task_timeout):     {_format_optional(worker.task_timeout_seconds, suffix='s')}",
        f"任务日志(task_log):         {_format_enabled(worker.task_log_enabled)}",
        f"心跳间隔(heartbeat):        {config.worker_heartbeat_interval_seconds}s",
        f"孤儿扫描(orphan_scan):      {worker.orphan_scavenger_interval_seconds}s",
        f"最大重试(max_retries):      {config.worker_max_retries}",
        f"重试退避(retry_backoff):    {config.worker_retry_backoff_seconds}s",
        f"僵尸判定(stale_after):      {config.stale_running_timeout_seconds}s",
        "",
        "[注册任务模块(modules)]",
        *_format_list(task_modules),
        "",
        "[已注册任务(registered tasks)]",
        *_format_list(registered_tasks),
        "",
        "[Redis Stream(redis stream)]",
        *await _format_redis_stream_status(worker, stream_name, group_name),
        "",
        "[数据库任务(database tasks)]",
        *await _format_database_task_status(worker),
        "=====================================================",
        "",
    ]
    return "\n".join(lines)


async def print_task_worker_status(worker: TaskWorker) -> None:
    """打印 Worker 启动状态。"""
    print(await format_task_worker_status(worker), flush=True)


async def _run_handler(
    handler: TaskHandler,
    context: TaskWorkerContext,
    *,
    timeout_seconds: float | None = None,
) -> TaskHandlerResult:
    result = handler(context)
    if inspect.isawaitable(result):
        if timeout_seconds is not None and timeout_seconds > 0:
            return await asyncio.wait_for(result, timeout=timeout_seconds)
        return await result
    return result


def _default_consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def _default_session_maker() -> Any:
    from app.core.database import async_session_maker

    return async_session_maker


def _coalesce(value: Any | None, default: Any) -> Any:
    return value if value is not None else default


def _elapsed_seconds(started_at: float) -> float:
    return time.perf_counter() - started_at


def _handler_name(handler: TaskHandler) -> str:
    module = getattr(handler, "__module__", "")
    name = getattr(handler, "__qualname__", getattr(handler, "__name__", repr(handler)))
    return f"{module}.{name}" if module else str(name)


def _result_summary(result: TaskHandlerResult) -> str:
    if result is None:
        return "None"
    if not isinstance(result, dict):
        return type(result).__name__
    keys = sorted(str(key) for key in result.keys())
    return f"dict(keys={keys})"


def _format_task_log_event(
    event: str,
    event_code: str,
    record: TaskStreamRecord,
    message: TaskStreamMessage,
    worker_id: str,
    *,
    started_at: float | None = None,
    extra_fields: list[tuple[str, str, Any]] | None = None,
) -> str:
    fields: list[tuple[str, str, Any]] = [
        ("事件", "event", event),
        ("事件代码", "event_code", event_code),
        ("Stream ID", "stream_id", record.stream_id),
        ("任务 ID", "job_public_id", message.job_public_id),
        ("子项 ID", "item_public_id", message.item_public_id),
        ("任务类型", "task_type", message.task_type),
        ("子项类型", "item_type", message.item_type or "-"),
        ("队列", "queue", message.queue_name),
        ("Worker", "worker", worker_id),
    ]
    if started_at is not None:
        fields.append(("耗时", "elapsed", f"{_elapsed_seconds(started_at):.3f}s"))
    if extra_fields:
        fields.extend(extra_fields)

    width = max(len(f"{zh}({en})") for zh, en, _ in fields)
    lines = ["", "---------------- 任务日志(Task Log) ----------------"]
    for zh, en, value in fields:
        label = f"{zh}({en})"
        padding = " " * max(width - len(label) + 1, 1)
        lines.append(f"{label}:{padding}{value}")
    lines.append("----------------------------------------------------")
    return "\n".join(lines)


async def _format_redis_stream_status(
    worker: TaskWorker,
    stream_name: str,
    group_name: str,
) -> list[str]:
    try:
        from app.core.database import redis_client as default_redis_client
        from app.core.tasks.stream import ensure_task_stream_group

        client = worker.redis_client or default_redis_client
        await ensure_task_stream_group(client, stream_name=stream_name, group_name=group_name)
        stream_info = await client.xinfo_stream(stream_name)
        groups = await client.xinfo_groups(stream_name)
        consumers = await client.xinfo_consumers(stream_name, group_name)
        pending = await client.xpending(stream_name, group_name)
    except Exception as exc:
        return [f"错误(error):                {type(exc).__name__}: {exc}"]

    group_info = _find_redis_named_record(groups, group_name)
    pending_count = _redis_value(pending, "pending", 0)
    lines = [
        f"消息长度(length):          {_redis_value(stream_info, 'length', 0)}",
        f"消费组数(groups):          {_redis_value(stream_info, 'groups', 0)}",
        f"最新消息 ID(last_id):      {_redis_value(stream_info, 'last-generated-id', '-')}",
        f"组内待确认(group_pending): {_redis_value(group_info, 'pending', 0)}",
        f"组内滞后(group_lag):       {_redis_value(group_info, 'lag', '-')}",
        f"PEL 待确认(pel_pending):   {pending_count}",
        f"消费者数(consumers):       {len(consumers)}",
    ]
    if consumers:
        lines.append("消费者列表(consumer_list):")
        for consumer in consumers:
            lines.append(
                "  - "
                f"{_redis_value(consumer, 'name', '-')}: "
                f"待确认(pending)={_redis_value(consumer, 'pending', 0)}, "
                f"空闲毫秒(idle_ms)={_redis_value(consumer, 'idle', '-')}"
            )
    return lines


async def _format_database_task_status(worker: TaskWorker) -> list[str]:
    try:
        async with worker._open_session() as session:
            job_counts = await _count_task_statuses(session, TaskJob)
            item_counts = await _count_task_statuses(session, TaskItem)
            running_items = await _list_running_task_items(session)
    except Exception as exc:
        return [f"错误(error):                {type(exc).__name__}: {exc}"]

    lines = [
        f"任务(jobs):                {_format_status_counts(job_counts)}",
        f"子项(items):               {_format_status_counts(item_counts)}",
    ]
    if running_items:
        lines.append("运行中子项(running_items):")
        for item in running_items:
            lines.append(
                "  - "
                f"{item.public_id} "
                f"类型(type)={item.item_type or '-'} "
                f"Worker(worker)={item.worker_id or '-'} "
                f"尝试(attempt)={item.attempt_count}/{item.max_attempts}"
            )
    return lines


async def _count_task_statuses(session: AsyncSession, model: Any) -> dict[TaskStatus, int]:
    statement = (
        select(model.status, func.count())
        .where(model.disabled_at.is_(None))
        .group_by(model.status)
    )
    result = await session.exec(statement)
    counts: dict[TaskStatus, int] = {}
    for raw_status, count in result.all():
        try:
            status = raw_status if isinstance(raw_status, TaskStatus) else TaskStatus(str(raw_status))
        except ValueError:
            continue
        counts[status] = int(count)
    return counts


async def _list_running_task_items(session: AsyncSession, *, limit: int = 10) -> list[TaskItem]:
    statement = (
        select(TaskItem)
        .where(TaskItem.status == TaskStatus.RUNNING, TaskItem.disabled_at.is_(None))
        .order_by(TaskItem.updated_at.desc(), TaskItem.id.desc())
        .limit(limit)
    )
    result = await session.exec(statement)
    return list(result.all())


def _format_status_counts(counts: dict[TaskStatus, int]) -> str:
    parts = [f"{TASK_STATUS_LABELS.get(status, status.value)}={counts.get(status, 0)}" for status in TaskStatus]
    return ", ".join(parts)


def _format_list(values: list[str]) -> list[str]:
    if not values:
        return ["  - （无）"]
    return [f"  - {value}" for value in values]


def _format_optional(value: Any | None, *, suffix: str = "") -> str:
    if value is None:
        return "无"
    return f"{value}{suffix}"


def _format_enabled(value: bool) -> str:
    return "开启(enabled)" if value else "关闭(disabled)"


def _find_redis_named_record(records: list[Any], name: str) -> dict[str, Any]:
    for record in records:
        if str(_redis_value(record, "name", "")) == name:
            return dict(record)
    return {}


def _redis_value(record: Any, key: str, default: Any) -> Any:
    if not isinstance(record, dict):
        return default
    return record.get(key, default)
