from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint

from sqlmodel import Field

from app.models.base import BaseModel


class ScriptPlan(BaseModel, table=True):
    """剧本计划：剧本创作工作台同步落库的一部短剧。

    一个（项目, 用户, 源会话隔离键）对应一份计划，重复同步更新同一行（幂等）；
    分集正文挂在 af_script_episode 上。
    """

    __tablename__ = "af_script_plan"

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="所属项目内部主键。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="计划所属用户公开标识。",
    )
    source_isolation_key: str = Field(
        sa_column=Column("source_isolation_key", String(180), nullable=False, unique=True, index=True),
        description="来源剧本创作会话隔离键（项目+用户唯一），用于幂等同步。",
    )
    title: str = Field(
        default="",
        sa_column=Column("title", String(200), nullable=False, default="", server_default=""),
        description="剧本标题。",
    )
    total_episodes: str = Field(
        default="",
        sa_column=Column("total_episodes", String(60), nullable=False, default="", server_default=""),
        description="集数配置快照。",
    )
    episode_duration: str = Field(
        default="",
        sa_column=Column("episode_duration", String(60), nullable=False, default="", server_default=""),
        description="单集时长配置快照。",
    )
    source_range: str = Field(
        default="",
        sa_column=Column("source_range", String(120), nullable=False, default="", server_default=""),
        description="原著章节范围配置快照。",
    )
    platform_spec: str = Field(
        default="",
        sa_column=Column("platform_spec", String(120), nullable=False, default="", server_default=""),
        description="平台规格配置快照。",
    )
    style: str = Field(
        default="",
        sa_column=Column("style", String(200), nullable=False, default="", server_default=""),
        description="风格定位配置快照。",
    )
    paywall: str = Field(
        default="",
        sa_column=Column("paywall", String(200), nullable=False, default="", server_default=""),
        description="付费策略配置快照。",
    )
    status: str = Field(
        default="synced",
        sa_column=Column("status", String(40), nullable=False, default="synced", server_default="synced"),
        description="计划状态（synced 已同步）。",
    )


class ScriptEpisode(BaseModel, table=True):
    """剧本分集：一个剧本计划下的单集正文与场次结构。"""

    __tablename__ = "af_script_episode"
    __table_args__ = (
        UniqueConstraint("plan_id", "episode_index", name="uq_script_episode_plan_index"),
    )

    plan_id: int = Field(
        sa_column=Column("plan_id", Integer, ForeignKey("af_script_plan.id"), nullable=False, index=True),
        description="所属剧本计划内部主键。",
    )
    episode_index: int = Field(
        sa_column=Column("episode_index", Integer, nullable=False, index=True),
        description="分集序号（EP 编号）。",
    )
    title: str = Field(
        default="",
        sa_column=Column("title", String(200), nullable=False, default="", server_default=""),
        description="单集标题。",
    )
    summary: str = Field(
        default="",
        sa_column=Column("summary", Text, nullable=False, default="", server_default=""),
        description="单集剧情梗概。",
    )
    body: str = Field(
        default="",
        sa_column=Column("body", Text, nullable=False, default="", server_default=""),
        description="单集剧本正文 Markdown。",
    )
    scenes: str = Field(
        default="[]",
        sa_column=Column("scenes", Text, nullable=False, default="[]", server_default="[]"),
        description="场次结构 JSON（场号/标题/地点/日夜/内外）。",
    )
    chapter_ids: str = Field(
        default="",
        sa_column=Column("chapter_ids", String(400), nullable=False, default="", server_default=""),
        description="溯源章节编号（逗号分隔）。",
    )
    version: int = Field(
        default=1,
        sa_column=Column("version", Integer, nullable=False, default=1, server_default="1"),
        description="版本号，每次实质变更递增。",
    )
    is_locked: int = Field(
        default=0,
        sa_column=Column("is_locked", Integer, nullable=False, default=0, server_default="0"),
        description="人工锁定标记，锁定后同步不覆盖（1 锁定）。",
    )