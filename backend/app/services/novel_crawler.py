from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import ipaddress
import json
import os
import random
import re
import socket
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse

import httpx
from parsel import Selector

try:  # 可选依赖：用于以浏览器 TLS 指纹绕过 JA3/JA4 反爬，缺失时回退 httpx
    from curl_cffi.requests import Session as _CurlSession
except ImportError:  # pragma: no cover
    _CurlSession = None

from app.core.config import Settings, settings
from app.models.novel import NovelCrawlSource
from app.schemas.novel import CrawlChapterDraft, CrawlSearchResult
from app.utils.novel_token_cipher import encrypt_token


HTTP_METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}
# 基于选择器规则解析 HTML 的来源类型；其余按 JSON 接口处理。
RULE_SOURCE_TYPE = "rule"
# URL 模板中嵌入的 token 加密指令：enc:算法名(载荷)，载荷内可含 {占位符}。
_ENC_DIRECTIVE_RE = re.compile(r"enc:([A-Za-z0-9_-]+)\(")
_DEFAULT_THROTTLE_STATUS_CODES = (403, 429)
_DEFAULT_NEXT_PAGE_LABELS = ("下一页", "下页", "下一頁", "下一张")
_FAKE_IP_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)
_TLS_FAILURE_MARKERS = (
    "ErrCode: 35",
    "curl: (35)",
    "SSL_ERROR_SYSCALL",
    "TLS connect error",
    "UNEXPECTED_EOF_WHILE_READING",
    "SSL/TLS connection failed",
    "BoringSSL SSL_connect",
)
_CLOUDFLARE_CHALLENGE_MARKERS = (
    "<title>just a moment",
    "cf-browser-verification",
    "cf-chl-",
    "cf_chl_",
    "__cf_chl_rt_tk",
    "challenge-platform",
    "cloudflare 挑战",
    "浏览器访问仍被 cloudflare",
)
_IMPERSONATE_ACCEPT_ENCODING = "gzip, deflate"
_IMPERSONATE_CONTROLLED_REQUEST_HEADERS = frozenset({"accept-encoding"})
_DECODED_RESPONSE_HEADER_NAMES = frozenset({"content-encoding", "content-length"})


def _resolve_crawl_proxy(configured_proxy: str | None) -> str | None:
    explicit = (configured_proxy or "").strip()
    if explicit:
        return explicit
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def _proxy_mapping(proxy: str | None) -> dict[str, str] | None:
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def _decoded_response_headers(headers: Any) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in dict(headers).items()
        if str(key).lower() not in _DECODED_RESPONSE_HEADER_NAMES
    }


def _impersonate_request_headers(headers: Any) -> Any:
    if headers is None:
        return None
    if isinstance(headers, dict):
        return {
            str(key): value
            for key, value in headers.items()
            if str(key).lower() not in _IMPERSONATE_CONTROLLED_REQUEST_HEADERS
        }
    return headers


@dataclass(frozen=True, slots=True)
class NovelCrawlerRuntimeConfig:
    """从项目 Settings 生成小说爬虫运行参数。"""

    http_timeout_seconds: float
    http_connect_timeout_seconds: float
    impersonate_profile: str
    proxy: str | None
    chapter_coroutines_per_process: int
    max_processes: int
    stream_chapter_concurrency: int
    http_retries: int
    http_retry_backoff_seconds: float
    max_search_pages: int
    max_content_pages: int
    rule_chapter_concurrency: int
    rule_request_jitter_seconds: float
    throttle_backoff_seconds: float
    throttle_status_codes: tuple[int, ...]
    next_page_labels: tuple[str, ...]

    @classmethod
    def from_settings(cls, config: Settings) -> "NovelCrawlerRuntimeConfig":
        """按爬虫运行边界规整 Settings 中的原始配置值。"""
        throttle_status_codes = tuple(config.novel_crawl_throttle_status_codes) or _DEFAULT_THROTTLE_STATUS_CODES
        next_page_labels = tuple(config.novel_crawl_next_page_labels) or _DEFAULT_NEXT_PAGE_LABELS
        return cls(
            http_timeout_seconds=max(float(config.novel_crawl_http_timeout_seconds), 0.001),
            http_connect_timeout_seconds=max(float(config.novel_crawl_http_connect_timeout_seconds), 0.001),
            impersonate_profile=config.novel_crawl_impersonate.strip() or "chrome",
            proxy=_resolve_crawl_proxy(config.novel_crawl_proxy),
            chapter_coroutines_per_process=max(int(config.novel_crawl_chapter_coroutines_per_process), 1),
            max_processes=max(int(config.novel_crawl_max_processes), 1),
            stream_chapter_concurrency=max(int(config.novel_crawl_stream_concurrency), 1),
            http_retries=max(int(config.novel_crawl_http_retries), 0),
            http_retry_backoff_seconds=max(float(config.novel_crawl_http_retry_backoff_seconds), 0.0),
            max_search_pages=max(int(config.novel_crawl_max_search_pages), 1),
            max_content_pages=max(int(config.novel_crawl_max_content_pages), 1),
            rule_chapter_concurrency=max(int(config.novel_crawl_rule_concurrency), 1),
            rule_request_jitter_seconds=max(float(config.novel_crawl_rule_jitter_seconds), 0.0),
            throttle_backoff_seconds=max(float(config.novel_crawl_throttle_backoff_seconds), 0.0),
            throttle_status_codes=throttle_status_codes,
            next_page_labels=next_page_labels,
        )


_RUNTIME_CONFIG = NovelCrawlerRuntimeConfig.from_settings(settings)
HTTP_TIMEOUT = httpx.Timeout(
    _RUNTIME_CONFIG.http_timeout_seconds,
    connect=_RUNTIME_CONFIG.http_connect_timeout_seconds,
)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value.strip())


def _browser_proxy_http_read_timeout_seconds(base_timeout_seconds: float) -> float:
    browser_timeout_ms = max(_env_float("NOVEL_BROWSER_PROXY_TIMEOUT_MS", 30000.0), 1000.0)
    selector_timeout_ms = max(
        _env_float("NOVEL_BROWSER_PROXY_WAIT_SELECTOR_TIMEOUT_MS", min(browser_timeout_ms, 8000.0)),
        100.0,
    )
    wait_after_load_ms = max(_env_float("NOVEL_BROWSER_PROXY_WAIT_AFTER_LOAD_MS", 1200.0), 0.0)
    wait_after_selector_ms = max(_env_float("NOVEL_BROWSER_PROXY_WAIT_AFTER_SELECTOR_MS", 0.0), 0.0)
    browser_budget_seconds = (
        browser_timeout_ms
        + selector_timeout_ms
        + max(wait_after_load_ms, wait_after_selector_ms)
    ) / 1000.0
    return max(base_timeout_seconds, browser_budget_seconds + 5.0)


BROWSER_PROXY_HTTP_TIMEOUT = httpx.Timeout(
    _browser_proxy_http_read_timeout_seconds(_RUNTIME_CONFIG.http_timeout_seconds),
    connect=_RUNTIME_CONFIG.http_connect_timeout_seconds,
)
# rule 来源默认使用的浏览器指纹画像，用于绕过 TLS 指纹反爬。
IMPERSONATE_PROFILE = _RUNTIME_CONFIG.impersonate_profile
# 可选代理（NOVEL_CRAWL_PROXY，如 http://127.0.0.1:7890）：来源站点按 IP 封禁时可换出口 IP。
CRAWL_PROXY = _RUNTIME_CONFIG.proxy
CHAPTER_COROUTINES_PER_PROCESS = _RUNTIME_CONFIG.chapter_coroutines_per_process
MAX_CRAWL_PROCESSES = _RUNTIME_CONFIG.max_processes
STREAM_CHAPTER_CONCURRENCY = _RUNTIME_CONFIG.stream_chapter_concurrency
CRAWL_HTTP_RETRIES = _RUNTIME_CONFIG.http_retries
CRAWL_HTTP_RETRY_BACKOFF_SECONDS = _RUNTIME_CONFIG.http_retry_backoff_seconds
# 搜索翻页上限（含 {page} 占位符的 rule 来源），以及单章正文分页拼接上限。
MAX_SEARCH_PAGES = _RUNTIME_CONFIG.max_search_pages
MAX_CONTENT_PAGES = _RUNTIME_CONFIG.max_content_pages
# rule 来源为规避反爬限流采用的低并发、请求抖动与命中限流后的加长退避。
RULE_CHAPTER_CONCURRENCY = _RUNTIME_CONFIG.rule_chapter_concurrency
RULE_REQUEST_JITTER_SECONDS = _RUNTIME_CONFIG.rule_request_jitter_seconds
CRAWL_THROTTLE_BACKOFF_SECONDS = _RUNTIME_CONFIG.throttle_backoff_seconds
# 被来源站点限流时的典型状态码。
THROTTLE_STATUS_CODES = frozenset(_RUNTIME_CONFIG.throttle_status_codes)
# rule 正文「下一页」链接的可识别文案。
_NEXT_PAGE_LABELS = _RUNTIME_CONFIG.next_page_labels


class NovelCrawlerError(Exception):
    """小说 HTTP 爬取基础异常。"""


class NovelCrawlerConfigError(NovelCrawlerError):
    """小说来源配置缺失或不合法时抛出。"""


def _create_http_client(source: NovelCrawlSource | None = None) -> Any:
    """创建抓取用 HTTP 客户端。

    rule 来源默认改用浏览器 TLS 指纹的客户端，以绕过 Cloudflare 等 JA3/JA4 反爬；
    其余来源及测试注入的客户端仍使用 httpx。
    """
    if source is not None and source.source_type == RULE_SOURCE_TYPE and _CurlSession is not None:
        return _ImpersonateClient(timeout=HTTP_TIMEOUT, impersonate=IMPERSONATE_PROFILE, proxy=CRAWL_PROXY)
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True, trust_env=False, proxy=CRAWL_PROXY)


class _ImpersonateClient:
    """以浏览器 TLS 指纹发起请求的客户端适配器，接口对齐 httpx.AsyncClient。

    请求经同步 curl_cffi Session 在线程中发出，响应统一封装为 httpx.Response，
    避免 AsyncSession 在已有 FastAPI event loop 内触发嵌套事件循环。
    """

    def __init__(self, *, timeout: httpx.Timeout, impersonate: str, proxy: str | None = None) -> None:
        self._timeout = timeout
        self._proxy = proxy
        self._proxies = _proxy_mapping(proxy)
        self._session = _CurlSession(
            timeout=timeout.read or 20.0,
            impersonate=impersonate,
            trust_env=False,
            proxies=self._proxies,
        )
        self._request_lock = asyncio.Lock()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Any = None,
        json: Any = None,
        content: Any = None,
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Response:
        request = httpx.Request(method, url)
        if _is_loopback_url(url):
            async with httpx.AsyncClient(timeout=timeout or self._timeout, follow_redirects=True, trust_env=False) as client:
                return await client.request(
                    method,
                    url,
                    headers=_impersonate_request_headers(headers),
                    json=json,
                    content=content,
                )

        kwargs: dict[str, Any] = {
            "headers": _impersonate_request_headers(headers),
            "json": json,
            "allow_redirects": True,
            "accept_encoding": _IMPERSONATE_ACCEPT_ENCODING,
        }
        if content is not None:
            kwargs.pop("json", None)
            kwargs["data"] = content
        try:
            async with self._request_lock:
                response = await asyncio.to_thread(self._session.request, method, url, **kwargs)
        except Exception as exc:  # curl_cffi 自有异常，统一转为 httpx 网络错误以复用重试逻辑
            detail = _format_impersonate_connect_error(exc, url, self._proxy)
            raise httpx.ConnectError(detail, request=request) from exc
        return httpx.Response(
            response.status_code,
            headers=_decoded_response_headers(response.headers),
            content=response.content,
            request=request,
        )

    async def aclose(self) -> None:
        await asyncio.to_thread(self._session.close)

    async def __aenter__(self) -> "_ImpersonateClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


def _format_impersonate_connect_error(exc: Exception, url: str, proxy: str | None) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if not _is_tls_connect_failure(message):
        return message

    host = urlparse(url).hostname or ""
    fake_ips = _resolve_fake_ips(host)
    if not fake_ips:
        return message

    if proxy:
        proxy_state = f"当前爬虫代理={proxy}（可通过 NOVEL_CRAWL_PROXY 覆盖）"
        guidance = (
            "这通常表示本机 DNS 被代理软件接管，但当前代理出口或 DNS fake-ip 映射未能完成该目标站 TLS 握手，"
            "请切换代理节点、确认 Clash/TUN/mixed-port 代理链路，或修复代理 DNS 后重试。"
        )
    else:
        proxy_state = "当前未配置爬虫代理（可设置 NOVEL_CRAWL_PROXY）"
        guidance = "这通常表示本机 DNS 被代理软件接管，但后端爬虫请求没有配置可用代理出口，请配置 NOVEL_CRAWL_PROXY 或修复代理/DNS 后重试。"
    return (
        f"{message}；检测到 {host} 解析到 fake-ip {', '.join(fake_ips)}，"
        f"{proxy_state}。{guidance}"
    )


def _is_tls_connect_failure(message: str) -> bool:
    return any(marker in message for marker in _TLS_FAILURE_MARKERS)


def _is_loopback_url(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _resolve_fake_ips(host: str) -> list[str]:
    if not host:
        return []
    fake_ips: list[str] = []
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return []
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if any(ip in network for network in _FAKE_IP_NETWORKS):
            fake_ips.append(str(ip))
    return sorted(set(fake_ips))


def extract_json_path_values(data: Any, path: str) -> list[Any]:
    """按来源配置支持的简化 JSONPath 提取值。"""
    tokens = _parse_json_path(path)
    if not tokens:
        return []

    values = [data]
    for token in tokens:
        next_values: list[Any] = []
        for value in values:
            if token == "*":
                if isinstance(value, list):
                    next_values.extend(value)
                elif isinstance(value, dict):
                    next_values.extend(value.values())
                continue
            if isinstance(token, int):
                if isinstance(value, list) and -len(value) <= token < len(value):
                    next_values.append(value[token])
                continue
            if isinstance(value, dict) and token in value:
                next_values.append(value[token])
        values = next_values
        if not values:
            break
    return values


def extract_css_values(selector: Selector, css: str) -> list[Any]:
    """按 CSS 选择器从 HTML 中提取值。

    选择器以 parsel 语法书写：带 ``::text`` / ``::attr(name)`` 伪元素时按字符串列表返回；
    否则视为元素选择器，逐个返回元素的规整文本（块级文本以换行连接，适合抽取正文）。
    """
    rule = css.strip()
    if not rule:
        return []
    if "::text" in rule or "::attr" in rule:
        return [value for value in selector.css(rule).getall()]
    return [_selector_text(node) for node in selector.css(rule)]


def _selector_text(node: Selector) -> str:
    """提取元素的全部后代文本，按文本节点换行连接并去除空白。"""
    parts = [part.strip() for part in node.css("::text").getall()]
    return "\n".join(part for part in parts if part)


def extract_values(source: NovelCrawlSource, document: Any, path: str) -> list[Any]:
    """按来源类型分派字段提取：rule 用 CSS 选择器，其余用 JSONPath。"""
    if not path or not path.strip():
        return []
    if source.source_type == RULE_SOURCE_TYPE:
        if not isinstance(document, Selector):
            return []
        return extract_css_values(document, path)
    return extract_json_path_values(document, path)


async def search_books(
    source: NovelCrawlSource,
    query: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[CrawlSearchResult]:
    """通过配置好的 HTTP 来源搜索小说。

    若 ``search_url_template`` 含 ``{page}`` 占位符，则自动翻页直至空页或达上限。
    """
    if not source.search_url_template.strip():
        raise NovelCrawlerConfigError("search_url_template is required")

    if client is not None:
        return await _search_with_client(source, query, client)
    async with _create_http_client(source) as owned_client:
        return await _search_with_client(source, query, owned_client)


async def _search_with_client(
    source: NovelCrawlSource,
    query: str,
    client: httpx.AsyncClient,
) -> list[CrawlSearchResult]:
    base_context = {"q": query.strip(), "keyword": query.strip(), "sort": query.strip()}
    paginated = "{page}" in source.search_url_template
    browser_proxy_paginated = (
        paginated
        and source.source_type == RULE_SOURCE_TYPE
        and _is_browser_proxy_fetch_url(source.search_url_template)
    )
    results: list[CrawlSearchResult] = []
    seen: set[str] = set()
    page = 1
    while True:
        data = await _request_document_with_retry(
            client,
            source.api_search_method,
            source.search_url_template,
            source.api_search_headers,
            source.api_search_body,
            {**base_context, "page": page},
            source,
            browser_proxy_wait_selector=_first_browser_proxy_wait_selector(
                source,
                source.api_search_book_title_path,
                source.api_search_book_id_path,
                source.api_search_book_url_path,
            ),
        )
        fresh = [
            book
            for book in _parse_search_results(source, data)
            if (book.dirid or book.title) and (book.dirid or book.title) not in seen
        ]
        for book in fresh:
            seen.add(book.dirid or book.title)
        results.extend(fresh)
        if (
            not paginated
            or not fresh
            or _has_exact_title_match(fresh, query)
            or browser_proxy_paginated
            or page >= MAX_SEARCH_PAGES
        ):
            break
        page += 1
    return results


def _has_exact_title_match(books: list[CrawlSearchResult], query: str) -> bool:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return False
    return any(_normalize_search_text(book.title) == normalized_query for book in books)


def _normalize_search_text(value: Any) -> str:
    return re.sub(r"\s+", "", _to_text(value)).casefold()


async def fetch_book_detail(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    *,
    client: httpx.AsyncClient | None = None,
) -> CrawlSearchResult:
    """获取选中小说详情，并合并配置字段。"""
    if not source.api_book_url.strip():
        return book

    context = _book_context(book)
    detail_wait_selector = _book_detail_browser_proxy_wait_selector(source)
    if client is not None:
        data = await _request_document(
            client,
            source.api_book_method,
            source.api_book_url,
            source.api_book_headers,
            source.api_book_body,
            context,
            source,
            browser_proxy_wait_selector=detail_wait_selector,
            format_status_error=True,
        )
        return _merge_book_detail(source, book, data)

    async with _create_http_client(source) as owned_client:
        data = await _request_document(
            owned_client,
            source.api_book_method,
            source.api_book_url,
            source.api_book_headers,
            source.api_book_body,
            context,
            source,
            browser_proxy_wait_selector=detail_wait_selector,
            format_status_error=True,
        )
        return _merge_book_detail(source, book, data)


async def fetch_chapter_count(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    *,
    client: httpx.AsyncClient | None = None,
) -> int:
    """返回选中小说的章节总数。"""
    if book.lastchapterid > 0:
        return book.lastchapterid
    metas = await fetch_chapter_metas(source, book, client=client)
    if metas:
        return len(metas)
    return max(book.lastchapterid, 0)


async def fetch_chapter_metas(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """获取并标准化章节列表元数据。"""
    if not source.api_chapter_list_url.strip():
        return _fallback_chapter_metas(book)

    context = _book_context(book)
    chapter_list_wait_selector = _first_browser_proxy_wait_selector(
        source,
        source.api_chapter_list_id_path,
        source.api_chapter_list_name_path,
    )
    if client is not None:
        data = await _request_document(
            client,
            source.api_chapter_list_method,
            source.api_chapter_list_url,
            source.api_chapter_list_headers,
            source.api_chapter_list_body,
            context,
            source,
            browser_proxy_wait_selector=chapter_list_wait_selector,
            format_status_error=True,
        )
        metas = _parse_chapter_metas(source, book, data)
        return metas or _fallback_chapter_metas(book)

    async with _create_http_client(source) as owned_client:
        data = await _request_document(
            owned_client,
            source.api_chapter_list_method,
            source.api_chapter_list_url,
            source.api_chapter_list_headers,
            source.api_chapter_list_body,
            context,
            source,
            browser_proxy_wait_selector=chapter_list_wait_selector,
            format_status_error=True,
        )
        metas = _parse_chapter_metas(source, book, data)
        return metas or _fallback_chapter_metas(book)


async def fetch_chapters(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    start_chapter: int,
    end_chapter: int,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[CrawlChapterDraft]:
    """爬取指定范围内的章节正文。"""
    metas = _slice_chapter_metas(await fetch_chapter_metas(source, book, client=client), start_chapter, end_chapter)
    if not metas:
        return []
    if client is not None:
        return await _fetch_chapters_from_metas(source, book, metas, client=client)

    chapters = [chapter async for chapter in crawl_chapters_parallel(source, book, metas)]
    return sorted(chapters, key=lambda chapter: chapter.key)


async def stream_chapters(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    start_chapter: int,
    end_chapter: int,
    *,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """以 NDJSON 兼容字典流式返回爬取进度。"""
    if client is not None:
        metas = _slice_chapter_metas(await fetch_chapter_metas(source, book, client=client), start_chapter, end_chapter)
        async for event in _stream_chapter_events(source, book, metas, start_chapter, end_chapter, client):
            yield event
        return

    async with _create_http_client(source) as owned_client:
        metas = _slice_chapter_metas(
            await fetch_chapter_metas(source, book, client=owned_client),
            start_chapter,
            end_chapter,
        )
        async for event in _stream_chapter_events(source, book, metas, start_chapter, end_chapter, owned_client):
            yield event


async def _stream_chapter_events(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    metas: list[dict[str, Any]],
    start_chapter: int,
    end_chapter: int,
    client: httpx.AsyncClient,
) -> AsyncIterator[dict[str, Any]]:
    total = len(metas)
    yield {"type": "start", "total": total, "startChapter": start_chapter, "endChapter": end_chapter}
    completed = 0
    async for chapter in _stream_chapters_from_metas(
        source,
        book,
        metas,
        client=client,
        concurrency=_chapter_concurrency(source, STREAM_CHAPTER_CONCURRENCY),
    ):
        completed += 1
        yield {
            "type": "chapter",
            "completed": completed,
            "total": total,
            "chapter": chapter.model_dump(mode="json", by_alias=True),
        }
    yield {"type": "done", "completed": completed, "total": total}


def _chapter_concurrency(source: NovelCrawlSource, default: int) -> int:
    """rule 来源使用更低并发以规避站点限流，其余沿用默认并发。"""
    if source.source_type == RULE_SOURCE_TYPE:
        return min(RULE_CHAPTER_CONCURRENCY, default) if default else RULE_CHAPTER_CONCURRENCY
    return default


def _is_throttle_error(exc: Exception | None) -> bool:
    """判断异常是否为来源站点限流（403/429）。"""
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in THROTTLE_STATUS_CODES


def _is_cloudflare_challenge_response(response: httpx.Response) -> bool:
    headers = response.headers
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    text = response.text[:5000].lower()
    if any(marker in text for marker in _CLOUDFLARE_CHALLENGE_MARKERS):
        return True
    server = headers.get("server", "").lower()
    return "cloudflare" in server and response.status_code in THROTTLE_STATUS_CODES


def _format_cloudflare_challenge_error(exc: httpx.HTTPStatusError) -> str:
    return (
        f"来源站点返回 Cloudflare 浏览器挑战: HTTP {exc.response.status_code} {exc.request.url}"
        "（当前 HTTP 爬虫不能执行需要浏览器 JavaScript/Cookie 的挑战；请稍后重试、切换代理出口、"
        "换用允许自动化访问的来源/API，或在有授权时配置已通过验证的浏览器会话 Cookie。）"
    )


def _format_source_status_error(exc: httpx.HTTPStatusError, source: NovelCrawlSource) -> str:
    if _is_cloudflare_challenge_response(exc.response):
        return _format_cloudflare_challenge_error(exc)

    status_code = exc.response.status_code
    url = str(exc.request.url)
    response_text = exc.response.text.strip()
    prefix = "来源站点拒绝或限流" if _is_throttle_error(exc) else "来源站点请求失败"
    detail = f"{prefix}: HTTP {status_code} {url}"
    if response_text:
        detail = f"{detail}: {response_text[:200]}"
    if _is_throttle_error(exc):
        suggestions = ["稍后重试", "切换 NOVEL_CRAWL_PROXY 代理出口", "调整来源请求头"]
        if source.source_type == RULE_SOURCE_TYPE:
            suggestions.append("降低 NOVEL_CRAWL_RULE_CONCURRENCY")
        detail = f"{detail}（可尝试：{'、'.join(suggestions)}）"
    return detail


def _format_http_error(exc: httpx.HTTPError) -> str:
    request = getattr(exc, "request", None)
    url = str(request.url) if request is not None else ""
    if isinstance(exc, httpx.TimeoutException):
        if _is_browser_proxy_fetch_url(url):
            return (
                f"浏览器代理请求超时: {url}"
                f"（当前等待约 {BROWSER_PROXY_HTTP_TIMEOUT.read:.1f} 秒；请确认 novel_browser_proxy 已重启到最新代码、"
                "目标站点可访问，或调大 NOVEL_BROWSER_PROXY_TIMEOUT_MS / NOVEL_CRAWL_HTTP_TIMEOUT_SECONDS。）"
            )
        return f"来源站点请求超时: {url or 'unknown url'}"
    if isinstance(exc, httpx.ConnectError) and _is_browser_proxy_fetch_url(url):
        return (
            f"浏览器代理不可用: {url}"
            "（未能连接到本地 /fetch 服务；请先启动 novel_browser_proxy，例如在 backend 目录运行 "
            "python -m app.services.novel_browser_proxy，并确认 127.0.0.1:8787 已监听。）"
        )
    message = str(exc).strip() or exc.__class__.__name__
    if url and url not in message:
        return f"来源站点请求失败: {message}: {url}"
    return f"来源站点请求失败: {message}"


def _is_browser_proxy_fetch_url(url: str) -> bool:
    return bool(url) and _is_loopback_url(url) and urlparse(url).path.rstrip("/") == "/fetch"


async def crawl_chapters_parallel(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    metas: list[dict[str, Any]],
) -> AsyncIterator[CrawlChapterDraft]:
    """多进程爬取章节详情，每个进程内并发运行协程。"""
    if not metas:
        return

    workers = min(MAX_CRAWL_PROCESSES, os.cpu_count() or 1, len(metas))
    # rule 来源强制单进程低并发：多进程并发的浏览器指纹连接极易触发 Cloudflare 限流。
    if source.source_type == RULE_SOURCE_TYPE:
        workers = 1
    if workers <= 1:
        concurrency = _chapter_concurrency(source, CHAPTER_COROUTINES_PER_PROCESS)
        async with _create_http_client(source) as client:
            for chapter in await _fetch_chapters_from_metas(source, book, metas, client=client, concurrency=concurrency):
                yield chapter
        return

    loop = asyncio.get_running_loop()
    source_data = _dump_source(source)
    book_data = book.model_dump(mode="json")
    chunks = _partition_metas(metas, workers)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            loop.run_in_executor(
                executor,
                _crawl_chapter_batch_worker,
                source_data,
                book_data,
                chunk,
                CHAPTER_COROUTINES_PER_PROCESS,
            )
            for chunk in chunks
        ]
        for future in futures:
            for item in await future:
                yield CrawlChapterDraft.model_validate(item)


def _crawl_chapter_batch_worker(
    source_data: dict[str, Any],
    book_data: dict[str, Any],
    metas: list[dict[str, Any]],
    concurrency: int,
) -> list[dict[str, Any]]:
    source = NovelCrawlSource(**source_data)
    book = CrawlSearchResult.model_validate(book_data)
    return asyncio.run(_crawl_chapter_batch_worker_async(source, book, metas, concurrency))


async def _crawl_chapter_batch_worker_async(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    metas: list[dict[str, Any]],
    concurrency: int,
) -> list[dict[str, Any]]:
    async with _create_http_client(source) as client:
        chapters = await _fetch_chapters_from_metas(source, book, metas, client=client, concurrency=concurrency)
        return [chapter.model_dump(mode="json") for chapter in chapters]


async def _fetch_chapters_from_metas(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    metas: list[dict[str, Any]],
    *,
    client: httpx.AsyncClient,
    concurrency: int = CHAPTER_COROUTINES_PER_PROCESS,
) -> list[CrawlChapterDraft]:
    semaphore = asyncio.Semaphore(max(concurrency, 1))

    async def fetch_one(meta: dict[str, Any]) -> CrawlChapterDraft:
        async with semaphore:
            return await _fetch_chapter_detail_with_retry(source, book, meta, client=client)

    return list(await asyncio.gather(*(fetch_one(meta) for meta in metas)))


async def _stream_chapters_from_metas(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    metas: list[dict[str, Any]],
    *,
    client: httpx.AsyncClient,
    concurrency: int,
) -> AsyncIterator[CrawlChapterDraft]:
    if not metas:
        return

    async def fetch_one(meta: dict[str, Any]) -> CrawlChapterDraft:
        return await _fetch_chapter_detail_with_retry(source, book, meta, client=client)

    meta_iter = iter(metas)
    pending: set[asyncio.Task[CrawlChapterDraft]] = set()

    def schedule_next() -> None:
        try:
            meta = next(meta_iter)
        except StopIteration:
            return
        pending.add(asyncio.create_task(fetch_one(meta)))

    for _ in range(min(max(concurrency, 1), len(metas))):
        schedule_next()

    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                yield await task
                schedule_next()
    finally:
        for task in pending:
            if not task.done():
                task.cancel()


async def _fetch_chapter_detail_with_retry(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    meta: dict[str, Any],
    *,
    client: httpx.AsyncClient,
) -> CrawlChapterDraft:
    last_exc: Exception | None = None
    for attempt in range(CRAWL_HTTP_RETRIES + 1):
        await _rule_request_jitter(source)
        try:
            return await _fetch_chapter_detail(source, book, meta, client=client)
        except NovelCrawlerConfigError:
            raise
        except (NovelCrawlerError, httpx.HTTPError) as exc:
            last_exc = exc
            if attempt >= CRAWL_HTTP_RETRIES:
                break
            delay = CRAWL_HTTP_RETRY_BACKOFF_SECONDS * (2**attempt)
            if _is_throttle_error(exc):
                # 命中限流：等待更久，给来源站点的速率窗口留出恢复时间。
                delay = max(delay, CRAWL_THROTTLE_BACKOFF_SECONDS * (attempt + 1))
            if delay > 0:
                await asyncio.sleep(delay)
    return _failed_chapter_draft(book, meta, _format_chapter_fetch_error(last_exc))


async def _rule_request_jitter(source: NovelCrawlSource) -> None:
    """rule 来源在每次请求前加入随机抖动，避免并发请求形成可被识别的突发流量。"""
    if source.source_type == RULE_SOURCE_TYPE and RULE_REQUEST_JITTER_SECONDS > 0:
        await asyncio.sleep(random.uniform(0, RULE_REQUEST_JITTER_SECONDS))


async def _fetch_chapter_detail(
    source: NovelCrawlSource,
    book: CrawlSearchResult,
    meta: dict[str, Any],
    *,
    client: httpx.AsyncClient,
) -> CrawlChapterDraft:
    url_template = source.api_chapter_url.strip()
    if source.source_type == RULE_SOURCE_TYPE and not url_template:
        url_template = _to_text(meta.get("url"))
    context = {**_book_context(book), **_chapter_context(meta)}
    data: Any = {}
    current_url = ""
    if url_template:
        current_url = _render_url(url_template, context)
        chapter_wait_selector = _chapter_content_browser_proxy_wait_selector(source)
        data = await _request_chapter_document(
            client,
            source.api_chapter_method,
            url_template,
            source.api_chapter_headers,
            source.api_chapter_body,
            context,
            source,
            browser_proxy_wait_selector=chapter_wait_selector,
        )

    name = _first_text(source, data, source.api_chapter_name_path) or str(meta.get("chaptername") or "")
    text = _first_text(source, data, source.api_chapter_content_path) or str(meta.get("txt") or "")
    if (
        source.source_type == RULE_SOURCE_TYPE
        and isinstance(data, Selector)
        and current_url
        and source.api_chapter_content_path.strip()
    ):
        text = await _collect_rule_content(
            source,
            meta,
            data,
            text,
            current_url=current_url,
            client=client,
            browser_proxy_wait_selector=chapter_wait_selector,
        )
    update_time = _first_text(source, data, source.api_chapter_time_path) or str(meta.get("time") or "")
    md5 = _first_text(source, data, source.api_chapter_md5_path) or str(meta.get("md5") or "")
    chapter_id = _to_int(meta.get("chapterid"), int(meta.get("ordinal") or 0))
    return CrawlChapterDraft(
        key=int(meta.get("ordinal") or chapter_id),
        novelDirid=book.dirid,
        chapterid=chapter_id,
        chaptername=name or f"第{meta.get('ordinal')}章",
        time=update_time,
        txt=text,
        md5=md5,
        event="",
        eventState=0,
        errorReason=None,
    )


async def _collect_rule_content(
    source: NovelCrawlSource,
    meta: dict[str, Any],
    first_page: Selector,
    first_text: str,
    *,
    current_url: str,
    client: httpx.AsyncClient,
    browser_proxy_wait_selector: str = "",
) -> str:
    """拼接同一章的多页正文：沿「下一页」链接逐页抓取并合并。

    仅跟随指向同一章节（URL 含 ``章节id_页码``）的分页链接，遇到「下一章」等跨章链接即停止。
    """
    chapter_id = _to_int(meta.get("chapterid"), int(meta.get("ordinal") or 0))
    browser_proxy_wait_selector = browser_proxy_wait_selector or _chapter_content_browser_proxy_wait_selector(source)
    parts = [first_text]
    visited = {_browser_proxy_target_url(current_url)}
    page = first_page
    page_url = current_url
    while len(visited) < MAX_CONTENT_PAGES:
        next_target_url = _find_next_content_page(page, _browser_proxy_target_url(page_url), chapter_id)
        if not next_target_url or next_target_url in visited:
            break
        visited.add(next_target_url)
        next_url = _browser_proxy_url_for_target(page_url, next_target_url)
        page = await _request_chapter_document(
            client,
            source.api_chapter_method,
            next_url,
            source.api_chapter_headers,
            source.api_chapter_body,
            {},
            source,
            browser_proxy_wait_selector=browser_proxy_wait_selector,
        )
        page_text = _first_text(source, page, source.api_chapter_content_path)
        if not page_text:
            break
        parts.append(page_text)
        page_url = next_url
    return "\n".join(part for part in parts if part)


def _find_next_content_page(page: Selector, current_url: str, chapter_id: int) -> str:
    """在正文页查找指向同一章下一分页的链接，找不到返回空串。"""
    for anchor in page.css("a"):
        label = "".join(anchor.css("::text").getall()).strip()
        if label not in _NEXT_PAGE_LABELS:
            continue
        href = anchor.attrib.get("href") or ""
        if not href:
            continue
        resolved = urljoin(current_url, href)
        if re.search(rf"/{chapter_id}_\d+\.html?(?:[?#]|$)", resolved):
            return resolved
    return ""


def _failed_chapter_draft(
    book: CrawlSearchResult,
    meta: dict[str, Any],
    error_reason: str,
) -> CrawlChapterDraft:
    chapter_id = _to_int(meta.get("chapterid"), int(meta.get("ordinal") or 0))
    return CrawlChapterDraft(
        key=int(meta.get("ordinal") or chapter_id),
        novelDirid=book.dirid,
        chapterid=chapter_id,
        chaptername=str(meta.get("chaptername") or f"Chapter {meta.get('ordinal') or chapter_id}"),
        time=str(meta.get("time") or ""),
        txt="",
        md5=str(meta.get("md5") or ""),
        event="",
        eventState=-1,
        errorReason=error_reason,
    )


def _format_chapter_fetch_error(exc: Exception | None) -> str:
    if exc is None:
        return "chapter fetch failed"
    if isinstance(exc, httpx.HTTPStatusError):
        response_text = exc.response.text.strip()
        detail = f"HTTP {exc.response.status_code}"
        if response_text:
            detail = f"{detail}: {response_text[:200]}"
        if _is_throttle_error(exc):
            detail = f"{detail}（疑似来源站点限流，可稍后重试或调低 NOVEL_CRAWL_RULE_CONCURRENCY）"
        return f"chapter fetch failed: {detail}"
    message = str(exc).strip() or exc.__class__.__name__
    return f"chapter fetch failed: {message}"


async def _request_chapter_document(
    client: httpx.AsyncClient,
    method: str,
    url_template: str,
    headers_raw: str,
    body_raw: str,
    context: dict[str, Any],
    source: NovelCrawlSource,
    *,
    browser_proxy_wait_selector: str = "",
) -> Any:
    rendered_url = _render_url(url_template, context)
    direct_url = _browser_proxy_target_url(rendered_url)
    if source.source_type == RULE_SOURCE_TYPE and direct_url != rendered_url:
        try:
            return await _request_document(
                client,
                method,
                direct_url,
                headers_raw,
                body_raw,
                context,
                source,
            )
        except httpx.HTTPStatusError as exc:
            if not _should_fallback_to_browser_proxy_for_chapter(exc):
                raise NovelCrawlerError(_format_source_status_error(exc, source)) from exc
        except httpx.HTTPError:
            pass

    return await _request_document(
        client,
        method,
        url_template,
        headers_raw,
        body_raw,
        context,
        source,
        browser_proxy_wait_selector=browser_proxy_wait_selector,
        format_status_error=True,
    )


def _should_fallback_to_browser_proxy_for_chapter(exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code in THROTTLE_STATUS_CODES:
        return True
    return _is_cloudflare_challenge_response(exc.response)


async def _request_document(
    client: httpx.AsyncClient,
    method: str,
    url_template: str,
    headers_raw: str,
    body_raw: str,
    context: dict[str, Any],
    source: NovelCrawlSource,
    *,
    browser_proxy_wait_selector: str = "",
    format_status_error: bool = False,
) -> Any:
    method = (method or "GET").strip().upper()
    url = _render_url(url_template, context)
    headers = _parse_json_mapping(headers_raw, context)
    body = _parse_request_body(body_raw, context, headers) if method in HTTP_METHODS_WITH_BODY else None
    browser_proxy_request = _build_browser_proxy_request(url, method, headers, body, browser_proxy_wait_selector)
    if browser_proxy_request is not None:
        proxy_url, proxy_payload = browser_proxy_request
        response = await client.request(
            "POST",
            proxy_url,
            headers=None,
            json=proxy_payload,
            timeout=BROWSER_PROXY_HTTP_TIMEOUT,
        )
    else:
        response = await client.request(method, url, **_request_kwargs(headers, body))
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if format_status_error:
            raise NovelCrawlerError(_format_source_status_error(exc, source)) from exc
        raise
    if source.source_type == RULE_SOURCE_TYPE:
        return Selector(text=response.text)
    try:
        return response.json()
    except ValueError as exc:
        raise NovelCrawlerError("crawl source did not return valid JSON") from exc


def _build_browser_proxy_request(
    url: str,
    method: str,
    headers: dict[str, str],
    body: Any,
    wait_selector: str = "",
) -> tuple[str, dict[str, Any]] | None:
    parsed = urlparse(url)
    if parsed.path.rstrip("/") != "/fetch" or not _is_loopback_url(url):
        return None

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    target_url = query.get("url", "").strip()
    if not target_url:
        return None

    payload: dict[str, Any] = {
        "url": _normalize_proxy_target_url(target_url),
        "method": method,
        "headers": headers,
    }
    if body is not None:
        payload["body"] = body
    for key in (
        "wait_until",
        "wait_selector",
        "wait_selector_timeout_ms",
        "wait_after_selector_ms",
        "wait_selector_state",
        "referer",
    ):
        if query.get(key):
            payload[key] = query[key]
    if wait_selector and "wait_selector" not in payload:
        payload["wait_selector"] = wait_selector

    proxy_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return proxy_url, payload


def _book_detail_browser_proxy_wait_selector(source: NovelCrawlSource) -> str:
    paths: list[str] = []
    if _same_nonempty_template(source.api_book_url, source.api_chapter_list_url):
        paths.extend([source.api_chapter_list_id_path, source.api_chapter_list_name_path])
    paths.extend(
        [
            source.api_book_title_path,
            source.api_book_author_path,
            source.api_book_intro_path,
        ]
    )
    return _first_browser_proxy_wait_selector(source, *paths)


def _chapter_content_browser_proxy_wait_selector(source: NovelCrawlSource) -> str:
    return _first_browser_proxy_wait_selector(
        source,
        source.api_chapter_content_path,
        source.api_chapter_name_path,
    )


def _first_browser_proxy_wait_selector(source: NovelCrawlSource, *paths: str) -> str:
    if source.source_type != RULE_SOURCE_TYPE:
        return ""
    for path in paths:
        selector = _css_wait_selector(path)
        if selector:
            return selector
    return ""


def _browser_proxy_target_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path.rstrip("/") != "/fetch" or not _is_loopback_url(url):
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    target_url = query.get("url", "").strip()
    return target_url or url


def _browser_proxy_url_for_target(proxy_url: str, target_url: str) -> str:
    parsed = urlparse(proxy_url)
    if parsed.path.rstrip("/") != "/fetch" or not _is_loopback_url(proxy_url):
        return target_url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["url"] = target_url
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(query), ""))


def _css_wait_selector(path: str) -> str:
    value = (path or "").strip()
    if not value:
        return ""
    selector = value.split("::", 1)[0].strip()
    return selector


def _same_nonempty_template(left: str, right: str) -> bool:
    left_value = (left or "").strip()
    return bool(left_value) and left_value == (right or "").strip()


def _normalize_proxy_target_url(url: str) -> str:
    return quote(url, safe=":/?&=%#[]@!$'()*+,;~-._")


async def _request_document_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url_template: str,
    headers_raw: str,
    body_raw: str,
    context: dict[str, Any],
    source: NovelCrawlSource,
    *,
    browser_proxy_wait_selector: str = "",
) -> Any:
    """带限流退避与抖动的请求封装，供搜索翻页等单次请求复用。"""
    last_exc: Exception | None = None
    for attempt in range(CRAWL_HTTP_RETRIES + 1):
        await _rule_request_jitter(source)
        try:
            return await _request_document(
                client,
                method,
                url_template,
                headers_raw,
                body_raw,
                context,
                source,
                browser_proxy_wait_selector=browser_proxy_wait_selector,
            )
        except (NovelCrawlerError, httpx.HTTPError) as exc:
            last_exc = exc
            if isinstance(exc, httpx.HTTPStatusError) and _is_cloudflare_challenge_response(exc.response):
                raise NovelCrawlerError(_format_source_status_error(exc, source)) from exc
            if attempt >= CRAWL_HTTP_RETRIES:
                if isinstance(exc, httpx.HTTPStatusError):
                    raise NovelCrawlerError(_format_source_status_error(exc, source)) from exc
                if isinstance(exc, httpx.HTTPError):
                    raise NovelCrawlerError(_format_http_error(exc)) from exc
                raise
            delay = CRAWL_HTTP_RETRY_BACKOFF_SECONDS * (2**attempt)
            if _is_throttle_error(exc):
                delay = max(delay, CRAWL_THROTTLE_BACKOFF_SECONDS * (attempt + 1))
            if delay > 0:
                await asyncio.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise NovelCrawlerError("request failed")


def _parse_search_results(source: NovelCrawlSource, data: Any) -> list[CrawlSearchResult]:
    ids = extract_values(source, data, source.api_search_book_id_path)
    titles = extract_values(source, data, source.api_search_book_title_path)
    urls = extract_values(source, data, source.api_search_book_url_path)
    last_chapters = extract_values(source, data, source.api_search_book_last_chapter_path)
    last_chapter_ids = extract_values(source, data, source.api_search_book_last_chapter_id_path)
    count = max(len(ids), len(titles), len(urls), 0)
    books: list[CrawlSearchResult] = []
    for index in range(count):
        raw_id = _nth(ids, index)
        if raw_id is None or _to_text(raw_id) == "":
            raw_id = _nth(urls, index)
        title = _to_text(_nth(titles, index))
        dirid, numeric_id = _resolve_source_id(source, raw_id, index + 1)
        if not dirid and not title:
            continue
        lastchapter = _to_text(_nth(last_chapters, index))
        books.append(
            CrawlSearchResult(
                dirid=dirid,
                id=numeric_id,
                full=_to_text(_nth(extract_values(source, data, source.api_search_book_update_status_path), index)),
                title=title,
                author=_to_text(_nth(extract_values(source, data, source.api_search_book_author_path), index)),
                cover=_to_text(_nth(extract_values(source, data, source.api_search_book_cover_path), index)),
                lastchapter=lastchapter,
                lastchapterid=_parse_last_chapter_count(
                    source,
                    _nth(last_chapter_ids, index),
                    fallback_text=lastchapter,
                ),
                lastupdate=_to_text(_nth(extract_values(source, data, source.api_search_book_last_update_path), index)),
                sortname=_to_text(_nth(extract_values(source, data, source.api_search_book_category_path), index)),
                intro=_to_text(_nth(extract_values(source, data, source.api_search_book_intro_path), index)),
                sourceKey=source.key,
            )
        )
    return books


def _merge_book_detail(source: NovelCrawlSource, book: CrawlSearchResult, data: Any) -> CrawlSearchResult:
    source_book_id = _first_text(source, data, source.api_book_id_path) or book.dirid
    lastchapter = _first_text(source, data, source.api_book_last_chapter_path) or book.lastchapter
    detail = CrawlSearchResult(
        dirid=source_book_id,
        id=_to_int(source_book_id, book.id),
        full=_first_text(source, data, source.api_book_update_status_path) or book.full,
        title=_first_text(source, data, source.api_book_title_path) or book.title,
        author=_first_text(source, data, source.api_book_author_path) or book.author,
        cover=_first_text(source, data, source.api_book_cover_path) or book.cover,
        lastchapter=lastchapter,
        lastchapterid=_parse_last_chapter_count(
            source,
            _first_value(source, data, source.api_book_last_chapter_id_path),
            fallback_text=lastchapter,
            default=book.lastchapterid,
        ),
        lastupdate=_first_text(source, data, source.api_book_last_update_path) or book.lastupdate,
        sortname=_first_text(source, data, source.api_book_category_path) or book.sortname,
        intro=_first_text(source, data, source.api_book_intro_path) or book.intro,
        sourceKey=book.source_key or source.key,
    )
    if detail.lastchapterid <= 0:
        chapter_count = len(_parse_chapter_metas(source, detail, data))
        if chapter_count > 0:
            detail = detail.model_copy(update={"lastchapterid": chapter_count})
    return detail


def _parse_chapter_metas(source: NovelCrawlSource, book: CrawlSearchResult, data: Any) -> list[dict[str, Any]]:
    ids = extract_values(source, data, source.api_chapter_list_id_path)
    names = extract_values(source, data, source.api_chapter_list_name_path)
    times = extract_values(source, data, source.api_chapter_list_time_path)
    texts = extract_values(source, data, source.api_chapter_list_content_path)
    md5s = extract_values(source, data, source.api_chapter_list_md5_path)
    count = max(len(ids), len(names), len(texts), 0)
    is_rule = source.source_type == RULE_SOURCE_TYPE
    metas: list[dict[str, Any]] = []
    for index in range(count):
        raw_id = _nth(ids, index)
        if is_rule:
            chapter_id = _last_int(raw_id, index + 1)
            chapter_url = _absolute_url(source, _to_text(raw_id))
        else:
            chapter_id = _to_int(raw_id, index + 1)
            chapter_url = ""
        metas.append(
            {
                "ordinal": index + 1,
                "novel_dirid": book.dirid,
                "chapterid": chapter_id,
                "chaptername": _to_text(_nth(names, index)) or f"第{index + 1}章",
                "time": _to_text(_nth(times, index)),
                "txt": _to_text(_nth(texts, index)),
                "md5": _to_text(_nth(md5s, index)),
                "url": chapter_url,
            }
        )
    return metas


def _fallback_chapter_metas(book: CrawlSearchResult) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": index,
            "novel_dirid": book.dirid,
            "chapterid": index,
            "chaptername": f"第{index}章",
            "time": "",
            "txt": "",
            "md5": "",
        }
        for index in range(1, max(book.lastchapterid, 0) + 1)
    ]


def _slice_chapter_metas(
    metas: list[dict[str, Any]],
    start_chapter: int,
    end_chapter: int,
) -> list[dict[str, Any]]:
    start = max(start_chapter, 1)
    end = max(end_chapter, start)
    return metas[start - 1 : end]


def _first_value(source: NovelCrawlSource, data: Any, path: str) -> Any:
    values = extract_values(source, data, path)
    return values[0] if values else None


def _first_text(source: NovelCrawlSource, data: Any, path: str) -> str:
    return _to_text(_first_value(source, data, path))


def _resolve_source_id(source: NovelCrawlSource, raw_id: Any, fallback_index: int) -> tuple[str, int]:
    """返回 (dirid, 数字 id)。rule 源从 URL/文本中取末尾数字，api 源保留原始标识。"""
    if source.source_type == RULE_SOURCE_TYPE:
        numeric = _last_int(raw_id, fallback_index)
        return str(numeric), numeric
    return _to_text(raw_id), _to_int(raw_id, fallback_index)


def _absolute_url(source: NovelCrawlSource, href: str) -> str:
    """将相对链接按来源站点根地址补全为绝对地址。"""
    href = _to_text(href)
    if not href:
        return ""
    return urljoin(source.base_url or "", href)


def _nth(values: list[Any], index: int) -> Any:
    if not values:
        return None
    if index < len(values):
        return values[index]
    if len(values) == 1:
        return values[0]
    return None


def _parse_json_path(path: str) -> list[str | int]:
    raw = path.strip()
    if not raw:
        return []
    if raw.startswith("$"):
        raw = raw[1:]
    tokens: list[str | int] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == ".":
            index += 1
            continue
        if char == "[":
            end = raw.find("]", index)
            if end < 0:
                raise NovelCrawlerConfigError(f"invalid JSON path: {path}")
            content = raw[index + 1 : end].strip().strip("'\"")
            if content == "*":
                tokens.append("*")
            elif re.fullmatch(r"-?\d+", content):
                tokens.append(int(content))
            else:
                tokens.append(content)
            index = end + 1
            continue
        end = index
        while end < len(raw) and raw[end] not in ".[":
            end += 1
        tokens.append(raw[index:end])
        index = end
    return [token for token in tokens if token != ""]


def _render_url(template: str, context: dict[str, Any]) -> str:
    """渲染请求 URL：先处理 token 加密指令，再替换并编码普通 {占位符}。"""
    with_tokens = _apply_enc_directives(template, context)
    return _render_template(with_tokens, context, encode_url_values=True)


def _apply_enc_directives(template: str, context: dict[str, Any]) -> str:
    """将 ``enc:算法名(载荷)`` 指令替换为 URL 编码后的加密 token。

    载荷内的 ``{占位符}`` 先按上下文渲染（不做 URL 编码，以保持 JSON 原貌），
    再交由指定算法加密、base64 输出并整体 URL 编码。
    """
    result: list[str] = []
    index = 0
    while True:
        match = _ENC_DIRECTIVE_RE.search(template, index)
        if not match:
            result.append(template[index:])
            break
        result.append(template[index : match.start()])
        cipher_name = match.group(1)
        payload, end = _read_balanced(template, match.end())
        rendered_payload = _render_template(payload, context, encode_url_values=False)
        token = encrypt_token(cipher_name, rendered_payload)
        result.append(quote(token, safe=""))
        index = end
    return "".join(result)


def _read_balanced(template: str, start: int) -> tuple[str, int]:
    """从 start 处读取括号平衡的载荷，返回 (载荷, 右括号后的位置)。"""
    depth = 1
    cursor = start
    while cursor < len(template):
        char = template[cursor]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return template[start:cursor], cursor + 1
        cursor += 1
    raise NovelCrawlerConfigError("unbalanced enc(...) directive in URL template")


def _render_template(template: str, context: dict[str, Any], *, encode_url_values: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = _to_text(context.get(key, ""))
        return quote(value, safe="") if encode_url_values else value

    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", replace, template)


def _parse_json_mapping(raw: str, context: dict[str, Any]) -> dict[str, str]:
    if not raw.strip():
        return {}
    rendered = _render_template(raw, context, encode_url_values=False)
    data = json.loads(rendered)
    if not isinstance(data, dict):
        raise NovelCrawlerConfigError("request headers must be a JSON object")
    return {str(key): _to_text(value) for key, value in data.items()}


def _parse_json_body(raw: str, context: dict[str, Any]) -> Any:
    rendered = _render_template(raw, context, encode_url_values=False)
    return json.loads(rendered)


def _parse_request_body(raw: str, context: dict[str, Any], headers: dict[str, str]) -> Any:
    stripped = raw.strip()
    if not stripped:
        return None
    if _is_form_urlencoded_headers(headers) and stripped.startswith('"'):
        template = json.loads(stripped)
        if isinstance(template, str):
            return _render_template(template, context, encode_url_values=True)
        return template
    if _looks_like_json_body(stripped):
        return _parse_json_body(raw, context)
    if _allows_raw_request_body(headers):
        return _render_template(raw, context, encode_url_values=_is_form_urlencoded_headers(headers))
    return _parse_json_body(raw, context)


def _request_kwargs(headers: dict[str, str], body: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"headers": headers}
    if body is None:
        return kwargs
    if _is_form_urlencoded_headers(headers):
        kwargs["content"] = _form_urlencoded_body(body)
    elif isinstance(body, str):
        kwargs["content"] = body
    else:
        kwargs["json"] = body
    return kwargs


def _form_urlencoded_body(body: Any) -> str:
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        return urlencode(
            {str(key): _normalize_form_value(value) for key, value in body.items()},
            doseq=True,
        )
    return _to_text(body)


def _normalize_form_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return [_normalize_form_value(item) for item in value]
    return _to_text(value)


def _looks_like_json_body(raw: str) -> bool:
    return raw[:1] in {'"', "{", "["} or raw in {"null", "true", "false"} or re.fullmatch(r"-?\d+(?:\.\d+)?", raw) is not None


def _allows_raw_request_body(headers: dict[str, str]) -> bool:
    content_type = _header_value(headers, "content-type").lower()
    return bool(content_type) and "application/json" not in content_type


def _is_form_urlencoded_headers(headers: dict[str, str]) -> bool:
    return "application/x-www-form-urlencoded" in _header_value(headers, "content-type").lower()


def _header_value(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def _book_context(book: CrawlSearchResult) -> dict[str, Any]:
    return {
        "id": book.id or book.dirid,
        "bookid": book.dirid or book.id,
        "dirid": book.dirid or book.id,
        "title": book.title,
        "sourceKey": book.source_key,
        "source_key": book.source_key,
    }


def _chapter_context(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "chapterid": meta.get("chapterid", ""),
        "chapter_id": meta.get("chapterid", ""),
        "chapter": meta.get("chapterid", ""),
        "chaptername": meta.get("chaptername", ""),
        "index": meta.get("ordinal", ""),
    }


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        text = _to_text(value)
        match = re.search(r"\d+", text)
        return int(match.group(0)) if match else default


def _parse_last_chapter_count(
    source: NovelCrawlSource,
    value: Any,
    *,
    fallback_text: str = "",
    default: int = 0,
) -> int:
    if source.source_type == RULE_SOURCE_TYPE and source.api_chapter_list_url.strip():
        if _looks_like_resource_locator(value):
            return default
        if value is None or _to_text(value) == "":
            return default
    parsed = _to_int(value, 0)
    if parsed > 0:
        return parsed
    if source.source_type == RULE_SOURCE_TYPE and not source.api_chapter_list_url.strip():
        return _to_int(fallback_text, default)
    return default


def _looks_like_resource_locator(value: Any) -> bool:
    text = _to_text(value)
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        return True
    if "/" in text or "\\" in text:
        return True
    return re.search(r"\.[A-Za-z0-9]{2,5}(?:[?#].*)?$", text) is not None


def _last_int(value: Any, default: int = 0) -> int:
    """提取文本中最后一个整数，常用于从章节链接 URL 末尾取章节 ID。"""
    matches = re.findall(r"\d+", _to_text(value))
    return int(matches[-1]) if matches else default


def _partition_metas(metas: list[dict[str, Any]], workers: int) -> list[list[dict[str, Any]]]:
    chunk_size = max((len(metas) + workers - 1) // workers, 1)
    return [metas[index : index + chunk_size] for index in range(0, len(metas), chunk_size)]


def _dump_source(source: NovelCrawlSource) -> dict[str, Any]:
    return {
        field: getattr(source, field)
        for field in (
            "key",
            "name",
            "base_url",
            "desc",
            "builtin",
            "source_type",
            "scope",
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
    }
