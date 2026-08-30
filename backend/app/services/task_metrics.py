from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.tasks import TaskItem, TaskJob, TaskStatus, utc_now
from app.schemas.tasks import (
    ActivityWindowView,
    QueueStatsView,
    RecentActivityView,
    TaskMetricsResponse,
    TaskMetricsTimeseriesResponse,
    TimeseriesPoint,
)

ALLOWED_WINDOW_SECONDS: tuple[int, ...] = (
    60,
    300,
    600,
    900,
    1800,
    3600,
    10800,
    21600,
    43200,
    86400,
)
TIMESERIES_BUCKET_COUNT = 30


class WindowNotAllowedError(ValueError):
    """非法的时间窗口长度。"""


class TaskMetricsService:
    """按项目维度聚合异步任务指标。"""

    async def snapshot(self, session: AsyncSession, project_public_id: str) -> TaskMetricsResponse:
        """返回任务页顶部指标快照。"""
        items = await self._list_project_items(session, project_public_id)
        return TaskMetricsResponse(
            queue_stats=self._queue_stats(items),
            recent_activity=self._recent_activity(items),
        )

    async def timeseries(
        self,
        session: AsyncSession,
        project_public_id: str,
        window_seconds: int,
    ) -> TaskMetricsTimeseriesResponse:
        """返回任务页折线图使用的时序指标。"""
        if window_seconds not in ALLOWED_WINDOW_SECONDS:
            raise WindowNotAllowedError(
                f"window_seconds 必须为 {ALLOWED_WINDOW_SECONDS} 之一，实际收到 {window_seconds}"
            )
        items = await self._list_project_items(session, project_public_id)
        return self._timeseries(items, window_seconds)

    async def _list_project_items(self, session: AsyncSession, project_public_id: str) -> list[TaskItem]:
        """读取项目关联任务的未删除子项。"""
        job_result = await session.exec(
            select(TaskJob).where(TaskJob.disabled_at.is_(None)).order_by(TaskJob.created_at.desc())
        )
        job_ids = [
            int(job.id)
            for job in job_result.all()
            if job.id is not None and _payload_project_public_id(job.payload) == project_public_id.strip()
        ]
        if not job_ids:
            return []

        item_result = await session.exec(
            select(TaskItem)
            .where(TaskItem.disabled_at.is_(None), col(TaskItem.job_id).in_(job_ids))
            .order_by(TaskItem.created_at.asc(), TaskItem.id.asc())
        )
        return list(item_result.all())

    def _queue_stats(self, items: list[TaskItem]) -> QueueStatsView:
        """统计当前队列堆积。"""
        pending_statuses = {TaskStatus.PENDING, TaskStatus.QUEUED}
        return QueueStatsView(
            pending_item_count=sum(1 for item in items if item.status in pending_statuses),
            running_item_count=sum(1 for item in items if item.status == TaskStatus.RUNNING),
            requeue_last5_min=0,
        )

    def _recent_activity(self, items: list[TaskItem]) -> RecentActivityView:
        """统计多时间窗口活跃度。"""
        now = utc_now()
        return RecentActivityView(
            last_minute=self._activity_window(items, now - timedelta(minutes=1)),
            last_thirty_minutes=self._activity_window(items, now - timedelta(minutes=30)),
            last_hour=self._activity_window(items, now - timedelta(hours=1)),
            last_six_hours=self._activity_window(items, now - timedelta(hours=6)),
        )

    def _activity_window(self, items: list[TaskItem], since: datetime) -> ActivityWindowView:
        """统计指定窗口内的提交、完成、失败与成功均耗。"""
        submitted = 0
        completed = 0
        failed = 0
        duration_sum = 0
        duration_count = 0

        for item in items:
            created_at = _normalize_datetime(item.created_at, since)
            completed_at = _normalize_datetime(item.completed_at, since)
            started_at = _normalize_datetime(item.started_at, since)

            if created_at is not None and created_at >= since:
                submitted += 1
            if completed_at is None or completed_at < since:
                continue
            if item.status == TaskStatus.SUCCEEDED:
                completed += 1
                duration = _duration_ms(started_at, completed_at)
                if duration is not None:
                    duration_sum += duration
                    duration_count += 1
            elif item.status == TaskStatus.FAILED:
                failed += 1

        return ActivityWindowView(
            submitted_item_count=submitted,
            completed_item_count=completed,
            failed_item_count=failed,
            avg_duration_ms=round(duration_sum / duration_count) if duration_count else 0,
        )

    def _timeseries(self, items: list[TaskItem], window_seconds: int) -> TaskMetricsTimeseriesResponse:
        """按固定桶数聚合时序指标。"""
        bucket_seconds = max(1, window_seconds // TIMESERIES_BUCKET_COUNT)
        now = utc_now()
        window_start = now - timedelta(seconds=window_seconds)

        submitted = [0] * TIMESERIES_BUCKET_COUNT
        completed = [0] * TIMESERIES_BUCKET_COUNT
        failed = [0] * TIMESERIES_BUCKET_COUNT
        duration_sum = [0] * TIMESERIES_BUCKET_COUNT
        duration_count = [0] * TIMESERIES_BUCKET_COUNT

        for item in items:
            created_at = _normalize_datetime(item.created_at, now)
            completed_at = _normalize_datetime(item.completed_at, now)
            started_at = _normalize_datetime(item.started_at, now)

            submit_index = _bucket_index(created_at, window_start, bucket_seconds)
            if submit_index is not None:
                submitted[submit_index] += 1

            finish_index = _bucket_index(completed_at, window_start, bucket_seconds)
            if finish_index is None:
                continue
            if item.status == TaskStatus.SUCCEEDED:
                completed[finish_index] += 1
                duration = _duration_ms(started_at, completed_at)
                if duration is not None:
                    duration_sum[finish_index] += duration
                    duration_count[finish_index] += 1
            elif item.status == TaskStatus.FAILED:
                failed[finish_index] += 1

        points: list[TimeseriesPoint] = []
        for index in range(TIMESERIES_BUCKET_COUNT):
            points.append(
                TimeseriesPoint(
                    bucket_start=window_start + timedelta(seconds=index * bucket_seconds),
                    submitted_item_count=submitted[index],
                    completed_item_count=completed[index],
                    failed_item_count=failed[index],
                    avg_duration_ms=round(duration_sum[index] / duration_count[index])
                    if duration_count[index]
                    else 0,
                )
            )

        return TaskMetricsTimeseriesResponse(
            window_seconds=window_seconds,
            bucket_seconds=bucket_seconds,
            points=points,
        )


def _payload_project_public_id(raw_payload: str) -> str:
    """从任务 payload 中读取项目公开标识。"""
    return str(_load_json(raw_payload).get("project_public_id") or "")


def _load_json(value: str | dict[str, Any] | None) -> dict[str, Any]:
    """兼容数据库 JSON 字符串和已解析字典。"""
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_datetime(value: datetime | None, fallback_tz: datetime) -> datetime | None:
    """统一 SQLite 返回的 naive datetime 与带时区 datetime。"""
    if value is None:
        return None
    if value.tzinfo is None and fallback_tz.tzinfo is not None:
        return value.replace(tzinfo=fallback_tz.tzinfo)
    return value


def _duration_ms(started_at: datetime | None, completed_at: datetime | None) -> int | None:
    """计算任务子项耗时毫秒。"""
    if started_at is None or completed_at is None or completed_at < started_at:
        return None
    return round((completed_at - started_at).total_seconds() * 1000)


def _bucket_index(ts: datetime | None, window_start: datetime, bucket_seconds: int) -> int | None:
    """将时间戳映射到时序桶下标。"""
    if ts is None:
        return None
    if ts < window_start:
        return None
    index = int((ts - window_start).total_seconds() // bucket_seconds)
    if index < 0 or index >= TIMESERIES_BUCKET_COUNT:
        return None
    return index
