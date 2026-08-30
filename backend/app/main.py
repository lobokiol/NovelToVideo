import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import oss_root_path, settings
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.routers.api import api_router
from app.services.user import ensure_default_admin

@asynccontextmanager
async def lifespan(_: FastAPI):
    """在应用启动时完成一些初始化操作，例如：数据库连接，启动一些后台任务之类的。
    """
    await ensure_default_admin()
    yield

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    Returns:
        FastAPI: 已注册全局路由和生命周期钩子的应用对象。
    """
    app = FastAPI(
            title=settings.app_name,
            description=settings.app_description,
            lifespan=lifespan
    )

    app.include_router(api_router)


    # 暴露 OSS 目录为静态资源，供头像等用户上传文件直接通过 URL 访问。
    oss_path = oss_root_path()
    oss_path.mkdir(parents=True, exist_ok=True)
    app.mount("/oss", StaticFiles(directory=str(oss_path)), name="oss")

    return app

app = create_app()
