from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.screenwriting import (
    ScreenwritingAssessPayload,
    ScreenwritingChatPayload,
    ScreenwritingChatResponse,
    ScreenwritingConfigDraftPayload,
    ScreenwritingHistoryRestorePayload,
    ScreenwritingRagWarmupResponse,
    ScreenwritingStateResponse,
    ScreenwritingWorkspaceUpdate,
)
from app.services import project as project_service
from app.services.screenwriting import chat as screenwriting_service
from app.services.screenwriting import state as screenwriting_state_service
from app.services.screenwriting.stream import format_ndjson_event

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SCREENWRITING_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class ScreenwritingView(BaseView):
    """剧本创作 Agent 接口。"""

    router_prefix = "/projects/{project_public_id}/novels/screenwriting"
    router_tags = ["screenwriting"]

    @staticmethod
    def _current_user_public_id(request: Request) -> str:
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
        if isinstance(exc, project_service.ProjectNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, project_service.ProjectAccessDeniedError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        if isinstance(exc, screenwriting_service.ScreenwritingValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, screenwriting_service.ScreenwritingServiceError):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        raise exc

    @route(
        "/state",
        methods=["GET"],
        response_model=ScreenwritingStateResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="获取剧本创作会话状态",
        description="返回当前项目与用户的剧本创作会话（对话消息、工作区与历史快照）。",
    )
    async def get_screenwriting_state(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingStateResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_state_service.get_screenwriting_state(
                session,
                project_public_id,
                current_user_public_id,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/state/reset",
        methods=["POST"],
        response_model=ScreenwritingStateResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="重置剧本创作会话",
        description="把当前会话归档进历史快照后开启全新对话。",
    )
    async def reset_screenwriting_state(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingStateResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_state_service.reset_screenwriting_state(
                session,
                project_public_id,
                current_user_public_id,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/history/restore",
        methods=["POST"],
        response_model=ScreenwritingStateResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="恢复剧本创作历史快照",
        description="把指定历史快照恢复为当前会话状态，恢复前自动归档当前状态。",
    )
    async def restore_screenwriting_history(
        self,
        project_public_id: str,
        payload: ScreenwritingHistoryRestorePayload,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingStateResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_state_service.restore_screenwriting_history(
                session,
                project_public_id,
                current_user_public_id,
                payload.history_id,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/history/{history_id}",
        methods=["DELETE"],
        response_model=ScreenwritingStateResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="删除剧本创作历史快照",
        description="从会话历史中删除指定快照。",
    )
    async def delete_screenwriting_history(
        self,
        project_public_id: str,
        history_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingStateResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_state_service.delete_screenwriting_history(
                session,
                project_public_id,
                current_user_public_id,
                history_id,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/workspace",
        methods=["PUT"],
        response_model=ScreenwritingStateResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="保存剧本创作工作区内容",
        description="手动编辑保存指定创作阶段的工作区 Markdown 内容。",
    )
    async def update_screenwriting_workspace(
        self,
        project_public_id: str,
        payload: ScreenwritingWorkspaceUpdate,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingStateResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_state_service.update_screenwriting_workspace(
                session,
                project_public_id,
                current_user_public_id,
                active_tab=payload.active_tab,
                content=payload.content,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/config/draft",
        methods=["POST"],
        response_model=ScreenwritingStateResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="保存剧本创作初始化配置草案",
        description="把结构化初始化配置写入草案（不锁定），用户仍需在对话中确认后生效。",
    )
    async def set_screenwriting_config_draft(
        self,
        project_public_id: str,
        payload: ScreenwritingConfigDraftPayload,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingStateResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_state_service.set_screenwriting_config_draft(
                session,
                project_public_id,
                current_user_public_id,
                fields=payload.model_dump(),
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/chat",
        methods=["POST"],
        response_model=ScreenwritingChatResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="剧本创作 Agent 多轮对话",
        description="将用户输入发送给 Harness Agent，并返回聚合后的对话响应。",
    )
    async def chat_screenwriting(
        self,
        project_public_id: str,
        payload: ScreenwritingChatPayload,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingChatResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_service.chat_screenwriting(
                session,
                project_public_id,
                current_user_public_id,
                payload,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/chat/stream",
        methods=["POST"],
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="剧本创作 Agent 多轮对话流",
        description="将用户输入发送给 Harness Agent，并以 NDJSON 返回运行状态和增量内容。",
    )
    async def stream_chat_screenwriting(
        self,
        project_public_id: str,
        payload: ScreenwritingChatPayload,
        request: Request,
        session: SessionDep,
    ) -> StreamingResponse:
        current_user_public_id = self._current_user_public_id(request)
        # 异步生成器在迭代时才执行；准备阶段异常由流内 error 事件承载。
        events = screenwriting_service.build_screenwriting_chat_stream(
            session,
            project_public_id,
            current_user_public_id,
            payload,
        )

        async def render_events():
            async for event in events:
                if await request.is_disconnected():
                    break
                yield format_ndjson_event(event)

        return StreamingResponse(
            render_events(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @route(
        "/assess/stream",
        methods=["POST"],
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="剧本创作阶段质量评估流",
        description="对指定阶段工作区内容做多维质量评估与打分，以 NDJSON 流式返回评估报告。",
    )
    async def stream_assess_screenwriting_stage(
        self,
        project_public_id: str,
        payload: ScreenwritingAssessPayload,
        request: Request,
        session: SessionDep,
    ) -> StreamingResponse:
        current_user_public_id = self._current_user_public_id(request)
        # 评估为只读操作，不持会话锁；准备阶段异常由流内 error 事件承载。
        events = screenwriting_service.build_screenwriting_assessment_stream(
            session,
            project_public_id,
            current_user_public_id,
            payload,
        )

        async def render_events():
            async for event in events:
                if await request.is_disconnected():
                    break
                yield format_ndjson_event(event)

        return StreamingResponse(
            render_events(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @route(
        "/rag/warmup",
        methods=["POST"],
        response_model=ScreenwritingRagWarmupResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="预热剧本创作 RAG 向量索引",
        description="在用户进入剧本创作页面时异步调度当前项目的 RAG 向量索引构建。",
    )
    async def warmup_screenwriting_rag_index(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingRagWarmupResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_service.warmup_screenwriting_rag_index(
                session,
                project_public_id,
                current_user_public_id,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)


router = ScreenwritingView()()