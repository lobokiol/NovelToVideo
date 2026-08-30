from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.provider import (
    ProviderCodeUpdate,
    ProviderConfig,
    ProviderCreate,
    ProviderFileRead,
    ProviderInputValuesUpdate,
    ProviderModel,
    ProviderModelsFetchRequest,
    ProviderTemplateGenerateRequest,
    ProviderTemplateRead,
)
from app.services import provider as provider_service
from app.services import user as user_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]

PROVIDER_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class ProviderView(BaseView):
    """大模型服务配置接口。"""

    router_prefix = "/providers"
    router_tags = ["provider"]

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

    async def _ensure_superuser(self, request: Request, session: SessionDep) -> None:
        current_user_public_id = self._current_user_public_id(request)
        try:
            current_user = await user_service.get_current_user(session, current_user_public_id)
        except user_service.UserServiceError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限") from exc
        if not current_user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")

    @staticmethod
    def _raise_as_http(exc: Exception) -> None:
        if isinstance(exc, provider_service.ProviderNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, provider_service.ProviderConflictError):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if isinstance(exc, provider_service.ProviderValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, provider_service.ProviderRemoteRequestError):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        raise exc

    @route(
        "/template",
        methods=["GET"],
        response_model=ProviderTemplateRead,
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="获取服务文件模板",
        description="返回一个基础大模型工具类服务文件模板。",
    )
    async def get_provider_template(self) -> ProviderTemplateRead:
        return ProviderTemplateRead(code=provider_service.build_provider_template())

    @route(
        "/template",
        methods=["POST"],
        response_model=ProviderTemplateRead,
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="根据当前配置生成服务文件模板",
        description="使用当前表单中的 PROVIDER_CONFIG 生成服务文件源码模板。",
    )
    async def generate_provider_template(
        self,
        payload: ProviderTemplateGenerateRequest,
        request: Request,
        session: SessionDep,
    ) -> ProviderTemplateRead:
        await self._ensure_superuser(request, session)
        try:
            return ProviderTemplateRead(code=provider_service.build_provider_template(payload.config))
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/",
        methods=["GET"],
        response_model=list[ProviderConfig],
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="获取服务配置列表",
        description="自动读取 app/providers 目录下每个服务文件的 PROVIDER_CONFIG。",
    )
    async def list_providers(self) -> list[ProviderConfig]:
        try:
            return [
                provider_service.prepare_provider_config_for_response(config)
                for config in provider_service.list_provider_configs()
            ]
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/",
        methods=["POST"],
        response_model=ProviderConfig,
        status_code=status.HTTP_201_CREATED,
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="创建服务文件",
        description="根据服务配置和可选源码创建新的 providers 服务文件。",
    )
    async def create_provider(self, payload: ProviderCreate) -> ProviderConfig:
        try:
            config = provider_service.create_provider_file(payload.config, code=payload.code)
            return provider_service.prepare_provider_config_for_response(config)
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/models/fetch",
        methods=["POST"],
        response_model=list[ProviderModel],
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="自动获取远端模型列表",
        description="使用当前表单中的临时凭据和请求地址调用服务商 /models，不写入服务文件。",
    )
    async def fetch_provider_models(
        self,
        payload: ProviderModelsFetchRequest,
    ) -> list[ProviderModel]:
        try:
            return await provider_service.fetch_provider_models(payload.config)
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{key}",
        methods=["GET"],
        response_model=ProviderFileRead,
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="获取服务配置与源码",
        description="根据服务唯一标记读取单个服务文件。",
    )
    async def get_provider(self, key: str) -> ProviderFileRead:
        try:
            config = provider_service.get_provider_config(key)
            code = provider_service.get_provider_code_for_response(key)
            return ProviderFileRead(
                config=provider_service.prepare_provider_config_for_response(config),
                code=code,
            )
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{key}/config",
        methods=["PUT"],
        response_model=ProviderConfig,
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="更新服务配置",
        description="替换已有服务文件中的 PROVIDER_CONFIG，保留工具类代码。",
    )
    async def update_provider_config(
        self,
        key: str,
        payload: ProviderConfig
    ) -> ProviderConfig:
        try:
            config = provider_service.update_provider_config(key, payload)
            return provider_service.prepare_provider_config_for_response(config)
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{key}/inputs",
        methods=["PUT"],
        response_model=ProviderConfig,
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="更新服务输入值",
        description="只更新已有服务配置中的 input_values。",
    )
    async def update_provider_inputs(
        self,
        key: str,
        payload: ProviderInputValuesUpdate
    ) -> ProviderConfig:
        try:
            config = provider_service.update_provider_input_values(key, payload.input_values)
            return provider_service.prepare_provider_config_for_response(config)
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{key}/code",
        methods=["PUT"],
        response_model=ProviderFileRead,
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="更新服务文件源码",
        description="校验 PROVIDER_CONFIG 后替换已有服务文件源码。",
    )
    async def update_provider_code(
        self,
        key: str,
        payload: ProviderCodeUpdate
    ) -> ProviderFileRead:
        try:
            config = provider_service.update_provider_code(key, payload.code)
            return ProviderFileRead(
                config=provider_service.prepare_provider_config_for_response(config),
                code=provider_service.get_provider_code_for_response(key),
            )
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)

    @route(
        "/{key}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=PROVIDER_ROUTE_MIDDLEWARES,
        summary="删除服务文件",
        description="备份后删除指定 providers 服务文件。",
    )
    async def delete_provider(self, key: str, request: Request, session: SessionDep) -> Response:
        await self._ensure_superuser(request, session)
        try:
            provider_service.delete_provider_file(key)
        except provider_service.ProviderServiceError as exc:
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


router = ProviderView()()
