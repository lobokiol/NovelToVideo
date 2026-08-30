from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.models.project import ProjectMemberRole
from app.routers.base import BaseView, route
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberInvite,
    ProjectMemberRead,
    ProjectRead,
    ProjectUpdate,
    VisualStyleCreate,
    VisualStyleFileRead,
    VisualStyleFileWrite,
    VisualStyleImageRead,
    VisualStyleImageWrite,
    VisualStyleRead,
    VisualStyleUpdate,
    DirectorManualCreate,
    DirectorManualFileRead,
    DirectorManualFileWrite,
    DirectorManualImageRead,
    DirectorManualImageWrite,
    DirectorManualRead,
)
from app.schemas.user import UserRead
from app.services import project as project_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]

PROJECT_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class ProjectView(BaseView):
    """项目类视图。"""

    router_prefix = "/projects"
    router_tags = ["project"]

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
        """将项目服务层异常转换为 HTTP 异常。"""
        if isinstance(exc, project_service.ProjectNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, project_service.ProjectMemberNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, project_service.ProjectAccessDeniedError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        if isinstance(exc, project_service.ProjectMemberConflictError):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if isinstance(exc, project_service.DirectorManualNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, project_service.DirectorManualConflictError):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if isinstance(exc, project_service.DirectorManualValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/",
        methods=["GET"],
        response_model=list[ProjectRead],
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="获取项目列表",
        description="返回当前用户可访问的项目列表；管理员可查看全部项目。",
    )
    async def list_projects(self, request: Request, session: SessionDep) -> list[ProjectRead]:
        """获取当前用户可访问的项目列表。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.list_projects(session, current_user_public_id)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/search/by-name",
        methods=["GET"],
        response_model=list[ProjectRead],
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="按项目名搜索项目",
        description="按项目名称关键字搜索当前用户可访问的项目；管理员可搜索全部项目。",
    )
    async def search_projects_by_name(
        self,
        name: str,
        request: Request,
        session: SessionDep,
    ) -> list[ProjectRead]:
        """按项目名搜索项目列表。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.search_projects_by_name(session, current_user_public_id, name)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/search/by-member",
        methods=["GET"],
        response_model=list[ProjectRead],
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="按项目成员搜索项目",
        description="按成员用户公开标识搜索当前用户可访问的项目；管理员可搜索全部项目。",
    )
    async def search_projects_by_member(
        self,
        member_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> list[ProjectRead]:
        """按项目成员搜索项目列表。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.search_projects_by_member(
                session,
                current_user_public_id,
                member_public_id,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id:uuid}",
        methods=["GET"],
        response_model=ProjectRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="获取项目详情",
        description="根据项目公开 ID 获取项目详情；非管理员只能访问自己相关项目。",
    )
    async def get_project_detail(
        self,
        public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ProjectRead:
        """获取项目详情。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.get_project_or_raise(session, public_id, current_user_public_id)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/",
        methods=["POST"],
        response_model=ProjectRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="创建项目",
        description="为当前登录用户创建项目，并自动添加 owner 项目成员记录。",
    )
    async def create_project(
        self,
        payload: ProjectCreate,
        request: Request,
        session: SessionDep,
    ) -> ProjectRead:
        """创建项目。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.create_project(session, current_user_public_id, payload)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}",
        methods=["PUT"],
        response_model=ProjectRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="更新项目",
        description="根据项目公开 ID 更新项目基础信息；非管理员只能更新自己相关项目。",
    )
    async def update_project(
        self,
        public_id: str,
        payload: ProjectUpdate,
        request: Request,
        session: SessionDep,
    ) -> ProjectRead:
        """更新项目基础信息。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.update_project(session, public_id, payload, current_user_public_id)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}/disable",
        methods=["PATCH"],
        response_model=ProjectRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="禁用项目",
        description="将指定项目标记为禁用状态；非管理员只能禁用自己相关项目。",
    )
    async def disable_project(
        self,
        public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ProjectRead:
        """禁用项目。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.disable_project(session, public_id, current_user_public_id)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}/enable",
        methods=["PATCH"],
        response_model=ProjectRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="启用项目",
        description="将指定项目恢复为可用状态；非管理员只能启用自己相关项目。",
    )
    async def enable_project(
        self,
        public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ProjectRead:
        """启用项目。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.enable_project(session, public_id, current_user_public_id)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="删除项目",
        description="根据项目公开 ID 删除项目及其成员关系；非管理员只能删除自己相关项目。",
    )
    async def delete_project(
        self,
        public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        """删除项目。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            await project_service.delete_project(session, public_id, current_user_public_id)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/{public_id}/members/candidates",
        methods=["GET"],
        response_model=list[UserRead],
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="搜索可邀请项目成员",
        description="在当前项目中按用户名或邮箱搜索可邀请用户，已在项目中的成员不会重复返回。",
    )
    async def search_project_member_candidates(
        self,
        public_id: str,
        keyword: str,
        request: Request,
        session: SessionDep,
    ) -> list[UserRead]:
        """搜索可邀请加入项目的用户。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.search_project_member_candidates(
                session,
                public_id,
                keyword,
                current_user_public_id,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}/members",
        methods=["GET"],
        response_model=list[ProjectMemberRead],
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="获取项目成员列表",
        description="根据项目公开 ID 获取项目成员列表；非管理员只能查看自己相关项目的成员。",
    )
    async def list_project_members(
        self,
        public_id: str,
        request: Request,
        session: SessionDep,
    ) -> list[ProjectMemberRead]:
        """获取项目成员列表。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.list_project_members(session, public_id, current_user_public_id)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}/members/invitations",
        methods=["POST"],
        response_model=ProjectMemberRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="邀请项目成员",
        description="使用搜索结果中的用户公开标识邀请用户加入项目，并指定成员角色。",
    )
    async def invite_project_member(
        self,
        public_id: str,
        payload: ProjectMemberInvite,
        request: Request,
        session: SessionDep,
    ) -> ProjectMemberRead:
        """邀请项目成员。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.invite_project_member(
                session,
                public_id,
                payload.user_public_id,
                payload.role,
                current_user_public_id,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}/members",
        methods=["POST"],
        response_model=ProjectMemberRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="新增项目成员",
        description="为指定项目新增成员；非管理员只能操作自己相关项目。",
    )
    async def add_project_member(
        self,
        public_id: str,
        user_public_id: str,
        role: ProjectMemberRole,
        request: Request,
        session: SessionDep,
    ) -> ProjectMemberRead:
        """新增项目成员。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.add_project_member(
                session,
                public_id,
                user_public_id,
                role,
                current_user_public_id,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}/members/{user_public_id}",
        methods=["PATCH"],
        response_model=ProjectMemberRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="更新项目成员角色",
        description="更新指定项目成员角色；非管理员只能操作自己相关项目。",
    )
    async def update_project_member_role(
        self,
        public_id: str,
        user_public_id: str,
        role: ProjectMemberRole,
        request: Request,
        session: SessionDep,
    ) -> ProjectMemberRead:
        """更新项目成员角色。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.update_project_member_role(
                session,
                public_id,
                user_public_id,
                role,
                current_user_public_id,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}/members/{user_public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="移除项目成员",
        description="移除指定项目成员；非管理员只能操作自己相关项目。",
    )
    async def remove_project_member(
        self,
        public_id: str,
        user_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        """移除项目成员。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            await project_service.remove_project_member(
                session,
                public_id,
                user_public_id,
                current_user_public_id,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


    @route(
        "/visual-styles",
        methods=["GET"],
        response_model=list[VisualStyleRead],
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="获取视觉风格列表",
        description="读取配置的视觉风格根目录；仅超级管理员可操作。",
    )
    async def list_visual_styles(self, request: Request, session: SessionDep) -> list[VisualStyleRead]:
        """获取视觉风格列表。"""
        try:
            return await project_service.list_visual_styles(session)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/visual-styles",
        methods=["POST"],
        response_model=VisualStyleRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="创建视觉风格",
        description="创建视觉风格目录并写入 Markdown 文件和图片；仅超级管理员可操作。",
    )
    async def create_visual_style(
        self,
        payload: VisualStyleCreate,
        request: Request,
        session: SessionDep,
    ) -> VisualStyleRead:
        """创建视觉风格。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.create_visual_style(session, current_user_public_id, payload)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/visual-styles/{style_path}",
        methods=["GET"],
        response_model=VisualStyleRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="获取视觉风格详情",
        description="读取单个视觉风格的 Markdown 文件和图片元数据；仅超级管理员可操作。",
    )
    async def get_visual_style(
        self,
        style_path: str,
        request: Request,
        session: SessionDep,
    ) -> VisualStyleRead:
        """获取视觉风格详情。"""
        try:
            return await project_service.get_visual_style(session, style_path)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/visual-styles/{style_path}",
        methods=["PUT"],
        response_model=VisualStyleRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="更新视觉风格",
        description="新增或覆盖视觉风格 Markdown 文件和图片；仅超级管理员可操作。",
    )
    async def update_visual_style(
        self,
        style_path: str,
        payload: VisualStyleUpdate,
        request: Request,
        session: SessionDep,
    ) -> VisualStyleRead:
        """更新视觉风格。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.update_visual_style(session, current_user_public_id, style_path, payload)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/visual-styles/{style_path}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="删除视觉风格",
        description="删除视觉风格目录；仅超级管理员可操作。",
    )
    async def delete_visual_style(
        self,
        style_path: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        """删除视觉风格。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            await project_service.delete_visual_style(session, current_user_public_id, style_path)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/visual-styles/{style_path}/files/{file_path:path}",
        methods=["GET"],
        response_model=VisualStyleFileRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="读取视觉风格文件",
        description="读取视觉风格目录中的单个 Markdown 文件；仅超级管理员可操作。",
    )
    async def read_visual_style_file(
        self,
        style_path: str,
        file_path: str,
        request: Request,
        session: SessionDep,
    ) -> VisualStyleFileRead:
        """读取视觉风格文件。"""
        try:
            return await project_service.read_visual_style_file(session, style_path, file_path)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/visual-styles/{style_path}/files/{file_path:path}",
        methods=["PUT"],
        response_model=VisualStyleFileRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="写入视觉风格文件",
        description="新增或覆盖视觉风格目录中的单个 Markdown 文件；仅超级管理员可操作。",
    )
    async def write_visual_style_file(
        self,
        style_path: str,
        file_path: str,
        payload: VisualStyleFileWrite,
        request: Request,
        session: SessionDep,
    ) -> VisualStyleFileRead:
        """写入视觉风格文件。"""
        try:
            file_payload = payload.model_copy(update={"path": file_path})
            return await project_service.write_visual_style_file(
                session,
                style_path,
                file_payload,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/visual-styles/{style_path}/files/{file_path:path}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="删除视觉风格文件",
        description="删除视觉风格目录中的单个 Markdown 文件；仅超级管理员可操作。",
    )
    async def delete_visual_style_file(
        self,
        style_path: str,
        file_path: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        """删除视觉风格文件。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            await project_service.delete_visual_style_file(session, current_user_public_id, style_path, file_path)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/visual-styles/{style_path}/images/{filename}",
        methods=["GET"],
        summary="读取视觉风格图片",
        description="读取视觉风格目录 images 子目录中的单个图片，可用于 CSS url() 或 HTML src 直接访问。",
    )
    async def get_visual_style_image(
        self,
        style_path: str,
        filename: str,
        request: Request,
        session: SessionDep,
    ) -> FileResponse:
        """读取视觉风格图片。"""
        try:
            image_path = await project_service.get_visual_style_image_path(
                session,
                style_path,
                filename,
            )
            return FileResponse(image_path, filename=filename)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/visual-styles/{style_path}/images/{filename}",
        methods=["PUT"],
        response_model=VisualStyleImageRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="写入视觉风格图片",
        description="新增或覆盖视觉风格目录 images 子目录中的单个图片；仅超级管理员可操作。",
    )
    async def write_visual_style_image(
        self,
        style_path: str,
        filename: str,
        payload: VisualStyleImageWrite,
        request: Request,
        session: SessionDep,
    ) -> VisualStyleImageRead:
        """写入视觉风格图片。"""
        try:
            image_payload = payload.model_copy(update={"filename": filename})
            return await project_service.write_visual_style_image(
                session,
                style_path,
                image_payload,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/visual-styles/{style_path}/images/{filename}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="删除视觉风格图片",
        description="删除视觉风格目录 images 子目录中的单个图片；仅超级管理员可操作。",
    )
    async def delete_visual_style_image(
        self,
        style_path: str,
        filename: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        """删除视觉风格图片。"""
        try:
            await project_service.delete_visual_style_image(session, style_path, filename)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/director-manuals",
        methods=["GET"],
        response_model=list[DirectorManualRead],
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="获取导演风格列表",
        description="读取配置的导演手册根目录，返回可供客户端选择的导演叙事风格列表。",
    )
    async def list_director_manuals(self, request: Request, session: SessionDep) -> list[DirectorManualRead]:
        """获取导演风格列表。"""
        try:
            return await project_service.list_director_manuals(session)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/director-manuals",
        methods=["POST"],
        response_model=DirectorManualRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="创建导演风格",
        description="创建导演手册目录并写入 Markdown 文件和图片；仅超级管理员可操作。",
    )
    async def create_director_manual(
        self,
        payload: DirectorManualCreate,
        request: Request,
        session: SessionDep,
    ) -> DirectorManualRead:
        """创建导演风格。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await project_service.create_director_manual(
                session,
                current_user_public_id,
                payload,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/director-manuals/{manual_path}/files/{file_path:path}",
        methods=["GET"],
        response_model=DirectorManualFileRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="读取导演手册文件",
        description="读取导演手册目录中的单个 Markdown 文件。",
    )
    async def read_director_manual_file(
        self,
        manual_path: str,
        file_path: str,
        request: Request,
        session: SessionDep,
    ) -> DirectorManualFileRead:
        """读取导演手册文件。"""
        try:
            return await project_service.read_director_manual_file(session, manual_path, file_path)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/director-manuals/{manual_path}/files/{file_path:path}",
        methods=["PUT"],
        response_model=DirectorManualFileRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="写入导演手册文件",
        description="新增或覆盖导演手册目录中的单个 Markdown 文件。",
    )
    async def write_director_manual_file(
        self,
        manual_path: str,
        file_path: str,
        payload: DirectorManualFileWrite,
        request: Request,
        session: SessionDep,
    ) -> DirectorManualFileRead:
        """写入导演手册文件。"""
        try:
            file_payload = payload.model_copy(update={"path": file_path})
            return await project_service.write_director_manual_file(session, manual_path, file_payload)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/director-manuals/{manual_path}/files/{file_path:path}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="删除导演手册文件",
        description="删除导演手册目录中的单个 Markdown 文件；需要管理员权限。",
    )
    async def delete_director_manual_file(
        self,
        manual_path: str,
        file_path: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        """删除导演手册文件。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            await project_service.delete_director_manual_file(
                session,
                current_user_public_id,
                manual_path,
                file_path,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/director-manuals/{manual_path}/images/{filename}",
        methods=["GET"],
        summary="读取导演风格图片",
        description="读取导演手册目录 images 子目录中的单个图片，可用于 CSS url() 或 HTML src 直接访问。",
    )
    async def get_director_manual_image(
        self,
        manual_path: str,
        filename: str,
        request: Request,
        session: SessionDep,
    ) -> FileResponse:
        """读取导演风格图片。"""
        try:
            image_path = await project_service.get_director_manual_image_path(
                session,
                manual_path,
                filename,
            )
            return FileResponse(image_path, filename=filename)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/director-manuals/{manual_path}/images/{filename}",
        methods=["PUT"],
        response_model=DirectorManualImageRead,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="写入导演手册图片",
        description="新增或覆盖导演手册目录 images 子目录中的单个图片。",
    )
    async def write_director_manual_image(
        self,
        manual_path: str,
        filename: str,
        payload: DirectorManualImageWrite,
        request: Request,
        session: SessionDep,
    ) -> DirectorManualImageRead:
        """写入导演手册图片。"""
        try:
            image_payload = payload.model_copy(update={"filename": filename})
            return await project_service.write_director_manual_image(
                session,
                manual_path,
                image_payload,
            )
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/director-manuals/{manual_path}/images/{filename}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=PROJECT_ROUTE_MIDDLEWARES,
        summary="删除导演手册图片",
        description="删除导演手册目录 images 子目录中的单个图片。",
    )
    async def delete_director_manual_image(
        self,
        manual_path: str,
        filename: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        """删除导演手册图片。"""
        try:
            await project_service.delete_director_manual_image(session, manual_path, filename)
        except project_service.ProjectServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


router = ProjectView()()
