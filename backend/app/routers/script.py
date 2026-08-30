from __future__ import annotations

from urllib.parse import quote

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.script import (
    ScriptExportRequest,
    ScriptEpisodeListItem,
    ScriptEpisodeRead,
    ScriptEpisodeUpdate,
    ScriptPlanCreate,
    ScriptPlanDetail,
    ScriptPlanSummary,
    ScriptPlanUpdate,
    ScriptSyncPayload,
)
from app.services import project as project_service
from app.services import script as script_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SCRIPT_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class ScriptView(BaseView):
    """剧本管理接口：剧本创作工作台产物的查询与同步。"""

    router_prefix = "/projects/{project_public_id}/scripts"
    router_tags = ["script"]

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
        if isinstance(
            exc,
            (script_service.ScriptPlanNotFoundError, script_service.ScriptEpisodeNotFoundError),
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, script_service.ScriptServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/plans",
        methods=["GET"],
        response_model=list[ScriptPlanSummary],
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="列出剧本计划",
        description="返回当前项目与用户的剧本计划列表（按更新时间倒序）。",
    )
    async def list_script_plans(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> list[ScriptPlanSummary]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            plans = await script_service.list_plans(session, project_public_id, current_user_public_id)
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            self._raise_as_http(exc)
        return [ScriptPlanSummary.model_validate(plan) for plan in plans]

    @route(
        "/plans/{plan_public_id}",
        methods=["GET"],
        response_model=ScriptPlanDetail,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="剧本计划详情",
        description="返回指定剧本计划及其分集与场次结构。",
    )
    async def get_script_plan(
        self,
        project_public_id: str,
        plan_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScriptPlanDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            plan, episodes = await script_service.get_plan_detail(
                session,
                project_public_id,
                current_user_public_id,
                plan_public_id,
            )
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            self._raise_as_http(exc)
        detail = ScriptPlanDetail.model_validate(plan)
        detail.episodes = [ScriptEpisodeRead.from_model(episode) for episode in episodes]
        return detail

    @route(
        "/sync",
        methods=["POST"],
        response_model=ScriptPlanDetail,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="同步剧本创作工作台到剧本管理",
        description="把当前剧本创作会话的剧本草案解析为分集并落库（幂等，已锁定集不覆盖）。",
    )
    async def sync_script_plan(
        self,
        project_public_id: str,
        payload: ScriptSyncPayload,
        request: Request,
        session: SessionDep,
    ) -> ScriptPlanDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            plan = await script_service.sync_current_workspace(
                session,
                project_public_id,
                current_user_public_id,
                title=payload.title,
            )
            await session.commit()
            plan, episodes = await script_service.get_plan_detail(
                session,
                project_public_id,
                current_user_public_id,
                plan.public_id,
            )
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        detail = ScriptPlanDetail.model_validate(plan)
        detail.episodes = [ScriptEpisodeRead.from_model(episode) for episode in episodes]
        return detail

    @route(
        "/episodes",
        methods=["GET"],
        response_model=list[ScriptEpisodeListItem],
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="列出项目全部分集",
        description="平铺返回当前项目与用户的所有分集（按所属计划更新时间倒序、集号正序）。",
    )
    async def list_script_episodes(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> list[ScriptEpisodeListItem]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            rows = await script_service.list_project_episodes(
                session, project_public_id, current_user_public_id
            )
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            self._raise_as_http(exc)
        return [
            ScriptEpisodeListItem.from_row(episode, plan_public_id, plan_title, assets)
            for episode, plan_public_id, plan_title, assets in rows
        ]

    @route(
        "/export",
        methods=["POST"],
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="导出剧本分集",
        description="把选中的剧本分集打包为 ZIP 文件下载。",
    )
    async def export_script_episodes(
        self,
        project_public_id: str,
        payload: ScriptExportRequest,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            exported = await script_service.export_episodes_zip(
                session,
                project_public_id,
                current_user_public_id,
                episode_public_ids=payload.episode_public_ids,
            )
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            self._raise_as_http(exc)
        disposition = (
            f"attachment; filename={exported.filename}; "
            f"filename*=UTF-8''{quote(exported.filename)}"
        )
        return Response(
            content=exported.content,
            media_type="application/zip",
            headers={
                "Content-Disposition": disposition,
                "X-Script-Episode-Count": str(exported.episode_count),
            },
        )

    @route(
        "/plans",
        methods=["POST"],
        response_model=ScriptPlanDetail,
        status_code=status.HTTP_201_CREATED,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="新建/导入剧本",
        description="把整段剧本 Markdown 解析为分集并落库为一份新的剧本计划。",
    )
    async def create_script_plan(
        self,
        project_public_id: str,
        payload: ScriptPlanCreate,
        request: Request,
        session: SessionDep,
    ) -> ScriptPlanDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            plan = await script_service.create_plan_from_content(
                session,
                project_public_id,
                current_user_public_id,
                title=payload.title,
                content=payload.content,
            )
            await session.commit()
            plan, episodes = await script_service.get_plan_detail(
                session,
                project_public_id,
                current_user_public_id,
                plan.public_id,
            )
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        detail = ScriptPlanDetail.model_validate(plan)
        detail.episodes = [ScriptEpisodeRead.from_model(episode) for episode in episodes]
        return detail

    @route(
        "/plans/{plan_public_id}",
        methods=["PUT"],
        response_model=ScriptPlanDetail,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="更新剧本计划",
        description="更新剧本计划元信息（当前支持剧名）。",
    )
    async def update_script_plan(
        self,
        project_public_id: str,
        plan_public_id: str,
        payload: ScriptPlanUpdate,
        request: Request,
        session: SessionDep,
    ) -> ScriptPlanDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            await script_service.update_plan(
                session,
                project_public_id,
                current_user_public_id,
                plan_public_id,
                title=payload.title,
            )
            await session.commit()
            plan, episodes = await script_service.get_plan_detail(
                session,
                project_public_id,
                current_user_public_id,
                plan_public_id,
            )
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        detail = ScriptPlanDetail.model_validate(plan)
        detail.episodes = [ScriptEpisodeRead.from_model(episode) for episode in episodes]
        return detail

    @route(
        "/plans/{plan_public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="删除剧本",
        description="删除整部剧本计划及其全部分集。",
    )
    async def delete_script_plan(
        self,
        project_public_id: str,
        plan_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            await script_service.delete_plan(
                session, project_public_id, current_user_public_id, plan_public_id
            )
            await session.commit()
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/episodes/{episode_public_id}",
        methods=["PUT"],
        response_model=ScriptEpisodeListItem,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="编辑分集",
        description="更新分集标题/梗概/正文；正文变更会重解析场次并递增版本。",
    )
    async def update_script_episode(
        self,
        project_public_id: str,
        episode_public_id: str,
        payload: ScriptEpisodeUpdate,
        request: Request,
        session: SessionDep,
    ) -> ScriptEpisodeListItem:
        current_user_public_id = self._current_user_public_id(request)
        try:
            episode, plan = await script_service.update_episode(
                session,
                project_public_id,
                current_user_public_id,
                episode_public_id,
                title=payload.title,
                summary=payload.summary,
                body=payload.body,
            )
            await session.commit()
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return ScriptEpisodeListItem.from_row(episode, plan.public_id, plan.title)

    @route(
        "/episodes/{episode_public_id}/lock",
        methods=["PATCH"],
        response_model=ScriptEpisodeListItem,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="锁定分集",
        description="锁定分集，后续从创作工作台同步时不覆盖该集。",
    )
    async def lock_script_episode(
        self,
        project_public_id: str,
        episode_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScriptEpisodeListItem:
        return await self._set_episode_lock(
            project_public_id, episode_public_id, request, session, locked=True
        )

    @route(
        "/episodes/{episode_public_id}/unlock",
        methods=["PATCH"],
        response_model=ScriptEpisodeListItem,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="解锁分集",
        description="解除分集锁定。",
    )
    async def unlock_script_episode(
        self,
        project_public_id: str,
        episode_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScriptEpisodeListItem:
        return await self._set_episode_lock(
            project_public_id, episode_public_id, request, session, locked=False
        )

    async def _set_episode_lock(
        self,
        project_public_id: str,
        episode_public_id: str,
        request: Request,
        session: AsyncSession,
        *,
        locked: bool,
    ) -> ScriptEpisodeListItem:
        current_user_public_id = self._current_user_public_id(request)
        try:
            episode, plan = await script_service.set_episode_lock(
                session,
                project_public_id,
                current_user_public_id,
                episode_public_id,
                locked=locked,
            )
            await session.commit()
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return ScriptEpisodeListItem.from_row(episode, plan.public_id, plan.title)

    @route(
        "/episodes/{episode_public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="删除分集",
        description="删除单个分集。",
    )
    async def delete_script_episode(
        self,
        project_public_id: str,
        episode_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            await script_service.delete_episode(
                session, project_public_id, current_user_public_id, episode_public_id
            )
            await session.commit()
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


router = ScriptView().router
