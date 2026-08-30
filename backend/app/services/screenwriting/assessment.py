"""阶段产出质量评估：制片人视角的多维评分报告（异步流式）。

评估为只读操作（不写会话状态、不持会话锁），不阻塞聊天与工作区功能。
模型输出纯 Markdown 报告（弹窗实时流式渲染），文末以固定标记携带改进
提示词；流式转发时缓冲过滤标记后内容，done 事件携带解析后的评分与
改进提示词；解析失败时有确定性兜底，绝不报错中断。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.services.agent_gateway import ProviderModelGateway
from app.services.screenwriting.constants import STAGE_ORDER, WORKFLOW_STAGE_ASSESSMENTS
from app.services.screenwriting.errors import ScreenwritingValidationError
from app.services.screenwriting.stage_generation import (
    format_configured_chapter_events,
    format_stage_workspace_context,
)
from app.services.screenwriting.project_config import format_project_config
from app.services.screenwriting.constants import WORKFLOW_PROJECT_CONFIG
from app.services.screenwriting.state import ScreenwritingSessionState, stage_label
from app.services.screenwriting.tool_prompts import load_script_prompt
from app.utils.time_tools import utc_now


IMPROVEMENT_PROMPT_MARKER = "<!--IMPROVEMENT_PROMPT-->"
ASSESSOR_PROMPT_NAMES: dict[str, str] = {
    "skeleton": "stage_quality_assessor_skeleton",
    "strategy": "stage_quality_assessor_strategy",
    "script": "stage_quality_assessor_script",
}
_SCORE_LINE_RE = re.compile(r"\*\*(.+?)[：:]\s*(\d+(?:\.\d+)?)(?:\s*[~～-]\s*\d+(?:\.\d+)?)?\s*/\s*10\*\*")
_IMPROVEMENT_PROMPT_MAX_FALLBACK_CHARS = 2000


@dataclass(frozen=True)
class StageAssessment:
    """单次阶段评估结果。"""

    stage: str
    report: str
    scores: dict[str, float] = field(default_factory=dict)
    improvement_prompt: str = ""


def build_assessment_system_prompt(
    stage: str,
    state: ScreenwritingSessionState,
    chapter_events: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
) -> str:
    """拼装评估系统提示词：评估技能 + 创作配置 + 配置章节事件 + 工作区内容。"""
    skill_prompt = load_script_prompt(ASSESSOR_PROMPT_NAMES.get(stage, ""))
    config_block = (
        format_project_config(state.workflow.get(WORKFLOW_PROJECT_CONFIG))
        or "- 尚未确认创作配置。"
    )
    workspace_context = format_stage_workspace_context(state.workspace, stage)
    events_block = format_configured_chapter_events(state, chapter_events)
    return (
        f"{skill_prompt}\n\n"
        "## 运行时上下文\n"
        f"已确认创作配置：\n{config_block}\n"
        f"{workspace_context}\n"
        f"配置章节事件：\n{events_block}\n\n"
        f"被评估对象是上方运行时上下文中的「当前{stage_label(stage)}」全文。"
    )


def ensure_stage_assessable(state: ScreenwritingSessionState, stage: str) -> None:
    """校验阶段可评估：阶段合法且工作区已有内容。"""
    if stage not in STAGE_ORDER:
        raise ScreenwritingValidationError(f"未知的创作阶段：{stage}")
    if not str(getattr(state.workspace, stage, "") or "").strip():
        raise ScreenwritingValidationError(
            f"「{stage_label(stage)}」工作区尚无内容，请先生成或撰写后再评估"
        )


def stage_content_fingerprint(content: str) -> str:
    """阶段内容指纹：缓存命中以内容完全一致为准。"""
    return hashlib.sha256(str(content or "").strip().encode("utf-8")).hexdigest()


def load_cached_assessment(
    state: ScreenwritingSessionState,
    stage: str,
) -> StageAssessment | None:
    """读取该阶段的评估缓存；内容指纹不匹配（已重新生成/手动编辑）时视为失效。"""
    cache = state.workflow.get(WORKFLOW_STAGE_ASSESSMENTS)
    if not isinstance(cache, dict):
        return None
    entry = cache.get(stage)
    if not isinstance(entry, dict):
        return None
    current_fingerprint = stage_content_fingerprint(str(getattr(state.workspace, stage, "") or ""))
    if str(entry.get("fingerprint") or "") != current_fingerprint:
        return None
    report = str(entry.get("report") or "").strip()
    if not report:
        return None
    scores = entry.get("scores")
    return StageAssessment(
        stage=stage,
        report=report,
        scores=dict(scores) if isinstance(scores, dict) else {},
        improvement_prompt=str(entry.get("improvementPrompt") or ""),
    )


def save_assessment_cache(
    state: ScreenwritingSessionState,
    assessment: StageAssessment,
    *,
    fingerprint: str,
) -> None:
    """把评估结果写入会话 workflow 缓存（绑定评估时刻的内容指纹）。"""
    cache = state.workflow.get(WORKFLOW_STAGE_ASSESSMENTS)
    if not isinstance(cache, dict):
        cache = {}
    cache[assessment.stage] = {
        "fingerprint": fingerprint,
        "report": assessment.report,
        "scores": dict(assessment.scores),
        "improvementPrompt": assessment.improvement_prompt,
        "assessedAt": utc_now().isoformat(),
    }
    state.workflow[WORKFLOW_STAGE_ASSESSMENTS] = cache
    state.updated_at = utc_now()


async def stream_stage_assessment(
    state: ScreenwritingSessionState,
    stage: str,
    chapter_events: list[dict[str, Any]],
    *,
    model_id: str,
    gateway: Any | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """流式执行阶段评估。

    产出事件：message.delta（报告增量，已过滤改进提示词标记之后的内容）、
    done（data: scores/report/improvementPrompt）、error（detail）。
    """
    try:
        ensure_stage_assessable(state, stage)
    except ScreenwritingValidationError as exc:
        yield {"type": "error", "detail": str(exc)}
        return
    resolved_gateway = gateway or ProviderModelGateway(timeout=180.0)
    system_prompt = build_assessment_system_prompt(stage, state, chapter_events)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"请对当前{stage_label(stage)}进行多维质量评估并打分，输出完整评估报告。",
        },
    ]

    raw_content = ""
    sent_length = 0
    try:
        async for chunk in resolved_gateway.generate_stream(model_id=model_id, messages=messages):
            raw_content += str(chunk or "")
            visible_length = _visible_report_length(raw_content)
            if visible_length > sent_length:
                yield {
                    "type": "message.delta",
                    "content": raw_content[sent_length:visible_length],
                }
                sent_length = visible_length
    except Exception as exc:
        yield {"type": "error", "detail": str(exc)}
        return

    assessment = parse_assessment(stage, raw_content, state=state)
    if not assessment.report:
        yield {"type": "error", "detail": "评估模型未返回可用报告内容"}
        return
    yield {
        "type": "done",
        "content": assessment.report,
        "data": {
            "stage": stage,
            "scores": assessment.scores,
            "report": assessment.report,
            "improvementPrompt": assessment.improvement_prompt,
        },
    }


def parse_assessment(
    stage: str,
    raw_content: str,
    *,
    state: ScreenwritingSessionState | None = None,
) -> StageAssessment:
    """解析评估输出：标记前为报告正文，标记后为改进提示词；评分按行正则提取。

    改进提示词缺失时用确定性兜底（报告前若干字 + 重新生成指令），保证
    "按评估改进"功能始终可用。
    """
    text = str(raw_content or "").strip()
    if not text:
        return StageAssessment(stage=stage, report="")

    if IMPROVEMENT_PROMPT_MARKER in text:
        report, _, improvement = text.partition(IMPROVEMENT_PROMPT_MARKER)
        report = report.strip()
        improvement_prompt = improvement.strip()
    else:
        report = text
        improvement_prompt = ""

    if not improvement_prompt:
        improvement_prompt = _fallback_improvement_prompt(stage, report)
    improvement_prompt = _guard_improvement_prompt_config(stage, improvement_prompt, state)

    return StageAssessment(
        stage=stage,
        report=report,
        scores=_parse_scores(report),
        improvement_prompt=improvement_prompt,
    )


def _parse_scores(report: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    for match in _SCORE_LINE_RE.finditer(report):
        name = match.group(1).strip()
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        if 0 <= value <= 10:
            scores[name] = value
    return scores


def _fallback_improvement_prompt(stage: str, report: str) -> str:
    label = stage_label(stage)
    excerpt = report[:_IMPROVEMENT_PROMPT_MAX_FALLBACK_CHARS].strip()
    return (
        f"请重新生成{label}：结合以下质量评估报告中指出的问题与改进建议逐条改进，"
        "保留已合格的结构与事实，仅针对问题项调整。\n\n"
        f"评估报告摘录：\n{excerpt}"
    )


_IMPROVEMENT_PROMPT_PREFIXES: dict[str, str] = {
    "skeleton": "请重新生成故事骨架：",
    "strategy": "请重新生成改编策略：",
    "script": "请重新生成剧本草案：",
}


def _guard_improvement_prompt_config(
    stage: str,
    improvement_prompt: str,
    state: ScreenwritingSessionState | None,
) -> str:
    """把评估改进提示词绑定到当前创作配置，避免模型输出旧集数或旧时长。"""
    prompt = str(improvement_prompt or "").strip()
    if state is None:
        return prompt
    config_block = format_project_config(state.workflow.get(WORKFLOW_PROJECT_CONFIG))
    if not config_block:
        return prompt

    prefix = _IMPROVEMENT_PROMPT_PREFIXES.get(stage, f"请重新生成{stage_label(stage)}：")
    body = prompt
    if body.startswith(prefix):
        body = body[len(prefix) :].strip()
    body = _strip_config_rewrite_directives(body)
    guarded = (
        f"{prefix}严格按以下已确认创作配置执行，不得改写、替换或新增集数、单集时长、"
        f"原著范围、平台规格、风格定位或付费策略。\n{config_block}"
    )
    if body:
        guarded += f"\n\n评估改进要求：{body}"
    return guarded


def _strip_config_rewrite_directives(text: str) -> str:
    """删除评估模型在改进提示词中误写的总集数或单集时长改配指令。"""
    cleaned = str(text or "").strip()
    patterns = (
        r"(?:把|将)?(?:全剧|整体|总集数|集数)[^。；;\n]*(?:\d+\s*集|\d+\s*分钟)[^。；;\n]*[。；;]?",
        r"(?:压缩|调整|改成|改为|变成|设置为|定为|做成)[^。；;\n]*(?:\d+\s*集|\d+\s*分钟)[^。；;\n]*[。；;]?",
        r"每集\s*\d+\s*分钟\s*[，,、和及与]?",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"^[，,；;。]\s*", "", cleaned)
    return cleaned.strip()


def _visible_report_length(raw_content: str) -> int:
    """计算可安全流式下发的报告长度。

    标记之后是改进提示词（不进报告弹窗正文）；标记可能跨 chunk 到达，
    故未见标记时也回扣一个标记长度作为缓冲。
    """
    marker_index = raw_content.find(IMPROVEMENT_PROMPT_MARKER)
    if marker_index >= 0:
        return marker_index
    return max(0, len(raw_content) - len(IMPROVEMENT_PROMPT_MARKER))