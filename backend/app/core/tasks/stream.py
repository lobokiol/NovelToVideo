from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from redis.exceptions import ResponseError
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.tasks.constants import (
    DEFAULT_TASK_CONSUMER_GROUP,
    DEFAULT_TASK_STREAM_MAX_LEN,
    DEFAULT_TASK_STREAM_NAME,
    TASK_STREAM_EVENT_ITEM_QUEUED,
    TASK_STREAM_MESSAGE_VERSION,
)
from app.models.tasks import TaskItem, TaskJob, TaskStatus, utc_now
from app.schemas.tasks import TaskStreamMessage, TaskStreamRecord
from app.services import tasks as task_service


class TaskStreamServiceError(Exception):
    """异步任务 Redis Stream 服务层基础异常。"""


class TaskStreamValidationError(TaskStreamServiceError):
    """异步任务 Redis Stream 请求不合法。"""


class TaskStreamPublishError(TaskStreamServiceError):
    """异步任务消息投递失败。"""


async def ensure_task_stream_group(
    redis_client: Any | None = None,
    *,
    stream_name: str | None = None,
    group_name: str | None = None,
) -> None:
    """确保异步任务 Redis Stream 消费组存在。"""
    client = _redis_client(redis_client)
    stream = _stream_name(stream_name)
    group = _group_name(group_name)
    try:
        await client.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise TaskStreamPublishError(str(exc)) from exc


async def enqueue_task_item(
    session: AsyncSession,
    item_public_id: str,
    *,
    redis_client: Any | None = None,
    stream_name: str | None = None,
    group_name: str | None = None,
    stream_max_len: int | None = None,
) -> TaskStreamRecord:
    """将单个任务子项投递到 Redis Stream。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    if item.status != TaskStatus.PENDING:
        raise TaskStreamValidationError("只有待处理任务子项可以入队")
    now = utc_now()
    if item.scheduled_at is not None and item.scheduled_at > now:
        raise TaskStreamValidationError("任务子项尚未到计划调度时间")
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)
    if job.status in {TaskStatus.PAUSED, TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.PARTIAL}:
        raise TaskStreamValidationError("任务当前状态不允许入队")
    record = await _publish_task_item(
        job,
        item,
        redis_client=redis_client,
        stream_name=stream_name,
        group_name=group_name,
        stream_max_len=stream_max_len,
    )
    item.status = TaskStatus.QUEUED
    item.updated_at = now
    session.add(item)
    await task_service.refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return record


async def enqueue_task_job(
    session: AsyncSession,
    job_public_id: str,
    *,
    redis_client: Any | None = None,
    stream_name: str | None = None,
    group_name: str | None = None,
    stream_max_len: int | None = None,
) -> list[TaskStreamRecord]:
    """将任务下所有待处理子项投递到 Redis Stream。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    if job.status in {TaskStatus.PAUSED, TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.PARTIAL}:
        raise TaskStreamValidationError("任务当前状态不允许入队")
    items = await _list_pending_task_items(session, int(job.id or 0))
    records: list[TaskStreamRecord] = []
    now = utc_now()
    for item in items:
        record = await _publish_task_item(
            job,
            item,
            redis_client=redis_client,
            stream_name=stream_name,
            group_name=group_name,
            stream_max_len=stream_max_len,
        )
        item.status = TaskStatus.QUEUED
        item.updated_at = now
        session.add(item)
        records.append(record)
    if records:
        await task_service.refresh_task_job_progress(session, job)
        await session.commit()
        for item in items:
            await session.refresh(item)
    return records


async def read_task_stream_records(
    consumer_name: str,
    *,
    redis_client: Any | None = None,
    stream_name: str | None = None,
    group_name: str | None = None,
    count: int = 1,
    block_ms: int | None = None,
) -> list[TaskStreamRecord]:
    """从异步任务 Redis Stream 读取消息。"""
    if not consumer_name.strip():
        raise TaskStreamValidationError("Consumer 名称不能为空")
    client = _redis_client(redis_client)
    stream = _stream_name(stream_name)
    group = _group_name(group_name)
    await ensure_task_stream_group(client, stream_name=stream, group_name=group)
    raw_streams = await client.xreadgroup(
        groupname=group,
        consumername=consumer_name.strip(),
        streams={stream: ">"},
        count=max(count, 1),
        block=max(block_ms, 0) if block_ms is not None else None,
    )
    return _parse_streams(raw_streams)


async def ack_task_stream_record(
    stream_id: str,
    *,
    redis_client: Any | None = None,
    stream_name: str | None = None,
    group_name: str | None = None,
) -> int:
    """确认异步任务 Redis Stream 消息已处理。"""
    if not stream_id.strip():
        raise TaskStreamValidationError("Stream 消息 ID 不能为空")
    client = _redis_client(redis_client)
    return int(await client.xack(_stream_name(stream_name), _group_name(group_name), stream_id.strip()))


async def claim_stale_task_stream_records(
    consumer_name: str,
    *,
    min_idle_ms: int,
    redis_client: Any | None = None,
    stream_name: str | None = None,
    group_name: str | None = None,
    start_id: str = "0-0",
    count: int = 100,
) -> list[TaskStreamRecord]:
    """从 Redis Stream PEL 中认领长时间未确认的消息。"""
    if not consumer_name.strip():
        raise TaskStreamValidationError("Consumer 名称不能为空")
    client = _redis_client(redis_client)
    stream = _stream_name(stream_name)
    group = _group_name(group_name)
    await ensure_task_stream_group(client, stream_name=stream, group_name=group)
    raw = await client.xautoclaim(
        name=stream,
        groupname=group,
        consumername=consumer_name.strip(),
        min_idle_time=max(min_idle_ms, 0),
        start_id=start_id,
        count=max(count, 1),
    )
    return [
        TaskStreamRecord(stream_id=str(stream_id), message=_fields_to_message(dict(fields)))
        for stream_id, fields in _xautoclaim_messages(raw)
    ]


async def _publish_task_item(
    job: TaskJob,
    item: TaskItem,
    *,
    redis_client: Any | None,
    stream_name: str | None,
    group_name: str | None,
    stream_max_len: int | None,
) -> TaskStreamRecord:
    client = _redis_client(redis_client)
    stream = _stream_name(stream_name)
    await ensure_task_stream_group(client, stream_name=stream, group_name=group_name)
    message = _build_task_stream_message(job, item)
    fields = _message_to_fields(message)
    try:
        stream_id = await client.xadd(
            stream,
            fields,
            maxlen=_stream_max_len(stream_max_len),
            approximate=True,
        )
    except ResponseError as exc:
        raise TaskStreamPublishError(str(exc)) from exc
    return TaskStreamRecord(stream_id=str(stream_id), message=message)


async def _get_task_job_model_or_raise(session: AsyncSession, job_public_id: str) -> TaskJob:
    statement = select(TaskJob).where(TaskJob.public_id == job_public_id, TaskJob.disabled_at.is_(None))
    result = await session.exec(statement)
    job = result.first()
    if job is None:
        raise task_service.TaskJobNotFoundError("异步任务不存在")
    return job


async def _get_task_job_model_by_id_or_raise(session: AsyncSession, job_id: int) -> TaskJob:
    statement = select(TaskJob).where(TaskJob.id == job_id, TaskJob.disabled_at.is_(None))
    result = await session.exec(statement)
    job = result.first()
    if job is None:
        raise task_service.TaskJobNotFoundError("异步任务不存在")
    return job


async def _get_task_item_model_or_raise(session: AsyncSession, item_public_id: str) -> TaskItem:
    statement = select(TaskItem).where(TaskItem.public_id == item_public_id, TaskItem.disabled_at.is_(None))
    result = await session.exec(statement)
    item = result.first()
    if item is None:
        raise task_service.TaskItemNotFoundError("异步任务子项不存在")
    return item


async def _list_pending_task_items(session: AsyncSession, job_id: int) -> list[TaskItem]:
    statement = (
        select(TaskItem)
        .where(
            TaskItem.job_id == job_id,
            TaskItem.status == TaskStatus.PENDING,
            TaskItem.disabled_at.is_(None),
            or_(TaskItem.scheduled_at.is_(None), TaskItem.scheduled_at <= utc_now()),
        )
        .order_by(TaskItem.priority.desc(), TaskItem.id)
    )
    result = await session.exec(statement)
    return list(result.all())


def _build_task_stream_message(job: TaskJob, item: TaskItem) -> TaskStreamMessage:
    return TaskStreamMessage(
        event=TASK_STREAM_EVENT_ITEM_QUEUED,
        job_public_id=job.public_id,
        item_public_id=item.public_id,
        task_type=job.task_type,
        item_type=item.item_type or job.task_type,
        queue_name=job.queue_name,
        priority=item.priority,
        payload=_load_json(item.payload),
        scheduled_at=item.scheduled_at,
        created_at=utc_now(),
    )


def _message_to_fields(message: TaskStreamMessage) -> dict[str, str]:
    return {
        "version": TASK_STREAM_MESSAGE_VERSION,
        "event": message.event,
        "job_public_id": message.job_public_id,
        "item_public_id": message.item_public_id,
        "task_type": message.task_type,
        "item_type": message.item_type,
        "queue_name": message.queue_name,
        "priority": str(message.priority),
        "payload": json.dumps(message.payload, ensure_ascii=False, separators=(",", ":")),
        "scheduled_at": _format_datetime(message.scheduled_at),
        "created_at": _format_datetime(message.created_at),
    }


def _fields_to_message(fields: dict[str, Any]) -> TaskStreamMessage:
    payload = fields.get("payload") or "{}"
    try:
        payload_value = json.loads(str(payload))
    except json.JSONDecodeError:
        payload_value = {}
    if not isinstance(payload_value, dict):
        payload_value = {"value": payload_value}
    return TaskStreamMessage(
        event=str(fields.get("event") or TASK_STREAM_EVENT_ITEM_QUEUED),
        job_public_id=str(fields.get("job_public_id") or ""),
        item_public_id=str(fields.get("item_public_id") or ""),
        task_type=str(fields.get("task_type") or ""),
        item_type=str(fields.get("item_type") or ""),
        queue_name=str(fields.get("queue_name") or "default"),
        priority=int(fields.get("priority") or 0),
        payload=payload_value,
        scheduled_at=_parse_datetime(fields.get("scheduled_at")),
        created_at=_parse_datetime(fields.get("created_at")) or utc_now(),
    )


def _parse_streams(raw_streams: list[Any]) -> list[TaskStreamRecord]:
    records: list[TaskStreamRecord] = []
    for _, messages in raw_streams:
        for stream_id, fields in messages:
            records.append(TaskStreamRecord(stream_id=str(stream_id), message=_fields_to_message(dict(fields))))
    return records


def _xautoclaim_messages(raw: Any) -> list[Any]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return []
    return list(raw[1] or [])


def _load_json(value: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {"value": loaded}


def _format_datetime(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    return datetime.fromisoformat(text)


def _stream_name(stream_name: str | None) -> str:
    return (stream_name or DEFAULT_TASK_STREAM_NAME).strip() or DEFAULT_TASK_STREAM_NAME


def _group_name(group_name: str | None) -> str:
    return (group_name or DEFAULT_TASK_CONSUMER_GROUP).strip() or DEFAULT_TASK_CONSUMER_GROUP


def _stream_max_len(stream_max_len: int | None) -> int:
    return stream_max_len if stream_max_len is not None else DEFAULT_TASK_STREAM_MAX_LEN


def _redis_client(redis_client: Any | None) -> Any:
    if redis_client is not None:
        return redis_client
    from app.core.database import redis_client as default_redis_client

    return default_redis_client
