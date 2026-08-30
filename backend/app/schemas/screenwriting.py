from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    """将 snake_case 字段名转换为 camelCase。"""
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)
READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)

ScreenwritingActiveTab = Literal["skeleton", "strategy", "script"]
ScreenwritingChatRole = Literal["user", "assistant"]


class ScreenwritingChatTurn(BaseModel):
    """剧本创作对话消息。"""

    model_config = SCHEMA_CONFIG

    role: ScreenwritingChatRole
    content: str = Field(min_length=1, max_length=4000)
    time: str = Field(default="", max_length=32)

    @field_validator("content", "time")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ScreenwritingChatPayload(BaseModel):
    """剧本创作 Agent 多轮对话请求。

    对话历史由服务端会话持久化承载，客户端只提交本轮输入。
    """

    model_config = SCHEMA_CONFIG

    message: str = Field(min_length=1, max_length=4000)
    active_tab: ScreenwritingActiveTab = "skeleton"
    reset: bool = False
    client_request_started_at_ms: int | None = Field(default=None, ge=0)

    @field_validator("message")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ScreenwritingWorkspaceRead(BaseModel):
    """剧本创作工作区快照。"""

    model_config = READ_SCHEMA_CONFIG

    skeleton: str = ""
    strategy: str = ""
    script: str = ""


class ScreenwritingHistoryEntryRead(BaseModel):
    """可恢复的剧本创作历史快照。"""

    model_config = READ_SCHEMA_CONFIG

    id: str
    title: str
    created_at: datetime
    active_tab: ScreenwritingActiveTab = "skeleton"
    workspace: ScreenwritingWorkspaceRead
    messages: list[ScreenwritingChatTurn] = Field(default_factory=list)


class ScreenwritingStateResponse(BaseModel):
    """剧本创作会话状态。"""

    model_config = READ_SCHEMA_CONFIG

    project_public_id: str
    isolation_key: str
    conversation_id: str
    model_id: str
    active_tab: ScreenwritingActiveTab = "skeleton"
    workspace: ScreenwritingWorkspaceRead
    messages: list[ScreenwritingChatTurn] = Field(default_factory=list)
    history: list[ScreenwritingHistoryEntryRead] = Field(default_factory=list)
    workflow: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class ScreenwritingWorkspaceUpdate(BaseModel):
    """剧本创作工作区手动编辑保存请求。"""

    model_config = SCHEMA_CONFIG

    active_tab: ScreenwritingActiveTab = "skeleton"
    content: str = Field(default="", max_length=2_000_000)


class ScreenwritingConfigDraftPayload(BaseModel):
    """剧本创作初始化配置草案（结构化表单提交）。

    抽屉表单提交后写入草案配置但不锁定，用户仍需在对话中回复「确认」才生效。
    所有字段可选，仅提交用户填写的项。
    """

    model_config = SCHEMA_CONFIG

    total_episodes: int | None = Field(default=None, ge=1, le=999)
    episode_duration: int | None = Field(default=None, ge=1, le=180)
    source_start: int | None = Field(default=None, ge=1)
    source_end: int | None = Field(default=None, ge=1)
    platform_spec: str | None = Field(default=None, max_length=40)
    style: str | None = Field(default=None, max_length=120)
    paywall: str | None = Field(default=None, max_length=200)


class ScreenwritingHistoryRestorePayload(BaseModel):
    """恢复剧本创作历史快照请求。"""

    model_config = SCHEMA_CONFIG

    history_id: str = Field(min_length=1, max_length=80)


class ScreenwritingChatResponse(BaseModel):
    """剧本创作 Agent 聚合响应。"""

    model_config = READ_SCHEMA_CONFIG

    conversation_id: str
    isolation_key: str
    model_id: str
    active_tab: ScreenwritingActiveTab
    content: str
    messages: list[ScreenwritingChatTurn] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)


class ScreenwritingRagWarmupResponse(BaseModel):
    """剧本创作 RAG 向量索引预热调度结果。"""

    model_config = READ_SCHEMA_CONFIG

    status: str
    rag_isolation_key: str


class ScreenwritingAssessPayload(BaseModel):
    """剧本创作阶段质量评估请求。"""

    model_config = SCHEMA_CONFIG

    active_tab: ScreenwritingActiveTab = "skeleton"


class ScreenwritingStreamEvent(BaseModel):
    """剧本创作 Agent 流式事件。"""

    model_config = READ_SCHEMA_CONFIG

    type: str
    content: str = ""
    conversation_id: str
    isolation_key: str
    model_id: str
    active_tab: ScreenwritingActiveTab
    data: dict[str, Any] = Field(default_factory=dict)