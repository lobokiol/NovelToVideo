from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


ProviderInputType = Literal["text", "password", "url"]
ProviderModelType = Literal["text", "image", "video", "tts"]


class ProviderInput(BaseModel):
    """可编辑的服务凭据或地址输入项。"""

    model_config = ConfigDict(extra="ignore")

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    type: ProviderInputType = "text"
    required: bool = True


class ProviderDurationResolution(BaseModel):
    """视频时长与分辨率选项组。"""

    model_config = ConfigDict(extra="allow")

    duration: list[int] = Field(default_factory=list)
    resolution: list[str] = Field(default_factory=list)


class ProviderVoice(BaseModel):
    """语音生成音色选项。"""

    model_config = ConfigDict(extra="allow")

    title: str = Field(min_length=1, max_length=120)
    voice: str = Field(min_length=1, max_length=120)


class ProviderModel(BaseModel):
    """供客户端选择能力时使用的模型元数据。"""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str = Field(min_length=1, max_length=120)
    model_id: str = Field(
        min_length=1,
        max_length=160,
        validation_alias=AliasChoices("model_id", "modelId", "modelName"),
    )
    model_type: ProviderModelType = Field(
        validation_alias=AliasChoices("model_type", "modelType", "type"),
    )
    description: str = Field(default="", max_length=1000)
    modes: list[str | list[str]] = Field(
        default_factory=list,
        validation_alias=AliasChoices("modes", "mode"),
    )
    think: bool | None = None
    voices: list[ProviderVoice] | None = None
    audio: bool | str | None = None
    duration_resolution_map: list[ProviderDurationResolution] | None = Field(
        default=None,
        validation_alias=AliasChoices("duration_resolution_map", "durationResolutionMap"),
    )


class ProviderConfig(BaseModel):
    """服务文件中的 PROVIDER_CONFIG 配置结构。"""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    protocol: str = Field(min_length=1, max_length=64)
    version: str = Field(default="1.0", max_length=32)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    decs_url: str = Field(default="", max_length=512)
    icon: str = Field(default="")
    inputs: list[ProviderInput] = Field(default_factory=list)
    input_values: dict[str, str] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("input_values", "inputValues"),
    )
    base_url: str = Field(
        default="",
        max_length=512,
        validation_alias=AliasChoices("base_url", "baseUrl"),
    )
    enabled: bool = True
    sort_order: int = Field(
        default=0,
        validation_alias=AliasChoices("sort_order", "sortOrder"),
    )
    models: list[ProviderModel] = Field(default_factory=list)
    url: str = Field(default="", max_length=512)

    @field_validator("input_values", mode="before")
    @classmethod
    def stringify_input_values(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("input_values 必须是对象")
        return {str(key): "" if item is None else str(item) for key, item in value.items()}


class ProviderInputValuesUpdate(BaseModel):
    """只更新服务输入值的请求体。"""

    input_values: dict[str, str] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("input_values", "inputValues"),
    )


class ProviderModelsFetchRequest(BaseModel):
    """根据当前未保存的服务配置临时拉取远端模型列表。"""

    config: ProviderConfig


class ProviderTemplateGenerateRequest(BaseModel):
    """根据当前表单配置生成服务文件模板。"""

    config: ProviderConfig


class ProviderCreate(BaseModel):
    """创建服务文件的请求体。"""

    config: ProviderConfig
    code: str | None = None


class ProviderCodeUpdate(BaseModel):
    """替换服务文件源码的请求体。"""

    code: str = Field(min_length=1)


class ProviderFileRead(BaseModel):
    """服务配置与源码读取结果。"""

    config: ProviderConfig
    code: str


class ProviderTemplateRead(BaseModel):
    """基础服务文件模板。"""

    code: str
