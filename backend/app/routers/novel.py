from __future__ import annotations

import json
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.novel import (
    CrawlAnalyzePayload,
    CrawlAnalyzeResult,
    CrawlBookChapterCountResult,
    CrawlBookDetailResult,
    CrawlBookPayload,
    CrawlChapterDraft,
    CrawlChapterFetchPayload,
    CrawlImportPayload,
    CrawlImportResult,
    CrawlSearchPayload,
    CrawlSearchResult,
    CrawlSourceDuplicate,
    CrawlSourcePayload,
    CrawlSourceRead,
    CrawlSourceUpdate,
    NovelChapterBatchClean,
    NovelChapterBatchCleanActiveJobList,
    NovelChapterBatchCleanCancelResult,
    NovelChapterBatchCleanProgress,
    NovelChapterBatchDelete,
    NovelChapterBatchResult,
    NovelChapterCleanStatus,
    NovelChapterCreate,
    NovelChapterEventStateUpdate,
    NovelChapterImport,
    NovelChapterPage,
    NovelChapterRead,
    NovelChapterUpdate,
    NovelImportSplitRule,
    ScreenwritingPreflightResult,
)
from app.services import novel as novel_service
from app.services import project as project_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]

NOVEL_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class NovelView(BaseView):
    """小说章节类视图。"""

    router_prefix = "/projects/{project_public_id}/novels"
    router_tags = ["novel"]

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
    def _raise_as_http(exc: Exception) -> None:
        """将服务层异常转换为 HTTP 异常。"""
        if isinstance(exc, project_service.ProjectNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, project_service.ProjectAccessDeniedError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        if isinstance(exc, novel_service.NovelChapterNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, novel_service.NovelChapterValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, novel_service.NovelCrawlSourceNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, novel_service.NovelCrawlSourceValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "",
        methods=["GET"],
        response_model=NovelChapterPage,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="获取小说章节列表",
        description="按项目公开 ID 分页获取小说章节列表。",
    )
    async def list_chapters(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=20, ge=1, le=100),
        search: str = "",
    ) -> NovelChapterPage:
        """获取小说章节列表。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.list_chapters(
                session,
                project_public_id,
                current_user_public_id,
                page=page,
                limit=limit,
                search=search,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "",
        methods=["POST"],
        response_model=NovelChapterRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="创建小说章节",
        description="在指定项目下创建小说章节。",
    )
    async def create_chapter(
        self,
        project_public_id: str,
        payload: NovelChapterCreate,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterRead:
        """创建小说章节。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.create_chapter(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/import",
        methods=["POST"],
        response_model=list[NovelChapterRead],
        status_code=status.HTTP_201_CREATED,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="导入小说全文",
        description="将全文按卷和章节拆分后导入指定项目。",
    )
    async def import_chapters(
        self,
        project_public_id: str,
        payload: NovelChapterImport,
        request: Request,
        session: SessionDep,
    ) -> list[NovelChapterRead]:
        """导入小说全文。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.import_chapters(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/import-split-rules",
        methods=["GET"],
        response_model=list[NovelImportSplitRule],
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="获取小说导入切分规则",
        description="获取服务端内置的全文导入章节切分规则。",
    )
    async def list_import_split_rules(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> list[NovelImportSplitRule]:
        """获取全文导入切分规则。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
            return novel_service.list_import_split_rules()
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/batch-delete",
        methods=["POST"],
        response_model=NovelChapterBatchResult,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="批量删除小说章节",
        description="按章节 ID 批量删除指定项目下的小说章节。",
    )
    async def batch_delete_chapters(
        self,
        project_public_id: str,
        payload: NovelChapterBatchDelete,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterBatchResult:
        """批量删除小说章节。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.batch_delete_chapters(
                session,
                project_public_id,
                current_user_public_id,
                payload,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/batch-clean",
        methods=["POST"],
        response_model=NovelChapterBatchCleanProgress,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="批量清洗章节事件",
        description="按章节 ID 创建并立即启动批量清洗异步任务，进度和结果通过 SSE 通道返回。",
    )
    async def batch_clean_chapters(
        self,
        project_public_id: str,
        payload: NovelChapterBatchClean,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterBatchCleanProgress:
        """提交批量清洗章节事件异步任务。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.batch_clean_chapters(
                session,
                project_public_id,
                current_user_public_id,
                payload,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/batch-clean/jobs/active",
        methods=["GET"],
        response_model=NovelChapterBatchCleanActiveJobList,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="列出未完结批量清洗任务",
        description="返回当前项目下未结束的批量清洗任务，用于客户端恢复 SSE 订阅。",
    )
    async def list_active_batch_clean_jobs(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterBatchCleanActiveJobList:
        """列出未完结批量清洗任务。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.list_active_batch_clean_jobs(
                session,
                project_public_id,
                current_user_public_id,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/batch-clean/jobs/{job_public_id}/events",
        methods=["GET"],
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="订阅批量清洗任务进度",
        description="以 text/event-stream 持续推送批量清洗任务进度，直到任务进入终态。",
    )
    async def stream_batch_clean_job_events(
        self,
        project_public_id: str,
        job_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> StreamingResponse:
        """通过 SSE 推送批量清洗任务进度。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            await novel_service.get_batch_clean_job_progress(
                session,
                project_public_id,
                current_user_public_id,
                job_public_id,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

        async def render_events():
            async for progress in novel_service.stream_batch_clean_job_progress(
                project_public_id,
                current_user_public_id,
                job_public_id,
            ):
                if await request.is_disconnected():
                    break
                yield _format_sse_event(
                    "progress",
                    progress.model_dump(by_alias=True, mode="json"),
                )

        return StreamingResponse(
            render_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @route(
        "/batch-clean/jobs/{job_public_id}",
        methods=["GET"],
        response_model=NovelChapterBatchCleanProgress,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="查询批量清洗任务进度快照",
        description="返回批量清洗任务当前进度快照，用于调试或 SSE 失败后的兜底查询。",
    )
    async def get_batch_clean_job_progress(
        self,
        project_public_id: str,
        job_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterBatchCleanProgress:
        """查询批量清洗任务进度快照。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.get_batch_clean_job_progress(
                session,
                project_public_id,
                current_user_public_id,
                job_public_id,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/batch-clean/jobs/{job_public_id}/cancel",
        methods=["POST"],
        response_model=NovelChapterBatchCleanCancelResult,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="取消批量清洗任务",
        description="取消批量清洗任务中尚未开始执行的章节子项。",
    )
    async def cancel_batch_clean_job(
        self,
        project_public_id: str,
        job_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterBatchCleanCancelResult:
        """取消批量清洗任务。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.cancel_batch_clean_job(
                session,
                project_public_id,
                current_user_public_id,
                job_public_id,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/event-state",
        methods=["POST"],
        response_model=NovelChapterBatchResult,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="批量更新章节事件状态",
        description="按章节 ID 批量更新事件清洗状态。",
    )
    async def update_event_state(
        self,
        project_public_id: str,
        payload: NovelChapterEventStateUpdate,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterBatchResult:
        """批量更新章节事件状态。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.update_event_state(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl-sources",
        methods=["GET"],
        response_model=list[CrawlSourceRead],
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="获取小说爬取来源",
        description="获取当前项目可用的小说爬取来源。",
    )
    async def list_crawl_sources(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> list[CrawlSourceRead]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.list_crawl_sources(session, project_public_id, current_user_public_id)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl-sources",
        methods=["POST"],
        response_model=CrawlSourceRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="创建小说爬取来源",
        description="为当前项目创建一个 API 型小说爬取来源。",
    )
    async def create_crawl_source(
        self,
        project_public_id: str,
        payload: CrawlSourcePayload,
        request: Request,
        session: SessionDep,
    ) -> CrawlSourceRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.create_crawl_source(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl-sources/analyze",
        methods=["POST"],
        response_model=CrawlAnalyzeResult,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="分析小说爬取来源",
        description="返回待完善的来源配置草稿。",
    )
    async def analyze_crawl_source(
        self,
        project_public_id: str,
        payload: CrawlAnalyzePayload,
        request: Request,
        session: SessionDep,
    ) -> CrawlAnalyzeResult:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.analyze_crawl_source(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl-sources/{key}",
        methods=["PUT"],
        response_model=CrawlSourceRead,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="更新小说爬取来源",
        description="更新当前项目下的小说爬取来源。",
    )
    async def update_crawl_source(
        self,
        project_public_id: str,
        key: str,
        payload: CrawlSourceUpdate,
        request: Request,
        session: SessionDep,
    ) -> CrawlSourceRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.update_crawl_source(session, project_public_id, current_user_public_id, key, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl-sources/{key}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="删除小说爬取来源",
        description="删除当前项目下的小说爬取来源。",
    )
    async def delete_crawl_source(
        self,
        project_public_id: str,
        key: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            await novel_service.delete_crawl_source(session, project_public_id, current_user_public_id, key)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/crawl-sources/{key}/duplicate",
        methods=["POST"],
        response_model=CrawlSourceRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="复制小说爬取来源",
        description="把一个可见来源复制为当前项目的私有来源。",
    )
    async def duplicate_crawl_source(
        self,
        project_public_id: str,
        key: str,
        payload: CrawlSourceDuplicate,
        request: Request,
        session: SessionDep,
    ) -> CrawlSourceRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.duplicate_crawl_source(
                session,
                project_public_id,
                current_user_public_id,
                key,
                payload,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl/search",
        methods=["POST"],
        response_model=list[CrawlSearchResult],
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="搜索可爬取小说",
        description="使用当前来源配置搜索小说。",
    )
    async def search_crawl_books(
        self,
        project_public_id: str,
        payload: CrawlSearchPayload,
        request: Request,
        session: SessionDep,
    ) -> list[CrawlSearchResult]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.search_crawl_books(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl/book-detail",
        methods=["POST"],
        response_model=CrawlBookDetailResult,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="获取爬取小说详情",
        description="点击小说后获取详情信息。",
    )
    async def fetch_crawl_book_detail(
        self,
        project_public_id: str,
        payload: CrawlBookPayload,
        request: Request,
        session: SessionDep,
    ) -> CrawlBookDetailResult:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.fetch_crawl_book_detail(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl/book-chapter-count",
        methods=["POST"],
        response_model=CrawlBookChapterCountResult,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="获取爬取小说章节总数",
        description="通过章节列表接口获取小说章节总数。",
    )
    async def fetch_crawl_book_chapter_count(
        self,
        project_public_id: str,
        payload: CrawlBookPayload,
        request: Request,
        session: SessionDep,
    ) -> CrawlBookChapterCountResult:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.fetch_crawl_book_chapter_count(
                session,
                project_public_id,
                current_user_public_id,
                payload,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl/chapters",
        methods=["POST"],
        response_model=list[CrawlChapterDraft],
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="爬取小说章节",
        description="使用多进程和子协程爬取指定章节范围。",
    )
    async def fetch_crawl_chapters(
        self,
        project_public_id: str,
        payload: CrawlChapterFetchPayload,
        request: Request,
        session: SessionDep,
    ) -> list[CrawlChapterDraft]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.fetch_crawl_chapters(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/crawl/chapters/stream",
        methods=["POST"],
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="流式爬取小说章节",
        description="以 NDJSON 形式返回章节爬取进度。",
    )
    async def stream_crawl_chapters(
        self,
        project_public_id: str,
        payload: CrawlChapterFetchPayload,
        request: Request,
        session: SessionDep,
    ) -> StreamingResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            events = await novel_service.build_crawl_chapter_stream(
                session,
                project_public_id,
                current_user_public_id,
                payload,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

        async def render_events():
            async for event in events:
                yield json.dumps(event, ensure_ascii=False) + "\n"

        # StreamingResponse 流水响应响应对象，把当前视图方法中，yield产生的结果逐个返回给客户端
        return StreamingResponse(
            render_events(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache", # 如果没有这两个响应头，则有可能遭到浏览器的缓存
                "X-Accel-Buffering": "no",
            },
        )

    @route(
        "/crawl/import",
        methods=["POST"],
        response_model=CrawlImportResult,
        status_code=status.HTTP_201_CREATED,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="导入爬取小说章节",
        description="把已爬取章节写入现有小说管理章节表。",
    )
    async def import_crawl_chapters(
        self,
        project_public_id: str,
        payload: CrawlImportPayload,
        request: Request,
        session: SessionDep,
    ) -> CrawlImportResult:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.import_crawl_chapters(session, project_public_id, current_user_public_id, payload)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/clean/status",
        methods=["GET"],
        response_model=list[NovelChapterCleanStatus],
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="获取章节事件清洗状态",
        description="按章节 ID 批量获取事件清洗状态，不返回章节正文。",
    )
    async def list_clean_statuses(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        ids: str = Query(default=""),
    ) -> list[NovelChapterCleanStatus]:
        """批量获取章节事件清洗状态。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            chapter_ids = _parse_id_list(ids)
            return await novel_service.list_chapter_clean_statuses(
                session,
                project_public_id,
                current_user_public_id,
                chapter_ids,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/clean-status",
        methods=["GET"],
        response_model=list[NovelChapterCleanStatus],
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="兼容获取章节事件清洗状态",
        description="兼容旧前端按章节 ID 批量获取事件清洗状态，不返回章节正文。",
    )
    async def list_clean_statuses_legacy(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        ids: str = Query(default=""),
    ) -> list[NovelChapterCleanStatus]:
        """兼容旧版清洗状态查询路径。"""
        return await self.list_clean_statuses(project_public_id, request, session, ids)

    @route(
        "/screenwriting/preflight",
        methods=["GET"],
        response_model=ScreenwritingPreflightResult,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="剧本创作准入校验",
        description="校验当前项目是否已配置文本模型，并完成足够数量章节的事件提取。",
    )
    async def screenwriting_preflight(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingPreflightResult:
        """剧本创作准入校验。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.get_screenwriting_preflight(
                session,
                project_public_id,
                current_user_public_id,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/{chapter_id}",
        methods=["PUT"],
        response_model=NovelChapterRead,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="更新小说章节",
        description="更新指定项目下的单个小说章节。",
    )
    async def update_chapter(
        self,
        project_public_id: str,
        chapter_id: int,
        payload: NovelChapterUpdate,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterRead:
        """更新小说章节。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await novel_service.update_chapter(
                session,
                project_public_id,
                chapter_id,
                current_user_public_id,
                payload,
            )
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/{chapter_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="删除小说章节",
        description="删除指定项目下的单个小说章节。",
    )
    async def delete_chapter(
        self,
        project_public_id: str,
        chapter_id: int,
        request: Request,
        session: SessionDep,
    ) -> Response:
        """删除小说章节。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            await novel_service.delete_chapter(session, project_public_id, chapter_id, current_user_public_id)
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/{chapter_id}/clean",
        methods=["POST"],
        response_model=NovelChapterRead,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=NOVEL_ROUTE_MIDDLEWARES,
        summary="清洗章节事件",
        description="提交指定项目下的单个章节事件清洗任务，实际清洗在后台执行。",
    )
    async def clean_chapter(
        self,
        project_public_id: str,
        chapter_id: int,
        request: Request,
        session: SessionDep,
    ) -> NovelChapterRead:
        """提交单章事件清洗后台任务。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            chapter = await novel_service.queue_clean_chapter(
                session,
                project_public_id,
                chapter_id,
                current_user_public_id,
            )
            novel_service.submit_clean_chapter_task(
                project_public_id,
                chapter_id,
                current_user_public_id,
            )
            return chapter
        except (project_service.ProjectServiceError, novel_service.NovelServiceError) as exc:
            self._raise_as_http(exc)


router = NovelView()()


def _parse_id_list(raw_ids: str) -> list[int]:
    """解析逗号分隔的章节 ID 查询参数。"""
    ids: list[int] = []
    for item in raw_ids.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            ids.append(int(value))
        except ValueError as exc:
            raise novel_service.NovelChapterValidationError("章节 ID 必须是整数") from exc
    return ids


def _format_sse_event(event: str, data: object) -> str:
    """把事件名和 JSON 数据格式化为 SSE 帧。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
