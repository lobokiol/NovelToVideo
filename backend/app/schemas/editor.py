from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.screenwriting import to_camel


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
WRITE_SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class EditorProjectRead(BaseModel):
    """剪辑工程响应。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    name: str = "剪辑工程"
    timeline: str = "{}"
    duration_ms: int = 0
    ratio: str = ""
    updated_at: datetime


class EditorProjectSaveRequest(BaseModel):
    """剪辑工程保存请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    timeline: str = Field(description="时间线工程 JSON 字符串。")
    duration_ms: int = Field(default=0, ge=0, description="时间线总时长毫秒。")
    ratio: str = Field(default="", max_length=20, description="画幅比例；留空保持不变。")
    name: str = Field(default="", max_length=120, description="工程名称；留空保持不变。")