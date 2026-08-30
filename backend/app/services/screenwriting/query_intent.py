"""剧本创作 RAG 查询意图模型与本地兜底解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class ChapterRangeIntent:
    """基于章节 metadata 的精确章节范围查询。"""

    start_index: int
    end_index: int


@dataclass(frozen=True)
class ChapterTailIntent:
    """基于当前最高章节序号的相对尾部章节查询。"""

    count: int


@dataclass(frozen=True)
class FieldLookupIntent:
    """基于文档类型和字段标记的精确字段查询。"""

    source_type: str
    document_markers: tuple[str, ...]


@dataclass(frozen=True)
class EventSelector:
    """基于结构化事件 metadata 的检索选择器。"""

    characters: tuple[str, ...] = ()
    scenes: tuple[str, ...] = ()
    organizations: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    focus: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalToolCall:
    """一次计划中的检索工具调用。"""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    priority: int = 100


@dataclass(frozen=True)
class RetrievalToolPlan:
    """LLM 或兜底解析生成的检索工具计划。"""

    tools: tuple[RetrievalToolCall, ...] = ()
    answer_focus: str = ""
    confidence: float = 0.0
    source: str = "fallback"


@dataclass(frozen=True)
class ScreenwritingQueryIntent:
    """一次用户查询的结构化检索意图。"""

    raw_query: str
    normalized_query: str
    lookup_terms: tuple[str, ...]
    chapter_range: ChapterRangeIntent | None = None
    chapter_tail: ChapterTailIntent | None = None
    field_lookups: tuple[FieldLookupIntent, ...] = ()
    event_selector: EventSelector | None = None
    tool_plan: RetrievalToolPlan = field(default_factory=RetrievalToolPlan)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def with_updates(self, **changes: Any) -> "ScreenwritingQueryIntent":
        """返回一个更新了部分字段的新意图对象。"""
        return replace(self, **changes)


_LOOKUP_TEXT_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]+")
_LOOKUP_SEGMENT_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+")
_CHAPTER_NUMBER_PATTERN = r"\d+|[零〇一二两三四五六七八九十百]+"
_FRONT_CHAPTERS_RE = re.compile(rf"前\s*({_CHAPTER_NUMBER_PATTERN})\s*章")
_CHAPTER_RANGE_RE = re.compile(
    rf"第?\s*({_CHAPTER_NUMBER_PATTERN})\s*章?\s*(?:[-~—到至])\s*第?\s*({_CHAPTER_NUMBER_PATTERN})\s*章"
)
_SINGLE_CHAPTER_RE = re.compile(rf"第\s*({_CHAPTER_NUMBER_PATTERN})\s*章")
_TAIL_CHAPTERS_RE = re.compile(rf"(?:最后|最近|最新|末尾|结尾)\s*({_CHAPTER_NUMBER_PATTERN})\s*章")
_LOOKUP_STOP_WORDS = (
    "是什么",
    "是啥",
    "是谁",
    "是多少",
    "叫什么",
    "请问",
    "告诉我",
    "帮我查",
    "帮我看",
    "一下",
    "吗",
    "呢",
    "啊",
    "呀",
    "的",
    "是",
)
_QUERY_TERM_ALIASES = (
    ("项目名", ("项目名称", "项目名字")),
    ("项目名称", ("项目名称", "项目名字")),
    ("项目叫什么", ("项目名称", "项目名字")),
    ("作品名", ("项目名称", "作品名称")),
    ("作品名称", ("项目名称", "作品名称")),
    ("小说名", ("小说标题", "书名")),
    ("小说标题", ("小说标题", "书名")),
    ("书名", ("小说标题", "书名")),
)
_FIELD_INTENT_SPECS = (
    ("project", ("项目名", "项目名称", "项目叫什么", "作品名", "作品名称"), ("项目名称",)),
    ("novel", ("小说名", "小说标题", "书名", "原著名", "原著名称"), ("小说标题",)),
    ("novel", ("作者", "谁写", "作者是谁"), ("作者",)),
)


def parse_screenwriting_query_intent(query: str) -> ScreenwritingQueryIntent:
    """本地兜底解析，覆盖少量确定性高的查询。"""
    raw_query = str(query or "").strip()
    normalized_query = normalize_lookup_text(raw_query)
    lookup_terms = query_lookup_terms(raw_query)
    chapter_range = chapter_index_query_range(raw_query)
    chapter_tail = chapter_tail_query(raw_query) if chapter_range is None else None
    field_lookups = field_lookup_intents(normalized_query)
    tool_plan = fallback_tool_plan(
        has_metadata_lookup=chapter_range is not None or chapter_tail is not None or bool(field_lookups),
        lookup_terms=lookup_terms,
    )
    return ScreenwritingQueryIntent(
        raw_query=raw_query,
        normalized_query=normalized_query,
        lookup_terms=lookup_terms,
        chapter_range=chapter_range,
        chapter_tail=chapter_tail,
        field_lookups=field_lookups,
        tool_plan=tool_plan,
    )


def fallback_tool_plan(
    *,
    has_metadata_lookup: bool,
    has_event_lookup: bool = False,
    lookup_terms: tuple[str, ...] = (),
    diagnostics: dict[str, Any] | None = None,
) -> RetrievalToolPlan:
    """生成模型不可用时的保守检索计划。"""
    tools: list[RetrievalToolCall] = []
    if has_metadata_lookup:
        tools.append(RetrievalToolCall(tool="metadata_lookup", priority=1))
    if has_event_lookup:
        tools.append(RetrievalToolCall(tool="event_json_search", priority=20))
    tools.extend(
        (
            RetrievalToolCall(tool="chapter_vector_search", priority=50),
            RetrievalToolCall(tool="lexical_fallback", args={"lookup_terms": list(lookup_terms)}, priority=100),
        )
    )
    return RetrievalToolPlan(
        tools=tuple(tools),
        answer_focus="",
        confidence=0.35 if diagnostics else 0.55,
        source="fallback",
    )


def chapter_index_query_range(query: str) -> ChapterRangeIntent | None:
    """识别“前x章”“第x-x章”“第x章”等章节 metadata 查询。"""
    query_text = str(query or "").strip()
    if not query_text:
        return None

    front_match = _FRONT_CHAPTERS_RE.search(query_text)
    if front_match:
        end_index = parse_chapter_number(front_match.group(1))
        if end_index is not None:
            return ChapterRangeIntent(start_index=1, end_index=end_index)

    range_match = _CHAPTER_RANGE_RE.search(query_text)
    if range_match:
        start_index = parse_chapter_number(range_match.group(1))
        end_index = parse_chapter_number(range_match.group(2))
        if start_index is not None and end_index is not None:
            return ChapterRangeIntent(start_index=start_index, end_index=end_index)

    single_match = _SINGLE_CHAPTER_RE.search(query_text)
    if single_match:
        chapter_index = parse_chapter_number(single_match.group(1))
        if chapter_index is not None:
            return ChapterRangeIntent(start_index=chapter_index, end_index=chapter_index)
    return None


def chapter_tail_query(query: str) -> ChapterTailIntent | None:
    """识别“最后x章”“最后x章”“最近x章”等基于最高章节序号的尾部查询。"""
    query_text = str(query or "").strip()
    if not query_text:
        return None
    tail_match = _TAIL_CHAPTERS_RE.search(query_text)
    if not tail_match:
        return None
    count = parse_chapter_number(tail_match.group(1))
    if count is None:
        return None
    return ChapterTailIntent(count=count)


def field_lookup_intents(normalized_query: str) -> tuple[FieldLookupIntent, ...]:
    """识别适合走字段精确检索的问题。"""
    if not normalized_query:
        return ()
    intents: list[FieldLookupIntent] = []
    for source_type, query_terms, document_markers in _FIELD_INTENT_SPECS:
        normalized_terms = tuple(normalize_lookup_text(term) for term in query_terms)
        if any(term and term in normalized_query for term in normalized_terms):
            intents.append(
                FieldLookupIntent(
                    source_type=source_type,
                    document_markers=tuple(document_markers),
                )
            )
    return tuple(intents)


def parse_chapter_number(value: str) -> int | None:
    """解析阿拉伯数字或常见中文章节数字。"""
    token = str(value or "").strip()
    if not token:
        return None
    if token.isdigit():
        number = int(token)
        return number if number > 0 else None
    number = parse_chinese_number(token)
    return number if number is not None and number > 0 else None


def parse_chinese_number(value: str) -> int | None:
    """解析一到三位常见中文数字。"""
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    text = str(value or "").strip()
    if not text or any(char not in {*digits, "十", "百"} for char in text):
        return None
    if "百" in text:
        head, tail = text.split("百", 1)
        hundred = digits.get(head, 1 if not head else -1)
        if hundred < 0:
            return None
        tail_value = parse_chinese_number(tail) if tail else 0
        return hundred * 100 + int(tail_value or 0)
    if "十" in text:
        head, tail = text.split("十", 1)
        ten = digits.get(head, 1 if not head else -1)
        if ten < 0:
            return None
        tail_digit = digits.get(tail, 0 if not tail else -1)
        if tail_digit < 0:
            return None
        return ten * 10 + tail_digit
    if len(text) == 1:
        return digits.get(text)
    if all(char in digits for char in text):
        return int("".join(str(digits[char]) for char in text))
    return None


def normalize_lookup_text(value: str) -> str:
    """把查询或资料文本归一化为便于包含匹配的形式。"""
    return "".join(_LOOKUP_TEXT_PATTERN.findall(str(value or "").lower()))


def query_lookup_terms(query: str) -> tuple[str, ...]:
    """提取用于词法精确加权的查询关键词和字段别名。"""
    normalized_query = normalize_lookup_text(query)
    if not normalized_query:
        return ()

    terms: set[str] = set()
    reduced_query = remove_lookup_stop_words(normalized_query)
    if len(reduced_query) >= 2:
        terms.add(reduced_query)

    for segment in _LOOKUP_SEGMENT_PATTERN.findall(str(query or "").lower()):
        reduced_segment = remove_lookup_stop_words(normalize_lookup_text(segment))
        if len(reduced_segment) >= 2:
            terms.add(reduced_segment)

    for trigger, aliases in _QUERY_TERM_ALIASES:
        normalized_trigger = normalize_lookup_text(trigger)
        if normalized_trigger in normalized_query or normalized_trigger in reduced_query:
            terms.update(normalize_lookup_text(alias) for alias in aliases)
    return tuple(sorted((term for term in terms if term), key=lambda item: (-len(item), item)))


def remove_lookup_stop_words(value: str) -> str:
    """移除中文问句中不影响检索定位的高频词。"""
    reduced = value
    for stop_word in _LOOKUP_STOP_WORDS:
        reduced = reduced.replace(stop_word, "")
    return reduced
