"""剧本创作 RAG 资料加载与标准化。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import BASE_DIR, Settings, settings
from app.core.rag import RagDocument
from app.models.novel import NovelChapter, NovelCrawlBook
from app.services.screenwriting.event_extraction import StructuredEvent, parse_chapter_events


DEFAULT_CHAPTER_EXCERPT_CHARS = 0
SKILL_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")


async def load_screenwriting_knowledge_documents(
    session: AsyncSession,
    project: Any,
    *,
    config: Settings | None = None,
) -> list[RagDocument]:
    """从项目章节和项目配置的技能资料加载剧本创作 RAG 文档。"""
    chapters = await _load_project_chapters(session, project)
    novel_books = await _load_project_novel_books(session, project)
    return [
        *build_project_basic_documents(project),
        *build_novel_basic_documents(novel_books),
        *build_chapter_documents(chapters, last_chapter_index=_chapter_sequence_last_index(chapters)),
        *build_event_documents(chapters, last_chapter_index=_chapter_sequence_last_index(chapters)),
        *build_project_skill_documents(project, config=config),
    ]


async def iter_screenwriting_knowledge_document_batches(
    session: AsyncSession,
    project: Any,
    *,
    config: Settings | None = None,
    batch_size: int | None = None,
) -> AsyncIterator[list[RagDocument]]:
    """分批加载剧本创作 RAG 文档，供 warmup 避免一次性持有完整资料。"""
    current = config or settings
    safe_batch_size = max(
        1,
        int(
            batch_size
            if batch_size is not None
            else current.screenwriting_rag_warmup_document_batch_size
        ),
    )
    novel_books = await _load_project_novel_books(session, project)
    basic_documents = [
        *build_project_basic_documents(project),
        *build_novel_basic_documents(novel_books),
    ]
    if basic_documents:
        yield basic_documents

    last_chapter_index = await _load_project_last_chapter_index(session, project)
    async for chapters in _iter_project_chapter_batches(session, project, batch_size=safe_batch_size):
        documents = [
            *build_chapter_documents(chapters, last_chapter_index=last_chapter_index),
            *build_event_documents(chapters, last_chapter_index=last_chapter_index),
        ]
        if documents:
            yield documents

    for documents in _iter_project_skill_document_batches(
        project,
        config=current,
        batch_size=safe_batch_size,
    ):
        yield documents


def build_project_basic_documents(project: Any) -> list[RagDocument]:
    """把项目基础配置标准化为 RAG 文档。"""
    project_public_id = _normalize_text(getattr(project, "public_id", ""))
    project_identity = project_public_id or _normalize_text(getattr(project, "id", "")) or "unknown"
    project_name = _normalize_text(getattr(project, "name", ""))
    parts = _labeled_parts(
        project,
        (
            ("项目名称", "name"),
            ("项目简介", "intro"),
            ("项目类型", "project_type"),
            ("内容类型", "content_type"),
            ("视觉风格", "art_style"),
            ("导演手册", "director_manual"),
            ("视频比例", "video_ratio"),
            ("文本模型", "text_model"),
            ("图像模型", "image_model"),
            ("视频模型", "video_model"),
            ("语音模型", "tts_model"),
            ("图像质量", "image_quality"),
            ("视频生成模式", "mode"),
        ),
    )
    if not parts:
        return []
    return [
        RagDocument(
            source_id=f"project:{project_identity}",
            source_type="project",
            title=f"项目基础信息 {project_name}".strip(),
            content="\n".join(parts),
            metadata={
                "project_id": getattr(project, "id", None),
                "project_public_id": project_public_id,
            },
        )
    ]


def build_novel_basic_documents(books: Sequence[Any]) -> list[RagDocument]:
    """把项目关联的小说基础信息标准化为 RAG 文档。"""
    documents: list[RagDocument] = []
    for index, book in enumerate(sorted(books, key=_novel_book_sort_key), start=1):
        novel_book_public_id = _normalize_text(getattr(book, "public_id", ""))
        source_key = _normalize_text(getattr(book, "source_key", ""))
        source_book_id = _normalize_text(getattr(book, "source_book_id", ""))
        source_identity = (
            novel_book_public_id
            or ":".join(part for part in (source_key, source_book_id) if part)
            or _normalize_text(getattr(book, "id", ""))
            or str(index)
        )
        title_text = _normalize_text(getattr(book, "title", ""))
        parts = _labeled_parts(
            book,
            (
                ("小说标题", "title"),
                ("作者", "author"),
                ("分类", "category"),
                ("更新状态", "update_status"),
                ("简介", "intro"),
                ("最新章节", "last_chapter"),
                ("最后更新", "last_update"),
            ),
        )
        if not parts:
            continue
        documents.append(
            RagDocument(
                source_id=f"novel:{source_identity}",
                source_type="novel",
                title=f"小说基础信息 {title_text}".strip(),
                content="\n".join(parts),
                metadata={
                    "novel_book_id": getattr(book, "id", None),
                    "novel_book_public_id": novel_book_public_id,
                    "source_key": source_key,
                    "source_book_id": source_book_id,
                },
            )
        )
    return documents


def build_chapter_documents(
    chapters: Sequence[Any],
    *,
    excerpt_chars: int = DEFAULT_CHAPTER_EXCERPT_CHARS,
    last_chapter_index: int | None = None,
) -> list[RagDocument]:
    """把小说章节模型标准化为 RAG 文档。"""
    documents: list[RagDocument] = []
    resolved_last_chapter_index = (
        int(last_chapter_index)
        if last_chapter_index is not None and int(last_chapter_index) > 0
        else _chapter_sequence_last_index(chapters)
    )
    for chapter in sorted(chapters, key=_chapter_sort_key):
        chapter_index = int(getattr(chapter, "chapter_index", 0) or 0)
        chapter_public_id = str(getattr(chapter, "public_id", "") or getattr(chapter, "chapter_public_id", "") or "")
        if not chapter_public_id:
            chapter_public_id = str(getattr(chapter, "id", chapter_index) or chapter_index)
        chapter_title = _normalize_text(getattr(chapter, "chapter", "") or getattr(chapter, "chapter_title", ""))
        reel = _normalize_text(getattr(chapter, "reel", ""))
        event = _normalize_text(getattr(chapter, "event", ""))
        excerpt = _text_excerpt(getattr(chapter, "chapter_data", "") or getattr(chapter, "chapter_excerpt", ""), excerpt_chars)
        excerpt_label = "正文摘录" if excerpt_chars > 0 else "正文"
        title = f"第{chapter_index}章 {chapter_title}".strip()
        is_max_chapter_index = resolved_last_chapter_index > 0 and chapter_index == resolved_last_chapter_index
        parts = [
            f"章节序号: {chapter_index}",
            f"章节编号: #{chapter_index}",
            f"章节序列: 第{chapter_index}章",
            f"当前最高章节序号: {resolved_last_chapter_index}" if resolved_last_chapter_index > 0 else "",
            f"是否为最高章节序号: {str(is_max_chapter_index).lower()}"
            if resolved_last_chapter_index > 0
            else "",
            f"标题: {chapter_title}" if chapter_title else "",
            f"卷次: {reel}" if reel else "",
            f"事件: {event}" if event else "",
            f"{excerpt_label}: {excerpt}" if excerpt else "",
        ]
        documents.append(
            RagDocument(
                source_id=f"chapter:{chapter_public_id}",
                source_type="chapter",
                title=title,
                content="\n".join(part for part in parts if part),
                metadata={
                    "chapter_id": getattr(chapter, "id", None),
                    "chapter_public_id": chapter_public_id,
                    "chapter_index": chapter_index,
                    "chapter_max_index": resolved_last_chapter_index,
                    "is_max_chapter_index": is_max_chapter_index,
                    "reel": reel,
                    "chapter_title": chapter_title,
                    "event": event,
                },
            )
        )
    return documents


def build_event_documents(
    chapters: Sequence[Any],
    *,
    last_chapter_index: int | None = None,
) -> list[RagDocument]:
    """把章节结构化事件标准化为 RAG 事件文档。"""
    documents: list[RagDocument] = []
    resolved_last_chapter_index = (
        int(last_chapter_index)
        if last_chapter_index is not None and int(last_chapter_index) > 0
        else _chapter_sequence_last_index(chapters)
    )
    for chapter in sorted(chapters, key=_chapter_sort_key):
        if int(getattr(chapter, "event_state", 0) or 0) != 1:
            continue
        events = _chapter_structured_events(chapter)
        if not events:
            continue
        chapter_index = int(getattr(chapter, "chapter_index", 0) or 0)
        chapter_public_id = str(getattr(chapter, "public_id", "") or getattr(chapter, "chapter_public_id", "") or "")
        if not chapter_public_id:
            chapter_public_id = str(getattr(chapter, "id", chapter_index) or chapter_index)
        chapter_title = _normalize_text(getattr(chapter, "chapter", "") or getattr(chapter, "chapter_title", ""))
        for offset, event in enumerate(events, start=1):
            sequence = event.sequence or offset
            documents.append(
                RagDocument(
                    source_id=f"event:{chapter_public_id}:{sequence}",
                    source_type="event",
                    title=f"第{chapter_index}章 {chapter_title} 事件{sequence}".strip(),
                    content=_event_document_content(
                        event,
                        chapter_index=chapter_index,
                        chapter_title=chapter_title,
                    ),
                    metadata={
                        "chapter_id": getattr(chapter, "id", None),
                        "chapter_public_id": chapter_public_id,
                        "chapter_index": chapter_index,
                        "chapter_max_index": resolved_last_chapter_index,
                        "chapter_title": chapter_title,
                        "event_sequence": sequence,
                        "summary": event.summary,
                        "characters": _metadata_join(event.characters),
                        "scenes": _metadata_join(event.scenes),
                        "organizations": _metadata_join(event.organizations),
                        "event_type": event.event_type,
                        "conflict": event.conflict,
                        "outcome": event.outcome,
                    },
                )
            )
    return documents


def build_project_skill_documents(project: Any, *, config: Settings | None = None) -> list[RagDocument]:
    """读取项目配置中的视觉风格和导演手册 Markdown 资料。"""
    current = config or settings
    documents: list[RagDocument] = []
    documents.extend(
        _load_markdown_skill_documents(
            root=_configured_path(current.visual_style_root),
            skill_path=str(getattr(project, "art_style", "") or ""),
            source_type="art_style",
            title_prefix="视觉风格",
        )
    )
    documents.extend(
        _load_markdown_skill_documents(
            root=_configured_path(current.director_manual_root),
            skill_path=str(getattr(project, "director_manual", "") or ""),
            source_type="director_manual",
            title_prefix="导演手册",
        )
    )
    return documents


async def _load_project_chapters(session: AsyncSession, project: Any) -> list[NovelChapter]:
    project_id = getattr(project, "id", None)
    if project_id is None:
        return []
    statement = (
        select(NovelChapter)
        .where(NovelChapter.project_id == int(project_id))
        .order_by(NovelChapter.chapter_index, NovelChapter.id)
    )
    result = await session.exec(statement)
    return list(result.all())


async def _iter_project_chapter_batches(
    session: AsyncSession,
    project: Any,
    *,
    batch_size: int,
) -> AsyncIterator[list[NovelChapter]]:
    project_id = getattr(project, "id", None)
    if project_id is None:
        return
    offset = 0
    while True:
        statement = (
            select(NovelChapter)
            .where(NovelChapter.project_id == int(project_id))
            .order_by(NovelChapter.chapter_index, NovelChapter.id)
            .offset(offset)
            .limit(batch_size)
        )
        result = await session.exec(statement)
        chapters = list(result.all())
        if not chapters:
            return
        yield chapters
        if len(chapters) < batch_size:
            return
        offset += len(chapters)


async def _load_project_novel_books(session: AsyncSession, project: Any) -> list[NovelCrawlBook]:
    project_id = getattr(project, "id", None)
    if project_id is None:
        return []
    statement = (
        select(NovelCrawlBook)
        .where(NovelCrawlBook.project_id == int(project_id))
        .order_by(NovelCrawlBook.id)
    )
    result = await session.exec(statement)
    return list(result.all())


async def _load_project_last_chapter_index(session: AsyncSession, project: Any) -> int:
    project_id = getattr(project, "id", None)
    if project_id is None:
        return 0
    statement = (
        select(NovelChapter.chapter_index)
        .where(NovelChapter.project_id == int(project_id))
        .order_by(NovelChapter.chapter_index.desc(), NovelChapter.id.desc())
        .limit(1)
    )
    result = await session.exec(statement)
    return int(result.first() or 0)


def _chapter_sort_key(chapter: Any) -> tuple[int, int]:
    return (
        int(getattr(chapter, "chapter_index", 0) or 0),
        int(getattr(chapter, "id", 0) or 0),
    )


def _novel_book_sort_key(book: Any) -> tuple[int, str]:
    return (
        int(getattr(book, "id", 0) or 0),
        _normalize_text(getattr(book, "title", "")),
    )


def _chapter_sequence_last_index(chapters: Sequence[Any]) -> int:
    indices = [int(getattr(chapter, "chapter_index", 0) or 0) for chapter in chapters]
    return max(indices, default=0)


def _chapter_structured_events(chapter: Any) -> tuple[StructuredEvent, ...]:
    raw_event = str(getattr(chapter, "event", "") or "").strip()
    if not raw_event:
        return ()
    try:
        return parse_chapter_events(raw_event)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    return ()


def _event_document_content(
    event: StructuredEvent,
    *,
    chapter_index: int,
    chapter_title: str,
) -> str:
    parts = [
        f"章节序号: {chapter_index}",
        f"章节序列: 第{chapter_index}章",
        f"章节标题: {chapter_title}" if chapter_title else "",
        f"事件序号: {event.sequence}",
        f"事件摘要: {event.summary}" if event.summary else "",
        f"角色: {_human_join(event.characters)}" if event.characters else "",
        f"场景: {_human_join(event.scenes)}" if event.scenes else "",
        f"组织: {_human_join(event.organizations)}" if event.organizations else "",
        f"事件类型: {event.event_type}" if event.event_type else "",
        f"冲突: {event.conflict}" if event.conflict else "",
        f"结果: {event.outcome}" if event.outcome else "",
    ]
    return "\n".join(part for part in parts if part)


def _metadata_join(values: Sequence[str]) -> str:
    return ",".join(str(value).strip() for value in values if str(value).strip())


def _human_join(values: Sequence[str]) -> str:
    return ", ".join(str(value).strip() for value in values if str(value).strip())


def _labeled_parts(item: Any, fields: Sequence[tuple[str, str]]) -> list[str]:
    parts: list[str] = []
    for label, attr_name in fields:
        value = _normalize_text(_field_value(getattr(item, attr_name, "")))
        if value:
            parts.append(f"{label}: {value}")
    return parts


def _field_value(value: Any) -> Any:
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return enum_value
    return value


def _iter_project_skill_document_batches(
    project: Any,
    *,
    config: Settings,
    batch_size: int,
) -> Iterator[list[RagDocument]]:
    yield from _iter_markdown_skill_document_batches(
        root=_configured_path(config.visual_style_root),
        skill_path=str(getattr(project, "art_style", "") or ""),
        source_type="art_style",
        title_prefix="视觉风格",
        batch_size=batch_size,
    )
    yield from _iter_markdown_skill_document_batches(
        root=_configured_path(config.director_manual_root),
        skill_path=str(getattr(project, "director_manual", "") or ""),
        source_type="director_manual",
        title_prefix="导演手册",
        batch_size=batch_size,
    )


def _load_markdown_skill_documents(
    *,
    root: Path,
    skill_path: str,
    source_type: str,
    title_prefix: str,
) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for batch in _iter_markdown_skill_document_batches(
        root=root,
        skill_path=skill_path,
        source_type=source_type,
        title_prefix=title_prefix,
        batch_size=10_000,
    ):
        documents.extend(batch)
    return documents


def _iter_markdown_skill_document_batches(
    *,
    root: Path,
    skill_path: str,
    source_type: str,
    title_prefix: str,
    batch_size: int,
) -> Iterator[list[RagDocument]]:
    skill_dir = _safe_skill_dir(root, skill_path)
    if skill_dir is None or not skill_dir.exists() or not skill_dir.is_dir():
        return

    batch: list[RagDocument] = []
    for file_path in sorted(skill_dir.rglob("*.md")):
        if not file_path.is_file():
            continue
        try:
            relative_path = file_path.resolve().relative_to(skill_dir).as_posix()
        except ValueError:
            continue
        content = file_path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        batch.append(
            RagDocument(
                source_id=f"{source_type}:{skill_dir.name}:{relative_path}",
                source_type=source_type,
                title=f"{title_prefix} {skill_dir.name} {relative_path}",
                content=content,
                metadata={"skill_path": skill_dir.name, "file_path": relative_path},
            )
        )
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _safe_skill_dir(root: Path, skill_path: str) -> Path | None:
    value = skill_path.strip()
    if not value or not SKILL_PATH_PATTERN.fullmatch(value) or value in {".", ".."} or value.isdigit():
        return None
    resolved_root = root.resolve()
    candidate = (resolved_root / value).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate


def _configured_path(value: str) -> Path:
    configured = Path(value).expanduser()
    return (configured if configured.is_absolute() else BASE_DIR / configured).resolve()


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _text_excerpt(value: Any, limit: int) -> str:
    text = _normalize_text(value)
    if limit <= 0:
        return text
    return text[:limit]
