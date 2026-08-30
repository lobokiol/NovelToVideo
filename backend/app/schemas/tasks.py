from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.tasks import TaskStatus


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True)


class TaskItemCreate(BaseModel):
    """创建异步任务子项请求。"""

    item_type: str = Field(default="", max_length=100, description="任务子项类型标识")
    item_key: str | None = Field(default=None, max_length=120, description="任务子项唯一键")
    priority: int = Field(default=0, description="任务子项优先级")
    max_attempts: int = Field(default=3, ge=1, le=100, description="最大尝试次数")
    payload: dict[str, Any] = Field(default_factory=dict, description="任务子项参数")
    scheduled_at: datetime | None = Field(default=None, description="计划调度时间")


class TaskJobCreate(BaseModel):
    """创建异步任务请求。"""

    task_type: str = Field(min_length=1, max_length=100, description="任务类型标识")
    queue_name: str = Field(default="default", min_length=1, max_length=120, description="任务队列名称")
    name: str = Field(default="", max_length=255, description="任务展示名称")
    created_by: str = Field(default="", max_length=36, description="任务创建人的用户公开标识")
    idempotency_key: str = Field(default="", max_length=120, description="幂等键")
    priority: int = Field(default=0, description="任务优先级")
    payload: dict[str, Any] = Field(default_factory=dict, description="任务参数")
    scheduled_at: datetime | None = Field(default=None, description="计划调度时间")
    items: list[TaskItemCreate] = Field(default_factory=list, description="初始任务子项")


class TaskStatusUpdate(BaseModel):
    """更新异步任务状态请求。"""

    status: TaskStatus = Field(description="目标状态")
    result: dict[str, Any] | None = Field(default=None, description="执行结果")
    error_code: str = Field(default="", max_length=100, description="错误码")
    error_message: str = Field(default="", description="错误信息")
    worker_id: str | None = Field(default=None, max_length=120, description="Worker 标识")


class TaskItemRead(BaseModel):
    """异步任务子项响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    job_id: int
    item_type: str
    item_key: str | None
    status: TaskStatus
    priority: int
    attempt_count: int
    max_attempts: int
    worker_id: str
    payload: dict[str, Any]
    result: dict[str, Any]
    error_code: str
    error_message: str
    scheduled_at: datetime | None
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class TaskJobRead(BaseModel):
    """异步任务响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    task_type: str
    queue_name: str
    name: str
    status: TaskStatus
    created_by: str
    idempotency_key: str
    priority: int
    total_items: int
    pending_items: int = Field(default=0, description="待处理任务子项数量")
    queued_items: int = Field(default=0, description="已入队待消费任务子项数量")
    running_items: int = Field(default=0, description="运行中任务子项数量")
    completed_items: int
    failed_items: int
    cancelled_items: int
    paused_items: int = Field(default=0, description="已暂停任务子项数量")
    payload: dict[str, Any]
    result: dict[str, Any]
    error_code: str
    error_message: str
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class TaskJobDetail(TaskJobRead):
    """异步任务详情响应。"""

    items: list[TaskItemRead] = Field(default_factory=list)


class TaskJobPage(BaseModel):
    """异步任务分页响应。"""

    data: list[TaskJobRead]
    total: int
    page: int
    limit: int


class TaskItemPage(BaseModel):
    """异步任务子项分页响应。"""

    data: list[TaskItemRead]
    total: int
    page: int
    limit: int


class TaskItemIdsRequest(BaseModel):
    """按任务子项公开标识批量操作的通用请求。"""

    item_public_ids: list[str] | None = Field(
        default=None,
        description="任务子项公开标识列表，空值表示操作整个任务",
    )


class TaskJobCancelRequest(TaskItemIdsRequest):
    """取消异步任务请求。"""


class TaskJobPauseRequest(TaskItemIdsRequest):
    """暂停异步任务请求。"""


class TaskJobResumeRequest(TaskItemIdsRequest):
    """恢复异步任务请求。"""


class TaskJobRetryRequest(BaseModel):
    """重试异步任务子项请求。"""

    item_public_ids: list[str] = Field(
        default_factory=list,
        description="需要重试的任务子项公开标识列表",
    )


class TaskJobCancelResponse(BaseModel):
    """取消异步任务响应。"""

    canceled_count: int = Field(description="本次取消的任务子项数量")


class TaskJobPauseResponse(BaseModel):
    """暂停异步任务响应。"""

    paused_count: int = Field(description="本次暂停的任务子项数量")


class TaskJobResumeResponse(BaseModel):
    """恢复异步任务响应。"""

    resumed_count: int = Field(description="本次恢复的任务子项数量")


class TaskJobRetryResponse(BaseModel):
    """重试异步任务响应。"""

    new_item_public_ids: list[str] = Field(description="重新投递的任务子项公开标识列表")


class TaskJobDeleteResponse(BaseModel):
    """删除异步任务响应。"""

    status: str = Field(default="deleted", description="删除结果状态")


class QueueStatsView(BaseModel):
    """任务队列堆积指标。"""

    pending_item_count: int = Field(description="待执行或已入队的任务子项数量")
    running_item_count: int = Field(description="运行中的任务子项数量")
    requeue_last5_min: int = Field(default=0, description="最近 5 分钟重新入队次数")


class ActivityWindowView(BaseModel):
    """指定时间窗口内的任务活跃度。"""

    submitted_item_count: int = Field(description="窗口内提交的任务子项数量")
    completed_item_count: int = Field(description="窗口内成功完成的任务子项数量")
    failed_item_count: int = Field(description="窗口内失败的任务子项数量")
    avg_duration_ms: int = Field(description="窗口内成功子项平均耗时，单位毫秒")


class RecentActivityView(BaseModel):
    """多窗口任务活跃度。"""

    last_minute: ActivityWindowView
    last_thirty_minutes: ActivityWindowView
    last_hour: ActivityWindowView
    last_six_hours: ActivityWindowView


class TaskMetricsResponse(BaseModel):
    """项目维度任务指标快照。"""

    queue_stats: QueueStatsView
    recent_activity: RecentActivityView


class TimeseriesPoint(BaseModel):
    """任务活跃度时序桶。"""

    bucket_start: datetime = Field(description="桶起始时间")
    submitted_item_count: int
    completed_item_count: int
    failed_item_count: int
    avg_duration_ms: int


class TaskMetricsTimeseriesResponse(BaseModel):
    """任务指标时序响应。"""

    window_seconds: int
    bucket_seconds: int
    points: list[TimeseriesPoint]


class TaskDeadLetterRead(BaseModel):
    """异步任务死信响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    job_id: int | None
    item_id: int | None
    job_public_id: str
    item_public_id: str
    task_type: str
    item_type: str
    queue_name: str
    stream_id: str
    stage: str
    worker_id: str
    attempt_count: int
    max_attempts: int
    error_code: str
    error_message: str
    payload: dict[str, Any]
    result: dict[str, Any]
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class TaskStreamMessage(BaseModel):
    """Redis Stream 中的异步任务消息。"""

    event: str = Field(default="task.item.queued", description="消息事件类型")
    job_public_id: str = Field(min_length=1, max_length=36, description="任务公开标识")
    item_public_id: str = Field(min_length=1, max_length=36, description="任务子项公开标识")
    task_type: str = Field(min_length=1, max_length=100, description="任务类型标识")
    item_type: str = Field(default="", max_length=100, description="任务子项类型标识")
    queue_name: str = Field(default="default", max_length=120, description="任务队列名称")
    priority: int = Field(default=0, description="任务子项优先级")
    payload: dict[str, Any] = Field(default_factory=dict, description="任务子项参数")
    scheduled_at: datetime | None = Field(default=None, description="计划调度时间")
    created_at: datetime = Field(description="消息创建时间")


class TaskStreamRecord(BaseModel):
    """Redis Stream 消息读取结果。"""

    stream_id: str
    message: TaskStreamMessage
