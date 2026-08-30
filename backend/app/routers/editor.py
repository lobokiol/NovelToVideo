from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.editor import EditorProjectRead, EditorProjectSaveRequest
from app.services import editor as editor_service
from app.services import project as project_service


SessionDep = Annotated[AsyncSession, Depends(get_session)]

EDITOR_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class EditorView(BaseView):
    """在线剪辑台工程接口。"""

    router_prefix = "/projects/{project_public_id}/editor"
    router_tags = ["editor"]

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
        if isinstance(exc, editor_service.EditorServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/project",
        methods=["GET"],
        response_model=EditorProjectRead,
        middlewares=EDITOR_ROUTE_MIDDLEWARES,
        summary="读取剪辑工程",
        description="取项目的剪辑工程；不存在则创建一份空工程。",
    )
    async def get_editor_project(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> EditorProjectRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            editor_project = await editor_service.get_or_create_editor_project(
                session, project_public_id, current_user_public_id
            )
            await session.commit()
        except (project_service.ProjectServiceError, editor_service.EditorServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return EditorProjectRead.model_validate(editor_project)

    @route(
        "/project",
        methods=["PUT"],
        response_model=EditorProjectRead,
        middlewares=EDITOR_ROUTE_MIDDLEWARES,
        summary="保存剪辑工程",
        description="保存时间线工程 JSON 与总时长、画幅、名称等元信息。",
    )
    async def save_editor_project(
        self,
        project_public_id: str,
        payload: EditorProjectSaveRequest,
        request: Request,
        session: SessionDep,
    ) -> EditorProjectRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            editor_project = await editor_service.save_editor_project(
                session,
                project_public_id,
                current_user_public_id,
                timeline=payload.timeline,
                duration_ms=payload.duration_ms,
                ratio=payload.ratio,
                name=payload.name,
            )
            await session.commit()
        except (project_service.ProjectServiceError, editor_service.EditorServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return EditorProjectRead.model_validate(editor_project)


router = EditorView().router