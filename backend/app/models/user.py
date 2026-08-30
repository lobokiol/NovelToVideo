from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field

from app.models.base import BaseModel
from app.utils.time_tools import utc_now


class User(BaseModel, table=True):
    """用户表模型。"""
    __tablename__ = "af_user"

    username: str = Field( sa_column=Column("username", String(64), unique=True, nullable=False, index=True,), description="登录用户名，全局唯一。",)
    nickname: str | None = Field(default=None, sa_column=Column("nickname", String(64), nullable=True,), description="用户昵称，用于前端展示。",)
    email: str | None = Field(default=None, sa_column=Column("email", String(255), unique=True, nullable=True, index=True,), description="用户邮箱。",)
    avatar_url: str | None = Field(default=None, sa_column=Column("avatar_url", String(512), nullable=True,), description="用户头像地址。",)
    password_hash: str = Field(sa_column=Column("password_hash", String(255), nullable=False,), description="密码哈希值。",)

    is_superuser: bool = Field(default=False, sa_column=Column("is_superuser", Boolean, nullable=False, default=False,), description="是否为超级管理员。",)
    last_login_at: datetime | None = Field(default=None, sa_column=Column("last_login_at", DateTime(timezone=True), nullable=True,), description="最近登录时间。",)

    async def update_last_login(self) -> None:
        """更新最近登录时间。"""
        self.last_login_at = utc_now()
