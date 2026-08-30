from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.screenwriting import to_camel


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
WRITE_SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class StoryboardGenerateRequest(BaseModel):
    """从剧本分集生成分镜镜头的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    model_id: str = Field(min_length=1, max_length=120, description="文本模型 ID。")
    episode_public_ids: list[str] = Field(default_factory=list, description="目标分集公开 ID；留空表示使用最新方案。")
    shot_public_ids: list[str] = Field(
        default_factory=list,
        description="按镜头重生成：只重写这些镜头的分镜脚本字段；留空表示整集生成。",
    )
    art_style: str = Field(default="", max_length=120, description="可选视觉风格标识。")
    director_style: str = Field(default="", max_length=120, description="可选导演风格标识。")


class StoryboardGridImageRequest(BaseModel):
    """宫格分镜图生成任务提交请求（每个镜头生成一张宫格图）。"""

    model_config = WRITE_SCHEMA_CONFIG

    grid_size: int = Field(default=9, description="宫格规格：1/4/9/16/25；1 表示直接生成单帧首帧图。")
    image_size: str = Field(default="2K", max_length=8, description="分镜图分辨率：1K/2K/4K；格数越多要求分辨率越高，1 宫格各档位均可用。")
    episode_public_ids: list[str] = Field(default_factory=list, description="目标分集公开 ID；留空表示全部分集。")
    shot_public_ids: list[str] = Field(default_factory=list, description="目标镜头公开 ID；留空表示按分集选取。")
    only_missing: bool = Field(default=False, description="仅为尚无分镜图的镜头生成。")
    model_id: str = Field(default="", max_length=120, description="图像模型 ID；留空用项目绑定模型。")


class StoryboardShotVideoRequest(BaseModel):
    """镜头视频生成任务提交请求（以镜头分镜图为首帧做图生视频）。"""

    model_config = WRITE_SCHEMA_CONFIG

    episode_public_ids: list[str] = Field(default_factory=list, description="目标分集公开 ID；留空表示全部分集。")
    shot_public_ids: list[str] = Field(default_factory=list, description="目标镜头公开 ID；留空表示按分集选取。")
    only_missing: bool = Field(default=True, description="仅为尚无选定视频的镜头生成。")
    generate_audio: bool = Field(default=False, description="是否随视频同生音频（需模型支持音画同生）。")
    resolution: str = Field(default="", max_length=20, description="分辨率档位，如 720p/1080p；留空用默认。")
    ratio: str = Field(default="", max_length=10, description="视频比例，如 9:16/16:9；留空用项目设置。")
    model_id: str = Field(default="", max_length=120, description="视频模型 ID；留空用项目绑定模型。")
    duration_seconds: int | None = Field(
        default=None,
        ge=4,
        le=15,
        description="本次生成时长秒数；留空使用镜头时长。",
    )
    quantity: int = Field(default=1, ge=1, le=4, description="每个目标镜头生成的候选数量。")


class StoryboardShotUpdate(BaseModel):
    """单个分镜镜头的局部更新字段。"""

    model_config = WRITE_SCHEMA_CONFIG

    scene_number: str | None = Field(default=None, max_length=40)
    shot_size: str | None = Field(default=None, max_length=40)
    camera: str | None = Field(default=None, max_length=120)
    action: str | None = None
    dialogue: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    asset_public_ids: str | None = Field(default=None, max_length=400)
    asset_names: str | None = Field(default=None, max_length=400)
    art_style_key: str | None = Field(default=None, max_length=120)
    director_style_key: str | None = Field(default=None, max_length=120)
    model_id: str | None = Field(default=None, max_length=120)
    prompt: str | None = None
    negative_prompt: str | None = None
    reference_media_public_id: str | None = Field(default=None, max_length=36)
    last_frame_media_public_id: str | None = Field(default=None, max_length=36)
    seed: str | None = Field(default=None, max_length=60)


class StoryboardShotRead(BaseModel):
    """分镜镜头响应。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    episode_public_id: str = ""
    episode_index: int = 0
    scene_number: str = ""
    shot_index: int = 0
    shot_size: str = ""
    camera: str = ""
    action: str = ""
    dialogue: str = ""
    duration_seconds: int = 0
    asset_public_ids: str = ""
    asset_names: str = ""
    art_style_key: str = ""
    director_style_key: str = ""
    model_id: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    reference_media_public_id: str = ""
    last_frame_media_public_id: str = ""
    seed: str = ""
    status: str = "draft"
    created_at: datetime
    updated_at: datetime


class StoryboardGenerateResult(BaseModel):
    """同步生成结果。"""

    model_config = READ_SCHEMA_CONFIG

    created: int = 0
    updated: int = 0
    shots: list[StoryboardShotRead] = Field(default_factory=list)