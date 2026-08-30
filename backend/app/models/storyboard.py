from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


STORYBOARD_STATUS_DRAFT = "draft"
STORYBOARD_STATUS_LOCKED = "locked"


class StoryboardShot(BaseModel, table=True):
    """用于制作工作台的结构化故事板镜头"""

    __tablename__ = "af_storyboard_shot"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_public_id",
            "episode_public_id",
            "shot_index",
            name="uq_af_storyboard_shot_episode_index",
        ),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="所属项目内部主键。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="所属用户公开标识。",
    )
    episode_public_id: str = Field(
        default="",
        sa_column=Column("episode_public_id", String(36), nullable=False, default="", server_default="", index=True),
        description="来源剧本分集公开标识。",
    )
    episode_index: int = Field(
        default=0,
        sa_column=Column("episode_index", Integer, nullable=False, default=0, server_default="0", index=True),
        description="来源分集序号。",
    )
    scene_number: str = Field(
        default="",
        sa_column=Column("scene_number", String(40), nullable=False, default="", server_default=""),
        description="场号。",
    )
    shot_index: int = Field(
        default=0,
        sa_column=Column("shot_index", Integer, nullable=False, default=0, server_default="0", index=True),
        description="镜头序号。",
    )
    shot_size: str = Field(
        default="",
        sa_column=Column("shot_size", String(40), nullable=False, default="", server_default=""),
        description="景别。",
    )
    camera: str = Field(
        default="",
        sa_column=Column("camera", String(120), nullable=False, default="", server_default=""),
        description="机位与运镜。",
    )
    action: str = Field(
        default="",
        sa_column=Column("action", Text, nullable=False, default="", server_default=""),
        description="画面动作。",
    )
    dialogue: str = Field(
        default="",
        sa_column=Column("dialogue", Text, nullable=False, default="", server_default=""),
        description="对白或旁白。",
    )
    duration_seconds: int = Field(
        default=0,
        sa_column=Column("duration_seconds", Integer, nullable=False, default=0, server_default="0"),
        description="镜头时长（秒）。"
    )
    asset_public_ids: str = Field(
        default="",
        sa_column=Column("asset_public_ids", String(400), nullable=False, default="", server_default=""),
        description="引用资产公开标识。",
    )
    asset_names: str = Field(
        default="",
        sa_column=Column("asset_names", String(400), nullable=False, default="", server_default=""),
        description="逗号分隔的引用资产名称。",
    )
    art_style_key: str = Field(
        default="",
        sa_column=Column("art_style_key", String(120), nullable=False, default="", server_default=""),
        description="分镜图生成使用的视觉风格名称。"
    )
    director_style_key: str = Field(
        default="",
        sa_column=Column("director_style_key", String(120), nullable=False, default="", server_default=""),
        description="分镜图生成使用的导演风格名称。"
    )
    model_id: str = Field(
        default="",
        sa_column=Column("model_id", String(120), nullable=False, default="", server_default=""),
        description="分镜图生成使用的文本大模型 ID。",
    )
    prompt: str = Field(
        default="",
        sa_column=Column("prompt", Text, nullable=False, default="", server_default=""),
        description="分镜图的正面提示。",
    )
    negative_prompt: str = Field(
        default="",
        sa_column=Column("negative_prompt", Text, nullable=False, default="", server_default=""),
        description="分镜图的负面提示。"
    )
    reference_media_public_id: str = Field(
        default="",
        sa_column=Column(
            "reference_media_public_id",
            String(36),
            nullable=False,
            default="",
            server_default="",
            index=True,
        ),
        description="分镜图公开标识。",
    )
    first_frame_media_public_id: str = Field(
        default="",
        sa_column=Column(
            "first_frame_media_public_id",
            String(36),
            nullable=True,
            default="",
            server_default=""
        ),
        description="镜头视频生成使用的可选首帧图片公开标识。",
    )
    last_frame_media_public_id: str = Field(
        default="",
        sa_column=Column(
            "last_frame_media_public_id",
            String(36),
            nullable=True,
            default="",
            server_default=""
        ),
        description="镜头视频生成使用的可选尾帧图片公开标识。",
    )
    seed: str = Field(
        default="",
        sa_column=Column("seed", String(60), nullable=False, default="", server_default=""),
        description="分镜图固定生成种子。",
    )
    status: str = Field(
        default=STORYBOARD_STATUS_DRAFT,
        sa_column=Column(
            "status",
            String(20),
            nullable=False,
            default=STORYBOARD_STATUS_DRAFT,
            server_default=STORYBOARD_STATUS_DRAFT,
            index=True,
        ),
        description="分镜状态：draft/locked。",
    )