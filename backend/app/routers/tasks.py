from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.tasks.engine import default_async_task_engine
from app.middlewares import common
from app.models.tasks import TaskStatus
from app.routers.base import BaseView, route
from app.schemas.tasks import (
    TaskItemPage,
    TaskItemRead,
    TaskJobCancelRequest,
    TaskJobCancelResponse,
    TaskJobCreate,
    TaskJobDeleteResponse,
    TaskJobDetail,
    TaskJobPage,
    TaskJobPauseRequest,
    TaskJobPauseResponse,
    TaskJobRead,
    TaskJobResumeRequest,
    TaskJobResumeResponse,
    TaskJobRetryRequest,
    TaskJobRetryResponse,
    TaskMetricsResponse,
    TaskMetricsTimeseriesResponse,
)
from app.services import project as project_service
from app.services import task_metrics
from app.services import tasks as task_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]

TASK_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]

CANCELLABLE_ITEM_STATUSES = {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.PAUSED}
PAUSABLE_ITEM_STATUSES = {TaskStatus.PENDING, TaskStatus.QUEUED}
RESUMABLE_ITEM_STATUSES = {TaskStatus.PAUSED}
RETRYABLE_ITEM_STATUSES = {TaskStatus.FAILED, TaskStatus.CANCELLED}


class TaskView(BaseView):
    """异步任务类视图。"""

    router_prefix = "/tasks"
    router_tags = ["tasks"]

    @route(
        "",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_201_CREATED,
        summary="添加单个异步任务",
        description="创建单个异步任务记录，不立即投递到执行队列。",
    )
    async def create_task(
        self,
        payload: TaskJobCreate,
        session: SessionDep,
    ) -> TaskJobDetail:
        """添加单个异步任务。"""
        return await default_async_task_engine.create_task_job(session, payload)

    @route(
        "/enqueue",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        summary="添加并启动单个异步任务",
        description="创建单个异步任务记录，并立即投递可执行的任务子项。",
    )
    async def create_and_enqueue_task(
        self,
        payload: TaskJobCreate,
        session: SessionDep,
    ) -> TaskJobDetail:
        """添加并启动单个异步任务。"""
        return await default_async_task_engine.create_and_enqueue_task_job(session, payload)

    @route(
        "/batch",
        methods=["POST"],
        response_model=list[TaskJobDetail],
        status_code=status.HTTP_201_CREATED,
        summary="批量添加异步任务",
        description="批量创建异步任务记录，不立即投递到执行队列。",
    )
    async def create_tasks(
        self,
        payloads: list[TaskJobCreate],
        session: SessionDep,
    ) -> list[TaskJobDetail]:
        """批量添加异步任务。"""
        jobs: list[TaskJobDetail] = []
        for payload in payloads:
            jobs.append(await default_async_task_engine.create_task_job(session, payload))
        return jobs

    @route(
        "/batch/enqueue",
        methods=["POST"],
        response_model=list[TaskJobDetail],
        status_code=status.HTTP_202_ACCEPTED,
        summary="批量添加并启动异步任务",
        description="批量创建异步任务记录，并立即投递可执行的任务子项。",
    )
    async def create_and_enqueue_tasks(
        self,
        payloads: list[TaskJobCreate],
        session: SessionDep,
    ) -> list[TaskJobDetail]:
        """批量添加并启动异步任务。"""
        jobs: list[TaskJobDetail] = []
        for payload in payloads:
            jobs.append(await default_async_task_engine.create_and_enqueue_task_job(session, payload))
        return jobs

    @route(
        "/{job_public_id}/start",
        methods=["POST"],
        response_model=list[str],
        status_code=status.HTTP_202_ACCEPTED,
        summary="开启任务",
        description="将指定异步任务的可执行子项投递到任务队列。",
    )
    async def start_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> list[str]:
        """开启指定异步任务。"""
        records = await default_async_task_engine.enqueue_task_job(session, job_public_id)
        return [record.stream_id for record in records]

    @route(
        "/{job_public_id}/pause",
        methods=["POST"],
        response_model=TaskJobRead,
        summary="暂停任务",
        description="暂停指定异步任务，避免继续调度未执行的任务子项。",
    )
    async def pause_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> TaskJobRead:
        """暂停指定异步任务。"""
        return await default_async_task_engine.pause_task_job(session, job_public_id)

    @route(
        "/{job_public_id}/resume",
        methods=["POST"],
        response_model=list[str],
        status_code=status.HTTP_202_ACCEPTED,
        summary="恢复任务",
        description="恢复指定异步任务，并重新投递可执行的任务子项。",
    )
    async def resume_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> list[str]:
        """恢复指定异步任务。"""
        records = await default_async_task_engine.resume_task_job(session, job_public_id)
        return [record.stream_id for record in records]

    @route(
        "/{job_public_id}/cancel",
        methods=["POST"],
        response_model=TaskJobRead,
        summary="取消任务",
        description="取消指定异步任务及其尚未完成的任务子项。",
    )
    async def cancel_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> TaskJobRead:
        """取消指定异步任务。"""
        return await default_async_task_engine.cancel_task_job(session, job_public_id)

    @route(
        "/items/{item_public_id}/cancel",
        methods=["POST"],
        response_model=TaskItemRead,
        summary="取消任务子项",
        description="取消指定异步任务子项，并刷新所属任务的进度统计。",
    )
    async def cancel_task_item(
        self,
        item_public_id: str,
        session: SessionDep,
    ) -> TaskItemRead:
        """取消指定异步任务子项。"""
        return await default_async_task_engine.cancel_task_item(session, item_public_id)

    @route(
        "/items/{item_public_id}/retry",
        methods=["POST"],
        response_model=TaskItemRead,
        status_code=status.HTTP_202_ACCEPTED,
        summary="重试任务子项",
        description="将指定异步任务子项重置为待执行状态，等待后续重新调度。",
    )
    async def retry_task_item(
        self,
        item_public_id: str,
        session: SessionDep,
    ) -> TaskItemRead:
        """重试指定异步任务子项。"""
        return await default_async_task_engine.retry_task_item(session, item_public_id)

    @route(
        "/{job_public_id}",
        methods=["DELETE"],
        response_model=None,
        status_code=status.HTTP_204_NO_CONTENT,
        summary="删除任务",
        description="软删除指定异步任务及其任务子项。",
    )
    async def delete_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> Response:
        """删除指定异步任务。"""
        await default_async_task_engine.delete_task_job(session, job_public_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/{job_public_id}",
        methods=["GET"],
        response_model=TaskJobDetail,
        summary="查看单个任务",
        description="查看指定异步任务详情，并包含任务子项列表。",
    )
    async def get_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> TaskJobDetail:
        """查看单个异步任务。"""
        return await default_async_task_engine.get_task_job(
            session,
            job_public_id,
            include_items=True,
        )

    @route(
        "",
        methods=["GET"],
        response_model=TaskJobPage,
        summary="查看批量任务",
        description="按分页和筛选条件查看异步任务列表。",
    )
    async def list_tasks(
        self,
        session: SessionDep,
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=20, ge=1, le=100),
        task_type: str = "",
        queue_name: str = "",
        project_public_id: str = "",
        status_: TaskStatus | None = Query(default=None, alias="status"),
    ) -> TaskJobPage:
        """查看批量异步任务。"""
        return await default_async_task_engine.list_task_jobs(
            session,
            page=page,
            limit=limit,
            task_type=task_type,
            queue_name=queue_name,
            project_public_id=project_public_id,
            status=status_,
        )


class ProjectTaskView(BaseView):
    """项目维度异步任务类视图。"""

    router_prefix = "/projects/{project_public_id}/tasks"
    router_tags = ["tasks"]

    @staticmethod
    def _current_user_public_id(request: Request) -> str:
        """从已认证请求中读取当前用户公开标识。"""
        public_id = getattr(request.state, "current_user_public_id", None)
        if not public_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请提供 access token",
                headers=common.BEARER_AUTH_HEADER,
            )
        return str(public_id)

    @staticmethod
    def _raise_project_error(exc: Exception) -> None:
        """将项目与任务服务层异常转换为 HTTP 异常。"""
        if isinstance(exc, project_service.ProjectNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, project_service.ProjectAccessDeniedError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        if isinstance(exc, (task_service.TaskJobNotFoundError, task_service.TaskItemNotFoundError)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, task_service.TaskValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, task_metrics.WindowNotAllowedError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    async def _ensure_project_access(
        self,
        session: SessionDep,
        project_public_id: str,
        current_user_public_id: str,
    ) -> None:
        """确认当前用户可以访问指定项目。"""
        try:
            await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
        except project_service.ProjectServiceError as exc:
            self._raise_project_error(exc)

    async def _get_project_task(
        self,
        session: SessionDep,
        project_public_id: str,
        job_public_id: str,
        *,
        include_items: bool = False,
    ) -> TaskJobRead | TaskJobDetail:
        """读取任务并校验其归属项目。"""
        try:
            job = await default_async_task_engine.get_task_job(
                session,
                job_public_id,
                include_items=include_items,
            )
        except task_service.TaskServiceError as exc:
            self._raise_project_error(exc)

        if str(job.payload.get("project_public_id") or "") != project_public_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        return job

    @staticmethod
    def _target_item_ids(values: list[str] | None) -> set[str]:
        """规整前端传入的子项公开标识。"""
        return {value.strip() for value in values or [] if value and value.strip()}

    @staticmethod
    def _count_items(
        items: list[TaskItemRead],
        allowed_statuses: set[TaskStatus],
        target_item_ids: set[str] | None = None,
    ) -> int:
        """统计符合状态和目标范围的子项数量。"""
        return sum(
            1
            for item in items
            if item.status in allowed_statuses and (not target_item_ids or item.public_id in target_item_ids)
        )

    @staticmethod
    def _filter_task_items_by_status(
        items: list[TaskItemRead],
        status_: TaskStatus | None,
    ) -> list[TaskItemRead]:
        """按前端展示语义筛选子项；排队中同时包含待处理和已入队。"""
        if status_ is None:
            return items
        allowed_statuses = {status_}
        if status_ == TaskStatus.PENDING:
            allowed_statuses.add(TaskStatus.QUEUED)
        return [item for item in items if item.status in allowed_statuses]

    @staticmethod
    def _page_task_items(items: list[TaskItemRead], page: int, page_size: int) -> TaskItemPage:
        """对子项列表做内存分页，保持与任务底座查询结果一致。"""
        safe_page = max(page, 1)
        safe_page_size = min(max(page_size, 1), 100)
        start = (safe_page - 1) * safe_page_size
        return TaskItemPage(
            data=items[start : start + safe_page_size],
            total=len(items),
            page=safe_page,
            limit=safe_page_size,
        )

    @route(
        "/",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="添加并启动项目异步任务",
        description="在指定项目下创建异步任务记录，并立即投递可执行的任务子项。",
    )
    async def create_project_task(
        self,
        project_public_id: str,
        payload: TaskJobCreate,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        """添加并启动指定项目下的异步任务。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)

        payload_data = payload.model_dump()
        payload_data["created_by"] = payload.created_by or current_user_public_id
        payload_data["payload"] = {
            **(payload.payload or {}),
            "project_public_id": project_public_id,
        }
        return await default_async_task_engine.create_and_enqueue_task_job(
            session,
            TaskJobCreate(**payload_data),
        )

    @route(
        "/",
        methods=["GET"],
        response_model=TaskJobPage,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="查看项目异步任务列表",
        description="按项目公开 ID 分页查看该项目关联的异步任务列表。",
    )
    async def list_project_tasks(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        task_type: str = "",
        queue_name: str = "",
        status_: TaskStatus | None = Query(default=None, alias="status"),
    ) -> TaskJobPage:
        """查看指定项目下的异步任务列表。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)

        return await default_async_task_engine.list_task_jobs(
            session,
            page=page,
            limit=page_size,
            task_type=task_type,
            queue_name=queue_name,
            project_public_id=project_public_id,
            status=status_,
        )

    @route(
        "/metrics",
        methods=["GET"],
        response_model=TaskMetricsResponse,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="查看项目异步任务指标",
        description="返回项目维度的队列堆积与近端活跃度指标。",
    )
    async def get_project_task_metrics(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> TaskMetricsResponse:
        """查看指定项目下的异步任务指标。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        service = task_metrics.TaskMetricsService()
        return await service.snapshot(session, project_public_id)

    @route(
        "/metrics/timeseries",
        methods=["GET"],
        response_model=TaskMetricsTimeseriesResponse,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="查看项目异步任务时序指标",
        description="按窗口长度返回固定桶数的提交、完成、失败和均耗时指标。",
    )
    async def get_project_task_metrics_timeseries(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        window: int = Query(description="时间窗口长度，单位秒。"),
    ) -> TaskMetricsTimeseriesResponse:
        """查看指定项目下的异步任务时序指标。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        service = task_metrics.TaskMetricsService()
        try:
            return await service.timeseries(session, project_public_id, window)
        except task_metrics.WindowNotAllowedError as exc:
            self._raise_project_error(exc)

    @route(
        "/{job_public_id}",
        methods=["GET"],
        response_model=TaskJobDetail,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="查看项目异步任务详情",
        description="查看指定项目下的单个异步任务详情，并包含任务子项列表。",
    )
    async def get_project_task(
        self,
        project_public_id: str,
        job_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        """查看指定项目下的单个异步任务。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        job = await self._get_project_task(
            session,
            project_public_id,
            job_public_id,
            include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        return job

    @route(
        "/{job_public_id}/items",
        methods=["GET"],
        response_model=TaskItemPage,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="查看项目异步任务子项列表",
        description="按分页和可选状态筛选查看指定异步任务的子项列表。",
    )
    async def list_project_task_items(
        self,
        project_public_id: str,
        job_public_id: str,
        request: Request,
        session: SessionDep,
        status_: TaskStatus | None = Query(default=None, alias="status"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> TaskItemPage:
        """查看指定项目任务的子项列表。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        await self._get_project_task(session, project_public_id, job_public_id)
        query_status = None if status_ == TaskStatus.PENDING else status_
        items = await default_async_task_engine.list_task_items(session, job_public_id, status=query_status)
        items = self._filter_task_items_by_status(items, status_)
        return self._page_task_items(items, page, page_size)

    @route(
        "/{job_public_id}/items/{item_public_id}",
        methods=["GET"],
        response_model=TaskItemRead,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="查看项目异步任务子项详情",
        description="查看指定项目任务下的单个子项执行详情。",
    )
    async def get_project_task_item(
        self,
        project_public_id: str,
        job_public_id: str,
        item_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> TaskItemRead:
        """查看指定项目任务下的单个子项。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        job = await self._get_project_task(
            session,
            project_public_id,
            job_public_id,
            include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        for item in job.items:
            if item.public_id == item_public_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务子项不存在")

    @route(
        "/{job_public_id}/cancel",
        methods=["POST"],
        response_model=TaskJobCancelResponse,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="取消项目异步任务",
        description="取消指定项目任务及其尚未完成的任务子项。",
    )
    async def cancel_project_task(
        self,
        project_public_id: str,
        job_public_id: str,
        payload: TaskJobCancelRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobCancelResponse:
        """取消指定项目下的异步任务。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        job = await self._get_project_task(
            session,
            project_public_id,
            job_public_id,
            include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")

        target_ids = self._target_item_ids(payload.item_public_ids)
        canceled_count = self._count_items(job.items, CANCELLABLE_ITEM_STATUSES, target_ids or None)
        if target_ids:
            for item in job.items:
                if item.public_id in target_ids and item.status in CANCELLABLE_ITEM_STATUSES:
                    await default_async_task_engine.cancel_task_item(session, item.public_id)
        else:
            await default_async_task_engine.cancel_task_job(session, job_public_id)
        return TaskJobCancelResponse(canceled_count=canceled_count)

    @route(
        "/{job_public_id}/pause",
        methods=["POST"],
        response_model=TaskJobPauseResponse,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="暂停项目异步任务",
        description="暂停指定项目任务，避免继续调度未执行的任务子项。",
    )
    async def pause_project_task(
        self,
        project_public_id: str,
        job_public_id: str,
        payload: TaskJobPauseRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobPauseResponse:
        """暂停指定项目下的异步任务。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        job = await self._get_project_task(
            session,
            project_public_id,
            job_public_id,
            include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        target_ids = self._target_item_ids(payload.item_public_ids)
        paused_count = self._count_items(job.items, PAUSABLE_ITEM_STATUSES, target_ids or None)
        if target_ids:
            await task_service.pause_task_items(session, job_public_id, target_ids)
        else:
            await default_async_task_engine.pause_task_job(session, job_public_id)
        return TaskJobPauseResponse(paused_count=paused_count)

    @route(
        "/{job_public_id}/resume",
        methods=["POST"],
        response_model=TaskJobResumeResponse,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="恢复项目异步任务",
        description="恢复指定项目任务，并重新投递可执行的任务子项。",
    )
    async def resume_project_task(
        self,
        project_public_id: str,
        job_public_id: str,
        payload: TaskJobResumeRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobResumeResponse:
        """恢复指定项目下的异步任务。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        job = await self._get_project_task(
            session,
            project_public_id,
            job_public_id,
            include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        target_ids = self._target_item_ids(payload.item_public_ids)
        resumed_count = self._count_items(job.items, RESUMABLE_ITEM_STATUSES, target_ids or None)
        if target_ids:
            await task_service.resume_task_items(session, job_public_id, target_ids)
            for item in job.items:
                if item.public_id in target_ids and item.status in RESUMABLE_ITEM_STATUSES:
                    await default_async_task_engine.enqueue_task_item(session, item.public_id)
        else:
            await default_async_task_engine.resume_task_job(session, job_public_id)
        return TaskJobResumeResponse(resumed_count=resumed_count)

    @route(
        "/{job_public_id}/retry",
        methods=["POST"],
        response_model=TaskJobRetryResponse,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="重试项目异步任务失败子项",
        description="将指定失败或已取消子项重新置为待执行，并立即重新投递。",
    )
    async def retry_project_task_items(
        self,
        project_public_id: str,
        job_public_id: str,
        payload: TaskJobRetryRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobRetryResponse:
        """重试指定项目任务下的子项。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        job = await self._get_project_task(
            session,
            project_public_id,
            job_public_id,
            include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        target_ids = self._target_item_ids(payload.item_public_ids)
        retried_ids: list[str] = []
        for item in job.items:
            if item.public_id in target_ids and item.status in RETRYABLE_ITEM_STATUSES:
                retried = await default_async_task_engine.retry_task_item(session, item.public_id)
                retried_ids.append(retried.public_id)
        return TaskJobRetryResponse(new_item_public_ids=retried_ids)

    @route(
        "/{job_public_id}",
        methods=["DELETE"],
        response_model=TaskJobDeleteResponse,
        middlewares=TASK_ROUTE_MIDDLEWARES,
        summary="删除项目异步任务",
        description="软删除指定项目任务及其任务子项。",
    )
    async def delete_project_task(
        self,
        project_public_id: str,
        job_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDeleteResponse:
        """删除指定项目下的异步任务。"""
        current_user_public_id = self._current_user_public_id(request)
        await self._ensure_project_access(session, project_public_id, current_user_public_id)
        await self._get_project_task(session, project_public_id, job_public_id)
        await default_async_task_engine.delete_task_job(session, job_public_id)
        return TaskJobDeleteResponse(status="deleted")


router = APIRouter()
router.include_router(TaskView()())
router.include_router(ProjectTaskView()())
