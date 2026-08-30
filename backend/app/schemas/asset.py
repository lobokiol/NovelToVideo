from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.screenwriting import to_camel


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
WRITE_SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class AssetRead(BaseModel):
    """资产响应。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    asset_type: str
    name: str = ""
    keyword: str = ""
    colors: str = ""
    summary: str = ""
    description: str = ""
    details: str = "{}"
    accessories: str = "{}"
    status: str = "draft"
    main_asset: bool = False
    variant_label: str = ""
    thumbnail_url: str = ""
    created_at: datetime
    updated_at: datetime


class AssetEpisodeBrief(BaseModel):
    """资产关联分集摘要。"""

    model_config = READ_SCHEMA_CONFIG

    episode_id: str
    episode_name: str = ""


class AssetDetailRead(AssetRead):
    """资产详情响应。"""

    episode_items: list[AssetEpisodeBrief] = Field(default_factory=list)


class AssetExtractRequest(BaseModel):
    """从剧本正文抽取资产的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    model_id: str = Field(min_length=1, max_length=120, description="抽取所用文本模型 ID。")
    episode_public_ids: list[str] = Field(default_factory=list, description="指定分集公开 ID；留空则抽取最新剧本全集。")


class AssetAssociationRequest(BaseModel):
    """设置分集关联资产的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    episode_public_id: str = Field(min_length=1, description="分集公开 ID。")
    asset_public_ids: list[str] = Field(default_factory=list, description="关联的资产公开 ID 列表。")


class AssetAutocompleteRequest(BaseModel):
    """资产描述补全请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    model_id: str = Field(min_length=1, max_length=120, description="补全所用文本模型 ID。")
    asset_public_ids: list[str] = Field(default_factory=list, description="待补全资产公开 ID 列表。")


class AssetAssociationResult(BaseModel):
    """分集关联资产结果。"""

    model_config = READ_SCHEMA_CONFIG

    affected: int = 0
    assets: list[AssetRead] = Field(default_factory=list)


class AssetExtractResult(BaseModel):
    """资产抽取结果。"""

    model_config = READ_SCHEMA_CONFIG

    created: int = 0
    updated: int = 0
    assets: list[AssetRead] = Field(default_factory=list)


class AssetBatchResult(BaseModel):
    """批量操作资产结果。"""

    model_config = READ_SCHEMA_CONFIG

    affected: int = 0
    assets: list[AssetRead] = Field(default_factory=list)


class AssetAutocompleteResult(BaseModel):
    """资产描述补全结果契约：对齐 code2 资产结构化字段形状。"""

    model_config = WRITE_SCHEMA_CONFIG

    summary: str = ""
    keyword: str = ""
    colors: str = ""
    description: dict[str, str] = Field(default_factory=dict)
    details: dict[str, str] = Field(default_factory=dict)
    accessories: dict[str, str] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        """全部字段为空视为无效补全。"""

        return not any(
            [
                self.summary.strip(),
                self.keyword.strip(),
                self.colors.strip(),
                self.description,
                self.details,
                self.accessories,
            ]
        )


class AssetReferenceRead(BaseModel):
    """资产被剧本分集引用的记录：区分显式关联与正文命中。"""

    model_config = READ_SCHEMA_CONFIG

    episode_public_id: str
    episode_index: int = 0
    episode_title: str = ""
    plan_public_id: str = ""
    plan_title: str = ""
    source: str = "text"
    snippet: str = ""


class AssetManageItem(AssetRead):
    """资产管理项：在资产响应基础上附带子资产树与引用记录。"""

    children: list["AssetManageItem"] = Field(default_factory=list)
    references: list[AssetReferenceRead] = Field(default_factory=list)


class AssetManageListResult(BaseModel):
    """资产管理分页结果。"""

    model_config = READ_SCHEMA_CONFIG

    items: list[AssetManageItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    pages: int = 0


class AssetCreateRequest(BaseModel):
    """手动创建根资产请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    asset_type: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    keyword: str = Field(default="", max_length=500)
    colors: str = Field(default="", max_length=1000)
    summary: str = ""
    description: str = ""
    details: str = "{}"
    accessories: str = "{}"
    main_asset: bool = True
    variant_label: str = Field(default="", max_length=100)


class AssetUpdateRequest(BaseModel):
    """编辑资产请求；未提供的字段保持不变。"""

    model_config = WRITE_SCHEMA_CONFIG

    name: str | None = Field(default=None, min_length=1, max_length=200)
    keyword: str | None = Field(default=None, max_length=500)
    colors: str | None = Field(default=None, max_length=1000)
    summary: str | None = None
    description: str | None = None
    details: str | None = None
    accessories: str | None = None
    variant_label: str | None = Field(default=None, max_length=100)


class AssetParentUpdateRequest(BaseModel):
    """设置资产父节点请求；空值表示解除当前父子关系。"""

    model_config = WRITE_SCHEMA_CONFIG

    parent_asset_public_id: str | None = Field(
        default=None,
        max_length=36,
        description="父资产公开标识；传空或空字符串表示解绑。",
    )


class AssetBatchRequest(BaseModel):
    """批量操作资产请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    asset_public_ids: list[str] = Field(default_factory=list)
    operation: str = Field(min_length=1, description="批量操作：lock/unlock/delete。")


class AssetMediaRead(BaseModel):
    """资产媒体响应。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    media_type: str = "image"
    media_role: str = "generated"
    url: str = ""
    mime_type: str = ""
    width: int = 0
    height: int = 0
    prompt: str = ""
    created_at: datetime


class AssetImageGenerateRequest(BaseModel):
    """资产图像生成请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    model_id: str = Field(min_length=1, max_length=120, description="图像模型 ID。")
    asset_public_ids: list[str] = Field(default_factory=list, description="待生成配图的资产公开 ID 列表。")
    prompt: str = Field(default="", description="可选自定义提示词；留空则由资产字段自动拼装。")
    aspect_ratio: str = Field(default="", max_length=20, description="图像比例，如 1:1 / 16:9；留空用模型默认。")
    image_size: str = Field(default="", max_length=10, description="分辨率档位 1K/2K/4K；留空用模型默认。")
    reference_media_public_ids: list[str] = Field(
        default_factory=list,
        description="用于衍生资产图像编辑的参考媒体公开 ID；非空时走图片编辑接口。",
    )
    count: int = Field(default=1, ge=1, le=4, description="每个资产生成张数。")


AssetManageItem.model_rebuild()
