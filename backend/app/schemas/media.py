from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.screenwriting import to_camel


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
WRITE_SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class MediaAssetRead(BaseModel):
    """媒体资产响应。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    media_type: str = "image"
    source: str = "generation"
    status: str = "pending"
    scope_type: str = ""
    scope_public_id: str = ""
    media_role: str = "generated"
    model_id: str = ""
    prompt: str = ""
    params: str = "{}"
    seed: str = ""
    url: str = ""
    mime_type: str = ""
    file_size: int = 0
    width: int = 0
    height: int = 0
    duration_ms: int = 0
    cost_tokens: int = 0
    task_job_public_id: str = ""
    error_message: str = ""
    created_at: datetime
    updated_at: datetime


class MediaVideoGenerateRequest(BaseModel):
    """视频生成任务提交请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    model_id: str = Field(default="", max_length=120, description="视频模型 ID；留空用项目绑定模型。")
    prompt: str = Field(min_length=1, description="视频生成提示词。")
    params: dict = Field(default_factory=dict, description="生成参数：分辨率、比例、时长、帧率、种子、音画同生开关等。")
    first_frame_media_public_id: str = Field(default="", max_length=36, description="首帧图媒体公开 ID。")
    last_frame_media_public_id: str = Field(default="", max_length=36, description="尾帧图媒体公开 ID。")
    reference_media_public_ids: list[str] = Field(default_factory=list, description="参考图媒体公开 ID 列表。")
    scope_type: str = Field(default="", max_length=20, description="挂靠业务对象类型：shot/track/episode/project。")
    scope_public_id: str = Field(default="", max_length=36, description="挂靠业务对象公开 ID。")
    count: int = Field(default=1, ge=1, le=4, description="生成候选段数。")
