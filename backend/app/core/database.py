from __future__ import annotations
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.utils.string_tools import build_database_url

from redis.asyncio import Redis

def build_engine() -> AsyncEngine:
    """根据当前配置构建异步数据库引擎。

    Returns:
        AsyncEngine: 基于当前配置创建的 SQLModel 异步引擎实例。
    """
    
    database_url = build_database_url(
        db_engine=settings.db_engine,
        db_driver=settings.db_driver,
        db_host=settings.db_host,
        db_port=settings.db_port,
        db_name=settings.db_name,
        db_user=settings.db_user,
        db_password=settings.db_password,
        db_sqlite_path=settings.db_sqlite_path,
    )
    # 根据数据库类型动态设置连接参数，专门针对 SQLite 做线程限制的放宽处理
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_async_engine(database_url, echo=False, connect_args=connect_args)


engine = build_engine()
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_db_and_tables() -> None:
    """使用异步数据库引擎创建所有 SQLModel 数据表。"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def drop_db_and_tables() -> None:
    """使用异步数据库引擎删除所有 SQLModel 数据表。"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """为 FastAPI 依赖项提供异步数据库会话。"""
    async with async_session_maker() as session:
        yield session

redis_client = Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    decode_responses=True,
)