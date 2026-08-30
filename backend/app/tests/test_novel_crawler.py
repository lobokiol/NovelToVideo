from __future__ import annotations

import asyncio
import socket
from types import SimpleNamespace
from typing import Any

import pytest
import httpx

from app.models.novel import NovelCrawlSource
from app.services import novel_crawler


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_rule_impersonate_client_runs_sync_curl_session_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class ForbiddenAsyncSession:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("rule requests must not use curl_cffi.AsyncSession")

    class FakeCurlSession:
        def __init__(self, *, timeout: float, impersonate: str, **kwargs: Any) -> None:
            calls["timeout"] = timeout
            calls["impersonate"] = impersonate
            calls["session_kwargs"] = kwargs
            calls["closed"] = False

        def request(self, method: str, url: str, **kwargs: Any) -> SimpleNamespace:
            with pytest.raises(RuntimeError, match="no running event loop"):
                asyncio.get_running_loop()
            calls["request"] = (method, url, kwargs)
            return SimpleNamespace(
                status_code=200,
                headers={"content-type": "text/html"},
                content=b"<html>ok</html>",
            )

        def close(self) -> None:
            calls["closed"] = True

    monkeypatch.setattr(novel_crawler, "_CurlAsyncSession", ForbiddenAsyncSession, raising=False)
    monkeypatch.setattr(novel_crawler, "_CurlSession", FakeCurlSession, raising=False)

    source = NovelCrawlSource(key="rule", name="Rule Source", source_type="rule")
    async with novel_crawler._create_http_client(source) as client:
        response = await client.request(
            "GET",
            "https://example.test/search",
            headers={"x-test": "1", "Accept-Encoding": "gzip, deflate, br"},
        )

    assert response.status_code == 200
    assert response.text == "<html>ok</html>"
    assert calls["impersonate"] == novel_crawler.IMPERSONATE_PROFILE
    assert calls["session_kwargs"]["trust_env"] is False
    assert calls["session_kwargs"]["proxies"] == {
        "http": novel_crawler.CRAWL_PROXY,
        "https": novel_crawler.CRAWL_PROXY,
    }
    assert calls["request"][0] == "GET"
    assert calls["request"][1] == "https://example.test/search"
    assert calls["request"][2]["headers"] == {"x-test": "1"}
    assert calls["request"][2]["accept_encoding"] == "gzip, deflate"
    assert "proxy" not in calls["request"][2]
    assert "proxies" not in calls["request"][2]
    assert calls["closed"] is True


@pytest.mark.anyio
async def test_rule_impersonate_client_wraps_decoded_body_without_encoded_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCurlSession:
        def __init__(self, *, timeout: float, impersonate: str, **kwargs: Any) -> None:
            pass

        def request(self, method: str, url: str, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                status_code=200,
                headers={
                    "content-encoding": "gzip",
                    "content-length": "120",
                    "content-type": "text/html; charset=utf-8",
                },
                content=b"<html>ok</html>",
            )

        def close(self) -> None:
            pass

    monkeypatch.setattr(novel_crawler, "_CurlSession", FakeCurlSession, raising=False)

    source = NovelCrawlSource(key="rule", name="Rule Source", source_type="rule")
    async with novel_crawler._create_http_client(source) as client:
        response = await client.request("GET", "https://example.test/search")

    assert response.text == "<html>ok</html>"
    assert "content-encoding" not in response.headers
    assert response.headers["content-length"] == str(len(b"<html>ok</html>"))
    assert response.headers["content-type"] == "text/html; charset=utf-8"


@pytest.mark.anyio
async def test_rule_impersonate_client_bypasses_proxy_for_loopback_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    httpx_calls: list[str] = []

    class FakeCurlSession:
        def __init__(self, *, timeout: float, impersonate: str, **kwargs: Any) -> None:
            pass

        def request(self, method: str, url: str, **kwargs: Any) -> SimpleNamespace:
            calls.append({"url": url, "kwargs": kwargs})
            return SimpleNamespace(status_code=200, headers={}, content=b"<html>ok</html>")

        def close(self) -> None:
            pass

    class FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["trust_env"] is False

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *exc_info: object) -> None:
            pass

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            httpx_calls.append(url)
            return httpx.Response(200, text="<html>local</html>", request=httpx.Request(method, url))

    monkeypatch.setattr(novel_crawler, "_CurlSession", FakeCurlSession, raising=False)
    monkeypatch.setattr(novel_crawler.httpx, "AsyncClient", FakeAsyncClient)

    async with novel_crawler._ImpersonateClient(
        timeout=novel_crawler.HTTP_TIMEOUT,
        impersonate=novel_crawler.IMPERSONATE_PROFILE,
        proxy="http://127.0.0.1:7897",
    ) as client:
        await client.request("GET", "http://127.0.0.1:8787/fetch")
        await client.request("GET", "https://example.test/search")

    assert len(calls) == 1
    assert calls[0]["url"] == "https://example.test/search"
    assert "proxy" not in calls[0]["kwargs"]
    assert "proxies" not in calls[0]["kwargs"]
    assert httpx_calls == ["http://127.0.0.1:8787/fetch"]


@pytest.mark.anyio
async def test_rule_impersonate_client_uses_httpx_for_loopback_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curl_calls: list[str] = []
    httpx_calls: list[tuple[str, str]] = []

    class FakeCurlSession:
        def __init__(self, *, timeout: float, impersonate: str, **kwargs: Any) -> None:
            pass

        def request(self, method: str, url: str, **kwargs: Any) -> SimpleNamespace:
            curl_calls.append(url)
            return SimpleNamespace(status_code=200, headers={}, content=b"<html>curl</html>")

        def close(self) -> None:
            pass

    class FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["trust_env"] is False

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *exc_info: object) -> None:
            pass

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            httpx_calls.append((method, url))
            return httpx.Response(200, text="<html>local</html>", request=httpx.Request(method, url))

    monkeypatch.setattr(novel_crawler, "_CurlSession", FakeCurlSession, raising=False)
    monkeypatch.setattr(novel_crawler.httpx, "AsyncClient", FakeAsyncClient)

    async with novel_crawler._ImpersonateClient(
        timeout=novel_crawler.HTTP_TIMEOUT,
        impersonate=novel_crawler.IMPERSONATE_PROFILE,
        proxy="http://127.0.0.1:7897",
    ) as client:
        response = await client.request("GET", "http://127.0.0.1:8787/fetch")

    assert response.text == "<html>local</html>"
    assert httpx_calls == [("GET", "http://127.0.0.1:8787/fetch")]
    assert curl_calls == []


@pytest.mark.anyio
async def test_rule_impersonate_client_reports_fake_ip_tls_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCurlSession:
        def __init__(self, *, timeout: float, impersonate: str, **kwargs: Any) -> None:
            pass

        def request(self, method: str, url: str, **kwargs: Any) -> SimpleNamespace:
            raise RuntimeError(
                "Failed to perform, ErrCode: 35, Reason: 'BoringSSL SSL_connect: "
                "SSL_ERROR_SYSCALL in connection to www.biquge.tw:443 '"
            )

        def close(self) -> None:
            pass

    def fake_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        assert host == "www.biquge.tw"
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("198.18.2.44", port))]

    monkeypatch.setattr(novel_crawler, "_CurlSession", FakeCurlSession, raising=False)
    monkeypatch.setattr(novel_crawler.socket, "getaddrinfo", fake_getaddrinfo)

    source = NovelCrawlSource(key="rule", name="Rule Source", source_type="rule")
    async with novel_crawler._create_http_client(source) as client:
        with pytest.raises(Exception) as exc_info:
            await client.request("GET", "https://www.biquge.tw/search/?searchkey=test")

    message = str(exc_info.value)
    assert "198.18.2.44" in message
    assert "fake-ip" in message
    assert "NOVEL_CRAWL_PROXY" in message


def test_crawl_proxy_falls_back_to_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("http_proxy", "http://127.0.0.1:7897")
    assert novel_crawler._resolve_crawl_proxy("") == "http://127.0.0.1:7897"

    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7899")
    assert novel_crawler._resolve_crawl_proxy("") == "http://127.0.0.1:7899"

    assert novel_crawler._resolve_crawl_proxy("http://127.0.0.1:18080") == "http://127.0.0.1:18080"


def test_fake_ip_tls_failure_with_proxy_reports_exit_or_dns_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        assert host == "example.test"
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("198.18.2.45", port))]

    monkeypatch.setattr(novel_crawler.socket, "getaddrinfo", fake_getaddrinfo)

    message = novel_crawler._format_impersonate_connect_error(
        RuntimeError("curl: (35) TLS connect error"),
        "https://example.test/search",
        "http://127.0.0.1:7899",
    )

    assert "fake-ip" in message
    assert "当前爬虫代理=http://127.0.0.1:7899" in message
    assert "代理出口或 DNS fake-ip 映射" in message
    assert "后端爬虫请求没有走通可用代理出口" not in message


@pytest.mark.anyio
async def test_search_books_reports_rule_source_forbidden_as_throttle_diagnostic() -> None:
    class ForbiddenClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request(method, url)
            return httpx.Response(403, text="Forbidden", request=request)

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template="https://example.test/search/?searchkey={q}&page={page}",
        api_search_book_title_path=".book-title::text",
    )

    with pytest.raises(novel_crawler.NovelCrawlerError) as exc_info:
        await novel_crawler.search_books(source, "太古神王", client=ForbiddenClient())

    message = str(exc_info.value)
    assert "来源站点拒绝或限流" in message
    assert "HTTP 403" in message
    assert "https://example.test/search/" in message
    assert "NOVEL_CRAWL_PROXY" in message


@pytest.mark.anyio
async def test_search_books_reports_cloudflare_challenge_without_html_snippet() -> None:
    class ChallengeClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request(method, url)
            return httpx.Response(
                403,
                text='<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title></head></html>',
                headers={"server": "cloudflare", "cf-mitigated": "challenge"},
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template="https://example.test/search/?searchkey={q}&page={page}",
        api_search_book_title_path=".book-title::text",
    )

    with pytest.raises(novel_crawler.NovelCrawlerError) as exc_info:
        await novel_crawler.search_books(source, "太古神王", client=ChallengeClient())

    message = str(exc_info.value)
    assert "Cloudflare 浏览器挑战" in message
    assert "HTTP 403" in message
    assert "https://example.test/search/" in message
    assert "<!DOCTYPE html>" not in message
    assert "Just a moment" not in message


@pytest.mark.anyio
async def test_search_books_does_not_retry_browser_proxy_cloudflare_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class BrowserProxyChallengeClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            calls.append(url)
            request = httpx.Request(method, url)
            return httpx.Response(
                403,
                text=(
                    '{"detail":"浏览器访问仍被 Cloudflare 挑战拦截: '
                    'https://www.biquge.tw/search/?searchkey=test&__cf_chl_rt_tk=token"}'
                ),
                request=request,
            )

    monkeypatch.setattr(novel_crawler, "CRAWL_HTTP_RETRIES", 2)
    monkeypatch.setattr(novel_crawler, "CRAWL_HTTP_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(novel_crawler, "CRAWL_THROTTLE_BACKOFF_SECONDS", 0)

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fwww.biquge.tw%2Fsearch%2F%3Fsearchkey%3D{q}%26page%3D1"
        ),
        api_search_book_title_path=".book-title::text",
    )

    with pytest.raises(novel_crawler.NovelCrawlerError) as exc_info:
        await novel_crawler.search_books(source, "test", client=BrowserProxyChallengeClient())

    assert calls == ["http://127.0.0.1:8787/fetch"]
    message = str(exc_info.value)
    assert "Cloudflare" in message
    assert "__cf_chl_rt_tk" not in message


@pytest.mark.anyio
async def test_search_books_stops_paginated_rule_search_after_exact_title_match() -> None:
    class PaginatedClient:
        def __init__(self) -> None:
            self.urls: list[str] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.urls.append(url)
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text=(
                    "<html><body>"
                    "<a class='book-title' href='/novel/1.html'>Target Book</a>"
                    "</body></html>"
                ),
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template="https://example.test/search/?searchkey={q}&page={page}",
        api_search_book_title_path=".book-title::text",
        api_search_book_id_path=".book-title::attr(href)",
    )
    client = PaginatedClient()

    results = await novel_crawler.search_books(source, "Target Book", client=client)

    assert [book.title for book in results] == ["Target Book"]
    assert client.urls == ["https://example.test/search/?searchkey=Target%20Book&page=1"]


@pytest.mark.anyio
async def test_search_books_returns_first_browser_proxy_page_when_results_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrowserProxyClient:
        def __init__(self) -> None:
            self.target_urls: list[str] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            payload = kwargs["json"]
            self.target_urls.append(payload["url"])
            page = len(self.target_urls)
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text=(
                    "<html><body>"
                    f"<a class='book-title' href='/book/{page}/'>Related Book {page}</a>"
                    "</body></html>"
                ),
                request=request,
            )

    monkeypatch.setattr(novel_crawler, "MAX_SEARCH_PAGES", 3)

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fsearch%3Fkeyword%3D{q}%26page%3D{page}&"
            "wait_selector=.book-title"
        ),
        api_search_book_title_path=".book-title::text",
        api_search_book_id_path=".book-title::attr(href)",
    )
    client = BrowserProxyClient()

    results = await novel_crawler.search_books(source, "Target Book", client=client)

    assert [book.title for book in results] == ["Related Book 1"]
    assert client.target_urls == ["https://example.test/search?keyword=Target%20Book&page=1"]


@pytest.mark.anyio
async def test_rule_browser_proxy_request_preserves_crawl_source_request_contract() -> None:
    class BrowserProxyClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.calls.append({"method": method, "url": url, "kwargs": kwargs})
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text=(
                    "<html><body>"
                    "<a class='book-title' href='/book/1/'>Target Book</a>"
                    "</body></html>"
                ),
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fsearch%3Fkeyword%3D{q}&"
            "wait_selector=.book-title"
        ),
        api_search_method="POST",
        api_search_headers='{"x-source":"{q}"}',
        api_search_body='{"keyword":"{q}"}',
        api_search_book_title_path=".book-title::text",
        api_search_book_id_path=".book-title::attr(href)",
    )
    client = BrowserProxyClient()

    results = await novel_crawler.search_books(source, "Target Book", client=client)

    assert [book.title for book in results] == ["Target Book"]
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://127.0.0.1:8787/fetch"
    assert call["kwargs"]["headers"] is None
    assert call["kwargs"]["json"] == {
        "url": "https://example.test/search?keyword=Target%20Book",
        "method": "POST",
        "headers": {"x-source": "Target Book"},
        "body": {"keyword": "Target Book"},
        "wait_selector": ".book-title",
    }


@pytest.mark.anyio
async def test_rule_browser_proxy_request_infers_wait_selector_from_search_selector() -> None:
    class BrowserProxyClient:
        def __init__(self) -> None:
            self.payloads: list[dict[str, Any]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.payloads.append(kwargs["json"])
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text="<html><body><a class='book-title' href='/book/1/'>Target Book</a></body></html>",
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fsearch%3Fkeyword%3D{q}"
        ),
        api_search_book_title_path=".result-card .book-title::text",
        api_search_book_id_path=".result-card .book-title::attr(href)",
    )
    client = BrowserProxyClient()

    await novel_crawler.search_books(source, "Target Book", client=client)

    assert client.payloads[0]["wait_selector"] == ".result-card .book-title"


@pytest.mark.anyio
async def test_rule_browser_proxy_request_preserves_form_encoded_body_contract() -> None:
    query = "\u8bdb\u4ed9"

    class BrowserProxyClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.calls.append({"method": method, "url": url, "kwargs": kwargs})
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text=(
                    "<html><body>"
                    f"<span class='name'><a href='/xiaoshuo/405525/'>{query}</a></span>"
                    "</body></html>"
                ),
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fs.php&"
            "wait_selector=.lastupdate%20ul%20li"
        ),
        api_search_method="POST",
        api_search_headers='{"content-type":"application/x-www-form-urlencoded; charset=UTF-8"}',
        api_search_body="s={q}&submit=",
        api_search_book_title_path=".name a::text",
        api_search_book_id_path=".name a::attr(href)",
    )
    client = BrowserProxyClient()

    results = await novel_crawler.search_books(source, query, client=client)

    assert [book.title for book in results] == [query]
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://127.0.0.1:8787/fetch"
    assert call["kwargs"]["json"] == {
        "url": "https://example.test/s.php",
        "method": "POST",
        "headers": {"content-type": "application/x-www-form-urlencoded; charset=UTF-8"},
        "body": "s=%E8%AF%9B%E4%BB%99&submit=",
        "wait_selector": ".lastupdate ul li",
    }


@pytest.mark.anyio
async def test_rule_browser_proxy_request_uses_browser_proxy_timeout() -> None:
    class BrowserProxyClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.calls.append({"method": method, "url": url, "kwargs": kwargs})
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text="<html><body><a class='book-title' href='/book/1/'>Target Book</a></body></html>",
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fsearch&"
            "wait_selector=.book-title"
        ),
        api_search_book_title_path=".book-title::text",
        api_search_book_id_path=".book-title::attr(href)",
    )
    client = BrowserProxyClient()

    await novel_crawler.search_books(source, "Target Book", client=client)

    timeout = client.calls[0]["kwargs"]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read > novel_crawler.HTTP_TIMEOUT.read


def test_browser_proxy_timeout_budget_includes_selector_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_TIMEOUT_MS", "30000")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_WAIT_SELECTOR_TIMEOUT_MS", "6000")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_WAIT_AFTER_LOAD_MS", "1200")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_WAIT_AFTER_SELECTOR_MS", "200")

    assert novel_crawler._browser_proxy_http_read_timeout_seconds(20.0) == pytest.approx(42.2)


@pytest.mark.anyio
async def test_fetch_chapter_count_passes_chapter_selector_to_browser_proxy() -> None:
    class BrowserProxyClient:
        def __init__(self) -> None:
            self.payloads: list[dict[str, Any]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.payloads.append(kwargs["json"])
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text=(
                    "<html><body><div class='list-chapter'><div class='booklist'><ul>"
                    "<li><a href='/chapter/1.html'>第一章</a></li>"
                    "<li><a href='/chapter/2.html'>第二章</a></li>"
                    "</ul></div></div></body></html>"
                ),
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_chapter_list_url=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fbook%2F{id}%2F"
        ),
        api_chapter_list_id_path=".list-chapter .booklist ul li a::attr(href)",
        api_chapter_list_name_path=".list-chapter .booklist ul li a::text",
    )
    book = novel_crawler.CrawlSearchResult(dirid="207513", title="Target Book")
    client = BrowserProxyClient()

    count = await novel_crawler.fetch_chapter_count(source, book, client=client)

    assert count == 2
    assert client.payloads[0]["wait_selector"] == ".list-chapter .booklist ul li a"


@pytest.mark.anyio
async def test_fetch_chapter_detail_prefers_direct_target_from_browser_proxy_url() -> None:
    class ChapterClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, Any]]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.calls.append((method, url, kwargs))
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text="<html><body><div id='chaptercontent'>正文内容</div></body></html>",
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_chapter_url=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fbook%2F{id}%2F{chapterid}.html"
        ),
        api_chapter_content_path="#chaptercontent",
    )
    book = novel_crawler.CrawlSearchResult(dirid="9002", title="Target Book")
    client = ChapterClient()

    chapter = await novel_crawler._fetch_chapter_detail(
        source,
        book,
        {"ordinal": 1, "chapterid": 286409, "chaptername": "第一章"},
        client=client,
    )

    assert chapter.txt == "正文内容"
    assert client.calls[0][0] == "GET"
    assert client.calls[0][1] == "https://example.test/book/9002/286409.html"
    assert "json" not in client.calls[0][2]


@pytest.mark.anyio
async def test_fetch_chapter_detail_falls_back_to_browser_proxy_when_direct_target_is_blocked() -> None:
    class ChapterClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, Any]]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.calls.append((method, url, kwargs))
            request = httpx.Request(method, url)
            if url == "https://example.test/book/9002/286409.html":
                return httpx.Response(
                    403,
                    text="<html><title>Just a moment...</title></html>",
                    headers={"server": "cloudflare"},
                    request=request,
                )
            return httpx.Response(
                200,
                text="<html><body><div id='chaptercontent'>代理正文</div></body></html>",
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_chapter_url=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fbook%2F{id}%2F{chapterid}.html"
        ),
        api_chapter_content_path="#chaptercontent",
    )
    book = novel_crawler.CrawlSearchResult(dirid="9002", title="Target Book")
    client = ChapterClient()

    chapter = await novel_crawler._fetch_chapter_detail(
        source,
        book,
        {"ordinal": 1, "chapterid": 286409, "chaptername": "第一章"},
        client=client,
    )

    assert chapter.txt == "代理正文"
    assert client.calls[0][1] == "https://example.test/book/9002/286409.html"
    assert client.calls[1][0] == "POST"
    assert client.calls[1][1] == "http://127.0.0.1:8787/fetch"
    assert client.calls[1][2]["json"]["wait_selector"] == "#chaptercontent"


@pytest.mark.anyio
async def test_collect_rule_content_prefers_direct_target_for_next_page() -> None:
    class ChapterClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, Any]]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.calls.append((method, url, kwargs))
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                text="<html><body><div id='chaptercontent'>第二页正文</div></body></html>",
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_chapter_method="GET",
        api_chapter_content_path="#chaptercontent",
    )
    first_page = novel_crawler.Selector(
        text=(
            "<html><body><div id='chaptercontent'>第一页正文</div>"
            "<a href='286409_2.html'>下一页</a></body></html>"
        )
    )
    client = ChapterClient()

    text = await novel_crawler._collect_rule_content(
        source,
        {"ordinal": 1, "chapterid": 286409},
        first_page,
        "第一页正文",
        current_url="http://127.0.0.1:8787/fetch?url=https%3A%2F%2Fexample.test%2Fbook%2F9002%2F286409.html",
        client=client,
    )

    assert text == "第一页正文\n第二页正文"
    assert client.calls[0][0] == "GET"
    assert client.calls[0][1] == "https://example.test/book/9002/286409_2.html"
    assert "json" not in client.calls[0][2]


@pytest.mark.anyio
async def test_collect_rule_content_falls_back_to_browser_proxy_for_blocked_next_page() -> None:
    class ChapterClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, Any]]] = []

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            self.calls.append((method, url, kwargs))
            request = httpx.Request(method, url)
            if url == "https://example.test/book/9002/286409_2.html":
                return httpx.Response(
                    403,
                    text="<html><title>Just a moment...</title></html>",
                    headers={"server": "cloudflare"},
                    request=request,
                )
            return httpx.Response(
                200,
                text="<html><body><div id='chaptercontent'>第二页代理正文</div></body></html>",
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_chapter_method="GET",
        api_chapter_content_path="#chaptercontent",
    )
    first_page = novel_crawler.Selector(
        text=(
            "<html><body><div id='chaptercontent'>第一页正文</div>"
            "<a href='286409_2.html'>下一页</a></body></html>"
        )
    )
    client = ChapterClient()

    text = await novel_crawler._collect_rule_content(
        source,
        {"ordinal": 1, "chapterid": 286409},
        first_page,
        "第一页正文",
        current_url="http://127.0.0.1:8787/fetch?url=https%3A%2F%2Fexample.test%2Fbook%2F9002%2F286409.html",
        client=client,
    )

    assert text == "第一页正文\n第二页代理正文"
    assert client.calls[1][0] == "POST"
    assert client.calls[1][1] == "http://127.0.0.1:8787/fetch"
    assert client.calls[1][2]["json"]["url"] == "https://example.test/book/9002/286409_2.html"
    assert client.calls[1][2]["json"]["wait_selector"] == "#chaptercontent"


@pytest.mark.anyio
async def test_fetch_chapter_detail_reports_browser_proxy_status_body() -> None:
    class BrowserProxyClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request(method, url)
            return httpx.Response(
                502,
                json={"detail": "browser fetch failed: Page.goto timeout"},
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_chapter_url=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fbook%2F{id}%2F{chapterid}.html"
        ),
        api_chapter_content_path="#chaptercontent",
    )
    book = novel_crawler.CrawlSearchResult(dirid="9002", title="Target Book")

    chapter = await novel_crawler._fetch_chapter_detail_with_retry(
        source,
        book,
        {"ordinal": 1, "chapterid": 286409, "chaptername": "第一章"},
        client=BrowserProxyClient(),
    )

    assert chapter.event_state == -1
    assert "HTTP 502" in str(chapter.error_reason)
    assert "browser fetch failed: Page.goto timeout" in str(chapter.error_reason)


@pytest.mark.anyio
async def test_rule_browser_proxy_timeout_reports_diagnostic_message() -> None:
    class TimeoutClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request(method, url)
            raise httpx.ReadTimeout("", request=request)

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        search_url_template=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fsearch&"
            "wait_selector=.book-title"
        ),
        api_search_book_title_path=".book-title::text",
    )

    with pytest.raises(novel_crawler.NovelCrawlerError) as exc_info:
        await novel_crawler.search_books(source, "Target Book", client=TimeoutClient())

    message = str(exc_info.value)
    assert message
    assert "浏览器代理请求超时" in message
    assert "http://127.0.0.1:8787/fetch" in message


def test_browser_proxy_connect_error_reports_startup_diagnostic() -> None:
    request = httpx.Request("POST", "http://127.0.0.1:8787/fetch")
    message = novel_crawler._format_http_error(
        httpx.ConnectError("All connection attempts failed", request=request)
    )

    assert "浏览器代理不可用" in message
    assert "http://127.0.0.1:8787/fetch" in message
    assert "python -m app.services.novel_browser_proxy" in message


@pytest.mark.anyio
async def test_fetch_book_detail_reports_browser_proxy_status_body() -> None:
    class BrowserProxyClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request(method, url)
            return httpx.Response(
                502,
                json={"detail": "browser fetch failed: wait_selector failed for chapter list"},
                request=request,
            )

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_book_url=(
            "http://127.0.0.1:8787/fetch?"
            "url=https%3A%2F%2Fexample.test%2Fbook%2F{id}%2F"
        ),
        api_book_title_path=".book-title::text",
    )
    book = novel_crawler.CrawlSearchResult(dirid="207513", title="Target Book")

    with pytest.raises(novel_crawler.NovelCrawlerError) as exc_info:
        await novel_crawler.fetch_book_detail(source, book, client=BrowserProxyClient())

    message = str(exc_info.value)
    assert "HTTP 502" in message
    assert "browser fetch failed: wait_selector failed for chapter list" in message


def test_rule_search_result_does_not_use_latest_chapter_url_as_chapter_count() -> None:
    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_search_book_id_path=".name a::attr(href)",
        api_search_book_title_path=".name a::text",
        api_search_book_last_chapter_path=".jie a::text",
        api_search_book_last_chapter_id_path=".jie a::attr(href)",
        api_chapter_list_url="https://example.test/xiaoshuo/{id}/",
    )
    data = novel_crawler.Selector(
        text=(
            "<html><body><div class='lastupdate'><ul><li>"
            "<span class='name'><a href='/xiaoshuo/512713/'>玄鉴仙族</a></span>"
            "<span class='jie'><a href='/zhangjie/512713/189071196.html'>第1497章 庙语</a></span>"
            "</li></ul></div></body></html>"
        )
    )

    books = novel_crawler._parse_search_results(source, data)

    assert len(books) == 1
    assert books[0].dirid == "512713"
    assert books[0].lastchapter == "第1497章 庙语"
    assert books[0].lastchapterid == 0


def test_rule_book_detail_uses_chapter_list_on_same_page_as_count() -> None:
    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_book_title_path="meta[property='og:novel:book_name']::attr(content)",
        api_chapter_list_id_path=".border_chapter a::attr(href)",
        api_chapter_list_name_path=".border_chapter a::text",
    )
    book = novel_crawler.CrawlSearchResult(dirid="207513", title="old", sourceKey="rule")
    data = novel_crawler.Selector(
        text=(
            "<html><head><meta property='og:novel:book_name' content='诛仙'></head>"
            "<body><div class='border_chapter'>"
            "<a href='/zhangjie/207513/1.html'>第一章</a>"
            "<a href='/zhangjie/207513/2.html'>第二章</a>"
            "<a href='/zhangjie/207513/3.html'>第三章</a>"
            "</div></body></html>"
        )
    )

    detail = novel_crawler._merge_book_detail(source, book, data)

    assert detail.title == "诛仙"
    assert detail.lastchapterid == 3


@pytest.mark.anyio
async def test_fetch_chapter_count_uses_existing_book_count_without_request() -> None:
    class FailingClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            raise AssertionError("chapter count should not request chapter list when count is already known")

    source = NovelCrawlSource(
        key="rule",
        name="Rule Source",
        source_type="rule",
        api_chapter_list_url="https://example.test/xiaoshuo/{id}/",
    )
    book = novel_crawler.CrawlSearchResult(dirid="207513", title="诛仙", lastchapterid=801)

    count = await novel_crawler.fetch_chapter_count(source, book, client=FailingClient())

    assert count == 801
