from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


class EditorProject(BaseModel, table=True):
    """在线剪辑台工程。

    一个项目对应一份剪辑工程；时间线结构（轨道/片段/入出点/音量等）以
    JSON 承载，由前端剪辑台读写，服务端只做持久化与尺寸约束，不解释
    其内部结构。片段引用媒体中枢的 media_public_id，导出成片经媒体
    上传接口回传中枢。
    """

    __tablename__ = "af_editor_project"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_af_editor_project_project"),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="所属项目内部主键；一个项目一份剪辑工程。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="最近编辑用户公开标识。",
    )
    name: str = Field(
        default="剪辑工程",
        sa_column=Column("name", String(120), nullable=False, default="剪辑工程", server_default="剪辑工程"),
        description="工程名称。",
    )
    timeline: str = Field(
        default="{}",
        sa_column=Column("timeline", Text, nullable=False, default="{}", server_default="{}"),
        description="时间线工程 JSON：轨道、片段、入出点、音量等。",
    )
    duration_ms: int = Field(
        default=0,
        sa_column=Column("duration_ms", Integer, nullable=False, default=0, server_default="0"),
        description="时间线总时长毫秒（保存时由前端计算回填）。",
    )
    ratio: str = Field(
        default="",
        sa_column=Column("ratio", String(20), nullable=False, default="", server_default=""),
        description="画幅比例，如 9:16 / 16:9；空表示跟随项目设置。",
    )