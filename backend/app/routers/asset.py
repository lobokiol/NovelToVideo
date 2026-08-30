from __future__ import annotations

from typing import Annotated

from fastapi import Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.asset import (
    AssetAssociationRequest,
    AssetAssociationResult,
    AssetAutocompleteRequest,
    AssetBatchRequest,
    AssetBatchResult,
    AssetCreateRequest,
    AssetDetailRead,
    AssetEpisodeBrief,
    AssetExtractRequest,
    AssetImageGenerateRequest,
    AssetManageListResult,
    AssetMediaRead,
    AssetParentUpdateRequest,
    AssetRead,
    AssetUpdateRequest,
)
from app.schemas.tasks import TaskJobDetail
from app.services import asset as asset_service
from app.services import media as media_service
from app.services import project as project_service
from app.services import tasks as task_service


SessionDep = Annotated[AsyncSession, Depends(get_session)]

ASSET_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class AssetView(BaseView):
    """资产抽取接口。"""

    router_prefix = "/projects/{project_public_id}/assets"
    router_tags = ["asset"]

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
        if isinstance(exc, asset_service.AssetNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, media_service.MediaNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, asset_service.AssetServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, media_service.MediaServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, task_service.TaskServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/extract",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="从剧本抽取资产",
    )
    async def extract_assets(
        self,
        project_public_id: str,
        payload: AssetExtractRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await asset_service.submit_extract_assets_task(
                session,
                project_public_id,
                current_user_public_id,
                model_id=payload.model_id,
                episode_public_ids=payload.episode_public_ids or None,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError, task_service.TaskServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="资产抽取任务提交失败")

    @route(
        "/autocomplete",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="资产描述补全",
    )
    async def autocomplete_assets(
        self,
        project_public_id: str,
        payload: AssetAutocompleteRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await asset_service.submit_autocomplete_task(
                session,
                project_public_id,
                current_user_public_id,
                model_id=payload.model_id,
                asset_public_ids=payload.asset_public_ids,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError, task_service.TaskServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="资产描述补全任务提交失败")

    @route(
        "/manage",
        methods=["GET"],
        response_model=AssetManageListResult,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="分页列出资产（含子资产树与引用）",
    )
    async def manage_assets(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        asset_type: str = Query(default="", alias="assetType"),
        keyword: str = Query(default=""),
        status_filter: str = Query(default="", alias="status"),
        referenced: str = Query(default=""),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    ) -> AssetManageListResult:
        current_user_public_id = self._current_user_public_id(request)
        try:
            result = await asset_service.list_assets_page(
                session,
                project_public_id,
                current_user_public_id,
                asset_type=asset_type,
                keyword=keyword,
                status=status_filter,
                referenced=referenced,
                page=page,
                page_size=page_size,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            self._raise_as_http(exc)
        return AssetManageListResult.model_validate(result)

    @route(
        "",
        methods=["POST"],
        response_model=AssetRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="手动创建资产",
    )
    async def create_asset(
        self,
        project_public_id: str,
        payload: AssetCreateRequest,
        request: Request,
        session: SessionDep,
    ) -> AssetRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            asset = await asset_service.create_asset(
                session,
                project_public_id,
                current_user_public_id,
                asset_type=payload.asset_type,
                name=payload.name,
                keyword=payload.keyword,
                colors=payload.colors,
                summary=payload.summary,
                description=payload.description,
                details=payload.details,
                accessories=payload.accessories,
                main_asset=payload.main_asset,
                variant_label=payload.variant_label,
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetRead.model_validate(asset)

    @route(
        "/batch",
        methods=["POST"],
        response_model=AssetBatchResult,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="批量锁定/解锁/删除资产",
    )
    async def batch_assets(
        self,
        project_public_id: str,
        payload: AssetBatchRequest,
        request: Request,
        session: SessionDep,
    ) -> AssetBatchResult:
        current_user_public_id = self._current_user_public_id(request)
        try:
            result = await asset_service.batch_update_assets(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_ids=payload.asset_public_ids,
                operation=payload.operation,
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetBatchResult(
            affected=result["affected"],
            assets=[AssetRead.model_validate(asset) for asset in result["assets"]],
        )

    @route(
        "/{asset_public_id}",
        methods=["PUT"],
        response_model=AssetRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="编辑资产",
    )
    async def update_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        payload: AssetUpdateRequest,
        request: Request,
        session: SessionDep,
    ) -> AssetRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            asset = await asset_service.update_asset(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id,
                fields=payload.model_dump(exclude_unset=True),
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetRead.model_validate(asset)

    @route(
        "/{asset_public_id}/parent",
        methods=["PUT"],
        response_model=AssetRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="设置或解除资产父子关系",
    )
    async def set_asset_parent(
        self,
        project_public_id: str,
        asset_public_id: str,
        payload: AssetParentUpdateRequest,
        request: Request,
        session: SessionDep,
    ) -> AssetRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            asset = await asset_service.set_asset_parent(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id,
                parent_asset_public_id=payload.parent_asset_public_id,
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetRead.model_validate(asset)

    @route(
        "/media/generate",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="资产配图生成",
    )
    async def generate_asset_images(
        self,
        project_public_id: str,
        payload: AssetImageGenerateRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await media_service.submit_asset_image_generation_task(
                session,
                project_public_id,
                current_user_public_id,
                model_id=payload.model_id,
                asset_public_ids=payload.asset_public_ids,
                prompt=payload.prompt,
                aspect_ratio=payload.aspect_ratio,
                image_size=payload.image_size,
                reference_media_public_ids=payload.reference_media_public_ids,
                count=payload.count,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError, task_service.TaskServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="资产配图任务提交失败")

    @route(
        "/{asset_public_id}/media/prompt",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="生成资产生图专业提示词",
    )
    async def synthesize_asset_image_prompt(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await media_service.submit_asset_image_prompt_task(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id=asset_public_id,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError, task_service.TaskServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="资产生图提示词任务提交失败")

    @route(
        "/{asset_public_id}/media/reference",
        methods=["POST"],
        response_model=AssetMediaRead,
        status_code=status.HTTP_201_CREATED,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="上传资产参考图",
    )
    async def upload_asset_reference_image(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
        file: UploadFile = File(..., description="参考图文件，支持 PNG/JPEG/WebP。"),
    ) -> AssetMediaRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            data = await file.read()
            media = await media_service.upload_asset_reference_image(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id=asset_public_id,
                filename=file.filename or "",
                content_type=file.content_type or "",
                data=data,
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetMediaRead.model_validate(media)

    @route(
        "/media/{media_public_id}/cover",
        methods=["POST"],
        response_model=AssetMediaRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="设为资产封面",
    )
    async def set_asset_media_cover(
        self,
        project_public_id: str,
        media_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> AssetMediaRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            media = await media_service.set_asset_cover(
                session, project_public_id, current_user_public_id, media_public_id
            )
            await session.commit()
        except (
            project_service.ProjectServiceError,
            asset_service.AssetServiceError,
            media_service.MediaServiceError,
        ) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetMediaRead.model_validate(media)

    @route(
        "/media/{media_public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="删除资产媒体",
    )
    async def delete_asset_media(
        self,
        project_public_id: str,
        media_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            await media_service.delete_asset_media(
                session, project_public_id, current_user_public_id, media_public_id
            )
            await session.commit()
        except (
            project_service.ProjectServiceError,
            asset_service.AssetServiceError,
            media_service.MediaServiceError,
        ) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/{asset_public_id}/media",
        methods=["GET"],
        response_model=list[AssetMediaRead],
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="列出资产媒体",
    )
    async def list_asset_media(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> list[AssetMediaRead]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            medias = await media_service.list_asset_media(
                session, project_public_id, current_user_public_id, asset_public_id
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            self._raise_as_http(exc)
        return [AssetMediaRead.model_validate(media) for media in medias]

    @route(
        "",
        methods=["GET"],
        response_model=list[AssetRead],
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="列出资产",
    )
    async def list_assets(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        asset_type: str = Query(default="", alias="assetType"),
    ) -> list[AssetRead]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            assets = await asset_service.list_assets(
                session,
                project_public_id,
                current_user_public_id,
                asset_type=asset_type,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            self._raise_as_http(exc)
        return [AssetRead.model_validate(asset) for asset in assets]

    @route(
        "/{asset_public_id}",
        methods=["GET"],
        response_model=AssetDetailRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="读取资产详情",
    )
    async def get_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> AssetDetailRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            asset = await asset_service.get_asset(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id,
            )
            episode_items = await asset_service.get_asset_episode_items(
                session,
                project_public_id,
                current_user_public_id,
                asset,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            self._raise_as_http(exc)
        detail = AssetDetailRead.model_validate(asset)
        detail.episode_items = [AssetEpisodeBrief.model_validate(item) for item in episode_items]
        return detail

    @route(
        "/associations",
        methods=["POST"],
        response_model=AssetAssociationResult,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="设置分集关联资产",
    )
    async def set_episode_assets(
        self,
        project_public_id: str,
        payload: AssetAssociationRequest,
        request: Request,
        session: SessionDep,
    ) -> AssetAssociationResult:
        current_user_public_id = self._current_user_public_id(request)
        try:
            result = await asset_service.set_episode_assets(
                session,
                project_public_id,
                current_user_public_id,
                payload.episode_public_id,
                payload.asset_public_ids,
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetAssociationResult(
            affected=result["affected"],
            assets=[AssetRead.model_validate(asset) for asset in result["assets"]],
        )

    @route(
        "/{asset_public_id}/lock",
        methods=["POST"],
        response_model=AssetRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="锁定资产",
    )
    async def lock_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> AssetRead:
        return await self._set_asset_lock(project_public_id, asset_public_id, request, session, locked=True)

    @route(
        "/{asset_public_id}/unlock",
        methods=["POST"],
        response_model=AssetRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="解锁资产",
    )
    async def unlock_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> AssetRead:
        return await self._set_asset_lock(project_public_id, asset_public_id, request, session, locked=False)

    async def _set_asset_lock(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: AsyncSession,
        *,
        locked: bool,
    ) -> AssetRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            asset = await asset_service.set_asset_lock(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id,
                locked=locked,
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetRead.model_validate(asset)

    @route(
        "/{asset_public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="删除资产",
    )
    async def delete_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            await asset_service.batch_update_assets(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_ids=[asset_public_id],
                operation="delete",
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


router = AssetView().router
