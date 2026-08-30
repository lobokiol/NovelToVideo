from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from app.utils.time_tools import utc_now


class BaseModel(SQLModel):
    """数据库实体模型抽象基类。"""

    id: int | None = Field(
        default=None,
        primary_key=True,
    )
    public_id: str = Field(
        default_factory=lambda: str(uuid4()),
        max_length=36,
        unique=True,
        nullable=False,
        index=True,
        description="对外公开的唯一标识。",
    )
    sort_order: int = Field(
        default=0,
        nullable=False,
        index=True,
        sa_column_kwargs={"default": 0},
        description="排序值，数值越小越靠前。",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        nullable=False,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"default": utc_now},
        description="创建时间。",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        nullable=False,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"default": utc_now, "onupdate": utc_now},
        description="最近更新时间。",
    )
    disabled_at: datetime | None = Field(
        default=None,
        nullable=True,
        index=True,
        sa_type=DateTime(timezone=True),
        description="禁用时间。",
    )

    @property
    def is_disabled(self) -> bool:
        """实体是否已被禁用。"""
        return self.disabled_at is not None

    @property
    def is_active(self) -> bool:
        """实体是否可用。"""
        return self.disabled_at is None

    async def disable(self) -> None:
        """禁用实体。"""
        self.disabled_at = utc_now()

    async def enable(self) -> None:
        """启用实体。"""
        self.disabled_at = None
