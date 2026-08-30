from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EVENT_STATES = {-1, 0, 1}


def to_camel(value: str) -> str:
    """将 snake_case 字段名转换为 camelCase。"""
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)
READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class NovelChapterBase(BaseModel):
    """小说章节请求基础字段。"""

    model_config = SCHEMA_CONFIG

    chapter_index: int = Field(default=1, ge=1, le=9999)
    reel: str = Field(default="", max_length=120)
    chapter: str = Field(min_length=1, max_length=255)
    chapter_data: str = Field(min_length=1)
    event: str = Field(default="")
    event_state: int = Field(default=0)
    error_reason: str | None = None
    crawl_source_key: str = Field(default="", max_length=64)
    crawl_novel_dirid: str = Field(default="", max_length=120)
    crawl_chapter_id: int | None = None
    crawl_time: str = Field(default="", max_length=64)
    crawl_md5: str = Field(default="", max_length=64)

    @field_validator("event_state")
    @classmethod
    def validate_event_state(cls, value: int) -> int:
        if value not in EVENT_STATES:
            raise ValueError("event_state must be -1, 0 or 1")
        return value


class NovelChapterCreate(NovelChapterBase):
    """创建小说章节请求。"""


class NovelChapterUpdate(BaseModel):
    """更新小说章节请求。"""

    model_config = SCHEMA_CONFIG

    chapter_index: int | None = Field(default=None, ge=1, le=9999)
    reel: str | None = Field(default=None, max_length=120)
    chapter: str | None = Field(default=None, min_length=1, max_length=255)
    chapter_data: str | None = Field(default=None, min_length=1)
    event: str | None = None
    event_state: int | None = None
    error_reason: str | None = None
    crawl_source_key: str | None = Field(default=None, max_length=64)
    crawl_novel_dirid: str | None = Field(default=None, max_length=120)
    crawl_chapter_id: int | None = None
    crawl_time: str | None = Field(default=None, max_length=64)
    crawl_md5: str | None = Field(default=None, max_length=64)

    @field_validator("event_state")
    @classmethod
    def validate_event_state(cls, value: int | None) -> int | None:
        if value is not None and value not in EVENT_STATES:
            raise ValueError("event_state must be -1, 0 or 1")
        return value


class NovelChapterRead(NovelChapterBase):
    """小说章节响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    project_id: int
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class NovelChapterCleanStatus(BaseModel):
    """章节事件清洗状态响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    chapter_index: int
    reel: str
    chapter: str
    event: str
    event_state: int
    error_reason: str | None
    updated_at: datetime


class NovelChapterPage(BaseModel):
    """小说章节分页响应。"""

    data: list[NovelChapterRead]
    total: int
    page: int
    limit: int


class ScreenwritingPreflightCheck(BaseModel):
    """剧本创作准入校验单项结果。"""

    model_config = SCHEMA_CONFIG

    key: str
    label: str
    passed: bool
    detail: str


class ScreenwritingPreflightResult(BaseModel):
    """剧本创作准入校验整体结果。"""

    model_config = SCHEMA_CONFIG

    ready: bool
    required_event_count: int
    event_ready_count: int
    text_model: str
    checks: list[ScreenwritingPreflightCheck]


class NovelChapterImportItem(BaseModel):
    """全文导入时前端预览得到的单章草稿。"""

    model_config = SCHEMA_CONFIG

    reel: str = Field(default="", max_length=120)
    chapter: str = Field(min_length=1, max_length=255)
    chapter_data: str = Field(min_length=1)


class NovelChapterImport(BaseModel):
    """全文导入请求。"""

    model_config = SCHEMA_CONFIG

    raw_text: str = ""
    chapters: list[NovelChapterImportItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_import_source(self) -> "NovelChapterImport":
        if not self.raw_text.strip() and not self.chapters:
            raise ValueError("raw_text or chapters is required")
        return self


class NovelImportSplitRule(BaseModel):
    """返回给前端导入弹窗的内置章节切分规则。"""

    model_config = SCHEMA_CONFIG

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="")
    chapter_pattern: str = Field(default="")
    chapter_flags_list: list[str] = Field(default_factory=list)
    reel_pattern: str = Field(default="")
    reel_flags_list: list[str] = Field(default_factory=list)
    builtin: bool = True


class NovelChapterBatchDelete(BaseModel):
    """批量删除章节请求。"""

    ids: list[int] = Field(min_length=1)


class NovelChapterBatchClean(BaseModel):
    """批量清洗章节请求。"""

    ids: list[int] = Field(min_length=1)


class NovelChapterBatchCleanItem(BaseModel):
    """批量清洗任务中单个章节的进度。"""

    model_config = SCHEMA_CONFIG

    chapter_id: int
    chapter_public_id: str
    chapter_index: int
    chapter_title: str = ""
    reel: str = ""
    item_public_id: str
    item_status: str
    event_state: int
    event: str = ""
    error_reason: str | None = None


class NovelChapterBatchCleanProgress(BaseModel):
    """批量清洗任务进度响应。"""

    model_config = SCHEMA_CONFIG

    job_public_id: str
    job_status: str
    total_count: int = 0
    pending_count: int = 0
    running_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    canceled_count: int = 0
    paused_count: int = 0
    finished_count: int = 0
    is_finished: bool = False
    items: list[NovelChapterBatchCleanItem] = Field(default_factory=list)


class NovelChapterBatchCleanCancelResult(BaseModel):
    """批量清洗任务取消结果。"""

    model_config = SCHEMA_CONFIG

    job_public_id: str
    canceled_count: int = 0


class NovelChapterBatchCleanActiveJob(BaseModel):
    """未结束批量清洗任务的轻量信息。"""

    model_config = SCHEMA_CONFIG

    job_public_id: str
    job_status: str
    total_count: int = 0
    pending_count: int = 0
    running_count: int = 0
    paused_count: int = 0
    created_at: datetime | None = None


class NovelChapterBatchCleanActiveJobList(BaseModel):
    """未结束批量清洗任务列表。"""

    model_config = SCHEMA_CONFIG

    items: list[NovelChapterBatchCleanActiveJob] = Field(default_factory=list)


class NovelChapterEventStateUpdate(BaseModel):
    """批量更新事件状态请求。"""

    model_config = SCHEMA_CONFIG

    ids: list[int] = Field(min_length=1)
    event_state: int
    event: str | None = None
    error_reason: str | None = None

    @field_validator("event_state")
    @classmethod
    def validate_event_state(cls, value: int) -> int:
        if value not in EVENT_STATES:
            raise ValueError("event_state must be -1, 0 or 1")
        return value


class NovelChapterBatchResult(BaseModel):
    """批量操作结果。"""

    affected: int


CRAWL_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
CRAWL_SOURCE_TYPES = {"api", "rule"}
CRAWL_SOURCE_SCOPES = {"private", "public"}


class CrawlSourceFields(BaseModel):
    """小说爬取来源请求和响应的通用字段。"""

    model_config = SCHEMA_CONFIG

    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(default="", max_length=1000)
    desc: str = Field(default="", max_length=1000)
    source_type: str = Field(default="api", max_length=20)
    search_url_template: str = Field(default="", max_length=2000)
    api_search_method: str = Field(default="GET", max_length=10)
    api_search_headers: str = ""
    api_search_body: str = ""
    api_search_book_url_path: str = Field(default="", max_length=1000)
    api_search_book_id_path: str = Field(default="", max_length=1000)
    api_search_book_title_path: str = Field(default="", max_length=1000)
    api_search_book_author_path: str = Field(default="", max_length=1000)
    api_search_book_intro_path: str = Field(default="", max_length=1000)
    api_search_book_cover_path: str = Field(default="", max_length=1000)
    api_search_book_category_path: str = Field(default="", max_length=1000)
    api_search_book_update_status_path: str = Field(default="", max_length=1000)
    api_search_book_last_chapter_path: str = Field(default="", max_length=1000)
    api_search_book_last_chapter_id_path: str = Field(default="", max_length=1000)
    api_search_book_last_update_path: str = Field(default="", max_length=1000)
    api_book_url: str = Field(default="", max_length=2000)
    api_book_method: str = Field(default="GET", max_length=10)
    api_book_headers: str = ""
    api_book_body: str = ""
    api_book_title_path: str = Field(default="", max_length=1000)
    api_book_author_path: str = Field(default="", max_length=1000)
    api_book_intro_path: str = Field(default="", max_length=1000)
    api_book_last_chapter_path: str = Field(default="", max_length=1000)
    api_book_last_chapter_id_path: str = Field(default="", max_length=1000)
    api_book_last_update_path: str = Field(default="", max_length=1000)
    api_book_cover_path: str = Field(default="", max_length=1000)
    api_book_category_path: str = Field(default="", max_length=1000)
    api_book_update_status_path: str = Field(default="", max_length=1000)
    api_book_id_path: str = Field(default="", max_length=1000)
    api_chapter_list_url: str = Field(default="", max_length=2000)
    api_chapter_list_method: str = Field(default="GET", max_length=10)
    api_chapter_list_headers: str = ""
    api_chapter_list_body: str = ""
    api_chapter_list_id_path: str = Field(default="", max_length=1000)
    api_chapter_list_name_path: str = Field(default="", max_length=1000)
    api_chapter_list_time_path: str = Field(default="", max_length=1000)
    api_chapter_list_content_path: str = Field(default="", max_length=1000)
    api_chapter_list_md5_path: str = Field(default="", max_length=1000)
    api_chapter_url: str = Field(default="", max_length=2000)
    api_chapter_method: str = Field(default="GET", max_length=10)
    api_chapter_headers: str = ""
    api_chapter_body: str = ""
    api_chapter_name_path: str = Field(default="", max_length=1000)
    api_chapter_content_path: str = Field(default="", max_length=1000)
    api_chapter_time_path: str = Field(default="", max_length=1000)
    api_chapter_md5_path: str = Field(default="", max_length=1000)

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in CRAWL_SOURCE_TYPES:
            raise ValueError("source_type must be api or rule")
        return normalized

    @field_validator(
        "api_search_method",
        "api_book_method",
        "api_chapter_list_method",
        "api_chapter_method",
    )
    @classmethod
    def validate_http_method(cls, value: str) -> str:
        normalized = value.strip().upper() or "GET"
        if normalized not in CRAWL_HTTP_METHODS:
            raise ValueError("unsupported HTTP method")
        return normalized


class CrawlSourcePayload(CrawlSourceFields):
    """创建小说爬取来源请求。"""

    key: str = Field(min_length=1, max_length=64)
    builtin: bool = False
    project_public_id: str | None = Field(default=None, max_length=36)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        key = value.strip()
        if not key.replace("_", "").replace("-", "").isalnum():
            raise ValueError("key may only contain letters, numbers, underscore and hyphen")
        return key


class CrawlSourceUpdate(BaseModel):
    """更新小说爬取来源请求。"""

    model_config = SCHEMA_CONFIG

    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=1000)
    desc: str | None = Field(default=None, max_length=1000)
    source_type: str | None = Field(default=None, max_length=20)
    search_url_template: str | None = Field(default=None, max_length=2000)
    api_search_method: str | None = Field(default=None, max_length=10)
    api_search_headers: str | None = None
    api_search_body: str | None = None
    api_search_book_url_path: str | None = Field(default=None, max_length=1000)
    api_search_book_id_path: str | None = Field(default=None, max_length=1000)
    api_search_book_title_path: str | None = Field(default=None, max_length=1000)
    api_search_book_author_path: str | None = Field(default=None, max_length=1000)
    api_search_book_intro_path: str | None = Field(default=None, max_length=1000)
    api_search_book_cover_path: str | None = Field(default=None, max_length=1000)
    api_search_book_category_path: str | None = Field(default=None, max_length=1000)
    api_search_book_update_status_path: str | None = Field(default=None, max_length=1000)
    api_search_book_last_chapter_path: str | None = Field(default=None, max_length=1000)
    api_search_book_last_chapter_id_path: str | None = Field(default=None, max_length=1000)
    api_search_book_last_update_path: str | None = Field(default=None, max_length=1000)
    api_book_url: str | None = Field(default=None, max_length=2000)
    api_book_method: str | None = Field(default=None, max_length=10)
    api_book_headers: str | None = None
    api_book_body: str | None = None
    api_book_title_path: str | None = Field(default=None, max_length=1000)
    api_book_author_path: str | None = Field(default=None, max_length=1000)
    api_book_intro_path: str | None = Field(default=None, max_length=1000)
    api_book_last_chapter_path: str | None = Field(default=None, max_length=1000)
    api_book_last_chapter_id_path: str | None = Field(default=None, max_length=1000)
    api_book_last_update_path: str | None = Field(default=None, max_length=1000)
    api_book_cover_path: str | None = Field(default=None, max_length=1000)
    api_book_category_path: str | None = Field(default=None, max_length=1000)
    api_book_update_status_path: str | None = Field(default=None, max_length=1000)
    api_book_id_path: str | None = Field(default=None, max_length=1000)
    api_chapter_list_url: str | None = Field(default=None, max_length=2000)
    api_chapter_list_method: str | None = Field(default=None, max_length=10)
    api_chapter_list_headers: str | None = None
    api_chapter_list_body: str | None = None
    api_chapter_list_id_path: str | None = Field(default=None, max_length=1000)
    api_chapter_list_name_path: str | None = Field(default=None, max_length=1000)
    api_chapter_list_time_path: str | None = Field(default=None, max_length=1000)
    api_chapter_list_content_path: str | None = Field(default=None, max_length=1000)
    api_chapter_list_md5_path: str | None = Field(default=None, max_length=1000)
    api_chapter_url: str | None = Field(default=None, max_length=2000)
    api_chapter_method: str | None = Field(default=None, max_length=10)
    api_chapter_headers: str | None = None
    api_chapter_body: str | None = None
    api_chapter_name_path: str | None = Field(default=None, max_length=1000)
    api_chapter_content_path: str | None = Field(default=None, max_length=1000)
    api_chapter_time_path: str | None = Field(default=None, max_length=1000)
    api_chapter_md5_path: str | None = Field(default=None, max_length=1000)


class CrawlSourceRead(CrawlSourcePayload):
    """小说爬取来源响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    project_public_id: str | None = None
    scope: str = "private"
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class CrawlSourceDuplicate(BaseModel):
    """复制小说爬取来源请求。"""

    model_config = SCHEMA_CONFIG

    new_key: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=120)


class CrawlSearchResult(BaseModel):
    """小说来源搜索或详情接口返回的小说信息。"""

    model_config = SCHEMA_CONFIG

    dirid: str = Field(default="", max_length=120)
    id: int = 0
    full: str = ""
    title: str = ""
    author: str = ""
    cover: str = ""
    lastchapter: str = ""
    lastchapterid: int = 0
    lastupdate: str = ""
    sortname: str = ""
    intro: str = ""
    source_key: str = Field(default="", max_length=64)


class CrawlSearchPayload(BaseModel):
    """在小说来源中搜索小说。"""

    model_config = SCHEMA_CONFIG

    source_key: str = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=255)


class CrawlBookPayload(BaseModel):
    """携带选中小说的请求参数。"""

    model_config = SCHEMA_CONFIG

    source_key: str = Field(min_length=1, max_length=64)
    book: CrawlSearchResult


class CrawlBookDetailResult(BaseModel):
    """选中小说详情响应。"""

    model_config = SCHEMA_CONFIG

    book: CrawlSearchResult


class CrawlBookChapterCountResult(CrawlBookDetailResult):
    """选中小说章节总数响应。"""

    lastchapterid: int = 0


class CrawlChapterDraft(BaseModel):
    """从小说来源爬取后、入库前的章节草稿。"""

    model_config = SCHEMA_CONFIG

    key: int = 0
    novel_dirid: str = Field(default="", max_length=120)
    chapterid: int = 0
    chaptername: str = Field(default="", max_length=255)
    time: str = Field(default="", max_length=64)
    txt: str = ""
    md5: str = Field(default="", max_length=64)
    event: str = ""
    event_state: int = 0
    error_reason: str | None = None

    @field_validator("event_state")
    @classmethod
    def validate_crawl_event_state(cls, value: int) -> int:
        if value not in EVENT_STATES:
            raise ValueError("event_state must be -1, 0 or 1")
        return value


class CrawlChapterFetchPayload(CrawlBookPayload):
    """爬取选中小说章节的请求。"""

    start_chapter: int = Field(default=1, ge=1)
    end_chapter: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "CrawlChapterFetchPayload":
        if self.end_chapter < self.start_chapter:
            raise ValueError("end_chapter must be greater than or equal to start_chapter")
        return self


class CrawlImportPayload(CrawlBookPayload):
    """把已爬取章节导入小说章节管理。"""

    chapters: list[CrawlChapterDraft] = Field(min_length=1)


class CrawlImportResult(BaseModel):
    """爬取章节导入结果。"""

    model_config = SCHEMA_CONFIG

    created: int = 0
    updated: int = 0
    skipped: int = 0
    chapters: list[NovelChapterRead] = Field(default_factory=list)


class CrawlAnalyzePayload(BaseModel):
    """来源分析占位请求。"""

    model_config = SCHEMA_CONFIG

    url: str = Field(min_length=1, max_length=2000)
    source_type: str = Field(default="api", max_length=20)


class CrawlAnalyzeResult(BaseModel):
    """来源分析占位响应。"""

    model_config = SCHEMA_CONFIG

    status: str = "pending"
    source: CrawlSourcePayload
    message: str = ""
