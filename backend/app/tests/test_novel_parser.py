from __future__ import annotations

from pathlib import Path
import re

from app.utils.novel_import_rules import get_builtin_import_split_rules
from app.utils.novel_parser import parse_novel_chapters
from app.services.novel import list_import_split_rules
from app.routers.novel import router as novel_router


def _compile_frontend_regex(pattern: str, flags: tuple[str, ...]) -> re.Pattern[str]:
    re_flags = 0
    if "i" in flags:
        re_flags |= re.IGNORECASE
    if "m" in flags:
        re_flags |= re.MULTILINE
    if "s" in flags:
        re_flags |= re.DOTALL
    return re.compile(pattern, re_flags)


def test_novel_regex_definitions_are_complete_use_case_patterns() -> None:
    root = Path(__file__).resolve().parents[1]
    source_by_file = {
        "novel_import_rules.py": (root / "utils" / "novel_import_rules.py").read_text(encoding="utf-8"),
        "novel_parser.py": (root / "utils" / "novel_parser.py").read_text(encoding="utf-8"),
    }
    fragment_pattern_names = (
        "CN_NUMBER_CHARS",
        "TITLE_NUMBER_PATTERN",
        "REEL_NUMBER_PATTERN",
        "REEL_PREFIX_PATTERN",
        "CHAPTER_TITLE_PATTERN",
        "CHAPTER_SERIES_PREFIX_PATTERN",
        "PREFACE_TITLE_PATTERN",
    )

    for source in source_by_file.values():
        for name in fragment_pattern_names:
            assert name not in source
    assert "from app.utils.novel_import_rules import" not in source_by_file["novel_parser.py"]


def test_builtin_import_split_rules_include_default_chapter_and_reel_patterns() -> None:
    rules = get_builtin_import_split_rules()

    default_rule = rules[0]
    expected_chapter_pattern = r"^\s*(?:[\d一二三四五六七八九十百千万零〇两廿]+集\s*)?(?:第\s*[\d一二三四五六七八九十百千万零〇两廿]+[章节回][^\n\r]*|序\s*[章节言幕]?)$"
    chapter_regex = _compile_frontend_regex(default_rule.chapter_pattern, default_rule.chapter_flags_list)
    reel_regex = _compile_frontend_regex(default_rule.reel_pattern, default_rule.reel_flags_list)

    assert default_rule.key == "zh-mixed"
    assert default_rule.chapter_pattern == expected_chapter_pattern
    assert chapter_regex.match("\u7b2c\u4e00\u7ae0 \u9752\u4e91")
    assert chapter_regex.match("二十二集 第三章 心魔")
    assert chapter_regex.match("\u5e8f\u7ae0")
    assert reel_regex.match("\u7b2c\u4e8c\u5341\u4e8c\u96c6")
    assert not chapter_regex.match("\u9752\u4e91\u6b63\u6587")


def test_novel_service_exposes_import_split_rules_as_camel_case_schema() -> None:
    rules = list_import_split_rules()

    dumped = rules[0].model_dump(by_alias=True)

    assert dumped["key"] == "zh-mixed"
    assert "chapterPattern" in dumped
    assert "chapterFlagsList" in dumped
    assert dumped["builtin"] is True


def test_novel_router_registers_import_split_rules_endpoint() -> None:
    routes = [
        route
        for route in novel_router.routes
        if getattr(route, "path", "").endswith("/import-split-rules")
    ]

    assert routes
    assert "GET" in routes[0].methods


def test_parse_novel_chapters_handles_reel_preface_and_inline_reel_titles() -> None:
    raw_text = "\n".join(
        [
            "\u300a\u8bdb\u4ed9\u300b",
            "\u4f5c\u8005\uff1a\u8427\u9f0e",
            "\u7b2c\u4e00\u96c6",
            "\u5e8f\u7ae0",
            "\u5e8f\u7ae0\u6b63\u6587",
            "\u7b2c\u4e00\u7ae0 \u9752\u4e91",
            "\u9752\u4e91\u6b63\u6587",
            "\u7b2c\u4e8c\u5341\u4e8c\u96c6  \u7b2c\u4e00\u7ae0\u3000\u5206\u522b",
            "\u5206\u522b\u6b63\u6587",
            "\u7b2c\u4e8c\u5341\u4e09\u96c6\u7b2c07\uff5e08\u7ae0",
            "\u8fde\u7eed\u7ae0\u6b63\u6587",
        ]
    )

    chapters = parse_novel_chapters(raw_text)

    assert [(item.reel, item.chapter, item.chapter_data) for item in chapters] == [
        ("\u7b2c\u4e00\u96c6", "\u5e8f\u7ae0", "\u5e8f\u7ae0\u6b63\u6587"),
        ("\u7b2c\u4e00\u96c6", "\u7b2c\u4e00\u7ae0 \u9752\u4e91", "\u9752\u4e91\u6b63\u6587"),
        (
            "\u7b2c\u4e8c\u5341\u4e8c\u96c6",
            "\u7b2c\u4e00\u7ae0 \u5206\u522b",
            "\u5206\u522b\u6b63\u6587",
        ),
        ("\u7b2c\u4e8c\u5341\u4e09\u96c6", "\u7b2c07\uff5e08\u7ae0", "\u8fde\u7eed\u7ae0\u6b63\u6587"),
    ]


def test_parse_novel_chapters_ignores_duplicate_catalog_heading_before_body() -> None:
    raw_text = "\n".join(
        [
            "\u7b2c\u4e8c\u5341\u4e8c\u96c6\u7b2c\u4e09\u7ae0 \u5fc3\u9b54",
            "\u8bdb\u4ed9\u7b2c\u4e8c\u5341\u4e8c\u96c6\u7b2c\u4e09\u7ae0\u5fc3\u9b54\u4f5c\u8005\uff1a\u8427\u9f0e",
            "\u7b2c\u4e09\u7ae0\u5fc3\u9b54",
            "\u5fc3\u9b54\u6b63\u6587",
        ]
    )

    chapters = parse_novel_chapters(raw_text)

    assert [(item.reel, item.chapter, item.chapter_data) for item in chapters] == [
        ("\u7b2c\u4e8c\u5341\u4e8c\u96c6", "\u7b2c\u4e09\u7ae0\u5fc3\u9b54", "\u5fc3\u9b54\u6b63\u6587"),
    ]


def test_parse_novel_chapters_handles_bare_number_titles() -> None:
    raw_text = "\n".join(
        [
            "\u516b \u864e\u5578\u9f99\u541f",
            "\u864e\u5578\u9f99\u541f\u6b63\u6587",
            "\u4e5d",
            "\u98ce\u96ea\u591c\u5f52\u4eba",
            "\u98ce\u96ea\u591c\u5f52\u4eba\u6b63\u6587",
        ]
    )

    chapters = parse_novel_chapters(raw_text)

    assert [(item.chapter, item.chapter_data) for item in chapters] == [
        ("\u516b \u864e\u5578\u9f99\u541f", "\u864e\u5578\u9f99\u541f\u6b63\u6587"),
        ("\u4e5d \u98ce\u96ea\u591c\u5f52\u4eba", "\u98ce\u96ea\u591c\u5f52\u4eba\u6b63\u6587"),
    ]
