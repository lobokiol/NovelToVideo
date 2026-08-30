from __future__ import annotations

import asyncio
import hashlib
from collections import Counter
from collections.abc import AsyncIterator
import json
import logging
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import database
from app.core.config import settings
from app.core.tasks.engine import default_async_task_engine
from app.models.novel import NovelChapter, NovelCrawlBook, NovelCrawlSource
from app.models.tasks import TaskJob, TaskStatus
from app.schemas.novel import (
    CrawlAnalyzePayload,
    CrawlAnalyzeResult,
    CrawlBookChapterCountResult,
    CrawlBookDetailResult,
    CrawlBookPayload,
    CrawlChapterDraft,
    CrawlChapterFetchPayload,
    CrawlImportPayload,
    CrawlImportResult,
    CrawlSearchPayload,
    CrawlSearchResult,
    CrawlSourceDuplicate,
    CrawlSourcePayload,
    CrawlSourceRead,
    CrawlSourceUpdate,
    NovelChapterBatchClean,
    NovelChapterBatchCleanActiveJob,
    NovelChapterBatchCleanActiveJobList,
    NovelChapterBatchCleanCancelResult,
    NovelChapterBatchDelete,
    NovelChapterBatchCleanItem,
    NovelChapterBatchCleanProgress,
    NovelChapterBatchResult,
    NovelChapterCleanStatus,
    NovelChapterCreate,
    NovelChapterEventStateUpdate,
    NovelChapterImport,
    NovelChapterPage,
    NovelChapterRead,
    NovelChapterUpdate,
    NovelImportSplitRule,
    ScreenwritingPreflightCheck,
    ScreenwritingPreflightResult,
)
from app.schemas.tasks import TaskItemCreate, TaskItemRead, TaskJobCreate, TaskJobDetail
from app.services.agent_gateway import ProviderModelGateway
from app.services.prompt_registry import PromptRegistry
from app.services import novel_crawler
from app.services import project as project_service
from app.services import tasks as task_service
from app.services.screenwriting.event_extraction import events_to_json, parse_chapter_events
from app.utils.novel_import_rules import get_builtin_import_split_rules
from app.utils.novel_parser import ParsedNovelChapter, parse_novel_chapters
from app.utils.time_tools import utc_now


CRAWL_SOURCE_CONFIG_FIELDS = (
    "name",
    "base_url",
    "desc",
    "source_type",
    "search_url_template",
    "api_search_method",
    "api_search_headers",
    "api_search_body",
    "api_search_book_url_path",
    "api_search_book_id_path",
    "api_search_book_title_path",
    "api_search_book_author_path",
    "api_search_book_intro_path",
    "api_search_book_cover_path",
    "api_search_book_category_path",
    "api_search_book_update_status_path",
    "api_search_book_last_chapter_path",
    "api_search_book_last_chapter_id_path",
    "api_search_book_last_update_path",
    "api_book_url",
    "api_book_method",
    "api_book_headers",
    "api_book_body",
    "api_book_title_path",
    "api_book_author_path",
    "api_book_intro_path",
    "api_book_last_chapter_path",
    "api_book_last_chapter_id_path",
    "api_book_last_update_path",
    "api_book_cover_path",
    "api_book_category_path",
    "api_book_update_status_path",
    "api_book_id_path",
    "api_chapter_list_url",
    "api_chapter_list_method",
    "api_chapter_list_headers",
    "api_chapter_list_body",
    "api_chapter_list_id_path",
    "api_chapter_list_name_path",
    "api_chapter_list_time_path",
    "api_chapter_list_content_path",
    "api_chapter_list_md5_path",
    "api_chapter_url",
    "api_chapter_method",
    "api_chapter_headers",
    "api_chapter_body",
    "api_chapter_name_path",
    "api_chapter_content_path",
    "api_chapter_time_path",
    "api_chapter_md5_path",
)

# 要求单章字数必须长度在800以上才会交给大模型。
MIN_EVENT_EXTRACTION_CONTENT_LENGTH = 300
# 单章事件清晰的并发数量（设置最多允许多少个清洗任务同时执行，默认设为3）
SINGLE_CHAPTER_CLEAN_MAX_CONCURRENCY = 3
NOVEL_CHAPTER_CLEAN_TASK_TYPE = "novel.chapter.clean_event"
NOVEL_CHAPTER_CLEAN_QUEUE_NAME = "novel"
BATCH_CLEAN_STREAM_INTERVAL_SECONDS = 2.0
# 进入剧本创作前，要求事件提取成功的章节数量下限。
SCREENWRITING_REQUIRED_EVENT_COUNT = 10
logger = logging.getLogger(__name__)
_single_chapter_clean_tasks: set[asyncio.Task[None]] = set()
_single_chapter_clean_semaphore: asyncio.Semaphore | None = None
_single_chapter_clean_semaphore_loop: asyncio.AbstractEventLoop | None = None


class NovelServiceError(Exception):
    """小说服务层基础异常。"""


class NovelChapterNotFoundError(NovelServiceError):
    """小说章节不存在。"""


class NovelChapterValidationError(NovelServiceError):
    """小说章节请求不合法。"""


class NovelCrawlSourceNotFoundError(NovelServiceError):
    """小说爬取来源不存在，或当前项目不可见。"""


class NovelCrawlSourceValidationError(NovelServiceError):
    """小说爬取来源配置或爬取请求不合法。"""


def _crawl_error_message(exc: Exception) -> str:
    return str(exc).strip() or f"爬取请求失败: {exc.__class__.__name__}"


async def list_chapters(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    *,
    page: int = 1,
    limit: int = 20,
    search: str = "",
) -> NovelChapterPage:
    """分页获取指定项目下的小说章节。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    conditions = [NovelChapter.project_id == project.id]
    keyword = search.strip()
    if keyword:
        conditions.append(
            or_(
                NovelChapter.chapter.ilike(f"%{keyword}%"),
                NovelChapter.reel.ilike(f"%{keyword}%"),
            )
        )

    count_statement = select(func.count()).select_from(NovelChapter).where(*conditions)
    count_result = await session.exec(count_statement)
    total = int(count_result.one())

    statement = (
        select(NovelChapter)
        .where(*conditions)
        .order_by(NovelChapter.chapter_index, NovelChapter.id)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.exec(statement)
    chapters = list(result.all())
    return NovelChapterPage(
        data=[_to_read(chapter) for chapter in chapters],
        total=total,
        page=page,
        limit=limit,
    )


async def get_chapter(
    session: AsyncSession,
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
) -> NovelChapterRead:
    """获取指定项目下的单个小说章节。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapter = await _get_chapter_model_or_raise(session, project.id, chapter_id)
    return _to_read(chapter)


async def list_chapter_clean_statuses(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    chapter_ids: list[int],
) -> list[NovelChapterCleanStatus]:
    """批量获取章节事件清洗状态，不返回章节正文。"""
    if not chapter_ids:
        raise NovelChapterValidationError("请选择要查询的章节")
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapters = await _list_chapter_models_by_ids(session, project.id, chapter_ids)
    return [_to_clean_status(chapter) for chapter in chapters]


async def get_screenwriting_preflight(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
) -> ScreenwritingPreflightResult:
    """校验当前项目是否满足进入剧本创作的准入条件。

    校验项：
        1. 项目已配置文本模型；
        2. 事件提取成功（event_state==1）的章节数达到下限。
    """
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)

    text_model = project.text_model.strip()
    text_model_passed = bool(text_model)

    count_statement = (
        select(func.count())
        .select_from(NovelChapter)
        .where(
            NovelChapter.project_id == project.id,
            NovelChapter.event_state == 1,
        )
    )
    count_result = await session.exec(count_statement)
    event_ready_count = int(count_result.one())
    required = SCREENWRITING_REQUIRED_EVENT_COUNT
    event_passed = event_ready_count >= required

    checks = [
        ScreenwritingPreflightCheck(
            key="text_model",
            label="已配置文本模型",
            passed=text_model_passed,
            detail=(
                f"当前文本模型：{text_model}"
                if text_model_passed
                else "项目尚未配置文本模型，请先在项目设置中选择文本模型"
            ),
        ),
        ScreenwritingPreflightCheck(
            key="chapter_events",
            label=f"已完成至少 {required} 章事件提取",
            passed=event_passed,
            detail=(
                f"已完成事件提取 {event_ready_count} 章"
                if event_passed
                else f"已完成事件提取 {event_ready_count} 章，至少需要 {required} 章，请先在小说页清洗章节事件"
            ),
        ),
    ]

    return ScreenwritingPreflightResult(
        ready=text_model_passed and event_passed,
        required_event_count=required,
        event_ready_count=event_ready_count,
        text_model=text_model,
        checks=checks,
    )


async def create_chapter(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: NovelChapterCreate,
) -> NovelChapterRead:
    """创建小说章节。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    now = utc_now()
    chapter_data = payload.chapter_data.strip()
    chapter = NovelChapter(
        project_id=project.id,
        chapter_index=payload.chapter_index,
        reel=payload.reel.strip(),
        chapter=payload.chapter.strip(),
        chapter_data=chapter_data,
        event=payload.event.strip(),
        event_state=_state_for_event(payload.event, payload.event_state),
        error_reason=payload.error_reason,
        crawl_source_key=payload.crawl_source_key.strip(),
        crawl_novel_dirid=payload.crawl_novel_dirid.strip(),
        crawl_chapter_id=payload.crawl_chapter_id,
        crawl_time=payload.crawl_time.strip(),
        crawl_md5=_chapter_content_md5(chapter_data),
        created_at=now,
        updated_at=now,
    )
    session.add(chapter)
    await session.commit()
    await session.refresh(chapter)
    return _to_read(chapter)


async def update_chapter(
    session: AsyncSession,
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
    payload: NovelChapterUpdate,
) -> NovelChapterRead:
    """更新小说章节。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapter = await _get_chapter_model_or_raise(session, project.id, chapter_id)
    fields = payload.model_fields_set
    values = payload.model_dump(exclude_unset=True)
    for field_name, value in values.items():
        if field_name == "crawl_md5":
            continue
        if isinstance(value, str):
            value = value.strip()
        setattr(chapter, field_name, value)

    if "event" in fields and "event_state" not in fields:
        chapter.event_state = 1 if chapter.event.strip() else 0
        chapter.error_reason = None
    if "event_state" in fields and chapter.event_state == 0:
        chapter.error_reason = None
    if "chapter_data" in fields:
        chapter.crawl_md5 = _chapter_content_md5(chapter.chapter_data)

    chapter.updated_at = utc_now()
    session.add(chapter)
    await session.commit()
    await session.refresh(chapter)
    return _to_read(chapter)


async def delete_chapter(
    session: AsyncSession,
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
) -> None:
    """删除小说章节。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapter = await _get_chapter_model_or_raise(session, project.id, chapter_id)
    await session.delete(chapter)
    await session.commit()


async def batch_delete_chapters(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: NovelChapterBatchDelete,
) -> NovelChapterBatchResult:
    """批量删除小说章节。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapters = await _list_chapter_models_by_ids(session, project.id, payload.ids)
    for chapter in chapters:
        await session.delete(chapter)
    await session.commit()
    return NovelChapterBatchResult(affected=len(chapters))


async def import_chapters(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: NovelChapterImport,
) -> list[NovelChapterRead]:
    """解析全文并导入为章节。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    parsed_chapters = _parse_import_payload(payload)
    if not parsed_chapters:
        raise NovelChapterValidationError("No chapter content found")

    start_index = await _next_chapter_index(session, project.id)
    now = utc_now()
    chapters = [
        NovelChapter(
            project_id=project.id,
            chapter_index=start_index + index,
            reel=item.reel,
            chapter=item.chapter,
            chapter_data=item.chapter_data,
            event="",
            event_state=0,
            error_reason=None,
            crawl_md5=_chapter_content_md5(item.chapter_data),
            created_at=now,
            updated_at=now,
        )
        for index, item in enumerate(parsed_chapters)
    ]
    session.add_all(chapters)
    await session.commit()
    for chapter in chapters:
        await session.refresh(chapter)
    return [_to_read(chapter) for chapter in chapters]


def list_import_split_rules() -> list[NovelImportSplitRule]:
    """返回前端导入弹窗使用的内置章节切分规则。"""
    return [
        NovelImportSplitRule(
            key=rule.key,
            label=rule.label,
            description=rule.description,
            chapter_pattern=rule.chapter_pattern,
            chapter_flags_list=list(rule.chapter_flags_list),
            reel_pattern=rule.reel_pattern,
            reel_flags_list=list(rule.reel_flags_list),
            builtin=True,
        )
        for rule in get_builtin_import_split_rules()
    ]


async def list_crawl_sources(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
) -> list[CrawlSourceRead]:
    """列出当前项目可见的公共来源和项目私有来源。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    statement = (
        select(NovelCrawlSource)
        .where(
            NovelCrawlSource.disabled_at.is_(None),
            or_(NovelCrawlSource.scope == "public", NovelCrawlSource.project_id == project.id),
        )
        .order_by(NovelCrawlSource.sort_order, NovelCrawlSource.id)
    )
    result = await session.exec(statement)
    return [_to_crawl_source_read(source, project_public_id if source.project_id == project.id else None) for source in result.all()]


async def create_crawl_source(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: CrawlSourcePayload,
) -> CrawlSourceRead:
    """创建项目私有的 API 小说爬取来源。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    await _ensure_crawl_source_key_available(session, payload.key)
    now = utc_now()
    source = NovelCrawlSource(
        project_id=project.id,
        owner_public_id=current_user_public_id,
        key=payload.key.strip(),
        builtin=False,
        scope="private",
        created_at=now,
        updated_at=now,
    )
    _apply_crawl_source_values(source, payload.model_dump())
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return _to_crawl_source_read(source, project_public_id)


async def update_crawl_source(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    key: str,
    payload: CrawlSourceUpdate,
) -> CrawlSourceRead:
    """更新项目私有的小说爬取来源。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    source = await _get_project_crawl_source_or_raise(session, project.id, key)
    _apply_crawl_source_values(source, payload.model_dump(exclude_unset=True))
    source.updated_at = utc_now()
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return _to_crawl_source_read(source, project_public_id)


async def delete_crawl_source(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    key: str,
) -> None:
    """删除项目私有的小说爬取来源。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    source = await _get_project_crawl_source_or_raise(session, project.id, key)
    await session.delete(source)
    await session.commit()


async def duplicate_crawl_source(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    key: str,
    payload: CrawlSourceDuplicate,
) -> CrawlSourceRead:
    """把可见来源复制到当前项目。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    origin = await _get_visible_crawl_source_or_raise(session, project.id, key)
    await _ensure_crawl_source_key_available(session, payload.new_key)
    now = utc_now()
    source = NovelCrawlSource(
        project_id=project.id,
        owner_public_id=current_user_public_id,
        key=payload.new_key.strip(),
        builtin=False,
        scope="private",
        created_at=now,
        updated_at=now,
    )
    values = {field: getattr(origin, field) for field in CRAWL_SOURCE_CONFIG_FIELDS}
    if payload.name:
        values["name"] = payload.name
    _apply_crawl_source_values(source, values)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return _to_crawl_source_read(source, project_public_id)


async def analyze_crawl_source(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: CrawlAnalyzePayload,
) -> CrawlAnalyzeResult:
    """返回用于手动配置的来源草稿。"""
    await _get_project_with_id(session, project_public_id, current_user_public_id)
    return CrawlAnalyzeResult(
        status="pending",
        source=CrawlSourcePayload(
            key="custom_source",
            name="Custom Source",
            baseUrl=payload.url,
            sourceType="api",
            searchUrlTemplate="",
            builtin=False,
            projectPublicId=project_public_id,
        ),
        message="Source analysis is not automated yet. Please complete the API paths manually.",
    )


async def search_crawl_books(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: CrawlSearchPayload,
) -> list[CrawlSearchResult]:
    """通过选中的小说来源搜索小说。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    source = await _get_visible_crawl_source_or_raise(session, project.id, payload.source_key)
    try:
        return await novel_crawler.search_books(source, payload.query)
    except Exception as exc:
        raise NovelCrawlSourceValidationError(_crawl_error_message(exc)) from exc


async def fetch_crawl_book_detail(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: CrawlBookPayload,
) -> CrawlBookDetailResult:
    """获取选中小说详情，并持久化爬取小说快照。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    source = await _get_visible_crawl_source_or_raise(session, project.id, payload.source_key)
    try:
        book = await novel_crawler.fetch_book_detail(source, payload.book)
    except Exception as exc:
        raise NovelCrawlSourceValidationError(_crawl_error_message(exc)) from exc
    await _upsert_crawl_book(session, project.id, source.key, book)
    await session.commit()
    return CrawlBookDetailResult(book=book)


async def fetch_crawl_book_chapter_count(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: CrawlBookPayload,
) -> CrawlBookChapterCountResult:
    """获取选中小说的章节总数。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    source = await _get_visible_crawl_source_or_raise(session, project.id, payload.source_key)
    try:
        count = await novel_crawler.fetch_chapter_count(source, payload.book)
    except Exception as exc:
        raise NovelCrawlSourceValidationError(_crawl_error_message(exc)) from exc
    book = payload.book.model_copy(update={"lastchapterid": count, "source_key": payload.source_key})
    await _upsert_crawl_book(session, project.id, source.key, book)
    await session.commit()
    return CrawlBookChapterCountResult(book=book, lastchapterid=count)


async def fetch_crawl_chapters(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: CrawlChapterFetchPayload,
) -> list[CrawlChapterDraft]:
    """爬取指定范围内的章节。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    source = await _get_visible_crawl_source_or_raise(session, project.id, payload.source_key)
    try:
        return await novel_crawler.fetch_chapters(source, payload.book, payload.start_chapter, payload.end_chapter)
    except Exception as exc:
        raise NovelCrawlSourceValidationError(_crawl_error_message(exc)) from exc


async def build_crawl_chapter_stream(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: CrawlChapterFetchPayload,
) -> AsyncIterator[dict[str, object]]:
    """创建指定章节范围的爬取进度流。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    source = await _get_visible_crawl_source_or_raise(session, project.id, payload.source_key)

    async def generate() -> AsyncIterator[dict[str, object]]:
        completed = 0
        total = max(payload.end_chapter - payload.start_chapter + 1, 0)
        try:
            async for event in novel_crawler.stream_chapters(
                source,
                payload.book,
                payload.start_chapter,
                payload.end_chapter,
            ):
                if event.get("type") == "chapter":
                    completed = int(event.get("completed") or completed)
                    total = int(event.get("total") or total)
                yield event
        except Exception as exc:
            yield {
                "type": "error",
                "detail": str(exc),
                "completed": completed,
                "total": total,
            }

    return generate()


async def import_crawl_chapters(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: CrawlImportPayload,
) -> CrawlImportResult:
    """把已爬取章节导入现有小说章节表。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    source = await _get_visible_crawl_source_or_raise(session, project.id, payload.source_key)
    book = payload.book.model_copy(update={"source_key": source.key})
    await _upsert_crawl_book(session, project.id, source.key, book)

    start_index = await _next_chapter_index(session, project.id)
    now = utc_now()
    created = 0
    updated = 0
    skipped = 0
    touched: list[NovelChapter] = []

    for draft in sorted(payload.chapters, key=lambda item: (item.key, item.chapterid)):
        chapter_text = draft.txt.strip()
        chapter_name = draft.chaptername.strip()
        if not chapter_text or not chapter_name:
            skipped += 1
            continue
        existing = await _get_chapter_by_crawl_identity(
            session,
            project.id,
            source.key,
            draft.novel_dirid or book.dirid,
            draft.chapterid,
        )
        if existing is not None:
            if (
                existing.chapter == chapter_name
                and existing.chapter_data == chapter_text
                and existing.event == draft.event.strip()
                and existing.event_state == draft.event_state
            ):
                skipped += 1
                continue
            existing.chapter = chapter_name
            existing.chapter_data = chapter_text
            existing.event = draft.event.strip()
            existing.event_state = draft.event_state
            existing.error_reason = draft.error_reason
            existing.crawl_time = draft.time.strip()
            existing.crawl_md5 = draft.md5.strip() or _chapter_content_md5(chapter_text)
            existing.updated_at = now
            session.add(existing)
            touched.append(existing)
            updated += 1
            continue

        chapter = NovelChapter(
            project_id=project.id,
            chapter_index=start_index + created,
            reel="",
            chapter=chapter_name,
            chapter_data=chapter_text,
            event=draft.event.strip(),
            event_state=draft.event_state,
            error_reason=draft.error_reason,
            crawl_source_key=source.key,
            crawl_novel_dirid=(draft.novel_dirid or book.dirid).strip(),
            crawl_chapter_id=draft.chapterid,
            crawl_time=draft.time.strip(),
            crawl_md5=draft.md5.strip() or _chapter_content_md5(chapter_text),
            created_at=now,
            updated_at=now,
        )
        session.add(chapter)
        touched.append(chapter)
        created += 1

    await session.commit()
    for chapter in touched:
        await session.refresh(chapter)
    return CrawlImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        chapters=[_to_read(chapter) for chapter in touched],
    )


def _parse_import_payload(payload: NovelChapterImport) -> list[ParsedNovelChapter]:
    """优先返回预览草稿解析结果，否则解析原始文本。"""
    if payload.chapters:
        parsed_chapters: list[ParsedNovelChapter] = []
        for index, item in enumerate(payload.chapters, start=1):
            chapter = item.chapter.strip()
            chapter_data = item.chapter_data.strip()
            if not chapter or not chapter_data:
                continue
            parsed_chapters.append(
                ParsedNovelChapter(
                    chapter_index=index,
                    reel=item.reel.strip(),
                    chapter=chapter,
                    chapter_data=chapter_data,
                )
            )
        return parsed_chapters
    return parse_novel_chapters(payload.raw_text)


async def clean_chapter(
    session: AsyncSession,
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
) -> NovelChapterRead:
    """清洗单个章节事件。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapter = await _get_chapter_model_or_raise(session, project.id, chapter_id)
    await _apply_chapter_event_extraction(chapter, project.text_model)
    chapter.updated_at = utc_now()
    session.add(chapter)
    await session.commit()
    await session.refresh(chapter)
    return _to_read(chapter)


async def clean_chapter_for_task(
    session: AsyncSession,
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
    *,
    model_id: str = "",
) -> dict[str, Any]:
    """清洗异步任务章节事件，并返回可写入任务结果的执行载荷。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapter = await _get_chapter_model_or_raise(session, project.id, chapter_id)
    prompt_trace = await _apply_chapter_event_extraction(chapter, model_id.strip() or project.text_model)
    chapter.updated_at = utc_now()
    session.add(chapter)
    await session.commit()
    await session.refresh(chapter)
    return _chapter_clean_task_result(chapter, prompt_trace)


async def queue_clean_chapter(
    session: AsyncSession,
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
) -> NovelChapterRead:
    """提交单章事件提取前，将章节重置为待清洗状态。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapter = await _get_chapter_model_or_raise(session, project.id, chapter_id)
    chapter.event = ""
    chapter.event_state = 0
    chapter.error_reason = None
    chapter.updated_at = utc_now()
    session.add(chapter)
    await session.commit()
    await session.refresh(chapter)
    return _to_read(chapter)


async def clean_chapter_in_background(
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
) -> None:
    """在后台任务中使用独立数据库会话清洗单章事件。"""
    async with database.async_session_maker() as session:
        try:
            await clean_chapter(session, project_public_id, chapter_id, current_user_public_id)
        except Exception:
            await session.rollback()
            logger.exception(
                "后台清洗章节事件失败：project_public_id=%s chapter_id=%s",
                project_public_id,
                chapter_id,
            )


def submit_clean_chapter_task(
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
) -> None:
    """提交单章事件清洗任务，并允许多个章节在后台并发处理。"""
    # 把清洗章节任务放后台（无阻塞）异步运行
    task = asyncio.create_task(
        _run_submitted_clean_chapter_task(
            project_public_id,
            chapter_id,
            current_user_public_id,
        )
    )
    # 添加任务记录到数据库
    _single_chapter_clean_tasks.add(task)
    # 回调函数
    task.add_done_callback(_discard_single_chapter_clean_task)


async def _run_submitted_clean_chapter_task(
    project_public_id: str,
    chapter_id: int,
    current_user_public_id: str,
) -> None:
    semaphore = _get_single_chapter_clean_semaphore()
    async with semaphore:
        await clean_chapter_in_background(project_public_id, chapter_id, current_user_public_id)


def _get_single_chapter_clean_semaphore() -> asyncio.Semaphore:
    global _single_chapter_clean_semaphore, _single_chapter_clean_semaphore_loop

    loop = asyncio.get_running_loop()
    if _single_chapter_clean_semaphore is None or _single_chapter_clean_semaphore_loop is not loop:
        _single_chapter_clean_semaphore = asyncio.Semaphore(SINGLE_CHAPTER_CLEAN_MAX_CONCURRENCY)
        _single_chapter_clean_semaphore_loop = loop
    return _single_chapter_clean_semaphore


def _discard_single_chapter_clean_task(task: asyncio.Task[None]) -> None:
    # 把任务结果注册到内存的列表中，后面我们实现批量章节清洗时，会使用Redis/RabbitMQ替代_single_chapter_clean_tasks
    _single_chapter_clean_tasks.discard(task)
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.error(
            "单章事件清洗任务异常",
            exc_info=(type(exc), exc, exc.__traceback__),
        )


async def batch_clean_chapters(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: NovelChapterBatchClean,
) -> NovelChapterBatchCleanProgress:
    """提交批量章节事件清洗异步任务，并返回初始进度快照。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapters = await _list_chapter_models_by_ids(session, project.id, payload.ids)
    if not chapters:
        raise NovelChapterValidationError("未找到任何待清洗章节")

    now = utc_now()
    model_id = project.text_model.strip()
    if not model_id:
        raise NovelChapterValidationError("项目未配置文本模型，无法提交批量清洗任务")
    items: list[TaskItemCreate] = []
    for chapter in chapters:
        chapter_id = int(chapter.id or 0)
        chapter.event = ""
        chapter.event_state = 0
        chapter.error_reason = None
        chapter.updated_at = now
        session.add(chapter)
        items.append(
            TaskItemCreate(
                item_type=NOVEL_CHAPTER_CLEAN_TASK_TYPE,
                item_key=f"chapter:{chapter_id}",
                payload={
                    "project_public_id": project_public_id,
                    "chapter_id": chapter_id,
                    "chapter_public_id": chapter.public_id,
                    "chapter_index": chapter.chapter_index,
                    "chapter_title": chapter.chapter,
                    "reel": chapter.reel,
                    "model_id": model_id,
                    "current_user_public_id": current_user_public_id,
                },
            )
        )

    await session.flush()
    job = await default_async_task_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=NOVEL_CHAPTER_CLEAN_TASK_TYPE,
            queue_name=NOVEL_CHAPTER_CLEAN_QUEUE_NAME,
            name="批量清洗章节事件",
            created_by=current_user_public_id,
            payload={
                "project_public_id": project_public_id,
                "chapter_count": len(chapters),
                "model_id": model_id,
            },
            items=items,
        ),
    )
    return await get_batch_clean_job_progress(
        session,
        project_public_id,
        current_user_public_id,
        job.public_id,
    )


async def get_batch_clean_job_progress(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    job_public_id: str,
) -> NovelChapterBatchCleanProgress:
    """查询批量清洗任务当前进度快照。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    job = await _get_batch_clean_job_detail_or_raise(session, project_public_id, job_public_id)
    chapter_ids = [_chapter_id_from_task_item(item) for item in job.items]
    chapters = await _list_chapter_models_by_ids(
        session,
        project.id,
        [chapter_id for chapter_id in chapter_ids if chapter_id > 0],
    )
    chapter_map = {int(chapter.id or 0): chapter for chapter in chapters}

    counts: Counter[str] = Counter()
    item_views: list[NovelChapterBatchCleanItem] = []
    for item in job.items:
        chapter_id = _chapter_id_from_task_item(item)
        chapter = chapter_map.get(chapter_id)
        item_status = _frontend_item_status(item.status, chapter)
        counts[item_status] += 1
        item_views.append(_to_batch_clean_item(item, chapter, chapter_id, item_status))

    total_count = len(job.items)
    finished_count = counts["succeeded"] + counts["failed"] + counts["canceled"]
    return NovelChapterBatchCleanProgress(
        jobPublicId=job.public_id,
        jobStatus=_frontend_job_status(job.status, counts, total_count),
        totalCount=total_count,
        pendingCount=counts["pending"],
        runningCount=counts["running"],
        succeededCount=counts["succeeded"],
        failedCount=counts["failed"],
        canceledCount=counts["canceled"],
        pausedCount=counts["paused"],
        finishedCount=finished_count,
        isFinished=total_count > 0 and finished_count == total_count,
        items=item_views,
    )


async def stream_batch_clean_job_progress(
    project_public_id: str,
    current_user_public_id: str,
    job_public_id: str,
    *,
    interval_seconds: float = BATCH_CLEAN_STREAM_INTERVAL_SECONDS,
) -> AsyncIterator[NovelChapterBatchCleanProgress]:
    """按 SSE 使用场景持续产出批量清洗任务进度。"""
    while True:
        async with database.async_session_maker() as session:
            progress = await get_batch_clean_job_progress(
                session,
                project_public_id,
                current_user_public_id,
                job_public_id,
            )
        yield progress
        if progress.is_finished:
            return
        await asyncio.sleep(max(interval_seconds, 0.1))


async def cancel_batch_clean_job(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    job_public_id: str,
) -> NovelChapterBatchCleanCancelResult:
    """取消批量清洗任务中尚未执行的章节子项。"""
    await _get_project_with_id(session, project_public_id, current_user_public_id)
    before = await _get_batch_clean_job_detail_or_raise(session, project_public_id, job_public_id)
    cancellable_count = sum(
        1
        for item in before.items
        if item.status in {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.PAUSED}
    )
    await default_async_task_engine.cancel_task_job(session, job_public_id)
    return NovelChapterBatchCleanCancelResult(
        jobPublicId=job_public_id,
        canceledCount=cancellable_count,
    )


async def list_active_batch_clean_jobs(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
) -> NovelChapterBatchCleanActiveJobList:
    """列出当前项目下未结束的批量清洗任务，用于客户端恢复 SSE 订阅。"""
    await _get_project_with_id(session, project_public_id, current_user_public_id)
    active_statuses = {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.PAUSED}
    statement = (
        select(TaskJob)
        .where(
            TaskJob.task_type == NOVEL_CHAPTER_CLEAN_TASK_TYPE,
            TaskJob.status.in_(active_statuses),
            TaskJob.disabled_at.is_(None),
        )
        .order_by(TaskJob.created_at.desc(), TaskJob.id.desc())
    )
    result = await session.exec(statement)
    items: list[NovelChapterBatchCleanActiveJob] = []
    for job in result.all():
        if _payload_project_public_id(job.payload) != project_public_id:
            continue
        task_job = await default_async_task_engine.get_task_job(session, job.public_id, include_items=True)
        if not isinstance(task_job, TaskJobDetail):
            continue
        counts = Counter(_frontend_item_status(item.status, None) for item in task_job.items)
        items.append(
            NovelChapterBatchCleanActiveJob(
                jobPublicId=task_job.public_id,
                jobStatus=_frontend_active_job_status(task_job.status),
                totalCount=len(task_job.items),
                pendingCount=counts["pending"],
                runningCount=counts["running"],
                pausedCount=counts["paused"],
                createdAt=task_job.created_at,
            )
        )
    return NovelChapterBatchCleanActiveJobList(items=items)


async def _get_batch_clean_job_detail_or_raise(
    session: AsyncSession,
    project_public_id: str,
    job_public_id: str,
) -> TaskJobDetail:
    try:
        task_job = await default_async_task_engine.get_task_job(session, job_public_id, include_items=True)
    except task_service.TaskJobNotFoundError as exc:
        raise NovelChapterNotFoundError("批量清洗任务不存在") from exc
    if not isinstance(task_job, TaskJobDetail):
        raise NovelChapterValidationError("批量清洗任务读取失败")
    if task_job.task_type != NOVEL_CHAPTER_CLEAN_TASK_TYPE:
        raise NovelChapterNotFoundError("批量清洗任务不存在")
    if task_job.queue_name != NOVEL_CHAPTER_CLEAN_QUEUE_NAME:
        raise NovelChapterNotFoundError("批量清洗任务不存在")
    if str(task_job.payload.get("project_public_id") or "") != project_public_id:
        raise NovelChapterNotFoundError("批量清洗任务不存在")
    return task_job


def _to_batch_clean_item(
    item: TaskItemRead,
    chapter: NovelChapter | None,
    chapter_id: int,
    item_status: str,
) -> NovelChapterBatchCleanItem:
    payload = item.payload
    return NovelChapterBatchCleanItem(
        chapterId=chapter_id,
        chapterPublicId=str(payload.get("chapter_public_id") or (chapter.public_id if chapter is not None else "")),
        chapterIndex=int(payload.get("chapter_index") or (chapter.chapter_index if chapter is not None else 0) or 0),
        chapterTitle=str(payload.get("chapter_title") or (chapter.chapter if chapter is not None else "")),
        reel=str(payload.get("reel") or (chapter.reel if chapter is not None else "")),
        itemPublicId=item.public_id,
        itemStatus=item_status,
        eventState=_batch_clean_event_state(item, chapter),
        event=(chapter.event if chapter is not None else str(item.result.get("event") or "")),
        errorReason=_batch_clean_error_reason(item, chapter),
    )


def _chapter_id_from_task_item(item: TaskItemRead) -> int:
    raw_value = item.payload.get("chapter_id")
    if raw_value is None and item.item_key:
        raw_value = item.item_key.removeprefix("chapter:")
    try:
        chapter_id = int(raw_value)
    except (TypeError, ValueError):
        return 0
    return max(chapter_id, 0)


def _frontend_item_status(status: TaskStatus, chapter: NovelChapter | None) -> str:
    if status == TaskStatus.QUEUED:
        return "pending"
    if status == TaskStatus.CANCELLED:
        return "canceled"
    if status == TaskStatus.SUCCEEDED and chapter is not None and chapter.event_state == -1:
        return "failed"
    if status == TaskStatus.SUCCEEDED:
        return "succeeded"
    if status == TaskStatus.FAILED:
        return "failed"
    if status == TaskStatus.RUNNING:
        return "running"
    if status == TaskStatus.PAUSED:
        return "paused"
    return "pending"


def _frontend_job_status(status: TaskStatus, counts: Counter[str], total_count: int) -> str:
    finished_count = counts["succeeded"] + counts["failed"] + counts["canceled"]
    if total_count > 0 and finished_count == total_count:
        if counts["failed"] and counts["succeeded"]:
            return "partial_failed"
        if counts["failed"]:
            return "failed"
        if counts["canceled"]:
            return "canceled"
        return "succeeded"
    if status == TaskStatus.CANCELLED:
        return "canceled"
    if status == TaskStatus.PARTIAL:
        return "partial_failed"
    if status == TaskStatus.QUEUED:
        return "pending"
    return status.value


def _frontend_active_job_status(status: TaskStatus) -> str:
    if status == TaskStatus.RUNNING:
        return "running"
    if status == TaskStatus.PAUSED:
        return "paused"
    return "pending"


def _batch_clean_event_state(item: TaskItemRead, chapter: NovelChapter | None) -> int:
    if chapter is not None:
        return chapter.event_state
    if item.status == TaskStatus.FAILED:
        return -1
    raw_state = item.result.get("event_state")
    try:
        return int(raw_state)
    except (TypeError, ValueError):
        return 0


def _batch_clean_error_reason(item: TaskItemRead, chapter: NovelChapter | None) -> str | None:
    if chapter is not None and chapter.error_reason:
        return chapter.error_reason
    if item.error_message:
        return item.error_message
    raw_reason = item.result.get("error_reason")
    return str(raw_reason) if raw_reason else None


def _payload_project_public_id(raw_payload: str) -> str:
    try:
        payload = json.loads(raw_payload or "{}")
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("project_public_id") or "")


async def update_event_state(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: NovelChapterEventStateUpdate,
) -> NovelChapterBatchResult:
    """批量更新章节事件状态。"""
    project = await _get_project_with_id(session, project_public_id, current_user_public_id)
    chapters = await _list_chapter_models_by_ids(session, project.id, payload.ids)
    now = utc_now()
    for chapter in chapters:
        chapter.event_state = payload.event_state
        if payload.event is not None:
            chapter.event = payload.event.strip()
        if payload.error_reason is not None:
            chapter.error_reason = payload.error_reason.strip()
        if payload.event_state == 0:
            chapter.error_reason = None
        chapter.updated_at = now
        session.add(chapter)
    await session.commit()
    return NovelChapterBatchResult(affected=len(chapters))


async def _get_project_with_id(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
):
    """获取项目并确保内部主键存在。"""
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    if project.id is None:
        raise project_service.ProjectNotFoundError("Project not found")
    return project


async def _get_chapter_model_or_raise(
    session: AsyncSession,
    project_id: int,
    chapter_id: int,
) -> NovelChapter:
    """按项目和章节 ID 获取章节模型。"""
    statement = select(NovelChapter).where(
        NovelChapter.project_id == project_id,
        NovelChapter.id == chapter_id,
    )
    result = await session.exec(statement)
    chapter = result.first()
    if chapter is None:
        raise NovelChapterNotFoundError("Novel chapter not found")
    return chapter


async def _list_chapter_models_by_ids(
    session: AsyncSession,
    project_id: int,
    chapter_ids: list[int],
) -> list[NovelChapter]:
    """按项目和 ID 列表获取章节模型。"""
    unique_ids = sorted(set(chapter_ids))
    if not unique_ids:
        return []
    statement = (
        select(NovelChapter)
        .where(
            NovelChapter.project_id == project_id,
            NovelChapter.id.in_(unique_ids),
        )
        .order_by(NovelChapter.chapter_index, NovelChapter.id)
    )
    result = await session.exec(statement)
    return list(result.all())


async def _next_chapter_index(session: AsyncSession, project_id: int) -> int:
    """返回指定项目下一章节序号。"""
    statement = select(func.max(NovelChapter.chapter_index)).where(NovelChapter.project_id == project_id)
    result = await session.exec(statement)
    max_index = result.one()
    return int(max_index or 0) + 1


async def _apply_chapter_event_extraction(chapter: NovelChapter, text_model: str) -> dict[str, Any]:
    """调用文本模型提取单章事件。"""
    content = chapter.chapter_data.strip()
    if len(content) < MIN_EVENT_EXTRACTION_CONTENT_LENGTH:
        _mark_event_extraction_failed(chapter, "正文字数过少，无法提取有效事件")
        return {}

    model_id = text_model.strip()
    if not model_id:
        _mark_event_extraction_failed(chapter, "项目未配置文本模型")
        return {}

    prompt_trace: dict[str, Any] = {}
    try:
        prompt_name = settings.chapter_event_extraction_prompt_name.strip()
        if not prompt_name:
            raise NovelChapterValidationError("单章事件提取提示词名称未配置")
        prompt = PromptRegistry.from_settings().skill(prompt_name)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": _chapter_event_user_message(chapter, content)},
        ]
        prompt_trace = _model_prompt_trace(
            model_id=model_id,
            prompt_name=prompt_name,
            messages=messages,
        )
        raw_event = await ProviderModelGateway(timeout=settings.model_request_timeout_seconds).generate_text(
            model_id=model_id,
            messages=messages,
        )
        prompt_trace["raw_output"] = raw_event
        payload = _parse_chapter_event_payload(raw_event)
        structured_events = parse_chapter_events(payload)
    except Exception as exc:
        _mark_event_extraction_failed(chapter, str(exc))
        return prompt_trace

    chapter.event = events_to_json(structured_events)
    chapter.event_state = 1
    chapter.error_reason = None
    return prompt_trace


def _chapter_clean_task_result(chapter: NovelChapter, prompt_trace: dict[str, Any]) -> dict[str, Any]:
    """构建写入异步任务 item.result 的章节清洗结果。"""
    return {
        "chapter_id": chapter.id,
        "chapter_public_id": chapter.public_id,
        "event_state": chapter.event_state,
        "event": chapter.event,
        "error_reason": chapter.error_reason,
        **prompt_trace,
    }


def _model_prompt_trace(
    *,
    model_id: str,
    prompt_name: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """记录本次模型调用的完整提示词，供异步任务详情排查使用。"""
    return {
        "model_id": model_id,
        "prompt_name": prompt_name,
        "messages": messages,
        "composed_prompt": _format_model_messages(messages),
    }


def _format_model_messages(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = str(message.get("role") or f"message_{index}").strip()
        content = str(message.get("content") or "").strip()
        if content:
            parts.append(f"{role}：\n{content}")
    return "\n\n".join(parts)


def _chapter_event_user_message(chapter: NovelChapter, content: str) -> str:
    return (
        f"章节标题：{chapter.chapter.strip() or '未提及'}\n"
        f"卷名：{chapter.reel.strip() or '未提及'}\n\n"
        "章节正文：\n"
        f"{content}"
    )


def _parse_chapter_event_payload(raw_event: str) -> dict[str, object]:
    text = _strip_json_code_fence(raw_event)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NovelChapterValidationError("事件提取结果不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise NovelChapterValidationError("事件提取结果必须是 JSON 对象")
    if set(payload.keys()) != {"events"}:
        raise NovelChapterValidationError("事件提取结果顶层只能包含 events 字段")
    if not isinstance(payload["events"], list):
        raise NovelChapterValidationError("事件提取结果 events 字段必须是数组")
    return {"events": payload["events"]}


def _strip_json_code_fence(raw_event: str) -> str:
    text = raw_event.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _mark_event_extraction_failed(chapter: NovelChapter, reason: str) -> None:
    chapter.event = ""
    chapter.event_state = -1
    chapter.error_reason = reason.strip() or "事件提取失败"


def _to_clean_status(chapter: NovelChapter) -> NovelChapterCleanStatus:
    return NovelChapterCleanStatus(
        id=int(chapter.id or 0),
        publicId=chapter.public_id,
        chapterIndex=chapter.chapter_index,
        reel=chapter.reel,
        chapter=chapter.chapter,
        event=chapter.event,
        eventState=chapter.event_state,
        errorReason=chapter.error_reason,
        updatedAt=chapter.updated_at,
    )


def _state_for_event(event: str, requested_state: int) -> int:
    """如果请求携带事件内容，默认认为事件已生成。"""
    if event.strip() and requested_state == 0:
        return 1
    return requested_state


def _chapter_content_md5(chapter_data: str) -> str:
    """按最终保存的章节正文计算内容指纹。"""
    return hashlib.md5(chapter_data.encode("utf-8")).hexdigest()


async def _ensure_crawl_source_key_available(session: AsyncSession, key: str) -> None:
    statement = select(NovelCrawlSource.id).where(NovelCrawlSource.key == key.strip())
    result = await session.exec(statement)
    if result.first() is not None:
        raise NovelCrawlSourceValidationError("Crawl source key already exists")


async def _get_visible_crawl_source_or_raise(
    session: AsyncSession,
    project_id: int,
    key: str,
) -> NovelCrawlSource:
    statement = select(NovelCrawlSource).where(
        NovelCrawlSource.key == key.strip(),
        NovelCrawlSource.disabled_at.is_(None),
        or_(NovelCrawlSource.scope == "public", NovelCrawlSource.project_id == project_id),
    )
    result = await session.exec(statement)
    source = result.first()
    if source is None:
        raise NovelCrawlSourceNotFoundError("Crawl source not found")
    return source


async def _get_project_crawl_source_or_raise(
    session: AsyncSession,
    project_id: int,
    key: str,
) -> NovelCrawlSource:
    statement = select(NovelCrawlSource).where(
        NovelCrawlSource.key == key.strip(),
        NovelCrawlSource.project_id == project_id,
        NovelCrawlSource.disabled_at.is_(None),
    )
    result = await session.exec(statement)
    source = result.first()
    if source is None:
        raise NovelCrawlSourceNotFoundError("Crawl source not found")
    return source


def _apply_crawl_source_values(source: NovelCrawlSource, values: dict[str, object]) -> None:
    for field in CRAWL_SOURCE_CONFIG_FIELDS:
        if field not in values:
            continue
        value = values[field]
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if field.endswith("_method"):
            value = str(value or "GET").upper()
        if field == "source_type":
            value = str(value or "api").lower()
        setattr(source, field, value)


def _to_crawl_source_read(source: NovelCrawlSource, project_public_id: str | None) -> CrawlSourceRead:
    return CrawlSourceRead(
        **{field: getattr(source, field) for field in CRAWL_SOURCE_CONFIG_FIELDS},
        key=source.key,
        builtin=source.builtin,
        projectPublicId=project_public_id,
        id=int(source.id or 0),
        publicId=source.public_id,
        scope=source.scope,
        sortOrder=source.sort_order,
        createdAt=source.created_at,
        updatedAt=source.updated_at,
        disabledAt=source.disabled_at,
    )


async def _upsert_crawl_book(
    session: AsyncSession,
    project_id: int,
    source_key: str,
    book: CrawlSearchResult,
) -> NovelCrawlBook:
    statement = select(NovelCrawlBook).where(
        NovelCrawlBook.project_id == project_id,
        NovelCrawlBook.source_key == source_key,
        NovelCrawlBook.source_book_id == book.dirid,
    )
    result = await session.exec(statement)
    crawl_book = result.first()
    now = utc_now()
    if crawl_book is None:
        crawl_book = NovelCrawlBook(
            project_id=project_id,
            source_key=source_key,
            source_book_id=book.dirid,
            created_at=now,
            updated_at=now,
        )
    crawl_book.source_book_numeric_id = book.id or None
    crawl_book.title = book.title
    crawl_book.author = book.author
    crawl_book.cover_url = book.cover
    crawl_book.category = book.sortname
    crawl_book.update_status = book.full
    crawl_book.intro = book.intro
    crawl_book.last_chapter = book.lastchapter
    crawl_book.last_chapter_id = book.lastchapterid
    crawl_book.last_update = book.lastupdate
    crawl_book.raw_data = json.dumps(book.model_dump(mode="json", by_alias=True), ensure_ascii=False)
    crawl_book.updated_at = now
    session.add(crawl_book)
    return crawl_book


async def _get_chapter_by_crawl_identity(
    session: AsyncSession,
    project_id: int,
    source_key: str,
    novel_dirid: str,
    chapter_id: int,
) -> NovelChapter | None:
    statement = select(NovelChapter).where(
        NovelChapter.project_id == project_id,
        NovelChapter.crawl_source_key == source_key,
        NovelChapter.crawl_novel_dirid == novel_dirid,
        NovelChapter.crawl_chapter_id == chapter_id,
    )
    result = await session.exec(statement)
    return result.first()


def _to_read(chapter: NovelChapter) -> NovelChapterRead:
    """将数据库模型转换为响应模型。"""
    return NovelChapterRead.model_validate(chapter)
