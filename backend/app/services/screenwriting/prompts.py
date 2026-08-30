from __future__ import annotations

from app.schemas.screenwriting import ScreenwritingActiveTab
from app.services.prompt_registry import PromptRegistry, PromptRegistryError
from app.services.screenwriting.tool_prompts import (
    GUIDE_RUNTIME_CONTRACT_PROMPT,
    load_script_prompt,
)


GUIDE_ASSISTANT_PROMPT_NAME = "screenwriting_guide_assistant"

FALLBACK_GUIDE_ASSISTANT_PROMPT = (
    "你是剧本创作的 AI 引导助理。你负责和用户进行多轮对话，"
    "帮助用户澄清创作目标、说明当前创作阶段，并把后续阶段能力的边界讲清楚。"
)

ACTIVE_TAB_LABELS: dict[str, str] = {
    "skeleton": "故事骨架",
    "strategy": "改编策略",
    "script": "剧本",
}


def load_guide_assistant_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取剧本创作引导助理提示词。"""
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(GUIDE_ASSISTANT_PROMPT_NAME)
    except PromptRegistryError:
        return FALLBACK_GUIDE_ASSISTANT_PROMPT


def build_guide_system_prompt(
    active_tab: ScreenwritingActiveTab,
    *,
    project_config_block: str = "",
    workspace_overview: str = "",
    config_confirmed: bool = True,
) -> str:
    """构建单次 Harness 对话的系统提示词，附带创作配置与工作区运行时上下文。

    config_confirmed 为假时创作配置仍是待确认草案，标题明确标注，避免模型把
    草案默认值（如默认集数）当作既定配置向用户复述。
    """
    active_label = ACTIVE_TAB_LABELS.get(active_tab, "故事骨架")
    sections = [
        load_guide_assistant_prompt(),
        f"当前右侧活动阶段：{active_label}（{active_tab}）。",
    ]
    if project_config_block.strip():
        config_heading = (
            "## 当前创作配置"
            if config_confirmed
            else "## 当前创作配置（待确认草案，最终以用户确认为准）"
        )
        sections.append(f"{config_heading}\n{project_config_block.strip()}")
    if workspace_overview.strip():
        sections.append(f"## 工作区概览\n{workspace_overview.strip()}")
    sections.append(load_script_prompt(GUIDE_RUNTIME_CONTRACT_PROMPT))
    return "\n\n".join(sections)