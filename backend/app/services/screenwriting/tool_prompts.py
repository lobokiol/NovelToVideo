"""剧本创作工具相关提示词加载。

工具描述与提示词契约段外置在 data/script/ 目录（Markdown 文件），
供 web 端可视化编辑；文件缺失或为空时回退到内置兜底文本，保证主链路可用。
复用 PromptRegistry 的索引与缓存机制（文件 stem 即提示词名称）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.config import Settings, script_prompts_root_path
from app.services.prompt_registry import PromptRegistry, PromptRegistryError


GUIDE_RUNTIME_CONTRACT_PROMPT = "guide_runtime_contract"
STAGE_RUNTIME_CONTRACT_PROMPT = "stage_runtime_contract"


def _assessor_fallback(stage_label: str, dimensions: str, prompt_prefix: str) -> str:
    return (
        f"你是商业短剧行业的资深制片人与评估专家，负责以付费竖屏短剧标准评估{stage_label}质量。\n"
        f"评估维度（每项 0-10 分）：{dimensions}。\n"
        "必须基于运行时上下文提供的创作配置、配置章节事件与工作区内容评估，"
        "每个问题给出具体证据与可执行改法。\n"
        "输出格式：直接输出 Markdown 评估报告（不要代码栅栏、不要 JSON）——"
        "开篇总评；`## 评分` 小节每行一个维度，格式严格为 `**维度名：X/10**`，"
        "最后一行 `**最终综合：X/10**`；随后是优点分析、主要问题、可执行改进清单。\n"
        "报告结束后输出单独一行 `<!--IMPROVEMENT_PROMPT-->`，其后输出改进提示词：\n"
        f"以「{prompt_prefix}」开头，把改进清单浓缩为 200-400 字的明确执行指令；"
        "改进提示词必须继续使用运行时上下文中的已确认创作配置，"
        "不得自行改写集数、单集时长、原著范围、平台规格、风格定位或付费策略。"
    )


# 内置兜底：与 data/script/ 下同名文件保持同义，文件缺失时使用。
SCRIPT_PROMPT_FALLBACKS: dict[str, str] = {
    "stage_quality_assessor_skeleton": _assessor_fallback(
        "故事骨架",
        "原著改编忠实度、短剧商业性、用户付费驱动力、节奏效率",
        "请重新生成故事骨架：",
    ),
    "stage_quality_assessor_strategy": _assessor_fallback(
        "改编策略",
        "骨架承接度、可执行性、商业取舍质量、风险控制",
        "请重新生成改编策略：",
    ),
    "stage_quality_assessor_script": _assessor_fallback(
        "剧本草案",
        "场面执行力、对白质量、节奏与时长、钩子强度",
        "请重新生成剧本草案：",
    ),
    "get_rag_context": "读取本轮剧本创作 RAG 检索上下文。",
    "get_project_config": "读取当前创作配置（集数、单集时长、原著范围、平台规格、风格定位、付费策略）。",
    "get_workspace": "读取三个创作阶段工作区（故事骨架、改编策略、剧本草案）的当前完整内容。",
    "get_novel_events": "按章节范围读取小说章节事件；不传范围时默认使用创作配置的原著范围。",
    GUIDE_RUNTIME_CONTRACT_PROMPT: (
        "可用工具：get_rag_context（检索项目资料）、get_project_config（只读创作配置）、"
        "get_workspace（读取三阶段工作区全文）、get_novel_events（按章节范围读取小说章节事件）。\n"
        "当前能力边界：本轮支持多轮对话、上下文延续、项目资料检索与创作配置读取；"
        "创作配置由用户确认锁定，助理只读不写，不得自行修改集数等配置；"
        "用户要调整配置时引导其用明确句式直接说明（例如「集数调整为8集」）。"
        "阶段生成请求（故事骨架/改编策略/剧本草案）会由阶段助理直写右侧工作区。\n"
        "回答要求：使用简体中文，直接回应用户问题；如果本轮提供了项目资料检索上下文，"
        "必须优先依据其中的章节资料、人物信息或技能资料作答；引用创作配置严格按 get_project_config "
        "返回值，不要复述记忆旧值或自行更改；资料不足时说明缺口，不要编造小说章节事件。"
    ),
    STAGE_RUNTIME_CONTRACT_PROMPT: (
        "数据来源：\"已确认创作配置\"是规格参数的唯一来源；\"配置章节事件\"是原著事实的"
        "唯一来源；以上数据已在运行时上下文中注入完整，直接依据其创作。\n"
        "硬性约束：章节范围、集数、单集时长、平台规格和付费策略必须严格匹配已确认创作配置；"
        "不得凭记忆编造章节事件、人物关系或情节因果。\n"
        "输出要求：只输出可直接写入右侧「{stage_label}」工作区的 Markdown 正文，"
        "不要输出确认语、工具调用说明、执行日志或代码栅栏包裹；"
        "输出必须聚焦{stage_label}，不要把其他阶段正文混入本阶段。"
    ),
}

_REGISTRY: PromptRegistry | None = None


def script_prompt_registry(config: Settings | None = None) -> PromptRegistry:
    """返回 data/script 提示词注册表（模块级缓存）。"""
    global _REGISTRY
    if _REGISTRY is None or config is not None:
        registry = PromptRegistry(script_prompts_root_path(config))
        if config is not None:
            return registry
        _REGISTRY = registry
    return _REGISTRY


def load_script_prompt(name: str, *, registry: PromptRegistry | None = None) -> str:
    """加载工具提示词；文件缺失或为空时回退内置兜底文本。"""
    prompt_registry = registry or script_prompt_registry()
    try:
        return prompt_registry.skill(name)
    except PromptRegistryError:
        return SCRIPT_PROMPT_FALLBACKS.get(name, "")


def stage_runtime_contract(stage_label: str, *, registry: PromptRegistry | None = None) -> str:
    """阶段提示词的工具/约束/输出契约段；{stage_label} 占位符替换为阶段名。"""
    template = load_script_prompt(STAGE_RUNTIME_CONTRACT_PROMPT, registry=registry)
    return template.replace("{stage_label}", stage_label)


def apply_tool_descriptions(
    tools: list[Callable[..., Any]],
    *,
    registry: PromptRegistry | None = None,
) -> list[Callable[..., Any]]:
    """按函数名从 data/script/tools/ 加载工具描述并覆盖 docstring。

    docstring 是 Agent 运行时暴露给模型的工具描述，外置后可在 web 端编辑。
    """
    for tool in tools:
        description = load_script_prompt(tool.__name__, registry=registry)
        if description:
            tool.__doc__ = description
    return tools