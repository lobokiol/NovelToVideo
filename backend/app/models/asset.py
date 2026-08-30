from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, Boolean, String, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


# 资产类型：人物、势力、道具、场景。
ASSET_TYPE_ROLE = "role"
ASSET_TYPE_FACTION = "faction"
ASSET_TYPE_PROP = "prop"
ASSET_TYPE_SCENE = "scene"

# 资产状态：锁定后，后续重新抽取不会覆盖资产描述与关联信息。
ASSET_STATUS_DRAFT = "draft"
ASSET_STATUS_LOCKED = "locked"

# 资产与分集关系来源。
ASSET_EPISODE_SOURCE_EXTRACTION = "extraction"
ASSET_EPISODE_SOURCE_MANUAL = "manual"

# 资产关系类型：source_asset_id 指向 target_asset_id。
ASSET_RELATION_CHILD_OF = "child_of"
ASSET_RELATION_DERIVATIVE_OF = "derivative_of"
ASSET_RELATION_USES = "uses"
ASSET_RELATION_APPEARS_WITH = "appears_with"
ASSET_RELATION_BELONGS_TO = "belongs_to"


class Asset(BaseModel, table=True):
    """剧本制作资产。

    资产从剧本分集正文中抽取，按（项目、用户、类型、名称）唯一归并。
    资产描述字段与 data/skills/asset_extraction.md 输出结构保持一致。
    """

    __tablename__ = "af_asset"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_public_id",
            "asset_type",
            "name",
            name="uq_af_asset_project_user_type_name",
        ),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="资产所属项目内部主键。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="资产所属用户公开标识。",
    )
    asset_type: str = Field(
        default=ASSET_TYPE_ROLE,
        sa_column=Column(
            "asset_type",
            String(20),
            nullable=False,
            default=ASSET_TYPE_ROLE,
            server_default=ASSET_TYPE_ROLE,
            index=True,
        ),
        description="资产类型：role/faction/prop/scene",
    )
    name: str = Field(
        default="",
        sa_column=Column("name", String(200), nullable=False, default="", server_default=""),
        description="资产名称。",
    )
    keyword: str = Field(
        default="",
        sa_column=Column("keyword", String(500), nullable=False, default="", server_default=""),
        description="资产关键词，来自抽取结果 keyword 字段。",
    )
    colors: str = Field(
        default="",
        sa_column=Column("colors", String(1000), nullable=False, default="", server_default=""),
        description="资产色彩方案，来自抽取结果 colors 字段。",
    )
    summary: str = Field(
        default="",
        sa_column=Column("summary", Text, nullable=False, default="", server_default=""),
        description="资产摘要概述，来自抽取结果 summary 字段。",
    )
    description: str = Field(
        default="",
        sa_column=Column("description", Text, nullable=False, default="", server_default=""),
        description="资产基础整体描述 JSON 字符串，对应抽取结果 description 对象。",
    )
    details: str = Field(
        default="{}",
        sa_column=Column("details", Text, nullable=False, default="{}", server_default="{}"),
        description="资产细节部位拆解 JSON 字符串，对应抽取结果 details 对象。",
    )
    accessories: str = Field(
        default="{}",
        sa_column=Column("accessories", Text, nullable=False, default="{}", server_default="{}"),
        description="资产外观附属元素 JSON 字符串，对应抽取结果 accessories 对象。",
    )
    status: str = Field(
        default=ASSET_STATUS_DRAFT,
        sa_column=Column(
            "status",
            String(20),
            nullable=False,
            default=ASSET_STATUS_DRAFT,
            server_default=ASSET_STATUS_DRAFT,
            index=True,
        ),
        description="资产状态：draft/locked。",
    )
    main_asset: bool = Field(
        default=False,
        sa_column=Column("main_asset", Boolean, nullable=False, default=0, server_default="0", index=True),
        description="是否为主资产；主资产在列表中优先展示，子资产不参与主资产列表展示。",
    )
    variant_label: str = Field(
        default="",
        sa_column=Column("variant_label", String(100), nullable=False, default="", server_default=""),
        description="子资产变体标签，例如黑衣人、少年状态、受伤状态。",
    )

class AssetRelation(BaseModel, table=True):
    """资产之间的语义关系表。"""

    __tablename__ = "af_asset_relation"
    __table_args__ = (
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "relation_type",
            name="uq_af_asset_relation_source_target_type",
        ),
    )

    source_asset_id: int = Field(
        sa_column=Column("source_asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="关系起点资产内部主键。",
    )

    target_asset_id: int = Field(
        sa_column=Column("target_asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="关系终点资产内部主键。",
    )

    relation_type: str = Field(
        default=ASSET_RELATION_APPEARS_WITH,
        sa_column=Column(
            "relation_type",
            String(40),
            nullable=False,
            default=ASSET_RELATION_APPEARS_WITH,
            server_default=ASSET_RELATION_APPEARS_WITH,
            index=True,
        ),
        description="关系类型：child_of/derivative_of/uses/appears_with/belongs_to。",
    )
    relation_label: str = Field(
        default="",
        sa_column=Column("relation_label", String(120), nullable=False, default="", server_default=""),
        description="面向展示的关系标签。",
    )

class AssetEpisode(BaseModel, table=True):
    """资产与剧本分集的关联表。"""

    __tablename__ = "af_asset_episode"
    __table_args__ = (
        UniqueConstraint("asset_id", "episode_id", name="uq_af_asset_episode_asset_episode"),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="资产所属项目内部主键，冗余保存以便按项目查询。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="资产所属用户公开标识，冗余保存以便按用户隔离。",
    )
    asset_id: int = Field(
        sa_column=Column("asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="资产内部主键。",
    )
    episode_id: int = Field(
        sa_column=Column("episode_id", Integer, ForeignKey("af_script_episode.id"), nullable=False, index=True),
        description="剧本分集内部主键。",
    )
    episode_index: int = Field(
        default=0,
        sa_column=Column("episode_index", Integer, nullable=False, default=0, server_default="0", index=True),
        description="分集序号快照，用于快速过滤和展示。",
    )
    source: str = Field(
        default=ASSET_EPISODE_SOURCE_EXTRACTION,
        sa_column=Column(
            "source",
            String(40),
            nullable=False,
            default=ASSET_EPISODE_SOURCE_EXTRACTION,
            server_default=ASSET_EPISODE_SOURCE_EXTRACTION,
            index=True,
        ),
        description="关联来源：extraction/manual。",
    )

class AssetVersion(BaseModel, table=True):
    """资产版本快照表。"""

    __tablename__ = "af_asset_version"
    __table_args__ = (
        UniqueConstraint("asset_id", "version", name="uq_af_asset_version_asset_version"),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="资产所属项目内部主键，冗余保存以便按项目查询。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="资产所属用户公开标识，冗余保存以便按用户隔离。",
    )
    asset_id: int = Field(
        sa_column=Column("asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="资产内部主键。",
    )
    version: int = Field(
        default=1,
        sa_column=Column("version", Integer, nullable=False, default=1, server_default="1"),
        description="资产版本号，同一资产内递增。",
    )
    snapshot: str = Field(
        default="{}",
        sa_column=Column("snapshot", Text, nullable=False, default="{}", server_default="{}"),
        description="资产字段与关联信息快照 JSON 字符串。",
    )
    change_note: str = Field(
        default="",
        sa_column=Column("change_note", Text, nullable=False, default="", server_default=""),
        description="版本变更说明。",
    )
    created_by: str = Field(
        default="",
        sa_column=Column("created_by", String(36), nullable=False, default="", server_default="", index=True),
        description="创建该版本的用户公开标识；系统生成时为空。",
    )