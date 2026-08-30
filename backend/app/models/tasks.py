from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel
from app.utils.time_tools import utc_now


class TaskBaseModel(BaseModel):
    """异步任务数据库实体基础字段。"""


class TaskStatus(str, Enum):
    """异步任务状态。"""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"
    PAUSED = "paused"

def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """返回枚举值列表，用于数据库字段存储枚举值而不是成员名。"""
    return [item.value for item in enum_cls]


def _task_status_column(name: str = "status") -> Column:
    """构建任务状态字段。"""
    return Column(
        name,
        SAEnum(
            TaskStatus,
            values_callable=_enum_values,
            name="task_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        default=TaskStatus.PENDING.value,
        server_default=TaskStatus.PENDING.value,
        index=True,
    )


class TaskJob(TaskBaseModel, table=True):
    """异步任务主表模型。"""

    __tablename__ = "af_task_job"

    task_type: str = Field(
        sa_column=Column("task_type", String(100), nullable=False, index=True),
        description="任务类型标识。",
    )
    queue_name: str = Field(
        default="default",
        sa_column=Column("queue_name", String(120), nullable=False, default="default", server_default="default", index=True),
        description="任务队列名称。",
    )
    name: str = Field(
        default="",
        sa_column=Column("name", String(255), nullable=False, default="", server_default=""),
        description="任务展示名称。",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        sa_column=_task_status_column(),
        description="任务当前状态。",
    )
    created_by: str = Field(
        default="",
        sa_column=Column("created_by", String(36), nullable=False, default="", server_default="", index=True),
        description="任务创建人的用户公开标识，系统任务为空。",
    )
    idempotency_key: str = Field(
        default="",
        sa_column=Column("idempotency_key", String(120), nullable=False, default="", server_default="", index=True),
        description="调用方提供的幂等键。",
    )
    priority: int = Field(
        default=0,
        sa_column=Column("priority", Integer, nullable=False, default=0, server_default="0", index=True),
        description="任务优先级，数值越大优先级越高。",
    )
    total_items: int = Field(
        default=0,
        sa_column=Column("total_items", Integer, nullable=False, default=0, server_default="0"),
        description="任务子项总数。",
    )
    completed_items: int = Field(
        default=0,
        sa_column=Column("completed_items", Integer, nullable=False, default=0, server_default="0"),
        description="已成功的任务子项数量。",
    )
    failed_items: int = Field(
        default=0,
        sa_column=Column("failed_items", Integer, nullable=False, default=0, server_default="0"),
        description="已失败的任务子项数量。",
    )
    cancelled_items: int = Field(
        default=0,
        sa_column=Column("cancelled_items", Integer, nullable=False, default=0, server_default="0"),
        description="已取消的任务子项数量。",
    )
    payload: str = Field(
        default="{}",
        sa_column=Column("payload", Text(), nullable=False, default="{}", server_default="{}"),
        description="任务输入参数，JSON 字符串。",
    )
    result: str = Field(
        default="{}",
        sa_column=Column("result", Text(), nullable=False, default="{}", server_default="{}"),
        description="任务执行结果，JSON 字符串。",
    )
    error_code: str = Field(
        default="",
        sa_column=Column("error_code", String(100), nullable=False, default="", server_default=""),
        description="任务错误码。",
    )
    error_message: str = Field(
        default="",
        sa_column=Column("error_message", Text(), nullable=False, default="", server_default=""),
        description="任务错误信息。",
    )
    scheduled_at: datetime | None = Field(
        default=None,
        sa_column=Column("scheduled_at", DateTime(timezone=True), nullable=True, index=True),
        description="任务计划调度时间。",
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column("started_at", DateTime(timezone=True), nullable=True),
        description="任务开始执行时间。",
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column("completed_at", DateTime(timezone=True), nullable=True),
        description="任务完成时间。",
    )


class TaskItem(TaskBaseModel, table=True):
    """异步任务子项表模型。"""

    __tablename__ = "af_task_item"
    __table_args__ = (UniqueConstraint("job_id", "item_key", name="uq_af_task_item_job_item_key"),)

    job_id: int = Field(
        sa_column=Column("job_id", Integer, ForeignKey("af_task_job.id"), nullable=False, index=True),
        description="所属任务内部主键。",
    )
    item_type: str = Field(
        default="",
        sa_column=Column("item_type", String(100), nullable=False, default="", server_default="", index=True),
        description="任务子项类型标识。",
    )
    item_key: str | None = Field(
        default=None,
        sa_column=Column("item_key", String(120), nullable=True, index=True),
        description="调用方提供的任务子项唯一键。",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        sa_column=_task_status_column(),
        description="任务子项当前状态。",
    )
    priority: int = Field(
        default=0,
        sa_column=Column("priority", Integer, nullable=False, default=0, server_default="0", index=True),
        description="任务子项优先级，数值越大优先级越高。",
    )
    attempt_count: int = Field(
        default=0,
        sa_column=Column("attempt_count", Integer, nullable=False, default=0, server_default="0"),
        description="任务子项已尝试次数。",
    )
    max_attempts: int = Field(
        default=3,
        sa_column=Column("max_attempts", Integer, nullable=False, default=3, server_default="3"),
        description="任务子项最大尝试次数。",
    )
    worker_id: str = Field(
        default="",
        sa_column=Column("worker_id", String(120), nullable=False, default="", server_default="", index=True),
        description="当前或最近处理该子项的 Worker 标识。",
    )
    payload: str = Field(
        default="{}",
        sa_column=Column("payload", Text(), nullable=False, default="{}", server_default="{}"),
        description="任务子项输入参数，JSON 字符串。",
    )
    result: str = Field(
        default="{}",
        sa_column=Column("result", Text(), nullable=False, default="{}", server_default="{}"),
        description="任务子项执行结果，JSON 字符串。",
    )
    error_code: str = Field(
        default="",
        sa_column=Column("error_code", String(100), nullable=False, default="", server_default=""),
        description="任务子项错误码。",
    )
    error_message: str = Field(
        default="",
        sa_column=Column("error_message", Text(), nullable=False, default="", server_default=""),
        description="任务子项错误信息。",
    )
    scheduled_at: datetime | None = Field(
        default=None,
        sa_column=Column("scheduled_at", DateTime(timezone=True), nullable=True, index=True),
        description="任务子项计划调度时间。",
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column("started_at", DateTime(timezone=True), nullable=True),
        description="任务子项开始执行时间。",
    )
    heartbeat_at: datetime | None = Field(
        default=None,
        sa_column=Column("heartbeat_at", DateTime(timezone=True), nullable=True),
        description="Worker 最近心跳时间。",
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column("completed_at", DateTime(timezone=True), nullable=True),
        description="任务子项完成时间。",
    )

class TaskDeadLetter(TaskBaseModel, table=True):
    """异步任务死信记录。"""

    __tablename__ = "af_task_dead_letter"

    job_id: int | None = Field(
        default=None,
        sa_column=Column("job_id", Integer, ForeignKey("af_task_job.id"), nullable=True, index=True),
        description="所属任务内部主键。",
    )
    item_id: int | None = Field(
        default=None,
        sa_column=Column("item_id", Integer, ForeignKey("af_task_item.id"), nullable=True, index=True),
        description="所属任务子项内部主键。",
    )
    job_public_id: str = Field(
        default="",
        sa_column=Column("job_public_id", String(36), nullable=False, default="", server_default="", index=True),
        description="任务公开标识。",
    )
    item_public_id: str = Field(
        default="",
        sa_column=Column("item_public_id", String(36), nullable=False, default="", server_default="", index=True),
        description="任务子项公开标识。",
    )
    task_type: str = Field(
        default="",
        sa_column=Column("task_type", String(100), nullable=False, default="", server_default="", index=True),
        description="任务类型标识。",
    )
    item_type: str = Field(
        default="",
        sa_column=Column("item_type", String(100), nullable=False, default="", server_default="", index=True),
        description="任务子项类型标识。",
    )
    queue_name: str = Field(
        default="default",
        sa_column=Column("queue_name", String(120), nullable=False, default="default", server_default="default", index=True),
        description="任务队列名称。",
    )
    stream_id: str = Field(
        default="",
        sa_column=Column("stream_id", String(120), nullable=False, default="", server_default="", index=True),
        description="Redis Stream 消息 ID。",
    )
    stage: str = Field(
        default="",
        sa_column=Column("stage", String(100), nullable=False, default="", server_default="", index=True),
        description="进入死信队列时所处阶段。",
    )
    worker_id: str = Field(
        default="",
        sa_column=Column("worker_id", String(120), nullable=False, default="", server_default="", index=True),
        description="处理该任务的 Worker 标识。",
    )
    attempt_count: int = Field(
        default=0,
        sa_column=Column("attempt_count", Integer, nullable=False, default=0, server_default="0"),
        description="进入死信队列时的已尝试次数。",
    )
    max_attempts: int = Field(
        default=0,
        sa_column=Column("max_attempts", Integer, nullable=False, default=0, server_default="0"),
        description="任务子项最大尝试次数。",
    )
    error_code: str = Field(
        default="",
        sa_column=Column("error_code", String(100), nullable=False, default="", server_default=""),
        description="死信错误码。",
    )
    error_message: str = Field(
        default="",
        sa_column=Column("error_message", Text(), nullable=False, default="", server_default=""),
        description="死信错误信息。",
    )
    payload: str = Field(
        default="{}",
        sa_column=Column("payload", Text(), nullable=False, default="{}", server_default="{}"),
        description="任务子项输入参数，JSON 字符串。",
    )
    result: str = Field(
        default="{}",
        sa_column=Column("result", Text(), nullable=False, default="{}", server_default="{}"),
        description="任务子项执行结果，JSON 字符串。",
    )
