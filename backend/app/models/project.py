from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlmodel import Field, SQLModel

from app.models.base import BaseModel
from app.utils.time_tools import utc_now


class ProjectVideoMode(str, Enum):
    """项目视频生成模式。"""

    TEXT = "text"
    SINGLE_IMAGE = "singleImage"
    MULTI_REFERENCE = "multiReference"
    START_END_REQUIRED = "startEndRequired"
    END_FRAME_OPTIONAL = "endFrameOptional"
    START_FRAME_OPTIONAL = "startFrameOptional"


class ProjectMemberRole(str, Enum):
    """项目成员角色。"""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    EDITOR = "editor"
    VIEWER = "viewer"


def enum_values(enum_cls: type[Enum]) -> list[str]:
    """返回枚举值列表，用于数据库字段存储枚举值而不是成员名。"""
    return [item.value for item in enum_cls]


class Project(BaseModel, table=True):
    """项目主表模型。"""

    __tablename__ = "af_project"

    name: str = Field(
        sa_column=Column("name", String(100), nullable=False, index=True),
        description="项目名称。",
    )
    intro: str = Field(
        default="",
        sa_column=Column("intro", String(2000), nullable=False, default="", server_default=""),
        description="项目简介或内容摘要。",
    )
    project_type: str = Field(
        default="novel_to_video",
        sa_column=Column(
            "project_type",
            String(50),
            nullable=False,
            default="novel_to_video",
            server_default="novel_to_video",
        ),
        description="项目业务类型，例如小说转视频。",
    )
    content_type: str = Field(
        default="novel",
        sa_column=Column(
            "content_type",
            String(50),
            nullable=False,
            default="novel",
            server_default="novel",
        ),
        description="项目源内容类型。",
    )
    art_style: str = Field(
        default="3D_chinese_traditional",
        sa_column=Column(
            "art_style",
            String(100),
            nullable=False,
            default="3D_chinese_traditional",
            server_default="3D_chinese_traditional",
        ),
        description="视觉风格。",
    )
    director_manual: str = Field(
        default="",
        sa_column=Column(
            "director_manual",
            String(4000),
            nullable=False,
            default="",
            server_default="",
        ),
        description="导演技能。",
    )
    art_style_prompt: str = Field(
        default="",
        sa_column=Column("art_style_prompt", Text, nullable=False, default="", server_default=""),
        description="从项目绑定艺术风格手册提炼固定的风格提示词，供分镜脚本与分镜图生成引用；重新绑定风格时清空。",
    )
    director_style_prompt: str = Field(
        default="",
        sa_column=Column("director_style_prompt", Text, nullable=False, default="", server_default=""),
        description="从项目绑定导演风格手册提炼固定的叙事提示词，供分镜脚本与分镜图生成引用；重新绑定手册时清空。",
    )
    video_ratio: str = Field(
        default="9:16",
        sa_column=Column(
            "video_ratio",
            String(20),
            nullable=False,
            default="9:16",
            server_default="9:16",
        ),
        description="默认视频画幅比例。",
    )
    text_model: str = Field(
        default="",
        sa_column=Column("text_model", String(100), nullable=False, default="", server_default=""),
        description="默认文本生成模型。",
    )
    image_model: str = Field(
        default="",
        sa_column=Column("image_model", String(100), nullable=False, default="", server_default=""),
        description="默认图像生成模型。",
    )
    video_model: str = Field(
        default="",
        sa_column=Column("video_model", String(100), nullable=False, default="", server_default=""),
        description="默认视频生成模型。",
    )
    tts_model: str = Field(
        default="",
        sa_column=Column("tts_model", String(100), nullable=False, default="", server_default=""),
        description="默认语音生成模型。",
    )
    image_quality: str = Field(
        default="standard",
        sa_column=Column(
            "image_quality",
            String(50),
            nullable=False,
            default="standard",
            server_default="standard",
        ),
        description="默认图像质量档位。",
    )
    mode: ProjectVideoMode = Field(
        default=ProjectVideoMode.TEXT,
        sa_column=Column(
            "mode",
            SAEnum(
                ProjectVideoMode,
                values_callable=enum_values,
                name="project_video_mode",
                native_enum=False,
                create_constraint=True,
                validate_strings=True,
                length=50,
            ),
            nullable=False,
            default=ProjectVideoMode.TEXT.value,
            server_default=ProjectVideoMode.TEXT.value,
        ),
        description="视频生成模式。",
    )
    owner_id: str = Field(
        sa_column=Column("owner_id", String(36), ForeignKey("af_user.public_id"), nullable=False, index=True),
        description="项目所有者的用户公开标识。",
    )


class ProjectMember(SQLModel, table=True):
    """项目成员表模型。"""

    __tablename__ = "af_project_member"

    id: int | None = Field(
        default=None,
        sa_column=Column("id", Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="项目内部主键。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), ForeignKey("af_user.public_id"), nullable=False, index=True),
        description="成员用户对外公开标识。",
    )
    role: ProjectMemberRole = Field(
        default=ProjectMemberRole.VIEWER,
        sa_column=Column(
            "role",
            SAEnum(
                ProjectMemberRole,
                values_callable=enum_values,
                name="project_member_role",
                native_enum=False,
                create_constraint=True,
                validate_strings=True,
                length=20,
            ),
            nullable=False,
            default=ProjectMemberRole.VIEWER.value,
            server_default=ProjectMemberRole.VIEWER.value,
        ),
        description="成员在项目中的角色。",
    )
    joined_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            "joined_at",
            DateTime(timezone=True),
            nullable=False,
            default=utc_now,
            server_default=func.now(),
        ),
        description="成员加入项目时间。",
    )