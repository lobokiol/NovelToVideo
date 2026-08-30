from __future__ import annotations

from dataclasses import dataclass


ZH_MIXED_CHAPTER_SPLIT_PATTERN = r"^\s*(?:[\d一二三四五六七八九十百千万零〇两廿]+集\s*)?(?:第\s*[\d一二三四五六七八九十百千万零〇两廿]+[章节回][^\n\r]*|序\s*[章节言幕]?)$"
ZH_REEL_SPLIT_PATTERN = r"^\s*第\s*[\d一二三四五六七八九十百千万零〇两廿]+\s*[卷部集册](?:\s+[^第\n\r]*)?$"
ZH_CHAPTER_SPLIT_PATTERN = r"^\s*第\s*[\d一二三四五六七八九十百千万零〇两廿]+\s*章[^\n\r]*$"
ZH_HUI_SPLIT_PATTERN = r"^\s*第\s*[\d一二三四五六七八九十百千万零〇两廿]+\s*回[^\n\r]*$"
EN_CHAPTER_SPLIT_PATTERN = r"^\s*Chapter\s+[0-9IVXLCM]+[^\n\r]*$"
EN_REEL_SPLIT_PATTERN = r"^\s*Book\s+[0-9IVXLCM]+[^\n\r]*$"


@dataclass(frozen=True)
class NovelImportSplitRule:
    """Builtin frontend chapter split rule."""

    key: str
    label: str
    description: str
    chapter_pattern: str
    chapter_flags_list: tuple[str, ...]
    reel_pattern: str
    reel_flags_list: tuple[str, ...]


BUILTIN_IMPORT_SPLIT_RULES: tuple[NovelImportSplitRule, ...] = (
    NovelImportSplitRule(
        key="zh-mixed",
        label="中文章节（默认）",
        description="识别「第X章 / 第X回 / 第X节 / 序章」，按「第X卷/部/集/册」归类",
        chapter_pattern=ZH_MIXED_CHAPTER_SPLIT_PATTERN,
        chapter_flags_list=(),
        reel_pattern=ZH_REEL_SPLIT_PATTERN,
        reel_flags_list=(),
    ),
    NovelImportSplitRule(
        key="zh-chapter",
        label="仅「第 X 章」",
        description="严格只匹配「第X章」",
        chapter_pattern=ZH_CHAPTER_SPLIT_PATTERN,
        chapter_flags_list=(),
        reel_pattern=ZH_REEL_SPLIT_PATTERN,
        reel_flags_list=(),
    ),
    NovelImportSplitRule(
        key="zh-hui",
        label="仅「第 X 回」",
        description="古典小说常见格式",
        chapter_pattern=ZH_HUI_SPLIT_PATTERN,
        chapter_flags_list=(),
        reel_pattern="",
        reel_flags_list=(),
    ),
    NovelImportSplitRule(
        key="en-chapter",
        label="Chapter N（英文）",
        description="识别「Chapter 1」「Chapter II」",
        chapter_pattern=EN_CHAPTER_SPLIT_PATTERN,
        chapter_flags_list=("i",),
        reel_pattern=EN_REEL_SPLIT_PATTERN,
        reel_flags_list=("i",),
    ),
)


def get_builtin_import_split_rules() -> list[NovelImportSplitRule]:
    """Return builtin import split rules in display order."""
    return list(BUILTIN_IMPORT_SPLIT_RULES)
