"""阶段产出质量护栏：确定性规则校验。

硬失败抛 ScreenwritingServiceError（产出拒绝写入工作区，触发自修复），
软问题返回警告列表（仍写入工作区，经 quality.warning 事件提示用户）。
规则按阶段不对称：故事骨架校验模板化占位与章节事件绑定；剧本校验分集/场次
结构、动作与对白密度、时长倍率、截断与转场钩子；改编策略仅做占位符兜底。
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from typing import Any

from app.services.screenwriting.constants import (
    SCRIPT_EPISODE_DURATION_MAX_RATIO,
    SCRIPT_EPISODE_DURATION_MIN_RATIO,
    SCRIPT_SCENE_MIN_ACTION_LINES,
    SCRIPT_SCENE_MIN_DIALOGUE_CHARS,
    SCRIPT_SCENE_MIN_DIALOGUE_LINES,
    TEMPLATE_SKELETON_MARKERS,
)
from app.services.screenwriting.errors import ScreenwritingServiceError


SKELETON_BINDING_WARNING = (
    "故事骨架缺少与具体章节事件的强绑定，建议补充明确章节编号、事件名称和关键因果后再进入改编策略。"
)

# 剧本中"标签：值"形式但不属于角色对白的标签集合。
SCRIPT_NON_DIALOGUE_LABELS: frozenset[str] = frozenset(
    {
        "人物",
        "角色",
        "剧情梗概",
        "目标时长",
        "时长",
        "平台",
        "风格",
        "节拍",
        "场景",
        "动作",
        "对白",
        "信息点",
        "本集功能",
        "集尾钩子",
        "付费点",
    }
)

_EPISODE_HEADING_MARKDOWN_EP_RE = re.compile(r"^\s{0,3}#{1,3}\s*.*?\bEP\s*0?(\d+)\b", re.IGNORECASE)
_EPISODE_HEADING_MARKDOWN_CN_RE = re.compile(r"^\s{0,3}#{1,3}\s*第\s*(\d+)\s*集\b")
_SCENE_HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,4}\s*)?(\d+)\s*-\s*(\d+)\s+\S.*$"
)
_SCENE_TIME_HINT_RE = re.compile(r"(日|夜|晨|昏|黄昏|清晨|傍晚|深夜|午)")
_ACTION_LINE_RE = re.compile(r"^\s*△")
_DIALOGUE_LINE_RE = re.compile(r"^\s*([^\s△#>\[\]【】\-*|`][^：:]{0,24}?)(?:（[^）]*）|\([^)]*\))?\s*[：:]\s*(\S.*)$")
_DURATION_LINE_RE = re.compile(r"^\s*时长\s*[:：]\s*(.+?)\s*$")
_DURATION_SECONDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:s|秒)", re.IGNORECASE)
_DURATION_MINUTES_RE = re.compile(r"(\d+(?:\.\d+)?)\s*分钟?")
_DURATION_CLOCK_RE = re.compile(r"^(\d+)\s*[:：]\s*(\d{1,2})$")
_SEPARATOR_LINE_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,}|={3,})\s*$")
_TRANSITION_RE = re.compile(r"\[(硬切|淡入|淡出|叠化|闪黑|切至|转场|黑场|定格)\]")
_SENTENCE_TERMINATORS = tuple("。！？!?；;…」』”’）)]】")
_HOOK_KEYWORDS = ("集尾钩子", "付费点", "悬念", "追更", "反转")
_PLACEHOLDER_QUESTION_RUN_RE = re.compile(r"\?{3,}|？{3,}")
_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")


def ensure_stage_output_quality(
    stage: str,
    content: str,
    *,
    chapter_events: Sequence[dict[str, Any]] = (),
    target_duration_minutes: int = 0,
) -> list[str]:
    """校验阶段产出质量；硬失败抛异常，软问题返回警告列表。"""
    text = (content or "").strip()
    if not text:
        raise ScreenwritingServiceError("模型未返回可用阶段内容")
    if _looks_like_placeholder_output(text):
        raise ScreenwritingServiceError("模型输出包含占位符或乱码，已拒绝写入工作区")
    if stage == "skeleton":
        return _ensure_skeleton_quality(text, chapter_events)
    if stage == "script":
        return _ensure_script_quality(text, target_duration_minutes=target_duration_minutes)
    return []


def parse_episode_duration_minutes(value: Any) -> int:
    """从创作配置的单集时长文本（如"2分钟/集"）解析分钟数。"""
    match = _DURATION_MINUTES_RE.search(str(value or ""))
    if not match:
        return 0
    minutes = int(float(match.group(1)))
    return minutes if minutes > 0 else 0


# ---------------------------------------------------------------------------
# 故事骨架
# ---------------------------------------------------------------------------


def _ensure_skeleton_quality(content: str, chapter_events: Sequence[dict[str, Any]]) -> list[str]:
    matched_markers = [marker for marker in TEMPLATE_SKELETON_MARKERS if marker in content]
    if matched_markers:
        raise ScreenwritingServiceError(
            "故事骨架仍包含模板化占位表达（"
            + "、".join(matched_markers[:3])
            + "），必须替换为真实角色、具体章节编号与事件名称"
        )

    required_bindings = min(3, len(chapter_events))
    if required_bindings <= 0:
        return []
    bound_count = sum(
        1 for event in chapter_events if _skeleton_binds_chapter_event(content, event)
    )
    if bound_count < required_bindings:
        return [SKELETON_BINDING_WARNING]
    return []


def _skeleton_binds_chapter_event(content: str, event: dict[str, Any]) -> bool:
    chapter_index = int(event.get("chapterIndex", 0) or 0)
    if chapter_index > 0 and f"第{chapter_index}章" in content:
        return True
    title = str(event.get("chapterTitle", "") or "").strip()
    return len(title) >= 4 and title in content


# ---------------------------------------------------------------------------
# 剧本草案
# ---------------------------------------------------------------------------


def _ensure_script_quality(text: str, *, target_duration_minutes: int) -> list[str]:
    warnings: list[str] = []
    if not _has_episode_heading(text):
        raise ScreenwritingServiceError("剧本输出缺少分集标题（# 项目名 EP01：标题 或 ## 第X集 标题）")
    scenes = list(_iter_scene_blocks(text))
    if not scenes:
        raise ScreenwritingServiceError("剧本输出缺少可拍摄场次（如 `1-1 场景地点 日/外`）")
    if not any(_ACTION_LINE_RE.match(line) for line in text.splitlines()):
        raise ScreenwritingServiceError("剧本输出缺少 △ 动作描写，无法满足剧本正文格式要求")
    if not any(_iter_dialogue_lines(text)):
        warnings.append("剧本输出缺少角色对白；请对照章节事件检查是否遗漏原著对白或关键信息点。")

    _ensure_scene_completion(scenes)
    warnings.extend(_ensure_scene_density(scenes))
    _ensure_scene_durations(text, target_duration_minutes=target_duration_minutes)
    _ensure_segment_separators(text, scene_count=len(scenes))
    if not _has_hook_or_transition(text):
        raise ScreenwritingServiceError("剧本输出缺少转场标记或集尾钩子，无法满足剧本正文格式要求")
    return warnings


def episode_heading_number(line: str) -> int | None:
    """解析 EP 标题行的集号；非标题行返回 None。"""
    text = line.strip()
    markdown_ep = _EPISODE_HEADING_MARKDOWN_EP_RE.match(text)
    if markdown_ep:
        return int(markdown_ep.group(1))
    markdown_cn = _EPISODE_HEADING_MARKDOWN_CN_RE.match(text)
    if markdown_cn:
        return int(markdown_cn.group(1))
    return None


def iter_episode_blocks(text: str) -> list[tuple[int, str]]:
    """按 EP 标题切分剧本，返回 (集号, 块文本) 列表。"""
    blocks: list[tuple[int, str]] = []
    current_no: int | None = None
    current_lines: list[str] = []
    for line in (text or "").splitlines():
        episode_no = episode_heading_number(line)
        if episode_no is not None:
            if current_no is not None:
                blocks.append((current_no, "\n".join(current_lines).strip()))
            current_no = episode_no
            current_lines = [line]
            continue
        if current_no is not None:
            current_lines.append(line)
    if current_no is not None:
        blocks.append((current_no, "\n".join(current_lines).strip()))
    return blocks


def _has_episode_heading(text: str) -> bool:
    return any(episode_heading_number(line) is not None for line in text.splitlines())


def _iter_scene_blocks(text: str) -> Iterator[tuple[str, str]]:
    """迭代 (场次标题, 场次正文) 块。"""
    heading: str | None = None
    body_lines: list[str] = []
    for line in (text or "").splitlines():
        if _is_scene_heading(line):
            if heading is not None:
                yield heading, "\n".join(body_lines)
            heading = line.strip()
            body_lines = []
            continue
        if episode_heading_number(line) is not None and heading is not None:
            yield heading, "\n".join(body_lines)
            heading = None
            body_lines = []
            continue
        if heading is not None:
            body_lines.append(line)
    if heading is not None:
        yield heading, "\n".join(body_lines)


def _is_scene_heading(line: str) -> bool:
    match = _SCENE_HEADING_RE.match(line)
    if not match:
        return False
    rest = line.strip()
    return bool(_SCENE_TIME_HINT_RE.search(rest)) or ("内" in rest or "外" in rest)


def _iter_dialogue_lines(text: str) -> Iterator[tuple[str, str]]:
    for line in (text or "").splitlines():
        match = _DIALOGUE_LINE_RE.match(line)
        if not match:
            continue
        speaker = match.group(1).strip()
        if speaker in SCRIPT_NON_DIALOGUE_LABELS:
            continue
        yield speaker, match.group(2).strip()


def _ensure_scene_completion(scenes: list[tuple[str, str]]) -> None:
    for heading, body in scenes:
        if _TRANSITION_RE.search(body):
            # 场内已有转场/收束标记即视为完整；标记后常跟集尾钩子说明等
            # 不带句末标点的附注行，不应据此误判截断。
            continue
        last_line = _last_content_line(body)
        if not last_line:
            continue
        if last_line.endswith(_SENTENCE_TERMINATORS):
            continue
        raise ScreenwritingServiceError(
            f"剧本输出疑似被截断；「{heading}」结尾停在「{last_line[:30]}」，"
            "每个场次必须以完整句子、转场标记或集尾钩子收束"
        )


def _last_content_line(body: str) -> str:
    """取场次正文的最后内容行；跳过空行、分隔线、Markdown 标题与列表行。

    标题/列表行（如"## 集尾钩子""- 付费点：……"）是结构性附注，
    本身不要求句末标点，不作为截断判定依据。
    """
    for line in reversed(body.splitlines()):
        text = line.strip()
        if not text or _SEPARATOR_LINE_RE.match(text):
            continue
        if re.match(r"^#{1,6}\s", text) or re.match(r"^[-*•]\s", text):
            continue
        return text
    return ""


def _ensure_scene_density(scenes: list[tuple[str, str]]) -> list[str]:
    warnings: list[str] = []
    for heading, body in scenes:
        action_count = sum(1 for line in body.splitlines() if _ACTION_LINE_RE.match(line))
        if action_count < SCRIPT_SCENE_MIN_ACTION_LINES:
            raise ScreenwritingServiceError(
                f"剧本场次动作描写密度不足；「{heading}」每场至少 "
                f"{SCRIPT_SCENE_MIN_ACTION_LINES} 段以 △ 开头的有效动作描写"
            )
        dialogue_lines = list(_iter_dialogue_lines(body))
        dialogue_chars = len(re.sub(r"\s+", "", "".join(line for _, line in dialogue_lines)))
        if (
            len(dialogue_lines) < SCRIPT_SCENE_MIN_DIALOGUE_LINES
            or dialogue_chars < SCRIPT_SCENE_MIN_DIALOGUE_CHARS
        ):
            warnings.append(
                f"剧本场次对白密度不足；「{heading}」请对照章节事件检查是否遗漏原著对白、"
                "人物反应或关键信息点，后续打磨时补足。"
            )
    return warnings[:3]


def _ensure_scene_durations(text: str, *, target_duration_minutes: int) -> None:
    episode_blocks = iter_episode_blocks(text) or [(0, text)]
    for episode_no, block_text in episode_blocks:
        episode_label = f"EP{episode_no:02d}" if episode_no > 0 else "当前 EP"
        durations: list[int] = []
        for heading, body in _iter_scene_blocks(block_text):
            seconds = _scene_duration_seconds(body)
            if seconds is None:
                raise ScreenwritingServiceError(
                    f"剧本场次缺少时长标记；「{heading}」必须在场次标题下写 `时长：Xs`"
                )
            durations.append(seconds)
        if not durations or target_duration_minutes <= 0:
            continue
        total_seconds = sum(durations)
        target_seconds = target_duration_minutes * 60
        min_seconds = int(target_seconds * SCRIPT_EPISODE_DURATION_MIN_RATIO)
        max_seconds = int(target_seconds * SCRIPT_EPISODE_DURATION_MAX_RATIO)
        if total_seconds < min_seconds or total_seconds > max_seconds:
            raise ScreenwritingServiceError(
                f"剧本场次时长总和与单集目标时长偏差过大；{episode_label} 当前合计 {total_seconds}s，"
                f"目标 {target_seconds}s，须落在 {min_seconds}-{max_seconds}s 区间"
            )


def _scene_duration_seconds(body: str) -> int | None:
    for line in body.splitlines():
        match = _DURATION_LINE_RE.match(line)
        if not match:
            continue
        return _parse_duration_seconds(match.group(1))
    return None


def _parse_duration_seconds(value: str) -> int | None:
    text = value.strip()
    clock = _DURATION_CLOCK_RE.match(text)
    if clock:
        return int(clock.group(1)) * 60 + int(clock.group(2))
    minutes = _DURATION_MINUTES_RE.search(text)
    seconds = _DURATION_SECONDS_RE.search(text)
    total = 0.0
    if minutes:
        total += float(minutes.group(1)) * 60
    if seconds:
        total += float(seconds.group(1))
    if total <= 0:
        return None
    return int(total)


def _ensure_segment_separators(text: str, *, scene_count: int) -> None:
    if scene_count <= 1:
        return
    if not any(_SEPARATOR_LINE_RE.match(line) for line in text.splitlines()):
        raise ScreenwritingServiceError(
            "剧本输出缺少场次分割符；多个场次之间必须使用单独一行 `---` 分割"
        )


def _has_hook_or_transition(text: str) -> bool:
    if _TRANSITION_RE.search(text):
        return True
    return any(keyword in text for keyword in _HOOK_KEYWORDS)


# ---------------------------------------------------------------------------
# 占位符/乱码检测
# ---------------------------------------------------------------------------


def _looks_like_placeholder_output(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    has_cjk = bool(_CJK_RE.search(compact))
    if _PLACEHOLDER_QUESTION_RUN_RE.search(compact) and not has_cjk:
        return True
    question_count = compact.count("?") + compact.count("？")
    if question_count >= 3 and not has_cjk and question_count / len(compact) >= 0.2:
        return True
    return all(not char.isalnum() and not _CJK_RE.match(char) for char in compact)