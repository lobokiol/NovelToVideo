from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.storyboard import (
    StoryboardGenerateRequest,
    StoryboardGenerateResult,
    StoryboardGridImageRequest,
    StoryboardShotRead,
    StoryboardShotUpdate,
    StoryboardShotVideoRequest,
)
from app.schemas.tasks import TaskJobDetail
from app.services import project as project_service
from app.services import shot_video as shot_video_service
from app.services import storyboard as storyboard_service
from app.services import storyboard_image as storyboard_image_service
from app.services import tasks as task_service


SessionDep = Annotated[AsyncSession, Depends(get_session)]

STORYBOARD_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class StoryboardView(BaseView):
    """分镜工作台的路由类"""

    router_prefix = "/projects/{project_public_id}/storyboards"
    router_tags = ["storyboard"]

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
        if isinstance(exc, storyboard_service.StoryboardShotNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, (storyboard_service.StoryboardServiceError, task_service.TaskServiceError)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/generate",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="提交分镜表生成任务",
    )
    async def generate_storyboard(
        self,
        project_public_id: str,
        payload: StoryboardGenerateRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await storyboard_service.submit_storyboard_generation_task(
                session,
                project_public_id,
                current_user_public_id,
                model_id=payload.model_id,
                episode_public_ids=payload.episode_public_ids or None,
                shot_public_ids=payload.shot_public_ids or None,
                art_style=payload.art_style,
                director_style=payload.director_style,
            )
        except (
            project_service.ProjectServiceError,
            storyboard_service.StoryboardServiceError,
            task_service.TaskServiceError,
        ) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="分镜生成任务提交失败")

    @route(
        "/images/generate",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="提交宫格分镜图生成任务",
        description="按镜头顺序把选中镜头打包成宫格分镜图，每个画格对应一个不同分镜镜头，并裁切画格回写到对应镜头。",
    )
    async def generate_storyboard_grid_images(
        self,
        project_public_id: str,
        payload: StoryboardGridImageRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await storyboard_image_service.submit_grid_image_task(
                session,
                project_public_id,
                current_user_public_id,
                grid_size=payload.grid_size,
                image_size=payload.image_size,
                episode_public_ids=payload.episode_public_ids or None,
                shot_public_ids=payload.shot_public_ids or None,
                only_missing=payload.only_missing,
                model_id=payload.model_id,
            )
        except (
            project_service.ProjectServiceError,
            storyboard_service.StoryboardServiceError,
            task_service.TaskServiceError,
        ) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="宫格分镜图任务提交失败")

    @route(
        "/videos/generate",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="提交镜头视频生成任务",
        description="以镜头分镜图为首帧做图生视频，每镜一个子项；默认仅为尚无选定视频的镜头生成，重复提交形成候选供择优。",
    )
    async def generate_storyboard_shot_videos(
        self,
        project_public_id: str,
        payload: StoryboardShotVideoRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await shot_video_service.submit_shot_video_task(
                session,
                project_public_id,
                current_user_public_id,
                episode_public_ids=payload.episode_public_ids or None,
                shot_public_ids=payload.shot_public_ids or None,
                only_missing=payload.only_missing,
                generate_audio=payload.generate_audio,
                resolution=payload.resolution,
                ratio=payload.ratio,
                model_id=payload.model_id,
                duration_seconds=payload.duration_seconds,
                quantity=payload.quantity,
            )
        except (
            project_service.ProjectServiceError,
            storyboard_service.StoryboardServiceError,
            task_service.TaskServiceError,
        ) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="镜头视频任务提交失败")

    @route(
        "/generate-sync",
        methods=["POST"],
        response_model=StoryboardGenerateResult,
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="同步生成分镜表（调试用）",
    )
    async def generate_storyboard_sync(
        self,
        project_public_id: str,
        payload: StoryboardGenerateRequest,
        request: Request,
        session: SessionDep,
    ) -> StoryboardGenerateResult:
        current_user_public_id = self._current_user_public_id(request)
        episode_ids = payload.episode_public_ids
        if len(episode_ids) != 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="同步生成仅支持单个分集")
        try:
            result = await storyboard_service.generate_storyboard(
                session,
                project_public_id,
                current_user_public_id,
                episode_ids[0],
                model_id=payload.model_id,
                art_style=payload.art_style,
                director_style=payload.director_style,
            )
            await session.commit()
        except (project_service.ProjectServiceError, storyboard_service.StoryboardServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return StoryboardGenerateResult(
            created=int(result["created"]),
            updated=int(result["updated"]),
            shots=[StoryboardShotRead.model_validate(shot) for shot in result["shots"]],
        )

    @route(
        "",
        methods=["GET"],
        response_model=list[StoryboardShotRead],
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="列出分镜镜头",
    )
    async def list_storyboard_shots(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        episode_public_id: str = Query(default="", alias="episodePublicId"),
    ) -> list[StoryboardShotRead]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            shots = await storyboard_service.list_storyboard_shots(
                session,
                project_public_id,
                current_user_public_id,
                episode_public_id=episode_public_id,
            )
        except (project_service.ProjectServiceError, storyboard_service.StoryboardServiceError) as exc:
            self._raise_as_http(exc)
        return [StoryboardShotRead.model_validate(shot) for shot in shots]

    @route(
        "/{shot_public_id}",
        methods=["PUT"],
        response_model=StoryboardShotRead,
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="编辑分镜镜头",
    )
    async def update_storyboard_shot(
        self,
        project_public_id: str,
        shot_public_id: str,
        payload: StoryboardShotUpdate,
        request: Request,
        session: SessionDep,
    ) -> StoryboardShotRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            shot = await storyboard_service.update_storyboard_shot(
                session,
                project_public_id,
                current_user_public_id,
                shot_public_id,
                fields=payload.model_dump(exclude_unset=True),
            )
            await session.commit()
        except (project_service.ProjectServiceError, storyboard_service.StoryboardServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return StoryboardShotRead.model_validate(shot)

    @route(
        "/{shot_public_id}/lock",
        methods=["POST"],
        response_model=StoryboardShotRead,
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="锁定分镜镜头",
    )
    async def lock_storyboard_shot(
        self,
        project_public_id: str,
        shot_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> StoryboardShotRead:
        return await self._set_shot_lock(project_public_id, shot_public_id, request, session, locked=True)

    @route(
        "/{shot_public_id}/unlock",
        methods=["POST"],
        response_model=StoryboardShotRead,
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="解锁分镜镜头",
    )
    async def unlock_storyboard_shot(
        self,
        project_public_id: str,
        shot_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> StoryboardShotRead:
        return await self._set_shot_lock(project_public_id, shot_public_id, request, session, locked=False)

    async def _set_shot_lock(
        self,
        project_public_id: str,
        shot_public_id: str,
        request: Request,
        session: AsyncSession,
        *,
        locked: bool,
    ) -> StoryboardShotRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            shot = await storyboard_service.set_storyboard_shot_lock(
                session,
                project_public_id,
                current_user_public_id,
                shot_public_id,
                locked=locked,
            )
            await session.commit()
        except (project_service.ProjectServiceError, storyboard_service.StoryboardServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return StoryboardShotRead.model_validate(shot)

    @route(
        "/{shot_public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=STORYBOARD_ROUTE_MIDDLEWARES,
        summary="删除分镜镜头",
    )
    async def delete_storyboard_shot(
        self,
        project_public_id: str,
        shot_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            await storyboard_service.delete_storyboard_shot(
                session,
                project_public_id,
                current_user_public_id,
                shot_public_id,
            )
            await session.commit()
        except (project_service.ProjectServiceError, storyboard_service.StoryboardServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


router = StoryboardView().router