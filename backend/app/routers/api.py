from fastapi import APIRouter

from app.core.config import settings
from app.routers.provider import router as provider_router
from app.routers.project import router as project_router
from app.routers.user import router as user_router
from app.routers.novel import router as novel_router
from app.routers.tasks import router as tasks_router
from app.routers.screenwriting import router as screenwriting_router
from app.routers.script import router as script_router
from app.routers.asset import router as asset_router
from app.routers.storyboard import router as storyboard_router
from app.routers.media import router as media_router
from app.routers.editor import router as editor_router

api_router = APIRouter(prefix=settings.api_prefix)

api_router.include_router(user_router)
api_router.include_router(project_router)
api_router.include_router(provider_router)
api_router.include_router(novel_router)
api_router.include_router(tasks_router)
api_router.include_router(screenwriting_router)
api_router.include_router(script_router)
api_router.include_router(asset_router)
api_router.include_router(storyboard_router)
api_router.include_router(media_router)
api_router.include_router(editor_router)

@api_router.get(
    "/health",  # 实际路径：/api/health
    summary="健康检查",
    description="检查后端服务是否正常运行。",
)
async def health_check() -> dict[str, str]:
    """返回服务健康状态。
    Returns:
        dict[str, str]: 固定返回 `status=ok` 的状态对象。
    """
    return {"status": "ok"}