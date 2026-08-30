from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.routers.base import BaseView, route
from app.schemas.user import (
    UserAvatarUpdate,
    UserCreate,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserRead,
    TokenRefreshRequest,
    TokenRefreshResponse,
    UserUpdate,
)
from app.services import user as user_service
from app.schemas.user import LoginUserInfo, UserLogin, UserLoginResponse
from app.utils.jwt_tools import create_access_token_from_refresh_token, create_login_tokens
from app.utils.string_tools import verify_password
from app.middlewares import common

SessionDep = Annotated[AsyncSession, Depends(get_session)]

USER_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class UserView(BaseView):
    """用户类视图。"""

    router_prefix = "/users"
    router_tags = ["user"]

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
        """将服务层异常转换为 HTTP 异常。

        Args:
            exc: 服务层抛出的异常对象。

        Raises:
            HTTPException: 对应的 HTTP 错误。
        """
        if isinstance(exc, user_service.UserNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, user_service.UserNameConflictError):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if isinstance(exc, user_service.UserEmailConflictError):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if isinstance(exc, user_service.UserPasswordMismatchError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, user_service.UserAvatarInvalidError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/",
        methods=["GET"],
        response_model=list[UserRead],
        summary="获取用户列表",
        middlewares=[Depends(common.jwt_auth_middleware), Depends(common.request_duration_middleware)],
        description="返回当前系统中的全部用户记录，按排序值和内部主键升序排列。",
    )
    async def list_users(self, session: SessionDep) -> list[UserRead]:
        """获取用户列表。

        Args:
            session: 当前数据库会话依赖。

        Returns:
            list[UserRead]: 用户列表结果。
        """
        return await user_service.list_users(session)

    @route(
        "/me",
        methods=["GET"],
        response_model=UserRead,
        summary="获取当前登录用户",
        middlewares=USER_ROUTE_MIDDLEWARES,
        description="根据 access token 返回当前登录用户资料，用于设置页初始化。",
    )
    async def get_current_user(self, request: Request, session: SessionDep) -> UserRead:
        """获取当前登录用户资料。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await user_service.get_current_user(session, current_user_public_id)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/me/profile",
        methods=["PUT"],
        response_model=UserRead,
        summary="更新当前用户资料",
        middlewares=USER_ROUTE_MIDDLEWARES,
        description="更新当前登录用户的账号、昵称和邮箱。",
    )
    async def update_current_user_profile(
        self,
        payload: UserProfileUpdate,
        request: Request,
        session: SessionDep,
    ) -> UserRead:
        """更新当前登录用户基础资料。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await user_service.update_current_user_profile(session, current_user_public_id, payload)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/me/password",
        methods=["PUT"],
        response_model=UserRead,
        summary="修改当前用户密码",
        middlewares=USER_ROUTE_MIDDLEWARES,
        description="校验当前密码后更新当前登录用户密码。",
    )
    async def update_current_user_password(
        self,
        payload: UserPasswordUpdate,
        request: Request,
        session: SessionDep,
    ) -> UserRead:
        """修改当前登录用户密码。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await user_service.update_current_user_password(session, current_user_public_id, payload)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/me/avatar",
        methods=["PUT"],
        response_model=UserRead,
        summary="更新当前用户头像",
        middlewares=USER_ROUTE_MIDDLEWARES,
        description="更新当前登录用户头像地址。",
    )
    async def update_current_user_avatar(
        self,
        payload: UserAvatarUpdate,
        request: Request,
        session: SessionDep,
    ) -> UserRead:
        """更新当前登录用户头像。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await user_service.update_current_user_avatar(session, current_user_public_id, payload)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/me/avatar/upload",
        methods=["POST"],
        response_model=UserRead,
        summary="上传当前用户头像图片",
        middlewares=USER_ROUTE_MIDDLEWARES,
        description="接收 PNG/JPEG/JPG 图片文件，中心裁剪为 1:1 比例并写回当前用户头像。",
    )
    async def upload_current_user_avatar(
        self,
        request: Request,
        session: SessionDep,
        file: UploadFile = File(..., description="待上传的头像图片，支持 PNG/JPEG/JPG。"),
    ) -> UserRead:
        """上传并裁剪当前登录用户头像。"""
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await user_service.upload_current_user_avatar(session, current_user_public_id, file)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/refresh-token",
        methods=["POST"],
        response_model=TokenRefreshResponse,
        middlewares=[Depends(common.request_duration_middleware)],
        summary="刷新 access token",
        description="使用 refresh token 签发新的 access token。",
    )
    async def refresh_token(self, payload: TokenRefreshRequest) -> TokenRefreshResponse:
        """使用 refresh token 签发新的 access token。"""
        try:
            tokens = await create_access_token_from_refresh_token(payload.refresh_token)
        except (jwt.PyJWTError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="refresh token 无效或已过期",
                headers=common.BEARER_AUTH_HEADER,
            ) from exc

        return TokenRefreshResponse(
            access_token=str(tokens["access_token"]),
            expires_in=int(tokens["expires_in"]),
        )

    @route(
        "/{public_id}",
        methods=["GET"],
        response_model=UserRead,
        summary="获取用户详情",
        middlewares=[Depends(common.jwt_auth_middleware), Depends(common.request_duration_middleware)],
        description="根据用户公开 ID 查询单个用户的详细信息。",
    )
    async def get_user_detail(self, public_id: str, session: SessionDep) -> UserRead:
        """获取用户详情。

        Args:
            public_id: 对外公开的用户标识。
            session: 当前数据库会话依赖。

        Returns:
            UserRead: 用户详情对象。
        """
        try:
            return await user_service.get_user_or_raise(session, public_id)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/",
        methods=["POST"],
        response_model=UserRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=[Depends(common.jwt_auth_middleware), Depends(common.request_duration_middleware)],
        summary="创建用户",
        description="创建新的用户记录，数据库自动生成整数主键，并对外返回 public_id。",
    )
    async def create_user(self, payload: UserCreate, session: SessionDep) -> UserRead:
        """创建用户。

        Args:
            payload: 用户创建请求体。
            session: 当前数据库会话依赖。

        Returns:
            UserRead: 新创建的用户对象。
        """
        try:
            return await user_service.create_user(session, payload)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}",
        methods=["PUT"],
        response_model=UserRead,
        summary="更新用户",
        middlewares=[Depends(common.jwt_auth_middleware), Depends(common.request_duration_middleware)],
        description="根据用户公开 ID 更新用户基础资料、密码、排序和账号状态等可编辑字段。",
    )
    async def update_user(self, public_id: str, payload: UserUpdate, session: SessionDep) -> UserRead:
        """更新用户信息。

        Args:
            public_id: 对外公开的用户标识。
            payload: 用户更新请求体。
            session: 当前数据库会话依赖。

        Returns:
            UserRead: 更新后的用户对象。
        """
        try:
            return await user_service.update_user(session, public_id, payload)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}/disable",
        methods=["PATCH"],
        response_model=UserRead,
        summary="禁用用户",
        middlewares=[Depends(common.jwt_auth_middleware), Depends(common.request_duration_middleware)],
        description="将指定用户标记为禁用状态。",
    )
    async def disable_user(self, public_id: str, session: SessionDep) -> UserRead:
        """禁用用户。

        Args:
            public_id: 对外公开的用户标识。
            session: 当前数据库会话依赖。

        Returns:
            UserRead: 已更新为禁用状态的用户对象。
        """
        try:
            return await user_service.disable_user(session, public_id)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        summary="删除用户",
        middlewares=[Depends(common.jwt_auth_middleware), Depends(common.request_duration_middleware)],
        description="根据用户公开 ID 删除对应的用户记录。",
    )
    async def delete_user(self, public_id: str, session: SessionDep) -> Response:
        """删除用户。

        Args:
            public_id: 对外公开的用户标识。
            session: 当前数据库会话依赖。

        Returns:
            Response: 空响应体的 204 删除结果。
        """
        try:
            await user_service.delete_user(session, public_id)
        except user_service.UserServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/login",
        methods=["POST"],
        response_model=UserLoginResponse,
        middlewares=[Depends(common.request_duration_middleware)],
        summary="用户登录",
        description="校验用户名和密码，登录成功后返回 token 和用户信息。",
    )
    async def login_user(self, data: UserLogin, session: SessionDep) -> UserLoginResponse:
        """校验用户凭据并签发登录 token。

        Args:
            data: 用户登录请求体，包含用户名和明文密码。
            session: 当前数据库会话依赖。

        Returns:
            UserLoginResponse: 登录 token 与当前登录用户的对外信息。

        Raises:
            HTTPException: 用户名不存在、密码错误或用户已被禁用时抛出。
        """
        # 登录必须基于数据库中的真实用户记录，避免绕过用户模型状态。
        user = await user_service.get_user_by_username(session, data.username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        # 禁用状态优先阻断，避免继续签发或刷新 token。
        if user.is_disabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="用户已被禁用",
            )

        # 用户名不存在和密码错误保持相同响应，减少账号枚举风险。
        if not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        # JWT 中只写入 public_id，避免向客户端暴露内部数据库主键。
        tokens = await create_login_tokens(
            public_id=user.public_id,
            username=user.username,
        )
        # 登录成功后记录最近登录时间，供审计和用户状态展示使用。
        await user.update_last_login()
        session.add(user)
        await session.commit()

        return UserLoginResponse(
            access_token=str(tokens["access_token"]),
            refresh_token=str(tokens["refresh_token"]),
            expires_in=int(tokens["expires_in"]),
            user=LoginUserInfo(
                public_id=user.public_id,
                username=user.username,
                nickname=user.nickname,
            ),
        )


router = UserView()()
