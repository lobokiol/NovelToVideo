from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import novel_browser_proxy


def test_validate_target_url_accepts_allowed_http_hosts() -> None:
    url = novel_browser_proxy.validate_target_url(
        "https://read.example.org/search/?searchkey=%E8%AF%9B%E4%BB%99&page=1",
        allowed_hosts={"read.example.org"},
    )

    assert url == "https://read.example.org/search/?searchkey=%E8%AF%9B%E4%BB%99&page=1"


def test_validate_target_url_accepts_wildcard_host_patterns() -> None:
    url = novel_browser_proxy.validate_target_url(
        "https://m.example.org/book/1.html",
        allowed_hosts={"*.example.org"},
    )

    assert url == "https://m.example.org/book/1.html"


def test_validate_target_url_allows_public_hosts_when_explicitly_configured() -> None:
    url = novel_browser_proxy.validate_target_url(
        "https://novel.example.org/book/1.html",
        allowed_hosts={"*"},
    )

    assert url == "https://novel.example.org/book/1.html"


def test_parse_allowed_hosts_defaults_to_public_host_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS", raising=False)

    assert novel_browser_proxy.parse_allowed_hosts() == {"*"}


def test_parse_allowed_hosts_treats_blank_env_as_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS", "  ")

    assert novel_browser_proxy.parse_allowed_hosts() == {"*"}


def test_load_config_default_hosts_accept_public_sources_and_reject_private_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS", raising=False)

    config = novel_browser_proxy.load_config()

    assert config.allowed_hosts == {"*"}
    assert (
        novel_browser_proxy.validate_target_url(
            "https://another-source.example.org/book/1.html",
            allowed_hosts=config.allowed_hosts,
        )
        == "https://another-source.example.org/book/1.html"
    )
    with pytest.raises(ValueError):
        novel_browser_proxy.validate_target_url(
            "http://127.0.0.1:8000/private",
            allowed_hosts=config.allowed_hosts,
        )


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "http://127.0.0.1:8000/private",
        "https://example.com/search",
    ],
)
def test_validate_target_url_rejects_untrusted_targets(url: str) -> None:
    with pytest.raises(ValueError):
        novel_browser_proxy.validate_target_url(url, allowed_hosts={"read.example.org"})


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/private",
        "http://localhost:8000/private",
        "http://10.0.0.8/private",
        "http://192.168.1.3/private",
    ],
)
def test_validate_target_url_rejects_private_targets_even_when_all_hosts_allowed(url: str) -> None:
    with pytest.raises(ValueError):
        novel_browser_proxy.validate_target_url(url, allowed_hosts={"*"})


def test_fetch_endpoint_returns_browser_html(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS", "read.example.org")

    async def fake_fetch(url: str, config: novel_browser_proxy.BrowserFetchConfig) -> novel_browser_proxy.BrowserFetchResult:
        assert url == "https://read.example.org/search/?searchkey=test&page=1"
        assert config.allowed_hosts == {"read.example.org"}
        return novel_browser_proxy.BrowserFetchResult(
            url=url,
            status_code=200,
            html="<html><body><a class='book-title'>ok</a></body></html>",
        )

    app = novel_browser_proxy.create_app(fetcher=fake_fetch)
    client = TestClient(app)

    response = client.get(
        "/fetch",
        params={"url": "https://read.example.org/search/?searchkey=test&page=1"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "book-title" in response.text


def test_fetch_endpoint_passes_request_options_to_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS", "*.example.org")
    captured: dict[str, object] = {}

    async def fake_fetch(url: str, config: novel_browser_proxy.BrowserFetchConfig) -> novel_browser_proxy.BrowserFetchResult:
        captured["url"] = url
        captured["config"] = config
        captured["headers"] = novel_browser_proxy.request_headers_for_target(config, url)
        return novel_browser_proxy.BrowserFetchResult(url=url, status_code=200, html="<html>ok</html>")

    app = novel_browser_proxy.create_app(fetcher=fake_fetch)
    client = TestClient(app)

    response = client.get(
        "/fetch",
        params={
            "url": "https://m.example.org/book/1.html",
            "wait_until": "load",
            "wait_selector": "#content",
            "referer": "auto",
        },
    )

    assert response.status_code == 200
    config = captured["config"]
    assert isinstance(config, novel_browser_proxy.BrowserFetchConfig)
    assert config.wait_until == "load"
    assert config.wait_selector == "#content"
    assert captured["headers"] == {
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "max-age=0",
        "upgrade-insecure-requests": "1",
        "referer": "https://m.example.org/",
    }


def test_fetch_endpoint_accepts_crawl_source_request_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS", "*.example.org")
    captured: dict[str, object] = {}

    async def fake_fetch(url: str, config: novel_browser_proxy.BrowserFetchConfig) -> novel_browser_proxy.BrowserFetchResult:
        captured["url"] = url
        captured["config"] = config
        captured["headers"] = novel_browser_proxy.request_headers_for_target(config, url)
        return novel_browser_proxy.BrowserFetchResult(url=url, status_code=200, html="<html>ok</html>")

    app = novel_browser_proxy.create_app(fetcher=fake_fetch)
    client = TestClient(app)

    response = client.post(
        "/fetch",
        json={
            "url": "https://m.example.org/search",
            "method": "POST",
            "headers": {"x-source": "rule", "referer": "https://m.example.org/search"},
            "body": {"keyword": "Target Book"},
            "waitSelector": ".result",
        },
    )

    assert response.status_code == 200
    assert captured["url"] == "https://m.example.org/search"
    config = captured["config"]
    assert isinstance(config, novel_browser_proxy.BrowserFetchConfig)
    assert config.target_method == "POST"
    assert config.target_body == {"keyword": "Target Book"}
    assert config.wait_selector == ".result"
    assert captured["headers"] == {
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "max-age=0",
        "content-type": "application/json",
        "upgrade-insecure-requests": "1",
        "referer": "https://m.example.org/search",
        "x-source": "rule",
    }


def test_fetch_endpoint_accepts_direct_post_body_when_url_is_in_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = "\u8bdb\u4ed9"
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS", "*.example.org")
    captured: dict[str, object] = {}

    async def fake_fetch(url: str, config: novel_browser_proxy.BrowserFetchConfig) -> novel_browser_proxy.BrowserFetchResult:
        captured["url"] = url
        captured["config"] = config
        captured["headers"] = novel_browser_proxy.request_headers_for_target(config, url)
        return novel_browser_proxy.BrowserFetchResult(url=url, status_code=200, html="<html>ok</html>")

    app = novel_browser_proxy.create_app(fetcher=fake_fetch)
    client = TestClient(app)

    response = client.post(
        "/fetch",
        params={
            "url": "https://m.example.org/search",
            "wait_selector": ".result",
        },
        json=f'{{"s":"{query}"}}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert captured["url"] == "https://m.example.org/search"
    config = captured["config"]
    assert isinstance(config, novel_browser_proxy.BrowserFetchConfig)
    assert config.target_method == "POST"
    assert config.target_body == f'{{"s":"{query}"}}'
    assert config.wait_selector == ".result"
    assert captured["headers"]["content-type"] == "application/json"


def test_target_post_data_encodes_form_body_dict() -> None:
    query = "\u8bdb\u4ed9"
    config = novel_browser_proxy.BrowserFetchConfig(
        allowed_hosts={"*"},
        proxy=None,
        headless=True,
        timeout_ms=30000,
        wait_after_load_ms=1200,
        channel=None,
        user_data_dir=None,
        extra_http_headers={},
        target_method="POST",
        target_headers={"content-type": "application/x-www-form-urlencoded; charset=UTF-8"},
        target_body={"s": query, "submit": ""},
    )

    assert novel_browser_proxy.target_post_data(config) == "s=%E8%AF%9B%E4%BB%99&submit="


def test_load_config_accepts_wait_tuning_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_TIMEOUT_MS", "30000")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_WAIT_SELECTOR_TIMEOUT_MS", "6000")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_WAIT_AFTER_SELECTOR_MS", "150")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_WAIT_SELECTOR_STATE", "visible")

    config = novel_browser_proxy.load_config()

    assert config.timeout_ms == 30000
    assert config.wait_selector_timeout_ms == 6000
    assert config.wait_after_selector_ms == 150
    assert config.wait_selector_state == "visible"


@pytest.mark.anyio
async def test_wait_for_page_ready_uses_selector_timeout_and_skips_extra_load_wait() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.selector_calls: list[dict[str, object]] = []
            self.timeout_calls: list[int] = []

        async def wait_for_selector(self, selector: str, **kwargs: object) -> None:
            self.selector_calls.append({"selector": selector, **kwargs})

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.timeout_calls.append(timeout_ms)

    config = novel_browser_proxy.BrowserFetchConfig(
        allowed_hosts={"*"},
        proxy=None,
        headless=True,
        timeout_ms=30000,
        wait_after_load_ms=1200,
        channel=None,
        user_data_dir=None,
        extra_http_headers={},
        wait_selector=".result",
        wait_selector_timeout_ms=6000,
        wait_after_selector_ms=0,
        wait_selector_state="attached",
    )
    page = FakePage()

    await novel_browser_proxy.wait_for_page_ready(page, config, status_code=200)

    assert page.selector_calls == [
        {"selector": ".result", "state": "attached", "timeout": 6000},
    ]
    assert page.timeout_calls == []


@pytest.mark.anyio
async def test_wait_for_page_ready_records_after_selector_wait_stage() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.timeout_calls: list[int] = []

        async def wait_for_selector(self, selector: str, **kwargs: object) -> None:
            return None

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.timeout_calls.append(timeout_ms)

    config = novel_browser_proxy.BrowserFetchConfig(
        allowed_hosts={"*"},
        proxy=None,
        headless=True,
        timeout_ms=30000,
        wait_after_load_ms=1200,
        channel=None,
        user_data_dir=None,
        extra_http_headers={},
        wait_selector=".result",
        wait_after_selector_ms=150,
    )
    page = FakePage()
    timings: dict[str, int] = {}

    await novel_browser_proxy.wait_for_page_ready(page, config, status_code=200, timings_ms=timings)

    assert page.timeout_calls == [150]
    assert "wait_after_selector" in timings
    assert "wait_after_load" not in timings


@pytest.mark.anyio
async def test_wait_for_page_ready_skips_selector_wait_for_error_status() -> None:
    class FakePage:
        async def wait_for_selector(self, selector: str, **kwargs: object) -> None:
            raise AssertionError("error pages should be returned without waiting for source selectors")

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            raise AssertionError("error pages should not run fixed waits")

    config = novel_browser_proxy.BrowserFetchConfig(
        allowed_hosts={"*"},
        proxy=None,
        headless=True,
        timeout_ms=30000,
        wait_after_load_ms=1200,
        channel=None,
        user_data_dir=None,
        extra_http_headers={},
        wait_selector=".result",
    )

    await novel_browser_proxy.wait_for_page_ready(FakePage(), config, status_code=403)


def test_fetch_endpoint_returns_browser_timing_headers() -> None:
    async def fake_fetch(url: str, config: novel_browser_proxy.BrowserFetchConfig) -> novel_browser_proxy.BrowserFetchResult:
        return novel_browser_proxy.BrowserFetchResult(
            url=url,
            status_code=200,
            html="<html>ok</html>",
            timings_ms={"goto": 12, "wait_selector": 3, "total": 20},
        )

    app = novel_browser_proxy.create_app(fetcher=fake_fetch)
    client = TestClient(app)

    response = client.get("/fetch", params={"url": "https://read.example.org/"})

    assert response.status_code == 200
    assert response.headers["x-novel-browser-total-ms"] == "20"
    assert response.headers["x-novel-browser-timing-ms"] == '{"goto":12,"total":20,"wait_selector":3}'


def test_fetch_endpoint_reports_browser_challenge_without_html() -> None:
    async def fake_fetch(url: str, config: novel_browser_proxy.BrowserFetchConfig) -> novel_browser_proxy.BrowserFetchResult:
        return novel_browser_proxy.BrowserFetchResult(
            url=url,
            status_code=403,
            html='<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>',
        )

    app = novel_browser_proxy.create_app(fetcher=fake_fetch)
    client = TestClient(app)

    response = client.get("/fetch", params={"url": "https://read.example.org/"})

    assert response.status_code == 403
    assert "浏览器访问仍被 Cloudflare 挑战拦截" in response.text
    assert "已通过验证的浏览器 Cookie/API 来源" in response.text
    assert "Cloudflare" in response.text
    assert "<!DOCTYPE html>" not in response.text


def test_cloudflare_attention_required_page_is_detected() -> None:
    assert novel_browser_proxy.looks_like_browser_challenge(
        '<!DOCTYPE html><html><head><title>Attention Required! | Cloudflare</title></head></html>'
    )


def test_load_config_accepts_real_chrome_profile_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS", "read.example.org")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_CHANNEL", "chrome")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_HEADLESS", "false")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_USER_DATA_DIR", "data/browser/rule_source")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_REFERER", "https://read.example.org/")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_WAIT_UNTIL", "load")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_WAIT_SELECTOR", "#chaptercontent")

    config = novel_browser_proxy.load_config()

    assert config.allowed_hosts == {"read.example.org"}
    assert config.channel == "chrome"
    assert config.headless is False
    assert config.user_data_dir == str(novel_browser_proxy.PROJECT_ROOT / "data/browser/rule_source")
    assert config.wait_until == "load"
    assert config.wait_selector == "#chaptercontent"
    assert config.extra_http_headers["accept-language"] == "zh-CN,zh;q=0.9"
    assert config.referer == "https://read.example.org/"


def test_request_headers_for_target_uses_auto_referer_origin() -> None:
    config = novel_browser_proxy.BrowserFetchConfig(
        allowed_hosts={"*"},
        proxy=None,
        headless=True,
        timeout_ms=30000,
        wait_after_load_ms=1200,
        channel=None,
        user_data_dir=None,
        extra_http_headers={},
        referer="auto",
    )

    assert novel_browser_proxy.request_headers_for_target(config, "https://read.example.org/book/1.html") == {
        "referer": "https://read.example.org/",
    }


def test_load_config_accepts_camoufox_engine_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_ENGINE", "camoufox")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_HEADLESS", "true")
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_CAMOUFOX_OS", "windows")

    config = novel_browser_proxy.load_config()

    assert config.engine == "camoufox"
    assert config.headless is True
    assert config.camoufox_os == "windows"


def test_load_config_resolves_relative_profile_dir_from_project_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_USER_DATA_DIR", "data/browser/rule_source")

    config = novel_browser_proxy.load_config()

    assert config.user_data_dir == str(novel_browser_proxy.PROJECT_ROOT / "data/browser/rule_source")


def test_load_config_accepts_generic_extra_http_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "NOVEL_BROWSER_PROXY_EXTRA_HTTP_HEADERS",
        '{"sec-ch-ua-platform":"\\"Windows\\"","priority":"u=0, i"}',
    )

    config = novel_browser_proxy.load_config()

    assert config.extra_http_headers["accept-language"] == "zh-CN,zh;q=0.9"
    assert config.extra_http_headers["sec-ch-ua-platform"] == '"Windows"'
    assert config.extra_http_headers["priority"] == "u=0, i"


@pytest.mark.anyio
async def test_camoufox_fetch_reuses_browser_engine_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class FakePage:
        url = "https://read.example.org/book/1.html"

        async def route(self, pattern: str, handler: object, *, times: int) -> None:
            events.append(f"route:{pattern}:{times}")

        async def goto(self, url: str, **kwargs: object) -> object:
            self.url = url
            events.append(f"goto:{url}")
            return SimpleNamespace(status=200)

        async def content(self) -> str:
            return "<html>ok</html>"

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            events.append(f"wait:{timeout_ms}")

    class FakeContext:
        pages: list[FakePage] = []

        async def new_page(self) -> FakePage:
            events.append("new_page")
            return FakePage()

        async def close(self) -> None:
            events.append("close_context")

    class FakeBrowser:
        async def new_context(self, **kwargs: object) -> FakeContext:
            events.append("new_context")
            return FakeContext()

    class FakeAsyncCamoufox:
        def __init__(self, **kwargs: object) -> None:
            events.append("init_engine")

        async def __aenter__(self) -> FakeBrowser:
            events.append("enter_engine")
            return FakeBrowser()

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            events.append("exit_engine")

    fake_camoufox_api = SimpleNamespace(AsyncCamoufox=FakeAsyncCamoufox)
    monkeypatch.setitem(sys.modules, "camoufox", SimpleNamespace(async_api=fake_camoufox_api))
    monkeypatch.setitem(sys.modules, "camoufox.async_api", fake_camoufox_api)

    config = novel_browser_proxy.BrowserFetchConfig(
        allowed_hosts={"*"},
        proxy=None,
        headless=True,
        timeout_ms=30000,
        wait_after_load_ms=0,
        channel=None,
        user_data_dir=None,
        extra_http_headers={},
        engine="camoufox",
    )

    await novel_browser_proxy.close_browser_resources()
    try:
        await novel_browser_proxy.camoufox_fetch("https://read.example.org/book/1.html", config)
        await novel_browser_proxy.camoufox_fetch("https://read.example.org/book/2.html", config)
    finally:
        await novel_browser_proxy.close_browser_resources()

    assert events.count("init_engine") == 1
    assert events.count("enter_engine") == 1
    assert events.count("new_context") == 2
    assert events.count("close_context") == 2
    assert events.count("exit_engine") == 1


def test_browser_launch_options_include_proxy_and_channel() -> None:
    config = novel_browser_proxy.BrowserFetchConfig(
        allowed_hosts={"read.example.org"},
        proxy="http://127.0.0.1:7897",
        headless=False,
        timeout_ms=30000,
        wait_after_load_ms=1200,
        channel="chrome",
        user_data_dir="data/browser/rule_source",
        extra_http_headers={},
    )

    assert novel_browser_proxy.browser_launch_options(config) == {
        "headless": False,
        "proxy": {"server": "http://127.0.0.1:7897"},
        "channel": "chrome",
    }


def test_camoufox_launch_options_include_proxy_and_stealth_defaults() -> None:
    config = novel_browser_proxy.BrowserFetchConfig(
        allowed_hosts={"read.example.org"},
        proxy="http://127.0.0.1:7897",
        headless=True,
        timeout_ms=30000,
        wait_after_load_ms=1200,
        channel="chrome",
        user_data_dir="data/browser/rule_source",
        extra_http_headers={},
        engine="camoufox",
        camoufox_os="windows",
    )

    assert novel_browser_proxy.camoufox_launch_options(config) == {
        "headless": True,
        "proxy": {"server": "http://127.0.0.1:7897"},
        "os": "windows",
        "humanize": False,
        "geoip": False,
        "i_know_what_im_doing": True,
        "block_webrtc": True,
        "disable_coop": True,
    }
