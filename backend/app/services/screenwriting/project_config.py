"""剧本创作配置链路：草拟、抽取更新、查询应答与确认锁定。

创作配置（集数/单集时长/原著范围/平台规格/风格定位/付费策略）持久化在会话
workflow JSON 中，是后续故事骨架、改编策略与剧本生成阶段的唯一约束来源。
解析全部为确定性规则（正则 + 关键词），不依赖模型调用，保证低延迟与可测试性。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.screenwriting.constants import (
    GENERATION_KEYWORDS,
    STAGE_KEYWORDS,
    STAGE_ORDER,
    WORKFLOW_BASIC_INFO_CONFIRMED,
    WORKFLOW_PENDING_CONFIG_CHANGE,
    WORKFLOW_PENDING_STAGE,
    WORKFLOW_PENDING_STAGE_MESSAGE,
    WORKFLOW_PROJECT_CONFIG,
)
from app.services.screenwriting.state import (
    ScreenwritingSessionState,
    stage_label,
)
from app.utils.time_tools import utc_now


CONFIRMATION_TOKENS: tuple[str, ...] = (
    "确认",
    "可以",
    "按以上",
    "按这个",
    "就这样",
    "同意",
    "开始",
    "继续",
    "ok",
    "okay",
    "yes",
    "confirm",
)

STYLE_TOKENS: tuple[str, ...] = ("爽剧", "甜宠", "复仇", "悬疑", "权谋", "都市", "古装")

CONFIG_FIELD_ROWS: tuple[tuple[str, str], ...] = (
    ("剧本集数", "totalEpisodes"),
    ("单集时长", "episodeDuration"),
    ("原著范围", "sourceRange"),
    ("平台规格", "platformSpec"),
    ("风格定位", "style"),
    ("付费策略", "paywall"),
)


@dataclass(frozen=True)
class ProjectConfigDialogResult:
    """配置链路分流结果。

    reply 非空表示本轮由配置链路直接应答（不进入模型）；
    proceed_message 非空表示配置已确认，应以该消息继续正常 Agent 链路。
    """

    reply: str = ""
    proceed_message: str = ""


def draft_project_config(chapter_index_range: tuple[int, int] | None) -> dict[str, str]:
    """根据项目章节事件范围草拟默认创作配置。"""
    if chapter_index_range is not None:
        source_range = f"第{chapter_index_range[0]}-{chapter_index_range[1]}章"
    else:
        source_range = "待确认（当前项目尚无可用章节事件）"
    return {
        "totalEpisodes": "24集，可按你的目标调整",
        "episodeDuration": "2分钟/集，可按平台规格调整",
        "sourceRange": source_range,
        "platformSpec": "竖屏短剧优先，可改为横屏或其他规格",
        "style": "由故事骨架阶段结合小说事件细化，可指定爽剧、甜宠、复仇等方向",
        "paywall": "前3集免费，第4集起设置付费点，可按平台策略调整",
    }


def ensure_project_config(
    state: ScreenwritingSessionState,
    chapter_index_range: tuple[int, int] | None = None,
) -> dict[str, str]:
    """读取（必要时草拟并写入）当前创作配置。"""
    config = state.workflow.get(WORKFLOW_PROJECT_CONFIG)
    if not isinstance(config, dict):
        config = draft_project_config(chapter_index_range)
        state.workflow[WORKFLOW_PROJECT_CONFIG] = config
        state.updated_at = utc_now()
    return config


_EPISODE_ORDINAL_RE = re.compile(r"(?:第|前|后|最后|头)\s*\d+\s*(?:[-—到至]\s*\d+\s*)?集")


def _extract_total_episodes(text: str) -> int | None:
    """抽取总集数。

    先剔除"第N集/前N集/第N-M集"等剧情序数引用，再抽取剩余文本里的"N集"，
    避免把剧情讨论中的集号误判为总集数配置（如"把第6集那段加戏"不应改动集数）。
    """
    cleaned = _EPISODE_ORDINAL_RE.sub("", text)
    match = re.search(r"(\d+)\s*集", cleaned)
    return int(match.group(1)) if match else None


def compute_config_changes(
    current: object,
    message: str,
    chapter_index_range: tuple[int, int] | None = None,
) -> dict[str, str]:
    """从用户发言确定性抽取配置字段，仅返回与当前值不同的变更（不写入 state）。

    供"拟变更 → 二次确认"写保护链路与即时更新共用，确保配置只在用户明文确认时改动。
    """
    current_config = current if isinstance(current, dict) else {}
    text = message.strip()
    candidate: dict[str, str] = {}

    episodes = _extract_total_episodes(text)
    if episodes is not None:
        candidate["totalEpisodes"] = f"{episodes}集"

    duration_match = re.search(r"(\d+)\s*分钟", text)
    if duration_match:
        candidate["episodeDuration"] = f"{duration_match.group(1)}分钟/集"

    range_match = re.search(r"第?\s*(\d+)\s*[-—到至]\s*(\d+)\s*章", text)
    if range_match:
        candidate["sourceRange"] = f"第{range_match.group(1)}-{range_match.group(2)}章"

    platform_spec = _extract_platform_spec(text)
    if platform_spec:
        candidate["platformSpec"] = platform_spec

    style_tokens = [token for token in STYLE_TOKENS if token in text]
    if style_tokens:
        candidate["style"] = "、".join(style_tokens)

    if "免费" in text or "付费" in text:
        candidate["paywall"] = _extract_labeled_config_value(text, ("付费策略", "付费", "免费")) or text

    return {key: value for key, value in candidate.items() if current_config.get(key) != value}


def update_project_config_from_message(
    state: ScreenwritingSessionState,
    message: str,
    chapter_index_range: tuple[int, int] | None = None,
) -> dict[str, str]:
    """从用户发言抽取配置项并即时合并到当前配置（用于抽屉草案等已明确场景）。"""
    config = ensure_project_config(state, chapter_index_range)
    changes = compute_config_changes(config, message, chapter_index_range)
    updated = dict(config)
    updated.update(changes)
    updated["lastUserAdjustment"] = message.strip()
    state.workflow[WORKFLOW_PROJECT_CONFIG] = updated
    state.updated_at = utc_now()
    return updated


def apply_config_settings(
    state: ScreenwritingSessionState,
    *,
    total_episodes: int | None = None,
    episode_duration: int | None = None,
    source_start: int | None = None,
    source_end: int | None = None,
    platform_spec: str | None = None,
    style: str | None = None,
    paywall: str | None = None,
    chapter_index_range: tuple[int, int] | None = None,
) -> dict[str, str]:
    """保存结构化创作配置并立即锁定（basicInfoConfirmed=True）。

    供创作配置面板"保存创作设置"使用：用户在表单中明文填写并保存,即作为本会话
    权威配置锁定——AI 只读不写、各阶段严格遵循,无需用户再在对话中回复确认。
    仅写入用户填写项,并清除待确认的阶段与配置变更标记。
    """
    config = dict(ensure_project_config(state, chapter_index_range))
    if total_episodes and int(total_episodes) > 0:
        config["totalEpisodes"] = f"{int(total_episodes)}集"
    if episode_duration and int(episode_duration) > 0:
        config["episodeDuration"] = f"{int(episode_duration)}分钟/集"
    if source_start and source_end and int(source_start) > 0 and int(source_end) > 0:
        start, end = sorted((int(source_start), int(source_end)))
        config["sourceRange"] = f"第{start}-{end}章"
    if platform_spec and platform_spec.strip():
        config["platformSpec"] = platform_spec.strip()
    if style and style.strip():
        config["style"] = style.strip()
    if paywall and paywall.strip():
        config["paywall"] = paywall.strip()
    config["lastUserAdjustment"] = "通过创作配置面板保存"
    state.workflow[WORKFLOW_PROJECT_CONFIG] = config
    state.workflow[WORKFLOW_BASIC_INFO_CONFIRMED] = True
    state.workflow["basicInfoConfirmation"] = "通过创作配置面板保存并锁定"
    state.workflow.pop(WORKFLOW_PENDING_STAGE, None)
    state.workflow.pop(WORKFLOW_PENDING_STAGE_MESSAGE, None)
    state.workflow.pop(WORKFLOW_PENDING_CONFIG_CHANGE, None)
    state.updated_at = utc_now()
    return config


def apply_pending_config_change(state: ScreenwritingSessionState) -> dict[str, str]:
    """把待确认配置变更合并进正式配置并清除暂存；无暂存时原样返回当前配置。"""
    config = state.workflow.get(WORKFLOW_PROJECT_CONFIG)
    config = dict(config) if isinstance(config, dict) else {}
    pending = state.workflow.get(WORKFLOW_PENDING_CONFIG_CHANGE)
    if isinstance(pending, dict) and pending:
        config.update(pending)
        state.workflow[WORKFLOW_PROJECT_CONFIG] = config
    state.workflow.pop(WORKFLOW_PENDING_CONFIG_CHANGE, None)
    state.updated_at = utc_now()
    return config


def format_pending_config_change(current: object, changes: dict[str, str]) -> str:
    """逐字段渲染"旧值 → 新值"，供配置变更二次确认回显。"""
    current_config = current if isinstance(current, dict) else {}
    label_by_key = {key: label for label, key in CONFIG_FIELD_ROWS}
    lines = []
    for key, new_value in changes.items():
        label = label_by_key.get(key, key)
        old_value = current_config.get(key) or "未设置"
        lines.append(f"- {label}：{old_value} → {new_value}")
    return "\n".join(lines)


def format_project_config(config: object) -> str:
    """把配置渲染为面向用户的清单文本。"""
    if not isinstance(config, dict):
        return ""
    return "\n".join(
        f"- {label}：{config.get(key, '')}"
        for label, key in CONFIG_FIELD_ROWS
        if config.get(key, "")
    )


def parse_source_chapter_range(value: object) -> tuple[int, int] | None:
    """解析"第X-Y章"形式的原著范围；解析失败返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"第?\s*(\d+)\s*[-—到至]\s*(\d+)\s*章", text)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if start > end:
        start, end = end, start
    return start, end


_EXPLICIT_STAGE_DIRECTIVE_RE = re.compile(
    r"^(?:请)?(?:重新)?(?:生成|梳理|制定|创作|撰写|输出)\s*(故事骨架|改编策略|剧本草案|骨架|策略|剧本)"
)
_STAGE_BY_DIRECTIVE_LABEL: dict[str, str] = {
    "故事骨架": "skeleton",
    "骨架": "skeleton",
    "改编策略": "strategy",
    "策略": "strategy",
    "剧本草案": "script",
    "剧本": "script",
}


def detect_stage_generation_request(message: str) -> str | None:
    """识别指向某个创作阶段的生成请求。

    消息以"请重新生成故事骨架"等显式指令开头时直接锁定该阶段——
    评估改进提示词等长消息的正文常包含其他阶段关键词，不得污染路由。
    其余情况（如"结合故事骨架，提出改编策略"）意图阶段出现在句尾，
    按关键词最后出现位置取最靠后的阶段。
    """
    text = message.strip()
    if not text:
        return None

    directive_match = _EXPLICIT_STAGE_DIRECTIVE_RE.match(text)
    if directive_match:
        return _STAGE_BY_DIRECTIVE_LABEL.get(directive_match.group(1))

    lowered = text.lower()
    if not any(keyword in lowered for keyword in GENERATION_KEYWORDS):
        return None
    best_stage: str | None = None
    best_position = -1
    for stage, keywords in STAGE_KEYWORDS:
        position = max(
            (lowered.rfind(keyword) for keyword in keywords if keyword in lowered),
            default=-1,
        )
        if position > best_position:
            best_position = position
            best_stage = stage
    return best_stage


def is_basic_info_confirmation(message: str) -> bool:
    text = message.strip().lower()
    if not text:
        return False
    return any(token in text for token in CONFIRMATION_TOKENS)


def resolve_project_config_dialog(
    state: ScreenwritingSessionState,
    message: str,
    chapter_index_range: tuple[int, int] | None = None,
) -> ProjectConfigDialogResult | None:
    """配置链路总分流：返回 None 表示与配置无关，走正常 Agent 链路。

    创作配置只能由用户在配置面板（⚙）设置并保存——保存即锁定，AI 只读不写、
    各阶段严格遵循；对话内不再用草案默认值确认锁定。

    分流顺序：
    0. 存在待确认配置变更（对已锁定配置的对话内微调）：确认 → 应用；
       给出新修改 → 重算再请确认；无关消息 → 放弃暂存后继续。
    1. 阶段生成请求且未锁定：引导用户去配置面板设置（不在对话内确认草案）。
    2. 配置更新请求：未锁定 → 引导去面板；已锁定 → 暂存变更并请确认。
    3. 配置查询请求：回显配置或单字段。
    """
    text = message.strip()
    if not text:
        return None

    confirmed = state.workflow.get(WORKFLOW_BASIC_INFO_CONFIRMED) is True
    current_config = state.workflow.get(WORKFLOW_PROJECT_CONFIG)

    pending_change = state.workflow.get(WORKFLOW_PENDING_CONFIG_CHANGE)
    if isinstance(pending_change, dict) and pending_change:
        if is_basic_info_confirmation(text):
            apply_pending_config_change(state)
            return ProjectConfigDialogResult(
                reply=(
                    "已更新当前项目创作配置：\n"
                    f"{format_project_config(state.workflow.get(WORKFLOW_PROJECT_CONFIG))}"
                )
            )
        new_changes = compute_config_changes(current_config, text, chapter_index_range)
        if new_changes:
            merged = {**pending_change, **new_changes}
            state.workflow[WORKFLOW_PENDING_CONFIG_CHANGE] = merged
            state.updated_at = utc_now()
            return ProjectConfigDialogResult(reply=_pending_change_prompt(current_config, merged))
        # 与配置无关：放弃未确认的变更，继续后续分流。
        state.workflow.pop(WORKFLOW_PENDING_CONFIG_CHANGE, None)
        state.updated_at = utc_now()

    requested_stage = detect_stage_generation_request(text)
    if requested_stage is not None:
        if confirmed:
            return None
        # 配置必须由用户在配置面板设置并锁定，不在对话内用草案确认。
        return ProjectConfigDialogResult(reply=_config_setup_required_prompt(requested_stage))

    if _is_project_config_update_request(text):
        if not confirmed:
            # 未锁定时一律引导去配置面板设置（保存即锁定），不在对话内改草案。
            return ProjectConfigDialogResult(reply=_config_setup_required_prompt(None))
        changes = compute_config_changes(current_config, text, chapter_index_range)
        if not changes:
            return None
        state.workflow[WORKFLOW_PENDING_CONFIG_CHANGE] = changes
        state.updated_at = utc_now()
        return ProjectConfigDialogResult(reply=_pending_change_prompt(current_config, changes))

    if _is_project_config_lookup_request(text):
        config = ensure_project_config(state, chapter_index_range)
        field = _project_config_field_from_message(text)
        if field is not None:
            label, key = field
            value = config.get(key) or "未设置"
            return ProjectConfigDialogResult(reply=f"当前项目配置的「{label}」是：{value}。")
        prefix = "当前项目创作配置如下："
        if not confirmed:
            prefix = "当前项目创作配置尚未设置，建议先在配置面板设置后开始创作。当前草案如下："
        return ProjectConfigDialogResult(reply=f"{prefix}\n{format_project_config(config)}")

    return None


def confirm_basic_info(state: ScreenwritingSessionState, message: str) -> None:
    """锁定创作配置并清理待确认阶段标记。"""
    state.workflow[WORKFLOW_BASIC_INFO_CONFIRMED] = True
    state.workflow["basicInfoConfirmation"] = message.strip()
    state.workflow.pop(WORKFLOW_PENDING_STAGE, None)
    state.workflow.pop(WORKFLOW_PENDING_STAGE_MESSAGE, None)
    state.updated_at = utc_now()


def message_contains_project_config_hint(message: str) -> bool:
    """判断发言是否包含可抽取的配置要素。"""
    text = message.strip()
    if not text:
        return False
    if re.search(r"第?\s*\d+\s*[-—到至]\s*\d+\s*章", text):
        return True
    if _extract_total_episodes(text) is not None:
        return True
    if re.search(r"\d+\s*分钟", text):
        return True
    if re.search(r"(16|9)\s*[:：]\s*(9|16)", text):
        return True
    return any(
        token in text
        for token in ("横屏", "竖屏", *STYLE_TOKENS, "付费", "免费")
    )


def _config_setup_required_prompt(stage: str | None) -> str:
    """引导用户去配置面板设置创作配置（配置只能源于面板，保存即锁定）。"""
    suffix = f"；保存后再次告诉我「生成{stage_label(stage)}」即可" if stage else ""
    return (
        "创作配置需要先在配置面板中设置并保存。\n\n"
        "请点击对话框工具栏的 ⚙「创作配置」按钮，打开面板填写集数、单集时长、原著范围、"
        "平台规格、风格定位与付费策略，点「保存创作设置」即可锁定（保存即生效，我会严格遵循）"
        f"{suffix}。"
    )


def _pending_change_prompt(current: object, changes: dict[str, str]) -> str:
    return (
        "我将按你的说明调整以下创作配置项（确认后才会生效）：\n"
        f"{format_pending_config_change(current, changes)}\n\n"
        "请回复「确认」应用此变更；如需继续调整，直接告诉我新的设置。"
    )


def _is_project_config_update_request(message: str) -> bool:
    text = message.strip()
    if not text or not message_contains_project_config_hint(text):
        return False
    # 仅明确的"赋值动词"算配置修改意图；去掉"就是/采用"等过宽词，避免剧情讨论误触发。
    update_tokens = ("改为", "设为", "设成", "设置为", "调整为", "改成", "换成", "定为", "定成", "配置为")
    return any(token in text for token in update_tokens)


def _is_project_config_lookup_request(message: str) -> bool:
    text = message.strip().lower()
    if not text:
        return False
    why_tokens = ("为什么", "为何", "原因", "理由", "依据")
    if any(token in text for token in why_tokens):
        return False
    config_tokens = (
        "配置",
        "项目配置",
        "创作配置",
        "剧本基本信息",
        "平台规格",
        "平台",
        "原著范围",
        "章节范围",
        "集数",
        "单集时长",
        "风格定位",
        "付费策略",
    )
    question_tokens = ("什么", "多少", "几", "当前", "查看", "读取", "显示", "是", "?", "？")
    return any(token in text for token in config_tokens) and any(token in text for token in question_tokens)


def _project_config_field_from_message(message: str) -> tuple[str, str] | None:
    text = message.strip().lower()
    fields = (
        ("平台规格", "platformSpec", ("平台规格", "平台", "横屏", "竖屏", "16:9", "9:16")),
        ("原著范围", "sourceRange", ("原著范围", "章节范围", "范围", "章节")),
        ("集数", "totalEpisodes", ("集数", "多少集", "几集")),
        ("单集时长", "episodeDuration", ("单集时长", "时长", "分钟")),
        ("风格定位", "style", ("风格定位", "风格", "类型")),
        ("付费策略", "paywall", ("付费策略", "付费", "免费", "付费点")),
    )
    for label, key, tokens in fields:
        if any(token in text for token in tokens):
            return label, key
    return None


def _extract_platform_spec(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if "横屏" in compact:
        if re.search(r"16[:：]9|16比9", compact):
            return "16:9横屏"
        return "横屏剧集优先"
    if "竖屏" in compact:
        if re.search(r"9[:：]16|9比16", compact):
            return "9:16竖屏短剧优先"
        return "竖屏短剧优先"
    return ""


def _extract_labeled_config_value(text: str, labels: tuple[str, ...]) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*•").strip()
        if not line:
            continue
        for label in labels:
            match = re.match(rf"^{re.escape(label)}\s*[:：]\s*(.+)$", line)
            if match:
                return match.group(1).strip()
    return ""