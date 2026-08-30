from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text

from sqlmodel import Field

from app.models.base import BaseModel


class ScreenwritingSession(BaseModel, table=True):
    """剧本创作会话持久化快照。

    每个（项目, 用户）只保留一行当前会话；历史快照以 JSON 形式内嵌在
    history 列中，可整体恢复。多 worker 部署时以数据库行为事实源。
    """

    __tablename__ = "af_screenwriting_session"

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="所属项目内部主键。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="会话所属用户公开标识。",
    )
    isolation_key: str = Field(
        sa_column=Column("isolation_key", String(180), nullable=False, unique=True, index=True),
        description="会话隔离键（项目+用户唯一）。",
    )
    conversation_id: str = Field(
        default="",
        sa_column=Column("conversation_id", String(120), nullable=False, default="", server_default=""),
        description="当前活跃对话标识，用于 Agent 线程续接。",
    )
    model_id: str = Field(
        default="",
        sa_column=Column("model_id", String(100), nullable=False, default="", server_default=""),
        description="文本模型标识。",
    )
    active_tab: str = Field(
        default="skeleton",
        sa_column=Column("active_tab", String(40), nullable=False, default="skeleton", server_default="skeleton"),
        description="当前激活的创作阶段。",
    )
    skeleton: str = Field(
        default="",
        sa_column=Column("skeleton", Text(), nullable=False, default="", server_default=""),
        description="故事骨架 Markdown。",
    )
    strategy: str = Field(
        default="",
        sa_column=Column("strategy", Text(), nullable=False, default="", server_default=""),
        description="改编策略 Markdown。",
    )
    script: str = Field(
        default="",
        sa_column=Column("script", Text(), nullable=False, default="", server_default=""),
        description="剧本草案 Markdown。",
    )
    messages: str = Field(
        default="[]",
        sa_column=Column("messages", Text(), nullable=False, default="[]", server_default="[]"),
        description="对话消息 JSON。",
    )
    history: str = Field(
        default="[]",
        sa_column=Column("history", Text(), nullable=False, default="[]", server_default="[]"),
        description="可恢复的历史快照 JSON。",
    )
    workflow: str = Field(
        default="{}",
        sa_column=Column("workflow", Text(), nullable=False, default="{}", server_default="{}"),
        description="创作流程状态 JSON。",
    )