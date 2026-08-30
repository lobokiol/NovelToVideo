from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.tasks.constants import (
    ASYNC_TASKS_ATTRIBUTE,
    DEFAULT_ASYNC_TASK_MODULES,
    DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS,
    DEFAULT_TASK_CONSUMER_GROUP,
    DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS,
    DEFAULT_TASK_STREAM_MAX_LEN,
    DEFAULT_TASK_STREAM_NAME,
    DEFAULT_TASK_WORKER_BATCH_SIZE,
    DEFAULT_TASK_WORKER_BLOCK_MS,
    DEFAULT_TASK_WORKER_CONSUMER_NAME,
    DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS,
    DEFAULT_TASK_WORKER_LOG_ENABLED,
    DEFAULT_TASK_WORKER_MAX_CONCURRENCY,
    DEFAULT_TASK_WORKER_MAX_RETRIES,
    DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS,
    DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS,
    DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS,
)
from app.models.tasks import TaskStatus
from app.schemas.tasks import (
    TaskItemCreate,
    TaskItemRead,
    TaskDeadLetterRead,
    TaskJobCreate,
    TaskJobDetail,
    TaskJobPage,
    TaskJobRead,
    TaskStatusUpdate,
    TaskStreamRecord,
)
from app.services import tasks as task_service
from app.services.tasks import (
    TaskItemNotFoundError,
    TaskJobNotFoundError,
    TaskServiceError,
    TaskValidationError,
)


TaskHandlerResult = dict[str, Any] | None
TaskHandler = Callable[[Any], TaskHandlerResult | Awaitable[TaskHandlerResult]]


class TaskHandlerFailure(Exception):
    """任务处理器主动声明的业务失败，可携带诊断结果写回任务子项。

    retryable=False 表示确定性失败（参数缺失、前置状态不满足等），
    重试也不会成功，任务系统应直接置失败而不进入指数退避重排队。
    """

    def __init__(
        self,
        error_message: str,
        *,
        error_code: str = "task_handler_failed",
        result: dict[str, Any] | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(error_message)
        self.error_code = error_code.strip() or "task_handler_failed"
        self.error_message = error_message.strip() or self.error_code
        self.result = result or {}
        self.retryable = bool(retryable)


class TaskHandlerRegistry:
    """异步任务处理器注册表。"""

    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, task_type: str, handler: TaskHandler) -> TaskHandler:
        """注册异步任务处理器。"""
        key = task_type.strip()
        if not key:
            raise ValueError("任务类型不能为空")
        self._handlers[key] = handler
        return handler

    def get(self, task_type: str, item_type: str = "") -> TaskHandler | None:
        """按任务类型获取处理器，优先匹配子项类型。"""
        item_key = item_type.strip()
        if item_key and item_key in self._handlers:
            return self._handlers[item_key]
        return self._handlers.get(task_type.strip())

    def keys(self) -> list[str]:
        """返回已注册的任务类型列表。"""
        return sorted(self._handlers.keys())


default_task_handler_registry = TaskHandlerRegistry()


@dataclass(frozen=True, slots=True)
class TaskEngineConfig:
    """异步任务引擎运行配置。"""

    modules: tuple[str, ...] = DEFAULT_ASYNC_TASK_MODULES
    stream_name: str = DEFAULT_TASK_STREAM_NAME
    consumer_group: str = DEFAULT_TASK_CONSUMER_GROUP
    stream_max_len: int = DEFAULT_TASK_STREAM_MAX_LEN
    worker_consumer_name: str = DEFAULT_TASK_WORKER_CONSUMER_NAME
    worker_batch_size: int = DEFAULT_TASK_WORKER_BATCH_SIZE
    worker_block_ms: int | None = DEFAULT_TASK_WORKER_BLOCK_MS
    worker_idle_sleep_seconds: float = DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS
    worker_max_concurrency: int = DEFAULT_TASK_WORKER_MAX_CONCURRENCY
    worker_task_timeout_seconds: float = DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS
    worker_log_enabled: bool = DEFAULT_TASK_WORKER_LOG_ENABLED
    worker_heartbeat_interval_seconds: float = DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS
    worker_max_retries: int = DEFAULT_TASK_WORKER_MAX_RETRIES
    worker_retry_backoff_seconds: float = DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS
    worker_shutdown_timeout_seconds: float = DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS
    stale_running_timeout_seconds: float = DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS
    orphan_scavenger_interval_seconds: float = DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS

    @classmethod
    def from_env(cls) -> "TaskEngineConfig":
        """从环境变量构建异步任务引擎配置。"""
        return cls(
            modules=_parse_modules(os.getenv("ASYNC_TASK_MODULES"), DEFAULT_ASYNC_TASK_MODULES),
            stream_name=os.getenv("REDIS_TASK_STREAM_NAME", DEFAULT_TASK_STREAM_NAME),
            consumer_group=os.getenv("REDIS_TASK_CONSUMER_GROUP", DEFAULT_TASK_CONSUMER_GROUP),
            stream_max_len=_env_int("REDIS_TASK_STREAM_MAX_LEN", DEFAULT_TASK_STREAM_MAX_LEN),
            worker_consumer_name=os.getenv("ASYNC_TASK_WORKER_CONSUMER_NAME", DEFAULT_TASK_WORKER_CONSUMER_NAME),
            worker_batch_size=_env_int("ASYNC_TASK_WORKER_BATCH_SIZE", DEFAULT_TASK_WORKER_BATCH_SIZE),
            worker_block_ms=_env_optional_int("ASYNC_TASK_WORKER_BLOCK_MS", DEFAULT_TASK_WORKER_BLOCK_MS),
            worker_idle_sleep_seconds=_env_float(
                "ASYNC_TASK_WORKER_IDLE_SLEEP_SECONDS",
                DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS,
            ),
            worker_max_concurrency=_env_int(
                "ASYNC_TASK_WORKER_MAX_CONCURRENCY",
                DEFAULT_TASK_WORKER_MAX_CONCURRENCY,
            ),
            worker_task_timeout_seconds=_env_float(
                "ASYNC_TASK_WORKER_TASK_TIMEOUT_SECONDS",
                DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS,
            ),
            worker_log_enabled=_env_bool(
                "ASYNC_TASK_WORKER_LOG_ENABLED",
                DEFAULT_TASK_WORKER_LOG_ENABLED,
            ),
            worker_heartbeat_interval_seconds=_env_float(
                "ASYNC_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS",
                DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS,
            ),
            worker_max_retries=_env_int(
                "ASYNC_TASK_WORKER_MAX_RETRIES",
                DEFAULT_TASK_WORKER_MAX_RETRIES,
            ),
            worker_retry_backoff_seconds=_env_float(
                "ASYNC_TASK_WORKER_RETRY_BACKOFF_SECONDS",
                DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS,
            ),
            worker_shutdown_timeout_seconds=_env_float(
                "ASYNC_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS",
                DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS,
            ),
            stale_running_timeout_seconds=_env_float(
                "ASYNC_TASK_STALE_RUNNING_TIMEOUT_SECONDS",
                DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS,
            ),
            orphan_scavenger_interval_seconds=_env_float(
                "ASYNC_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS",
                DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS,
            ),
        )

    @classmethod
    def from_settings(cls, settings: Any) -> "TaskEngineConfig":
        """从项目统一 Settings 对象构建异步任务引擎配置。"""
        return cls(
            modules=tuple(getattr(settings, "async_task_modules", DEFAULT_ASYNC_TASK_MODULES)),
            stream_name=str(getattr(settings, "redis_task_stream_name", DEFAULT_TASK_STREAM_NAME)),
            consumer_group=str(getattr(settings, "redis_task_consumer_group", DEFAULT_TASK_CONSUMER_GROUP)),
            stream_max_len=int(getattr(settings, "redis_task_stream_max_len", DEFAULT_TASK_STREAM_MAX_LEN)),
            worker_consumer_name=str(
                getattr(settings, "async_task_worker_consumer_name", DEFAULT_TASK_WORKER_CONSUMER_NAME)
            ),
            worker_batch_size=int(getattr(settings, "async_task_worker_batch_size", DEFAULT_TASK_WORKER_BATCH_SIZE)),
            worker_block_ms=getattr(settings, "async_task_worker_block_ms", DEFAULT_TASK_WORKER_BLOCK_MS),
            worker_idle_sleep_seconds=float(
                getattr(settings, "async_task_worker_idle_sleep_seconds", DEFAULT_TASK_WORKER_IDLE_SLEEP_SECONDS)
            ),
            worker_max_concurrency=int(
                getattr(settings, "async_task_worker_max_concurrency", DEFAULT_TASK_WORKER_MAX_CONCURRENCY)
            ),
            worker_task_timeout_seconds=float(
                getattr(settings, "async_task_worker_task_timeout_seconds", DEFAULT_TASK_WORKER_TASK_TIMEOUT_SECONDS)
            ),
            worker_log_enabled=bool(
                getattr(settings, "async_task_worker_log_enabled", DEFAULT_TASK_WORKER_LOG_ENABLED)
            ),
            worker_heartbeat_interval_seconds=float(
                getattr(
                    settings,
                    "async_task_worker_heartbeat_interval_seconds",
                    DEFAULT_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS,
                )
            ),
            worker_max_retries=int(getattr(settings, "async_task_worker_max_retries", DEFAULT_TASK_WORKER_MAX_RETRIES)),
            worker_retry_backoff_seconds=float(
                getattr(settings, "async_task_worker_retry_backoff_seconds", DEFAULT_TASK_WORKER_RETRY_BACKOFF_SECONDS)
            ),
            worker_shutdown_timeout_seconds=float(
                getattr(
                    settings,
                    "async_task_worker_shutdown_timeout_seconds",
                    DEFAULT_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS,
                )
            ),
            stale_running_timeout_seconds=float(
                getattr(settings, "async_task_stale_running_timeout_seconds", DEFAULT_TASK_STALE_RUNNING_TIMEOUT_SECONDS)
            ),
            orphan_scavenger_interval_seconds=float(
                getattr(
                    settings,
                    "async_task_orphan_scavenger_interval_seconds",
                    DEFAULT_TASK_ORPHAN_SCAVENGER_INTERVAL_SECONDS,
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class AsyncTaskDefinition:
    """异步任务处理器定义。"""

    task_type: str
    handler: TaskHandler


class AsyncTaskEngine:
    """异步任务引擎，聚合通用任务注册、任务操作与 Stream 调度能力。"""

    def __init__(
        self,
        registry: TaskHandlerRegistry | None = None,
        *,
        config: TaskEngineConfig | None = None,
        config_loader: Callable[[], TaskEngineConfig] | None = None,
        session_maker: Any | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self.registry = registry or default_task_handler_registry
        self._config = config
        self._config_loader = config_loader
        self.session_maker = session_maker
        self.redis_client = redis_client

    @property
    def config(self) -> TaskEngineConfig:
        """返回当前引擎配置。"""
        if self._config is not None:
            return self._config
        if self._config_loader is not None:
            return self._config_loader()
        return TaskEngineConfig.from_env()

    def register_task_handler(self, task_type: str, handler: TaskHandler) -> TaskHandler:
        """注册单个异步任务处理器。"""
        return self.registry.register(task_type, handler)

    def register_async_tasks(self, tasks: AsyncTaskDefinition | Iterable[AsyncTaskDefinition] | None = None) -> None:
        """批量注册异步任务处理器。"""
        if tasks is None:
            self.register_async_task_modules()
            return
        if isinstance(tasks, AsyncTaskDefinition):
            self.register_task_handler(tasks.task_type, tasks.handler)
            return
        for task in tasks:
            self.register_task_handler(task.task_type, task.handler)

    def register_async_task_modules(self, module_paths: Iterable[str] | None = None) -> None:
        """按模块路径加载并注册各服务声明的异步任务列表。"""
        paths = tuple(module_paths) if module_paths is not None else self.config.modules
        for module_path in paths:
            module = import_module(module_path)
            self.register_async_tasks(getattr(module, ASYNC_TASKS_ATTRIBUTE, ()))

    async def create_task_job(self, session: AsyncSession, payload: TaskJobCreate) -> TaskJobDetail:
        """创建异步任务及初始子项。"""
        return await task_service.create_task_job(session, self._apply_task_job_defaults(payload))

    async def append_task_items(
        self,
        session: AsyncSession,
        job_public_id: str,
        payloads: list[TaskItemCreate],
    ) -> TaskJobDetail:
        """追加异步任务子项。"""
        return await task_service.append_task_items(
            session,
            job_public_id,
            self._apply_task_item_defaults(payloads),
        )

    async def list_task_jobs(
        self,
        session: AsyncSession,
        *,
        page: int = 1,
        limit: int = 20,
        task_type: str = "",
        status: TaskStatus | None = None,
        created_by: str = "",
        queue_name: str = "",
        project_public_id: str = "",
    ) -> TaskJobPage:
        """分页查询异步任务列表。"""
        return await task_service.list_task_jobs(
            session,
            page=page,
            limit=limit,
            task_type=task_type,
            status=status,
            created_by=created_by,
            queue_name=queue_name,
            project_public_id=project_public_id,
        )

    async def get_task_job(
        self,
        session: AsyncSession,
        job_public_id: str,
        *,
        include_items: bool = False,
    ) -> TaskJobRead | TaskJobDetail:
        """按公开标识获取异步任务。"""
        return await task_service.get_task_job(session, job_public_id, include_items=include_items)

    async def list_task_items(
        self,
        session: AsyncSession,
        job_public_id: str,
        *,
        status: TaskStatus | None = None,
    ) -> list[TaskItemRead]:
        """查询异步任务子项列表。"""
        return await task_service.list_task_items(session, job_public_id, status=status)

    async def get_task_item(self, session: AsyncSession, item_public_id: str) -> TaskItemRead:
        """按公开标识获取异步任务子项。"""
        return await task_service.get_task_item(session, item_public_id)

    async def update_task_job_status(
        self,
        session: AsyncSession,
        job_public_id: str,
        payload: TaskStatusUpdate,
    ) -> TaskJobRead:
        """更新异步任务状态。"""
        return await task_service.update_task_job_status(session, job_public_id, payload)

    async def update_task_item_status(
        self,
        session: AsyncSession,
        item_public_id: str,
        payload: TaskStatusUpdate,
        *,
        refresh_job: bool = True,
    ) -> TaskItemRead:
        """更新异步任务子项状态。"""
        return await task_service.update_task_item_status(
            session,
            item_public_id,
            payload,
            refresh_job=refresh_job,
        )

    async def delete_task_job(self, session: AsyncSession, job_public_id: str) -> None:
        """软删除异步任务及其子项。"""
        await task_service.delete_task_job(session, job_public_id)

    async def delete_task_item(self, session: AsyncSession, item_public_id: str) -> None:
        """软删除异步任务子项。"""
        await task_service.delete_task_item(session, item_public_id)

    async def pause_task_job(self, session: AsyncSession, job_public_id: str) -> TaskJobRead:
        """暂停异步任务。"""
        return await task_service.pause_task_job(session, job_public_id)

    async def resume_task_job(
        self,
        session: AsyncSession,
        job_public_id: str,
        *,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
    ) -> list[TaskStreamRecord]:
        """恢复异步任务并重新投递可执行子项。"""
        await task_service.resume_task_job(session, job_public_id)
        return await self.enqueue_task_job(
            session,
            job_public_id,
            redis_client=redis_client,
            stream_name=stream_name,
            group_name=group_name,
        )

    async def cancel_task_job(self, session: AsyncSession, job_public_id: str) -> TaskJobRead:
        """取消异步任务。"""
        return await task_service.cancel_task_job(session, job_public_id)

    async def cancel_task_item(self, session: AsyncSession, item_public_id: str) -> TaskItemRead:
        """取消异步任务子项。"""
        return await task_service.cancel_task_item(session, item_public_id)

    async def retry_task_item(
        self,
        session: AsyncSession,
        item_public_id: str,
        *,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
    ) -> TaskItemRead:
        """重试异步任务子项，并立即重新投递。"""
        await task_service.retry_task_item(session, item_public_id)
        await self.enqueue_task_item(
            session,
            item_public_id,
            redis_client=redis_client,
            stream_name=stream_name,
            group_name=group_name,
        )
        return await task_service.get_task_item(session, item_public_id)

    async def mark_task_item_running(
        self,
        session: AsyncSession,
        item_public_id: str,
        worker_id: str,
    ) -> bool:
        """标记任务子项开始执行，子项不存在时返回 False。"""
        try:
            return await task_service.mark_task_item_running(session, item_public_id, worker_id)
        except TaskItemNotFoundError:
            await session.rollback()
            return False

    async def mark_task_item_succeeded(
        self,
        session: AsyncSession,
        item_public_id: str,
        result: dict[str, Any] | None,
        worker_id: str,
    ) -> bool:
        """标记任务子项执行成功，子项不存在时返回 False。"""
        return await self._mark_task_item_status(
            session,
            item_public_id,
            TaskStatus.SUCCEEDED,
            worker_id,
            result=result or {},
        )

    async def mark_task_item_failed(
        self,
        session: AsyncSession,
        item_public_id: str,
        error_code: str,
        error_message: str,
        worker_id: str,
        *,
        stream_id: str = "",
        stage: str = "handler",
        result: dict[str, Any] | None = None,
        retryable: bool = True,
    ) -> bool:
        """标记任务子项执行失败，子项不存在时返回 False。"""
        try:
            await task_service.record_task_item_failure(
                session,
                item_public_id,
                error_code,
                error_message,
                worker_id,
                retry_backoff_seconds=self.config.worker_retry_backoff_seconds,
                stream_id=stream_id,
                stage=stage,
                result=result,
                retryable=retryable,
            )
        except TaskItemNotFoundError:
            await session.rollback()
            return False
        return True

    async def heartbeat_task_item(
        self,
        session: AsyncSession,
        item_public_id: str,
        worker_id: str,
    ) -> bool:
        """刷新任务子项心跳。"""
        return await task_service.heartbeat_task_item(session, item_public_id, worker_id)

    async def enqueue_task_item(
        self,
        session: AsyncSession,
        item_public_id: str,
        *,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
    ) -> TaskStreamRecord:
        """将单个任务子项投递到 Redis Stream。"""
        import app.core.tasks.stream as task_stream

        config = self.config
        return await task_stream.enqueue_task_item(
            session,
            item_public_id,
            redis_client=_coalesce(redis_client, self.redis_client),
            stream_name=_coalesce(stream_name, config.stream_name),
            group_name=_coalesce(group_name, config.consumer_group),
            stream_max_len=config.stream_max_len,
        )

    async def enqueue_task_job(
        self,
        session: AsyncSession,
        job_public_id: str,
        *,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
    ) -> list[TaskStreamRecord]:
        """将任务下所有待处理子项投递到 Redis Stream。"""
        import app.core.tasks.stream as task_stream

        config = self.config
        return await task_stream.enqueue_task_job(
            session,
            job_public_id,
            redis_client=_coalesce(redis_client, self.redis_client),
            stream_name=_coalesce(stream_name, config.stream_name),
            group_name=_coalesce(group_name, config.consumer_group),
            stream_max_len=config.stream_max_len,
        )

    async def read_task_stream_records(
        self,
        consumer_name: str,
        *,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
        count: int = 1,
        block_ms: int | None = None,
    ) -> list[TaskStreamRecord]:
        """从异步任务 Redis Stream 读取消息。"""
        import app.core.tasks.stream as task_stream

        config = self.config
        return await task_stream.read_task_stream_records(
            consumer_name,
            redis_client=_coalesce(redis_client, self.redis_client),
            stream_name=_coalesce(stream_name, config.stream_name),
            group_name=_coalesce(group_name, config.consumer_group),
            count=count,
            block_ms=block_ms,
        )

    async def ack_task_stream_record(
        self,
        stream_id: str,
        *,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
    ) -> int:
        """确认异步任务 Redis Stream 消息已处理。"""
        import app.core.tasks.stream as task_stream

        config = self.config
        return await task_stream.ack_task_stream_record(
            stream_id,
            redis_client=_coalesce(redis_client, self.redis_client),
            stream_name=_coalesce(stream_name, config.stream_name),
            group_name=_coalesce(group_name, config.consumer_group),
        )

    async def create_and_enqueue_task_job(
        self,
        session: AsyncSession,
        payload: TaskJobCreate,
        *,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
    ) -> TaskJobDetail:
        """创建异步任务并投递所有初始子项。"""
        job = await self.create_task_job(session, payload)
        await self.enqueue_task_job(
            session,
            job.public_id,
            redis_client=redis_client,
            stream_name=stream_name,
            group_name=group_name,
        )
        return job

    async def enqueue_due_pending_task_items(
        self,
        session: AsyncSession,
        *,
        limit: int = 100,
        redis_client: Any | None = None,
        stream_name: str | None = None,
        group_name: str | None = None,
    ) -> int:
        """投递已经到调度时间的 pending 子项，用于重试和孤儿恢复。"""
        item_public_ids = await task_service.list_due_pending_task_item_public_ids(session, limit=limit)
        enqueued = 0
        for item_public_id in item_public_ids:
            try:
                await self.enqueue_task_item(
                    session,
                    item_public_id,
                    redis_client=redis_client,
                    stream_name=stream_name,
                    group_name=group_name,
                )
            except (TaskServiceError, Exception):
                await session.rollback()
                continue
            enqueued += 1
        return enqueued

    async def recover_stale_running_task_items(
        self,
        session: AsyncSession,
        *,
        limit: int = 100,
    ) -> int:
        """恢复心跳超时的 running 子项。"""
        return await task_service.recover_stale_running_task_items(
            session,
            stale_after_seconds=self.config.stale_running_timeout_seconds,
            retry_backoff_seconds=self.config.worker_retry_backoff_seconds,
            limit=limit,
        )

    async def create_task_dead_letter(
        self,
        session: AsyncSession,
        **kwargs: Any,
    ) -> TaskDeadLetterRead:
        """创建任务死信记录。"""
        return await task_service.create_task_dead_letter(session, **kwargs)

    def _apply_task_job_defaults(self, payload: TaskJobCreate) -> TaskJobCreate:
        return payload.model_copy(update={"items": self._apply_task_item_defaults(payload.items)})

    def _apply_task_item_defaults(self, payloads: list[TaskItemCreate]) -> list[TaskItemCreate]:
        max_attempts = min(max(int(self.config.worker_max_retries), 1), 100)
        return [
            payload
            if "max_attempts" in payload.model_fields_set
            else payload.model_copy(update={"max_attempts": max_attempts})
            for payload in payloads
        ]

    async def _mark_task_item_status(
        self,
        session: AsyncSession,
        item_public_id: str,
        status: TaskStatus,
        worker_id: str,
        *,
        result: dict[str, Any] | None = None,
        error_code: str = "",
        error_message: str = "",
    ) -> bool:
        try:
            await task_service.update_task_item_status(
                session,
                item_public_id,
                TaskStatusUpdate(
                    status=status,
                    result=result,
                    error_code=error_code,
                    error_message=error_message,
                    worker_id=worker_id,
                ),
            )
        except TaskItemNotFoundError:
            await session.rollback()
            return False
        return True


def _coalesce(value: Any | None, default: Any) -> Any:
    return value if value is not None else default


def _parse_modules(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _env_optional_int(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    if value is None:
        return default
    if not value.strip():
        return None
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_project_task_engine_config() -> TaskEngineConfig:
    try:
        from app.core.config import settings
    except ImportError:
        return TaskEngineConfig.from_env()
    return TaskEngineConfig.from_settings(settings)


default_async_task_engine = AsyncTaskEngine(config_loader=_load_project_task_engine_config)
