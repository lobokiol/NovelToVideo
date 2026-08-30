from __future__ import annotations

from typing import Annotated

from fastapi import Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.media import MediaAssetRead, MediaVideoGenerateRequest
from app.schemas.tasks import TaskJobDetail
from app.services import media as media_service
from app.services import project as project_service
from app.services import tasks as task_service


SessionDep = Annotated[AsyncSession, Depends(get_session)]

MEDIA_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class MediaView(BaseView):
    """统一媒体中枢接口：内容分发、缩略图、列举、上传、删除与视频生成。"""

    router_prefix = "/projects/{project_public_id}/media"
    router_tags = ["media"]

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
        if isinstance(exc, media_service.MediaNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, media_service.MediaServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, task_service.TaskServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/{media_public_id}/content",
        methods=["GET"],
        summary="读取媒体内容",
        description="按媒体公开 ID 读取媒体文件，供 <img>/<video> src 直接访问。",
    )
    async def get_media_content(
        self,
        project_public_id: str,
        media_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        try:
            media, path = await media_service.get_media_content(session, media_public_id)
            if path is not None:
                return FileResponse(path, media_type=media.mime_type or "application/octet-stream")
            data = await media_service.read_media_bytes(media)
        except media_service.MediaServiceError as exc:
            self._raise_as_http(exc)
        return Response(content=data, media_type=media.mime_type or "application/octet-stream")

    @route(
        "/{media_public_id}/thumbnail",
        methods=["GET"],
        summary="读取媒体缩略图",
        description="按媒体公开 ID 读取图像缩略图，懒生成后缓存于存储。",
    )
    async def get_media_thumbnail(
        self,
        project_public_id: str,
        media_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        try:
            data, mime_type = await media_service.get_media_thumbnail(session, media_public_id)
            await session.commit()
        except media_service.MediaServiceError as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return Response(content=data, media_type=mime_type)

    @route(
        "/{media_public_id}/select",
        methods=["POST"],
        response_model=MediaAssetRead,
        middlewares=MEDIA_ROUTE_MIDDLEWARES,
        summary="择优选定候选媒体",
        description="把候选媒体设为其挂靠对象的选定媒体（final），同对象同类型的其他选定自动降级为普通候选。",
    )
    async def select_media(
        self,
        project_public_id: str,
        media_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> MediaAssetRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            media = await media_service.select_media_as_final(
                session,
                project_public_id,
                current_user_public_id,
                media_public_id=media_public_id,
            )
            await session.commit()
        except (project_service.ProjectServiceError, media_service.MediaServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return MediaAssetRead.model_validate(media)

    @route(
        "",
        methods=["GET"],
        response_model=list[MediaAssetRead],
        middlewares=MEDIA_ROUTE_MIDDLEWARES,
        summary="列举项目媒体",
    )
    async def list_media(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        media_type: str = Query(default="", alias="mediaType"),
        status_filter: str = Query(default="", alias="status"),
        source: str = Query(default=""),
        scope_type: str = Query(default="", alias="scopeType"),
        scope_public_id: str = Query(default="", alias="scopePublicId"),
        media_role: str = Query(default="", alias="mediaRole"),
        limit: int = Query(default=200, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> list[MediaAssetRead]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            rows = await media_service.list_media_assets(
                session,
                project_public_id,
                current_user_public_id,
                media_type=media_type,
                status=status_filter,
                source=source,
                scope_type=scope_type,
                scope_public_id=scope_public_id,
                media_role=media_role,
                limit=limit,
                offset=offset,
            )
        except (project_service.ProjectServiceError, media_service.MediaServiceError) as exc:
            self._raise_as_http(exc)
        return [MediaAssetRead.model_validate(row) for row in rows]

    @route(
        "/upload",
        methods=["POST"],
        response_model=MediaAssetRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=MEDIA_ROUTE_MIDDLEWARES,
        summary="上传媒体文件",
    )
    async def upload_media(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        file: UploadFile = File(..., description="媒体文件：图像/视频/音频。"),
        scope_type: str = Query(default="", alias="scopeType"),
        scope_public_id: str = Query(default="", alias="scopePublicId"),
        media_role: str = Query(default="reference", alias="mediaRole"),
    ) -> MediaAssetRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            data = await file.read()
            media = await media_service.upload_media(
                session,
                project_public_id,
                current_user_public_id,
                filename=file.filename or "",
                content_type=file.content_type or "",
                data=data,
                scope_type=scope_type,
                scope_public_id=scope_public_id,
                media_role=media_role,
            )
            await session.commit()
        except (project_service.ProjectServiceError, media_service.MediaServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return MediaAssetRead.model_validate(media)

    @route(
        "/{media_public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=MEDIA_ROUTE_MIDDLEWARES,
        summary="删除媒体",
    )
    async def delete_media(
        self,
        project_public_id: str,
        media_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            await media_service.delete_media_asset(
                session, project_public_id, current_user_public_id, media_public_id
            )
            await session.commit()
        except (project_service.ProjectServiceError, media_service.MediaServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/video/generate",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=MEDIA_ROUTE_MIDDLEWARES,
        summary="提交视频生成任务",
    )
    async def generate_video(
        self,
        project_public_id: str,
        payload: MediaVideoGenerateRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await media_service.submit_video_generation_task(
                session,
                project_public_id,
                current_user_public_id,
                model_id=payload.model_id,
                prompt=payload.prompt,
                params=payload.params,
                first_frame_media_public_id=payload.first_frame_media_public_id,
                last_frame_media_public_id=payload.last_frame_media_public_id,
                reference_media_public_ids=payload.reference_media_public_ids,
                scope_type=payload.scope_type,
                scope_public_id=payload.scope_public_id,
                count=payload.count,
            )
        except (
            project_service.ProjectServiceError,
            media_service.MediaServiceError,
            task_service.TaskServiceError,
        ) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="视频生成任务提交失败")


router = MediaView().router