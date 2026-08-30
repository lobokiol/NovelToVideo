from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint, false
from sqlmodel import Field

from app.models.base import BaseModel


class NovelChapter(BaseModel, table=True):
    """小说章节表模型。"""

    __tablename__ = "af_novel_chapter"

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="所属项目内部主键。",
    )
    chapter_index: int = Field(
        default=1,
        sa_column=Column("chapter_index", Integer, nullable=False, default=1, index=True),
        description="章节序号。",
    )
    reel: str = Field(
        default="",
        sa_column=Column("reel", String(120), nullable=False, default="", server_default=""),
        description="卷次标题。",
    )
    chapter: str = Field(
        sa_column=Column("chapter", String(255), nullable=False, index=True),
        description="章节标题。",
    )
    chapter_data: str = Field(
        default="",
        sa_column=Column("chapter_data", Text(), nullable=False, default="", server_default=""),
        description="章节正文。",
    )
    event: str = Field(
        default="",
        sa_column=Column("event", Text(), nullable=False, default="", server_default=""),
        description="清洗后的事件内容。",
    )
    event_state: int = Field(
        default=0,
        sa_column=Column("event_state", Integer, nullable=False, default=0, server_default="0", index=True),
        description="事件清洗状态：0 待清洗，1 成功，-1 失败。",
    )
    error_reason: str | None = Field(
        default=None,
        sa_column=Column("error_reason", Text(), nullable=True),
        description="清洗失败原因。",
    )
    crawl_source_key: str = Field(
        default="",
        sa_column=Column("crawl_source_key", String(64), nullable=False, default="", server_default=""),
        description="小说来源唯一标识。",
    )
    crawl_novel_dirid: str = Field(
        default="",
        sa_column=Column("crawl_novel_dirid", String(120), nullable=False, default="", server_default=""),
        description="小说来源小说唯一ID。",
    )
    crawl_chapter_id: int | None = Field(
        default=None,
        sa_column=Column("crawl_chapter_id", Integer, nullable=True),
        description="小说来源章节唯一标识。",
    )
    crawl_time: str = Field(
        default="",
        sa_column=Column("crawl_time", String(64), nullable=False, default="", server_default=""),
        description="小说来源章节发布时间。",
    )
    crawl_md5: str = Field(
        default="",
        sa_column=Column("crawl_md5", String(64), nullable=False, default="", server_default=""),
        description="小说来源正文 MD5。",
    )


class NovelCrawlSource(BaseModel, table=True):
    """小说来源配置表模型。"""

    __tablename__ = "af_novel_crawl_source"

    project_id: int | None = Field(
        default=None,
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=True, index=True),
        description="私有来源所属项目内部主键；公共来源为空。",
    )
    owner_public_id: str = Field(
        default="",
        sa_column=Column("owner_public_id", String(36), nullable=False, default="", server_default="", index=True),
        description="来源创建人用户公开 ID。",
    )
    key: str = Field(
        sa_column=Column("key", String(64), nullable=False, unique=True, index=True),
        description="来源唯一标识。",
    )
    name: str = Field(
        sa_column=Column("name", String(120), nullable=False, index=True),
        description="来源名称。",
    )
    base_url: str = Field(
        default="",
        sa_column=Column("base_url", String(1000), nullable=False, default="", server_default=""),
        description="来源站点 URL。",
    )
    desc: str = Field(
        default="",
        sa_column=Column("desc", String(1000), nullable=False, default="", server_default=""),
        description="来源描述。",
    )
    builtin: bool = Field(
        default=False,
        sa_column=Column("builtin", Boolean, nullable=False, default=False, server_default=false()),
        description="是否为内置来源。",
    )
    source_type: str = Field(
        default="api",
        sa_column=Column("source_type", String(20), nullable=False, default="api", server_default="api"),
        description="来源配置类型，目前固定为 API。",
    )
    scope: str = Field(
        default="private",
        sa_column=Column(
            "scope",
            String(20),
            nullable=False,
            default="private",
            server_default="private",
            index=True,
        ),
        description="来源可见范围，private 为项目私有，public 为公共来源。",
    )
    search_url_template: str = Field(
        default="",
        sa_column=Column("search_url_template", String(2000), nullable=False, default="", server_default=""),
        description="小说搜索页请求 URL 模板。",
    )
    api_search_method: str = Field(
        default="GET",
        sa_column=Column("api_search_method", String(10), nullable=False, default="GET", server_default="GET"),
        description="小说搜索页请求 Method。",
    )
    api_search_headers: str = Field(
        default="",
        sa_column=Column("api_search_headers", Text(), nullable=False, default="", server_default=""),
        description="小说搜索页请求 Headers 配置。",
    )
    api_search_body: str = Field(
        default="",
        sa_column=Column("api_search_body", Text(), nullable=False, default="", server_default=""),
        description="小说搜索页请求 Body 配置。",
    )
    api_search_book_url_path: str = Field(
        default="",
        sa_column=Column("api_search_book_url_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的详情页 URL 选择器。",
    )
    api_search_book_id_path: str = Field(
        default="",
        sa_column=Column("api_search_book_id_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的小说 ID 选择器。",
    )
    api_search_book_title_path: str = Field(
        default="",
        sa_column=Column("api_search_book_title_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的标题选择器。",
    )
    api_search_book_author_path: str = Field(
        default="",
        sa_column=Column("api_search_book_author_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的作者选择器。",
    )
    api_search_book_intro_path: str = Field(
        default="",
        sa_column=Column("api_search_book_intro_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的简介选择器。",
    )
    api_search_book_cover_path: str = Field(
        default="",
        sa_column=Column("api_search_book_cover_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的封面图选择器。",
    )
    api_search_book_category_path: str = Field(
        default="",
        sa_column=Column("api_search_book_category_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的类别选择器。",
    )
    api_search_book_update_status_path: str = Field(
        default="",
        sa_column=Column("api_search_book_update_status_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的更新状态选择器。",
    )
    api_search_book_last_chapter_path: str = Field(
        default="",
        sa_column=Column("api_search_book_last_chapter_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的最新章节标题选择器。",
    )
    api_search_book_last_chapter_id_path: str = Field(
        default="",
        sa_column=Column(
            "api_search_book_last_chapter_id_path",
            String(1000),
            nullable=False,
            default="",
            server_default="",
        ),
        description="小说搜索结果中的最新章节 ID 选择器。",
    )
    api_search_book_last_update_path: str = Field(
        default="",
        sa_column=Column("api_search_book_last_update_path", String(1000), nullable=False, default="", server_default=""),
        description="小说搜索结果中的最新更新时间选择器。",
    )
    api_book_url: str = Field(
        default="",
        sa_column=Column("api_book_url", String(2000), nullable=False, default="", server_default=""),
        description="小说详情页请求 URL 模板。",
    )
    api_book_method: str = Field(
        default="GET",
        sa_column=Column("api_book_method", String(10), nullable=False, default="GET", server_default="GET"),
        description="小说详情页请求 Method。",
    )
    api_book_headers: str = Field(
        default="",
        sa_column=Column("api_book_headers", Text(), nullable=False, default="", server_default=""),
        description="小说详情页请求 Headers 配置。",
    )
    api_book_body: str = Field(
        default="",
        sa_column=Column("api_book_body", Text(), nullable=False, default="", server_default=""),
        description="小说详情页请求 Body 配置。",
    )
    api_book_title_path: str = Field(
        default="",
        sa_column=Column("api_book_title_path", String(1000), nullable=False, default="", server_default=""),
        description="小说标题选择器。",
    )
    api_book_author_path: str = Field(
        default="",
        sa_column=Column("api_book_author_path", String(1000), nullable=False, default="", server_default=""),
        description="小说作者选择器。",
    )
    api_book_intro_path: str = Field(
        default="",
        sa_column=Column("api_book_intro_path", String(1000), nullable=False, default="", server_default=""),
        description="小说简介选择器。",
    )
    api_book_last_chapter_path: str = Field(
        default="",
        sa_column=Column("api_book_last_chapter_path", String(1000), nullable=False, default="", server_default=""),
        description="小说最新章节标题选择器。",
    )
    api_book_last_chapter_id_path: str = Field(
        default="",
        sa_column=Column("api_book_last_chapter_id_path", String(1000), nullable=False, default="", server_default=""),
        description="小说最新章节 ID 选择器。",
    )
    api_book_last_update_path: str = Field(
        default="",
        sa_column=Column("api_book_last_update_path", String(1000), nullable=False, default="", server_default=""),
        description="小说最新更新时间选择器。",
    )
    api_book_cover_path: str = Field(
        default="",
        sa_column=Column("api_book_cover_path", String(1000), nullable=False, default="", server_default=""),
        description="小说封面图选择器。",
    )
    api_book_category_path: str = Field(
        default="",
        sa_column=Column("api_book_category_path", String(1000), nullable=False, default="", server_default=""),
        description="小说类别选择器。",
    )
    api_book_update_status_path: str = Field(
        default="",
        sa_column=Column("api_book_update_status_path", String(1000), nullable=False, default="", server_default=""),
        description="小说更新状态选择器。",
    )
    api_book_id_path: str = Field(
        default="",
        sa_column=Column("api_book_id_path", String(1000), nullable=False, default="", server_default=""),
        description="小说 ID 选择器。",
    )
    api_chapter_list_url: str = Field(
        default="",
        sa_column=Column("api_chapter_list_url", String(2000), nullable=False, default="", server_default=""),
        description="章节列表页请求 URL 模板。",
    )
    api_chapter_list_method: str = Field(
        default="GET",
        sa_column=Column("api_chapter_list_method", String(10), nullable=False, default="GET", server_default="GET"),
        description="章节列表页请求 Method。",
    )
    api_chapter_list_headers: str = Field(
        default="",
        sa_column=Column("api_chapter_list_headers", Text(), nullable=False, default="", server_default=""),
        description="章节列表页请求 Headers 配置。",
    )
    api_chapter_list_body: str = Field(
        default="",
        sa_column=Column("api_chapter_list_body", Text(), nullable=False, default="", server_default=""),
        description="章节列表页请求 Body 配置。",
    )
    api_chapter_list_id_path: str = Field(
        default="",
        sa_column=Column("api_chapter_list_id_path", String(1000), nullable=False, default="", server_default=""),
        description="章节 ID 选择器。",
    )
    api_chapter_list_name_path: str = Field(
        default="",
        sa_column=Column("api_chapter_list_name_path", String(1000), nullable=False, default="", server_default=""),
        description="章节标题选择器。",
    )
    api_chapter_list_time_path: str = Field(
        default="",
        sa_column=Column("api_chapter_list_time_path", String(1000), nullable=False, default="", server_default=""),
        description="章节更新时间选择器。",
    )
    api_chapter_list_content_path: str = Field(
        default="",
        sa_column=Column("api_chapter_list_content_path", String(1000), nullable=False, default="", server_default=""),
        description="章节正文选择器。",
    )
    api_chapter_list_md5_path: str = Field(
        default="",
        sa_column=Column("api_chapter_list_md5_path", String(1000), nullable=False, default="", server_default=""),
        description="章节正文 MD5 选择器。",
    )
    api_chapter_url: str = Field(
        default="",
        sa_column=Column("api_chapter_url", String(2000), nullable=False, default="", server_default=""),
        description="章节正文页请求 URL 模板。",
    )
    api_chapter_method: str = Field(
        default="GET",
        sa_column=Column("api_chapter_method", String(10), nullable=False, default="GET", server_default="GET"),
        description="章节正文页请求 Method。",
    )
    api_chapter_headers: str = Field(
        default="",
        sa_column=Column("api_chapter_headers", Text(), nullable=False, default="", server_default=""),
        description="章节正文页请求 Headers 配置。",
    )
    api_chapter_body: str = Field(
        default="",
        sa_column=Column("api_chapter_body", Text(), nullable=False, default="", server_default=""),
        description="章节正文页请求 Body 配置。",
    )
    api_chapter_name_path: str = Field(
        default="",
        sa_column=Column("api_chapter_name_path", String(1000), nullable=False, default="", server_default=""),
        description="章节正文页标题选择器。",
    )
    api_chapter_content_path: str = Field(
        default="",
        sa_column=Column("api_chapter_content_path", String(1000), nullable=False, default="", server_default=""),
        description="章节正文页正文选择器。",
    )
    api_chapter_time_path: str = Field(
        default="",
        sa_column=Column("api_chapter_time_path", String(1000), nullable=False, default="", server_default=""),
        description="章节正文页更新时间选择器。",
    )
    api_chapter_md5_path: str = Field(
        default="",
        sa_column=Column("api_chapter_md5_path", String(1000), nullable=False, default="", server_default=""),
        description="章节正文页正文 MD5 选择器。",
    )


class NovelCrawlBook(BaseModel, table=True):
    """小说爬取返回的小说信息表模型。"""

    __tablename__ = "af_novel_crawl_book"
    __table_args__ = (
        UniqueConstraint("project_id", "source_key", "source_book_id", name="uq_af_novel_crawl_book_project_source_book"),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="所属项目内部主键。",
    )
    source_key: str = Field(
        sa_column=Column("source_key", String(64), nullable=False, index=True),
        description="小说来源唯一标识。",
    )
    source_book_id: str = Field(
        sa_column=Column("source_book_id", String(120), nullable=False, index=True),
        description="来源站点小说 ID。",
    )
    source_book_numeric_id: int | None = Field(
        default=None,
        sa_column=Column("source_book_numeric_id", Integer, nullable=True),
        description="来源站点小说数字 ID。",
    )
    title: str = Field(
        sa_column=Column("title", String(255), nullable=False, index=True),
        description="小说标题。",
    )
    author: str = Field(
        default="",
        sa_column=Column("author", String(120), nullable=False, default="", server_default="", index=True),
        description="小说作者。",
    )
    cover_url: str = Field(
        default="",
        sa_column=Column("cover_url", String(1000), nullable=False, default="", server_default=""),
        description="封面图 URL。",
    )
    category: str = Field(
        default="",
        sa_column=Column("category", String(120), nullable=False, default="", server_default="", index=True),
        description="小说类别。",
    )
    update_status: str = Field(
        default="",
        sa_column=Column("update_status", String(120), nullable=False, default="", server_default=""),
        description="更新状态。",
    )
    intro: str = Field(
        default="",
        sa_column=Column("intro", Text(), nullable=False, default="", server_default=""),
        description="小说简介。",
    )
    last_chapter: str = Field(
        default="",
        sa_column=Column("last_chapter", String(255), nullable=False, default="", server_default=""),
        description="最新章节标题。",
    )
    last_chapter_id: int = Field(
        default=0,
        sa_column=Column("last_chapter_id", Integer, nullable=False, default=0, server_default="0"),
        description="最新章节 ID。",
    )
    last_update: str = Field(
        default="",
        sa_column=Column("last_update", String(64), nullable=False, default="", server_default=""),
        description="最新更新时间。",
    )
    raw_data: str = Field(
        default="",
        sa_column=Column("raw_data", Text(), nullable=False, default="", server_default=""),
        description="原始爬取数据。",
    )
