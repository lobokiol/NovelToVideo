"""剧本创作 Harness profile 注册。"""

from __future__ import annotations

from typing import Any

from app.core.config import project_path, settings


SCREENWRITING_HARNESS_PROFILE_KEY = "providergatewaychatmodel"
SCREENWRITING_DEEPAGENTS_EXCLUDED_TOOLS = frozenset(
    {
        "execute",
        "write_todos",
        "task",
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
    }
)
SCREENWRITING_HARNESS_BASE_PROMPT = (
    "你是剧本创作业务中的 Harness Agent，只能围绕剧本创作对话、状态和资料工具工作。"
)
SCREENWRITING_HARNESS_PROMPT_SKILL_NAME = "harness_agent"
_SCREENWRITING_HARNESS_PROFILE_REGISTERED = False


def load_screenwriting_harness_prompt() -> str:
    """从 data/skills 读取 Harness Agent 基础提示词。"""
    prompt_path = project_path(settings.skills_root) / f"{SCREENWRITING_HARNESS_PROMPT_SKILL_NAME}.md"
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        return SCREENWRITING_HARNESS_BASE_PROMPT
    return prompt or SCREENWRITING_HARNESS_BASE_PROMPT


def build_screenwriting_harness_profile() -> Any:
    """构建剧本创作专用 deepagents profile。"""
    from deepagents.profiles.harness import GeneralPurposeSubagentProfile, HarnessProfile

    return HarnessProfile(
        base_system_prompt=load_screenwriting_harness_prompt(),
        excluded_tools=SCREENWRITING_DEEPAGENTS_EXCLUDED_TOOLS,
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )


def register_screenwriting_harness_profile() -> None:
    """注册剧本创作专用 profile，收敛 deepagents 默认工具范围。"""
    global _SCREENWRITING_HARNESS_PROFILE_REGISTERED
    if _SCREENWRITING_HARNESS_PROFILE_REGISTERED:
        return
    try:
        from deepagents.profiles.harness import register_harness_profile
    except ImportError:
        return
    register_harness_profile(SCREENWRITING_HARNESS_PROFILE_KEY, build_screenwriting_harness_profile())
    _SCREENWRITING_HARNESS_PROFILE_REGISTERED = True
