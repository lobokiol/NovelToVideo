from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlmodel import Field

from app.models.base import BaseModel


# 媒体类型：图像、视频、音频。
MEDIA_TYPE_IMAGE = "image"
MEDIA_TYPE_VIDEO = "video"
MEDIA_TYPE_AUDIO = "audio"

# 媒体来源：模型生成、用户上传。
MEDIA_SOURCE_GENERATION = "generation"
MEDIA_SOURCE_UPLOAD = "upload"

# 媒体状态机：pending → processing → ready / failed。
MEDIA_STATUS_PENDING = "pending"
MEDIA_STATUS_PROCESSING = "processing"
MEDIA_STATUS_READY = "ready"
MEDIA_STATUS_FAILED = "failed"

# 媒体用途：参考素材、普通生成图、封面定妆、预览、宫格分镜图。
MEDIA_ROLE_REFERENCE = "reference"
MEDIA_ROLE_GENERATED = "generated"
MEDIA_ROLE_FINAL = "final"
MEDIA_ROLE_PREVIEW = "preview"
MEDIA_ROLE_GRID = "grid"

# 媒体挂靠的业务对象类型；业务侧仍以 media_public_id 回链，
# scope 仅用于画廊列举与级联清理，不承担外键约束。
MEDIA_SCOPE_ASSET = "asset"
MEDIA_SCOPE_SHOT = "shot"
MEDIA_SCOPE_TRACK = "track"
MEDIA_SCOPE_EPISODE = "episode"
MEDIA_SCOPE_PROJECT = "project"


class MediaAsset(BaseModel, table=True):
    """统一媒体中枢。

    项目内一切图像/视频/音频产物（生成或上传）都以一行媒体资产记录承载，
    生成参数、种子、用量与任务回链内嵌于本表；资产、镜头、片段、成片等
    业务对象一律通过 media_public_id 引用媒体，不再各自维护媒体子表。
    """

    __tablename__ = "af_media_asset"

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="所属项目内部主键。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="所属用户公开标识。",
    )
    media_type: str = Field(
        default=MEDIA_TYPE_IMAGE,
        sa_column=Column(
            "media_type",
            String(20),
            nullable=False,
            default=MEDIA_TYPE_IMAGE,
            server_default=MEDIA_TYPE_IMAGE,
            index=True,
        ),
        description="媒体类型：image/video/audio。",
    )
    source: str = Field(
        default=MEDIA_SOURCE_GENERATION,
        sa_column=Column(
            "source",
            String(20),
            nullable=False,
            default=MEDIA_SOURCE_GENERATION,
            server_default=MEDIA_SOURCE_GENERATION,
            index=True,
        ),
        description="媒体来源：generation/upload。",
    )
    status: str = Field(
        default=MEDIA_STATUS_PENDING,
        sa_column=Column(
            "status",
            String(20),
            nullable=False,
            default=MEDIA_STATUS_PENDING,
            server_default=MEDIA_STATUS_PENDING,
            index=True,
        ),
        description="媒体状态：pending/processing/ready/failed。",
    )
    scope_type: str = Field(
        default="",
        sa_column=Column("scope_type", String(20), nullable=False, default="", server_default="", index=True),
        description="挂靠业务对象类型：asset/shot/track/episode/project；空表示项目级散置媒体。",
    )
    scope_public_id: str = Field(
        default="",
        sa_column=Column(
            "scope_public_id",
            String(36),
            nullable=False,
            default="",
            server_default="",
            index=True,
        ),
        description="挂靠业务对象公开标识。",
    )
    media_role: str = Field(
        default=MEDIA_ROLE_GENERATED,
        sa_column=Column(
            "media_role",
            String(40),
            nullable=False,
            default=MEDIA_ROLE_GENERATED,
            server_default=MEDIA_ROLE_GENERATED,
            index=True,
        ),
        description="媒体用途：reference/generated/final/preview。",
    )
    provider_key: str = Field(
        default="",
        sa_column=Column("provider_key", String(80), nullable=False, default="", server_default="", index=True),
        description="生成服务提供方标识；上传媒体为空。",
    )
    model_id: str = Field(
        default="",
        sa_column=Column("model_id", String(120), nullable=False, default="", server_default="", index=True),
        description="生成模型标识；上传媒体为空。",
    )
    prompt: str = Field(
        default="",
        sa_column=Column("prompt", Text, nullable=False, default="", server_default=""),
        description="生成提示词；上传媒体为空。",
    )
    params: str = Field(
        default="{}",
        sa_column=Column("params", Text, nullable=False, default="{}", server_default="{}"),
        description="生成参数或上传元数据 JSON 字符串。",
    )
    seed: str = Field(
        default="",
        sa_column=Column("seed", String(60), nullable=False, default="", server_default=""),
        description="生成种子；未知或不适用为空。",
    )
    storage_backend: str = Field(
        default="",
        sa_column=Column("storage_backend", String(20), nullable=False, default="", server_default=""),
        description="存储后端：local/s3；未落盘为空。",
    )
    storage_key: str = Field(
        default="",
        sa_column=Column("storage_key", String(1000), nullable=False, default="", server_default="", index=True),
        description="存储相对路径：{project_public_id}/{media_type}/{public_id}.{ext}。",
    )
    url: str = Field(
        default="",
        sa_column=Column("url", String(2000), nullable=False, default="", server_default=""),
        description="媒体内容访问 URL。",
    )
    mime_type: str = Field(
        default="",
        sa_column=Column("mime_type", String(120), nullable=False, default="", server_default=""),
        description="媒体 MIME 类型。",
    )
    file_size: int = Field(
        default=0,
        sa_column=Column("file_size", Integer, nullable=False, default=0, server_default="0"),
        description="文件字节数，未知时为 0。",
    )
    width: int = Field(
        default=0,
        sa_column=Column("width", Integer, nullable=False, default=0, server_default="0"),
        description="图像或视频宽度，未知时为 0。",
    )
    height: int = Field(
        default=0,
        sa_column=Column("height", Integer, nullable=False, default=0, server_default="0"),
        description="图像或视频高度，未知时为 0。",
    )
    duration_ms: int = Field(
        default=0,
        sa_column=Column("duration_ms", Integer, nullable=False, default=0, server_default="0"),
        description="音视频时长毫秒，未知时为 0。",
    )
    cost_tokens: int = Field(
        default=0,
        sa_column=Column("cost_tokens", Integer, nullable=False, default=0, server_default="0"),
        description="生成消耗 token 数，未知时为 0。",
    )
    usage: str = Field(
        default="{}",
        sa_column=Column("usage", Text, nullable=False, default="{}", server_default="{}"),
        description="供应商原始用量与计费信息 JSON 字符串。",
    )
    task_job_public_id: str = Field(
        default="",
        sa_column=Column(
            "task_job_public_id",
            String(36),
            nullable=False,
            default="",
            server_default="",
            index=True,
        ),
        description="关联异步任务公开标识。",
    )
    task_item_public_id: str = Field(
        default="",
        sa_column=Column(
            "task_item_public_id",
            String(36),
            nullable=False,
            default="",
            server_default="",
            index=True,
        ),
        description="关联异步任务子项公开标识。",
    )
    error_message: str = Field(
        default="",
        sa_column=Column("error_message", Text, nullable=False, default="", server_default=""),
        description="生成失败原因；成功或上传媒体为空。",
    )