from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.screenwriting import to_camel


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
WRITE_SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class ScriptSyncPayload(BaseModel):
    """从剧本创作会话同步到剧本管理的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    title: str = Field(default="", max_length=200)


class ScriptPlanCreate(BaseModel):
    """手动新建/导入整部剧本的请求：把整段 Markdown 解析为分集落库。"""

    model_config = WRITE_SCHEMA_CONFIG

    title: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, description="整部剧本 Markdown，按分集标题拆分。")


class ScriptPlanUpdate(BaseModel):
    """更新剧本计划元信息的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    title: str = Field(min_length=1, max_length=200)


class ScriptEpisodeUpdate(BaseModel):
    """编辑单集的请求；仅提交的字段会被更新，正文变更会重解析场次并递增版本。"""

    model_config = WRITE_SCHEMA_CONFIG

    title: str | None = Field(default=None, max_length=200)
    summary: str | None = None
    body: str | None = None


class ScriptExportRequest(BaseModel):
    """导出选中剧本分集的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    episode_public_ids: list[str] = Field(default_factory=list, min_length=1)


class ScriptSceneRead(BaseModel):
    """剧本分集的单场结构。"""

    model_config = WRITE_SCHEMA_CONFIG

    number: str = ""
    title: str = ""
    location: str = ""
    day_night: str = ""
    interior_exterior: str = ""


class ScriptAssetRead(BaseModel):
    """分集列表中展示的主资产摘要。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    asset_type: str
    name: str = ""
    summary: str = ""
    description: str = ""
    status: str = "draft"


class ScriptEpisodeRead(BaseModel):
    """剧本分集。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    episode_index: int
    title: str = ""
    summary: str = ""
    body: str = ""
    scenes: list[ScriptSceneRead] = Field(default_factory=list)
    version: int = 1
    is_locked: bool = False

    @classmethod
    def from_model(cls, episode: Any) -> "ScriptEpisodeRead":
        try:
            raw_scenes = json.loads(episode.scenes or "[]")
        except (TypeError, ValueError):
            raw_scenes = []
        return cls(
            public_id=episode.public_id,
            episode_index=episode.episode_index,
            title=episode.title,
            summary=episode.summary,
            body=episode.body,
            scenes=[ScriptSceneRead.model_validate(scene) for scene in raw_scenes if isinstance(scene, dict)],
            version=episode.version,
            is_locked=bool(episode.is_locked),
        )


class ScriptPlanSummary(BaseModel):
    """剧本计划列表项。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    title: str = ""
    total_episodes: str = ""
    episode_duration: str = ""
    status: str = "synced"
    updated_at: datetime


class ScriptPlanDetail(BaseModel):
    """剧本计划详情（含分集）。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    title: str = ""
    total_episodes: str = ""
    episode_duration: str = ""
    source_range: str = ""
    platform_spec: str = ""
    style: str = ""
    paywall: str = ""
    status: str = "synced"
    updated_at: datetime
    episodes: list[ScriptEpisodeRead] = Field(default_factory=list)


class ScriptEpisodeListItem(BaseModel):
    """分集平铺列表项：携带所属剧本计划信息，供「我的剧本」卡片直接展示与编辑。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    plan_public_id: str
    plan_title: str = ""
    episode_index: int
    title: str = ""
    summary: str = ""
    body: str = ""
    scenes: list[ScriptSceneRead] = Field(default_factory=list)
    version: int = 1
    is_locked: bool = False
    updated_at: datetime
    assets: list[ScriptAssetRead] = Field(default_factory=list)

    @classmethod
    def from_row(
        cls,
        episode: Any,
        plan_public_id: str,
        plan_title: str,
        assets: list[Any] | None = None,
    ) -> "ScriptEpisodeListItem":
        try:
            raw_scenes = json.loads(episode.scenes or "[]")
        except (TypeError, ValueError):
            raw_scenes = []
        return cls(
            public_id=episode.public_id,
            plan_public_id=plan_public_id,
            plan_title=plan_title,
            episode_index=episode.episode_index,
            title=episode.title,
            summary=episode.summary,
            body=episode.body,
            scenes=[ScriptSceneRead.model_validate(scene) for scene in raw_scenes if isinstance(scene, dict)],
            version=episode.version,
            is_locked=bool(episode.is_locked),
            updated_at=episode.updated_at,
            assets=[ScriptAssetRead.model_validate(asset) for asset in assets or []],
        )
