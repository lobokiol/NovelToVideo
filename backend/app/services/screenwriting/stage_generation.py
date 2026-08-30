"""阶段化生成主链路：阶段计划解析、阶段提示词拼装、输出清洗与完成标记。

skeleton → strategy → script 按 STAGE_PREREQUISITES 强制顺序；请求缺前置阶段时
自动回退为生成缺失阶段并在调度文案中告知。script 阶段按 EP 逐集生成，单集
失败重试耗尽后转入"回滚 + 人工确认补全"闭环。本模块只做纯逻辑，模型调用与
事件编排由 chat 模块承担。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.prompt_registry import PromptRegistry, PromptRegistryError
from app.services.screenwriting.constants import (
    STAGE_ORDER,
    STAGE_PREREQUISITES,
    STAGE_PROMPT_SECTION_MAX_CHARS,
    STAGE_SKILL_PROMPTS,
    WORKFLOW_BASIC_INFO_CONFIRMED,
    WORKFLOW_COMPLETED_STAGE,
    WORKFLOW_PENDING_SCRIPT_REPAIR,
    WORKFLOW_PROJECT_CONFIG,
    WORKFLOW_STAGE_SOURCE,
)
from app.services.screenwriting.project_config import (
    detect_stage_generation_request,
    format_project_config,
    parse_source_chapter_range,
)
from app.services.screenwriting.quality import (
    episode_heading_number,
    iter_episode_blocks,
    parse_episode_duration_minutes,
)
from app.services.screenwriting.state import (
    ScreenwritingSessionState,
    ScreenwritingWorkspace,
    stage_label,
)
from app.services.screenwriting.tool_prompts import stage_runtime_contract
from app.utils.time_tools import utc_now


SCRIPT_REPAIR_CONFIRM_TOKENS: tuple[str, ...] = (
    "确认",
    "需要",
    "补全",
    "继续",
    "修复",
    "ok",
    "yes",
)
SCRIPT_REPAIR_DECLINE_TOKENS: tuple[str, ...] = (
    "不需要",
    "不用",
    "取消",
    "放弃",
    "否",
    "no",
)

_EPISODE_RANGE_RE = re.compile(r"(?:EP\s*0?(\d+)\s*[-—到至]\s*EP\s*0?(\d+))|(?:第\s*(\d+)\s*[-—到至]\s*(\d+)\s*集)", re.IGNORECASE)
_EPISODE_SINGLE_RE = re.compile(r"(?:EP\s*0?(\d+))|(?:第\s*(\d+)\s*集)", re.IGNORECASE)
_TOTAL_EPISODES_RE = re.compile(r"(\d+)\s*集")


@dataclass(frozen=True)
class StageGenerationPlan:
    """单次阶段生成执行计划。

    stage 是实际生成的阶段；blocked_stage 非空表示用户请求的阶段因缺前置
    被闸门回退；script 阶段 episode_numbers 为本次逐集生成的目标集号；
    repair 为真时表示这是用户确认后的单集截断修复轮。
    """

    stage: str
    requested_stage: str
    stage_message: str
    dispatch_reply: str
    blocked_stage: str | None = None
    episode_numbers: tuple[int, ...] = ()
    repair: bool = False
    repair_failure: str = ""
    repair_failed_output: str = ""


def resolve_stage_generation(
    state: ScreenwritingSessionState,
    message: str,
) -> StageGenerationPlan | None:
    """解析阶段生成请求；未确认配置或非阶段请求时返回 None 走普通对话。"""
    if state.workflow.get(WORKFLOW_BASIC_INFO_CONFIRMED) is not True:
        return None
    requested_stage = detect_stage_generation_request(message)
    if requested_stage is None:
        return None

    missing_stage = _missing_prerequisite_stage(state.workspace, requested_stage)
    if missing_stage is None:
        return StageGenerationPlan(
            stage=requested_stage,
            requested_stage=requested_stage,
            stage_message=message,
            dispatch_reply=f"当前调度{stage_label(requested_stage)}助理进行创作中...",
            episode_numbers=(
                resolve_script_episode_numbers(state, message)
                if requested_stage == "script"
                else ()
            ),
        )
    return StageGenerationPlan(
        stage=missing_stage,
        requested_stage=requested_stage,
        stage_message=(
            f"用户原始需求：{message}\n\n"
            f"固定流程缺少{stage_label(missing_stage)}，不能直接生成{stage_label(requested_stage)}。"
            f"请先作为{stage_label(missing_stage)}助理补齐该阶段内容；"
            f"输出必须服务于后续{stage_label(requested_stage)}生成。"
        ),
        dispatch_reply=(
            f"为了按固定流程推进，当前还缺少{stage_label(missing_stage)}，"
            f"我会先补齐{stage_label(missing_stage)}。"
            f"当前调度{stage_label(missing_stage)}助理进行创作中..."
        ),
        blocked_stage=requested_stage,
    )


def resolve_script_repair_dialog(
    state: ScreenwritingSessionState,
    message: str,
) -> StageGenerationPlan | str | None:
    """处理待确认的剧本单集修复：返回修复计划、拒绝直答文案或 None（继续正常流）。"""
    pending = load_pending_script_repair(state)
    if pending is None:
        return None
    if is_script_repair_decline(message):
        clear_pending_script_repair(state)
        return "已保留当前剧本草案内容。你可以直接在工作区手动编辑，或重新发起剧本生成。"
    if not is_script_repair_confirmation(message):
        return None

    episode_no = max(1, int(pending.get("episodeNo", 1) or 1))
    remaining = tuple(
        int(number)
        for number in (pending.get("remainingEpisodeNumbers") or [])
        if int(number) > 0
    )
    return StageGenerationPlan(
        stage="script",
        requested_stage="script",
        stage_message=str(pending.get("stageMessage") or message),
        dispatch_reply=f"已确认补全 EP{episode_no:02d}，当前调度剧本单步修复助理进行创作中...",
        episode_numbers=(episode_no, *remaining),
        repair=True,
        repair_failure=str(pending.get("failure") or ""),
        repair_failed_output=str(pending.get("failedOutput") or ""),
    )


def build_stage_system_prompt(
    stage: str,
    state: ScreenwritingSessionState,
    *,
    stage_message: str,
    rag_text: str,
    chapter_events: list[dict] | tuple[dict, ...] = (),
    registry: PromptRegistry | None = None,
) -> str:
    """拼装阶段子 Agent 系统提示词：技能提示词 + 运行时上下文 + 硬性约束。

    创作配置与配置范围内的章节事件直接注入提示词，阶段生成为纯文本输出，
    不依赖运行中工具调用（模型网关流式通道不透传工具调用增量）。
    """
    skill_prompt = _load_stage_skill_prompt(stage, registry)
    config_block = (
        format_project_config(state.workflow.get(WORKFLOW_PROJECT_CONFIG))
        or "- 尚未确认创作配置。"
    )
    workspace_context = format_stage_workspace_context(state.workspace, stage)
    rag_block = _truncate_stage_prompt_section(rag_text) if rag_text.strip() else "（本轮未命中项目资料）"
    events_block = format_configured_chapter_events(state, chapter_events)
    return (
        f"{skill_prompt}\n\n"
        "## 运行时上下文\n"
        f"已确认创作配置：\n{config_block}\n"
        f"用户原始需求：{stage_message}\n"
        f"{workspace_context}\n"
        f"相关项目资料（RAG 命中）：\n{rag_block}\n"
        f"配置章节事件：\n{events_block}\n\n"
        f"{stage_runtime_contract(stage_label(stage))}"
    )


def format_configured_chapter_events(
    state: ScreenwritingSessionState,
    chapter_events: list[dict] | tuple[dict, ...],
) -> str:
    """把创作配置原著范围内的章节事件压缩注入提示词。"""
    if not chapter_events:
        return "（当前项目尚无可用章节事件）"
    chapter_range = parse_source_chapter_range(
        (state.workflow.get(WORKFLOW_PROJECT_CONFIG) or {}).get("sourceRange", "")
        if isinstance(state.workflow.get(WORKFLOW_PROJECT_CONFIG), dict)
        else ""
    )
    lines: list[str] = []
    for event in chapter_events:
        chapter_index = int(event.get("chapterIndex", 0) or 0)
        if chapter_range is not None and not (chapter_range[0] <= chapter_index <= chapter_range[1]):
            continue
        title = str(event.get("chapterTitle", "") or "").strip()
        payload = re.sub(r"\s+", " ", str(event.get("event", "") or "")).strip()
        lines.append(f"- 第{chapter_index}章《{title}》：{payload}")
    if not lines:
        return "（创作配置的原著范围内没有可用章节事件，请提示用户调整范围或补充事件提取）"
    return _truncate_stage_prompt_section("\n".join(lines))


def clean_stage_output(content: str) -> str:
    """清洗阶段输出：剥离首尾 Markdown 代码栅栏包裹。"""
    text = (content or "").strip()
    lines = text.splitlines()
    if len(lines) < 2:
        return text
    opening = lines[0].strip()
    closing = lines[-1].strip()
    if not (opening.startswith("```") and closing == "```"):
        return text
    language = opening[3:].strip().lower()
    if language not in {"", "markdown", "md"}:
        return text
    inner = "\n".join(lines[1:-1]).strip()
    return inner or text


def mark_stage_completed(
    state: ScreenwritingSessionState,
    stage: str,
    *,
    source: str = "generated",
) -> None:
    """标记阶段完成并记录产出来源。"""
    state.workflow[WORKFLOW_COMPLETED_STAGE] = stage
    stage_source = state.workflow.get(WORKFLOW_STAGE_SOURCE)
    if not isinstance(stage_source, dict):
        stage_source = {}
    stage_source[stage] = source
    state.workflow[WORKFLOW_STAGE_SOURCE] = stage_source
    state.updated_at = utc_now()


def stage_completion_reply(plan: StageGenerationPlan) -> str:
    """阶段完成后的对话区收尾文案。"""
    label = stage_label(plan.stage)
    if plan.blocked_stage and plan.blocked_stage != plan.stage:
        return (
            f"{label}已生成并同步到右侧「{label}」。"
            f"这是按固定流程补齐的前置阶段；确认内容后，"
            f"请再次发起「{stage_label(plan.blocked_stage)}」，我会继续推进。"
        )
    next_stage = _next_stage_after(plan.stage)
    if next_stage is None:
        return f"{label}已生成并同步到右侧「{label}」。你可以直接在工作区查看与编辑。"
    return (
        f"{label}已生成并同步到右侧「{label}」。你可以直接在工作区编辑；"
        f"满意后告诉我「生成{stage_label(next_stage)}」，我会继续推进。"
    )


def _missing_prerequisite_stage(workspace: ScreenwritingWorkspace, requested_stage: str) -> str | None:
    for prerequisite in STAGE_PREREQUISITES.get(requested_stage, ()):
        if not getattr(workspace, prerequisite, "").strip():
            return prerequisite
    return None


def _next_stage_after(stage: str) -> str | None:
    try:
        index = STAGE_ORDER.index(stage)
    except ValueError:
        return None
    next_index = index + 1
    return STAGE_ORDER[next_index] if next_index < len(STAGE_ORDER) else None


def _load_stage_skill_prompt(stage: str, registry: PromptRegistry | None) -> str:
    prompt_registry = registry or PromptRegistry.from_settings()
    skill_name = STAGE_SKILL_PROMPTS.get(stage, "")
    if skill_name:
        try:
            return prompt_registry.skill(skill_name)
        except PromptRegistryError:
            pass
    label = stage_label(stage)
    return (
        f"你是剧本创作流程中的「{label}助理」，只负责基于已确认创作配置和小说章节事件，"
        f"生成可写入「{label}」工作区的 Markdown 正文。"
        "必须依据创作配置与章节事件创作，不得虚构原著事实。"
    )


def format_stage_workspace_context(workspace: ScreenwritingWorkspace, stage: str) -> str:
    if stage == "skeleton":
        sections = (("当前故事骨架", workspace.skeleton),)
    elif stage == "strategy":
        sections = (
            ("当前故事骨架", workspace.skeleton),
            ("当前改编策略", workspace.strategy),
        )
    else:
        sections = (
            ("当前故事骨架", workspace.skeleton),
            ("当前改编策略", workspace.strategy),
            ("当前剧本草案", workspace.script),
        )
    return "\n".join(
        f"{label}：\n{_truncate_stage_prompt_section(content)}"
        for label, content in sections
    )


def _truncate_stage_prompt_section(
    content: str,
    *,
    max_chars: int = STAGE_PROMPT_SECTION_MAX_CHARS,
) -> str:
    text = (content or "").strip()
    if not text:
        return "空"
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return (
        f"{text[:max_chars].rstrip()}\n\n"
        f"（以上内容已截断，省略 {omitted} 字；如需完整内容，请通过 get_workspace 工具读取。）"
    )


# ---------------------------------------------------------------------------
# 自修复指令
# ---------------------------------------------------------------------------


def build_stage_repair_message(
    stage: str,
    *,
    stage_message: str,
    failure_reason: str,
    failed_output: str,
) -> str:
    """构造单步自修复指令：原始需求 + 失败原因 + 修复要求 + 不合格全文。"""
    label = stage_label(stage)
    script_requirements = ""
    if stage == "script":
        script_requirements = (
            "- 保留既有 EP 编号与场次编号，逐场重写不合格内容；\n"
            "- 每场至少 4 段以 △ 开头的动作描写，并补齐 `时长：Xs` 标记；\n"
            "- 不得在半句、半段动作或未闭合场次处停止；\n"
            "- 每集结尾必须有转场标记或集尾钩子。\n"
        )
    return (
        f"用户原始需求：{stage_message}\n\n"
        f"上一轮{label}产出未通过质量校验，失败原因：{failure_reason}\n\n"
        "自修复要求：\n"
        f"- 在保留合格部分的前提下，针对失败原因完整重写{label}正文；\n"
        "- 只输出修复后的完整 Markdown 正文，不要输出修复说明或对比；\n"
        f"{script_requirements}\n"
        f"上一轮不合格全文：\n{_truncate_stage_prompt_section(failed_output)}"
    )


# ---------------------------------------------------------------------------
# script 阶段逐集生成
# ---------------------------------------------------------------------------


def resolve_script_episode_numbers(
    state: ScreenwritingSessionState,
    message: str,
) -> tuple[int, ...]:
    """解析本次剧本生成的目标集号。

    优先级：用户显式区间/单集（明确指定即允许重写对应已有集）>
    创作配置总集数内的"缺失集"（已有集绝不静默重写）> 兜底 EP01。
    返回空元组表示配置范围内已无缺失集，由调用方直答引导用户显式指定。
    """
    text = (message or "").strip()
    range_match = _EPISODE_RANGE_RE.search(text)
    if range_match:
        groups = [group for group in range_match.groups() if group]
        start, end = int(groups[0]), int(groups[1])
        if start > end:
            start, end = end, start
        if start > 0:
            return tuple(range(start, end + 1))
    singles = sorted(
        {
            int(match.group(1) or match.group(2))
            for match in _EPISODE_SINGLE_RE.finditer(text)
            if int(match.group(1) or match.group(2)) > 0
        }
    )
    if singles:
        return tuple(singles)

    existing_numbers = {number for number, _ in iter_episode_blocks(state.workspace.script)}
    config = state.workflow.get(WORKFLOW_PROJECT_CONFIG)
    if isinstance(config, dict):
        total_match = _TOTAL_EPISODES_RE.search(str(config.get("totalEpisodes", "")))
        if total_match:
            total = int(total_match.group(1))
            if total > 0:
                return tuple(
                    number for number in range(1, total + 1) if number not in existing_numbers
                )
    return (1,) if 1 not in existing_numbers else ()


def configured_episode_duration_minutes(state: ScreenwritingSessionState) -> int:
    """从创作配置读取单集时长（分钟），未配置返回 0。"""
    config = state.workflow.get(WORKFLOW_PROJECT_CONFIG)
    if not isinstance(config, dict):
        return 0
    return parse_episode_duration_minutes(config.get("episodeDuration"))


def script_episode_message(
    stage_message: str,
    episode_no: int,
    *,
    duration_minutes: int,
) -> str:
    """构造单集生成任务消息：原始需求 + 本集硬指令。"""
    duration_line = ""
    if duration_minutes > 0:
        duration_line = (
            f"- 标题下一行必须写 `# 目标时长：{duration_minutes}分钟 ≈ {duration_minutes * 60}s`，"
            "所有场次 `时长：Xs` 合计须接近该目标；\n"
        )
    return (
        f"{stage_message}\n\n"
        f"本次仅生成 EP{episode_no:02d}，不得生成其他 EP：\n"
        f"- 输出必须以 `# 项目名 EP{episode_no:02d}：单集标题` 或 `## 第{episode_no}集 标题` 开头；\n"
        f"{duration_line}"
        "- 每场至少 4 段以 △ 开头的动作描写，场次之间用单独一行 `---` 分割；\n"
        "- 集尾必须有明确悬念、转场标记或付费钩子；不得输出剧情概述或分集大纲。"
    )


def merge_script_episode_blocks(
    existing_script: str,
    incoming_script: str,
    *,
    target_episode_numbers: tuple[int, ...],
) -> str:
    """按集合并剧本：incoming 中只有目标集会覆盖同号旧集（污染隔离）。"""
    existing_blocks = iter_episode_blocks(existing_script)
    incoming_blocks = iter_episode_blocks(incoming_script)
    if existing_blocks and not incoming_blocks:
        return existing_script.strip()
    if not existing_blocks or not incoming_blocks:
        return incoming_script.strip()

    targets = set(target_episode_numbers)
    existing_by_no = {number: block.strip() for number, block in existing_blocks}
    incoming_by_no = {
        number: block.strip()
        for number, block in incoming_blocks
        if number in targets
    }
    if not incoming_by_no:
        return existing_script.strip()

    merged_numbers = sorted(set(existing_by_no) | set(incoming_by_no))
    return "\n\n---\n\n".join(
        _strip_trailing_separator(incoming_by_no.get(number) or existing_by_no[number])
        for number in merged_numbers
        if incoming_by_no.get(number) or existing_by_no.get(number)
    ).strip()


def _strip_trailing_separator(block: str) -> str:
    lines = block.rstrip().splitlines()
    while lines and re.match(r"^\s*(-{3,}|\*{3,}|_{3,}|={3,})\s*$", lines[-1]):
        lines.pop()
    return "\n".join(lines).rstrip()


def script_block_matches_episode(content: str, episode_no: int) -> bool:
    """检查产出首个 EP 标题是否为目标集（防串集）。"""
    for line in (content or "").splitlines():
        number = episode_heading_number(line)
        if number is not None:
            return number == episode_no
    return False


# ---------------------------------------------------------------------------
# script 截断修复人工确认闭环
# ---------------------------------------------------------------------------


def save_pending_script_repair(
    state: ScreenwritingSessionState,
    *,
    failure_reason: str,
    failed_output: str,
    stage_message: str,
    episode_no: int,
    remaining_episode_numbers: tuple[int, ...],
) -> None:
    """记录剧本单集修复确认状态，等待用户确认或放弃。"""
    state.workflow[WORKFLOW_PENDING_SCRIPT_REPAIR] = {
        "failure": failure_reason,
        "failedOutput": failed_output,
        "stageMessage": stage_message,
        "episodeNo": int(episode_no),
        "remainingEpisodeNumbers": [int(number) for number in remaining_episode_numbers],
        "createdAt": utc_now().isoformat(),
    }
    state.updated_at = utc_now()


def load_pending_script_repair(state: ScreenwritingSessionState) -> dict | None:
    payload = state.workflow.get(WORKFLOW_PENDING_SCRIPT_REPAIR)
    return payload if isinstance(payload, dict) else None


def clear_pending_script_repair(state: ScreenwritingSessionState) -> None:
    state.workflow.pop(WORKFLOW_PENDING_SCRIPT_REPAIR, None)
    state.updated_at = utc_now()


def is_script_repair_confirmation(message: str) -> bool:
    text = message.strip().lower()
    if not text:
        return False
    if any(token in text for token in SCRIPT_REPAIR_DECLINE_TOKENS):
        return False
    return any(token in text for token in SCRIPT_REPAIR_CONFIRM_TOKENS)


def is_script_repair_decline(message: str) -> bool:
    text = message.strip().lower()
    return bool(text) and any(token in text for token in SCRIPT_REPAIR_DECLINE_TOKENS)


def script_repair_confirmation_prompt(failure_reason: str, episode_no: int) -> str:
    return (
        f"EP{episode_no:02d} 经多次自动修复仍未通过质量校验：{failure_reason}\n\n"
        "当前已保留通过校验的集与本集的最新尝试稿。是否需要我重新补充完整该集的"
        "动作、对白、转场或集尾钩子？回复「确认」继续修复，回复「不需要」保留当前草案。"
    )