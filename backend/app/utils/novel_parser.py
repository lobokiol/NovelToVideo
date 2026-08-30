from __future__ import annotations

from dataclasses import dataclass
import re


REEL_PATTERN = re.compile(r"^(?P<reel>第\s*[\d一二三四五六七八九十百千万零〇两廿]+\s*[卷部集册])(?:\s+[^第\n\r]*)?$")
INLINE_REEL_CHAPTER_PATTERN = re.compile(r"^(?P<reel>第\s*[\d一二三四五六七八九十百千万零〇两廿]+\s*[卷部集册])\s*(?P<chapter>第\s*[\d一二三四五六七八九十百千万零〇两廿]+(?:\s*[~～\-—至]\s*[\d一二三四五六七八九十百千万零〇两廿]+)?\s*[章节回].*)$")
CHAPTER_PATTERN = re.compile(r"^(第\s*[\d一二三四五六七八九十百千万零〇两廿]+(?:\s*[~～\-—至]\s*[\d一二三四五六七八九十百千万零〇两廿]+)?\s*[章节回].*|Chapter\s+[0-9IVXLCM]+.*)$", re.IGNORECASE)
PREFACE_PATTERN = re.compile(r"^序\s*[章节言幕]?$")
EN_REEL_PATTERN = re.compile(r"^Book\s+[0-9IVXLCM]+.*$", re.IGNORECASE)
BARE_NUMBER_TITLE_PATTERN = re.compile(r"^(?P<number>[\d一二三四五六七八九十百千万零〇两廿]+)\s+(?P<title>\S.*)$")
BARE_NUMBER_ONLY_PATTERN = re.compile(r"^(?P<number>[\d一二三四五六七八九十百千万零〇两廿]+)$")
TITLE_END_PUNCTUATION_PATTERN = re.compile(r"[。！？；，、.,;!?]$")


@dataclass(frozen=True)
class ParsedNovelChapter:
    """从原始小说文本中解析出的章节。"""

    chapter_index: int
    reel: str
    chapter: str
    chapter_data: str


def parse_novel_chapters(raw_text: str) -> list[ParsedNovelChapter]:
    """按常见中文卷、章节标题拆分小说正文。"""
    lines = [_normalize_line(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return []

    chapters: list[ParsedNovelChapter] = []
    current_reel = ""
    current_chapter = ""
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_chapter, current_lines
        if not current_chapter:
            return
        chapter_data = "\n".join(current_lines).strip()
        if not chapter_data:
            current_chapter = ""
            current_lines = []
            return
        chapters.append(
            ParsedNovelChapter(
                chapter_index=len(chapters) + 1,
                reel=current_reel,
                chapter=current_chapter,
                chapter_data=chapter_data,
            )
        )
        current_chapter = ""
        current_lines = []

    preface_lines: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        inline_heading = _parse_inline_reel_chapter(line)
        if inline_heading is not None:
            flush_current()
            current_reel, current_chapter = inline_heading
            current_lines = []
            index += 1
            continue
        bare_heading = _parse_bare_number_chapter(line, next_line)
        if bare_heading is not None:
            flush_current()
            current_chapter, consumed = bare_heading
            current_lines = []
            index += consumed
            continue
        if _looks_like_reel(line):
            flush_current()
            current_reel = line
            index += 1
            continue
        if _looks_like_chapter(line):
            flush_current()
            current_chapter = line
            current_lines = []
            index += 1
            continue
        if current_chapter:
            if _looks_like_heading_metadata(line):
                index += 1
                continue
            current_lines.append(line)
        else:
            preface_lines.append(line)
        index += 1

    flush_current()
    if chapters:
        return chapters

    return [
        ParsedNovelChapter(
            chapter_index=1,
            reel="",
            chapter="正文",
            chapter_data="\n".join(preface_lines).strip(),
        )
    ]


def _normalize_line(line: str) -> str:
    """压缩标题和正文行两侧空白。"""
    return re.sub(r"\s+", " ", line.strip())


def _normalize_title(title: str) -> str:
    """Normalize title spacing while keeping the human-readable split."""
    return re.sub(r"\s+", " ", title.strip())


def _parse_inline_reel_chapter(line: str) -> tuple[str, str] | None:
    """Parse headings like "第十二集 第一章 标题"."""
    if len(line) > 140:
        return None
    match = INLINE_REEL_CHAPTER_PATTERN.match(line)
    if match is None:
        return None
    return _normalize_title(match.group("reel")), _normalize_title(match.group("chapter"))


def _parse_bare_number_chapter(line: str, next_line: str | None) -> tuple[str, int] | None:
    """Parse headings like "八 虎啸龙吟" or two-line "八" + "虎啸龙吟"."""
    if len(line) > 80:
        return None
    inline_match = BARE_NUMBER_TITLE_PATTERN.match(line)
    if inline_match is not None:
        title = inline_match.group("title").strip()
        if _looks_like_short_title(title):
            return _normalize_title(f"{inline_match.group('number')} {title}"), 1

    number_match = BARE_NUMBER_ONLY_PATTERN.match(line)
    if number_match is None or next_line is None:
        return None
    title = next_line.strip()
    if not _looks_like_short_title(title):
        return None
    if _looks_like_reel(title) or _looks_like_chapter(title) or _parse_inline_reel_chapter(title) is not None:
        return None
    if BARE_NUMBER_ONLY_PATTERN.match(title) is not None or _looks_like_heading_metadata(title):
        return None
    return _normalize_title(f"{number_match.group('number')} {title}"), 2


def _looks_like_short_title(line: str) -> bool:
    """Return whether a short standalone line can safely serve as a bare chapter title."""
    return 0 < len(line) <= 80 and TITLE_END_PUNCTUATION_PATTERN.search(line) is None


def _looks_like_reel(line: str) -> bool:
    """判断是否为卷次标题。"""
    return len(line) <= 80 and (REEL_PATTERN.match(line) is not None or EN_REEL_PATTERN.match(line) is not None)


def _looks_like_chapter(line: str) -> bool:
    """判断是否为章节标题。"""
    return len(line) <= 120 and (CHAPTER_PATTERN.match(line) is not None or PREFACE_PATTERN.match(line) is not None)


def _looks_like_heading_metadata(line: str) -> bool:
    """Skip short source page headers such as "诛仙第X集第Y章标题作者：..."."""
    return (
        len(line) <= 100
        and "作者" in line
        and "第" in line
        and any(unit in line for unit in ("章", "节", "回"))
    )
