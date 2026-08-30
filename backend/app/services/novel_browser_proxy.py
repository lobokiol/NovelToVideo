from __future__ import annotations

import asyncio
import json
import os
import ipaddress
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode, urlparse

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv


DEFAULT_ALLOWED_HOSTS = "*"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_BROWSER_ENGINE = "playwright"
DEFAULT_CAMOUFOX_OS = "windows"
DEFAULT_REFERER = "auto"
DEFAULT_WAIT_UNTIL = "domcontentloaded"
DEFAULT_WAIT_SELECTOR_TIMEOUT_MS = 8000
DEFAULT_WAIT_SELECTOR_STATE = "attached"
SUPPORTED_BROWSER_ENGINES = {"playwright", "camoufox"}
SUPPORTED_WAIT_UNTIL = {"commit", "domcontentloaded", "load", "networkidle"}
SUPPORTED_WAIT_SELECTOR_STATES = {"attached", "detached", "hidden", "visible"}
SUPPORTED_TARGET_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
HTTP_METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}
SKIPPED_TARGET_HEADER_NAMES = {"connection", "content-length", "host"}
DEFAULT_EXTRA_HTTP_HEADERS = {
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
}
CHALLENGE_MARKERS = (
    "<title>just a moment",
    "<title>attention required! | cloudflare",
    "cf-browser-verification",
    "cf-chl-",
    "cf_chl_",
    "challenge-platform",
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE, override=False)


@dataclass(frozen=True, slots=True)
class BrowserFetchConfig:
    allowed_hosts: set[str]
    proxy: str | None
    headless: bool
    timeout_ms: int
    wait_after_load_ms: int
    channel: str | None
    user_data_dir: str | None
    extra_http_headers: dict[str, str]
    engine: str = DEFAULT_BROWSER_ENGINE
    camoufox_os: str | None = DEFAULT_CAMOUFOX_OS
    referer: str | None = DEFAULT_REFERER
    wait_until: str = DEFAULT_WAIT_UNTIL
    wait_selector: str | None = None
    wait_selector_timeout_ms: int = DEFAULT_WAIT_SELECTOR_TIMEOUT_MS
    wait_after_selector_ms: int = 0
    wait_selector_state: str = DEFAULT_WAIT_SELECTOR_STATE
    target_method: str = "GET"
    target_headers: dict[str, str] | None = None
    target_body: Any = None


@dataclass(frozen=True, slots=True)
class BrowserFetchResult:
    url: str
    status_code: int
    html: str
    timings_ms: dict[str, int] = field(default_factory=dict)


BrowserFetcher = Callable[[str, BrowserFetchConfig], Awaitable[BrowserFetchResult]]


@dataclass(frozen=True, slots=True)
class ReusableCamoufoxBrowser:
    key: tuple[tuple[str, Any], ...]
    manager: Any
    browser: Any


_CAMOUFOX_BROWSER: ReusableCamoufoxBrowser | None = None
_CAMOUFOX_BROWSER_LOCK = asyncio.Lock()


async def measure_stage(timings_ms: dict[str, int], name: str, operation: Callable[[], Awaitable[Any]]) -> Any:
    started_at = time.perf_counter()
    try:
        return await operation()
    finally:
        timings_ms[name] = int((time.perf_counter() - started_at) * 1000)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value.strip())


def env_str(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def resolve_user_data_dir(raw: str | None) -> str | None:
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


def normalize_browser_engine(raw: str | None) -> str:
    engine = (raw or DEFAULT_BROWSER_ENGINE).strip().lower()
    if engine not in SUPPORTED_BROWSER_ENGINES:
        supported = ", ".join(sorted(SUPPORTED_BROWSER_ENGINES))
        raise ValueError(f"NOVEL_BROWSER_PROXY_ENGINE must be one of: {supported}")
    return engine


def normalize_wait_until(raw: str | None) -> str:
    value = (raw or DEFAULT_WAIT_UNTIL).strip().lower()
    if value not in SUPPORTED_WAIT_UNTIL:
        supported = ", ".join(sorted(SUPPORTED_WAIT_UNTIL))
        raise ValueError(f"NOVEL_BROWSER_PROXY_WAIT_UNTIL must be one of: {supported}")
    return value


def normalize_wait_selector_state(raw: str | None) -> str:
    value = (raw or DEFAULT_WAIT_SELECTOR_STATE).strip().lower()
    if value not in SUPPORTED_WAIT_SELECTOR_STATES:
        supported = ", ".join(sorted(SUPPORTED_WAIT_SELECTOR_STATES))
        raise ValueError(f"NOVEL_BROWSER_PROXY_WAIT_SELECTOR_STATE must be one of: {supported}")
    return value


def normalize_target_method(raw: str | None) -> str:
    value = (raw or "GET").strip().upper()
    if value not in SUPPORTED_TARGET_METHODS:
        supported = ", ".join(sorted(SUPPORTED_TARGET_METHODS))
        raise ValueError(f"target method must be one of: {supported}")
    return value


def parse_allowed_hosts(raw: str | None = None) -> set[str]:
    value = raw if raw is not None else os.getenv("NOVEL_BROWSER_PROXY_ALLOWED_HOSTS")
    if value is None or not value.strip():
        value = DEFAULT_ALLOWED_HOSTS
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def resolve_proxy() -> str | None:
    for name in ("NOVEL_CRAWL_PROXY", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def load_extra_http_headers() -> dict[str, str]:
    headers = dict(DEFAULT_EXTRA_HTTP_HEADERS)
    extra_raw = env_str("NOVEL_BROWSER_PROXY_EXTRA_HTTP_HEADERS")
    if extra_raw:
        extra = json.loads(extra_raw)
        if not isinstance(extra, dict):
            raise ValueError("NOVEL_BROWSER_PROXY_EXTRA_HTTP_HEADERS must be a JSON object")
        headers.update({str(key): str(value) for key, value in extra.items() if str(key).strip()})
    return headers


def load_config() -> BrowserFetchConfig:
    timeout_ms = max(env_int("NOVEL_BROWSER_PROXY_TIMEOUT_MS", 30000), 1000)
    return BrowserFetchConfig(
        allowed_hosts=parse_allowed_hosts(),
        proxy=resolve_proxy(),
        headless=env_bool("NOVEL_BROWSER_PROXY_HEADLESS", True),
        timeout_ms=timeout_ms,
        wait_after_load_ms=max(env_int("NOVEL_BROWSER_PROXY_WAIT_AFTER_LOAD_MS", 1200), 0),
        channel=env_str("NOVEL_BROWSER_PROXY_CHANNEL"),
        user_data_dir=resolve_user_data_dir(env_str("NOVEL_BROWSER_PROXY_USER_DATA_DIR")),
        extra_http_headers=load_extra_http_headers(),
        engine=normalize_browser_engine(env_str("NOVEL_BROWSER_PROXY_ENGINE")),
        camoufox_os=env_str("NOVEL_BROWSER_PROXY_CAMOUFOX_OS") or DEFAULT_CAMOUFOX_OS,
        referer=env_str("NOVEL_BROWSER_PROXY_REFERER") or DEFAULT_REFERER,
        wait_until=normalize_wait_until(env_str("NOVEL_BROWSER_PROXY_WAIT_UNTIL")),
        wait_selector=env_str("NOVEL_BROWSER_PROXY_WAIT_SELECTOR"),
        wait_selector_timeout_ms=max(
            env_int("NOVEL_BROWSER_PROXY_WAIT_SELECTOR_TIMEOUT_MS", min(timeout_ms, DEFAULT_WAIT_SELECTOR_TIMEOUT_MS)),
            100,
        ),
        wait_after_selector_ms=max(env_int("NOVEL_BROWSER_PROXY_WAIT_AFTER_SELECTOR_MS", 0), 0),
        wait_selector_state=normalize_wait_selector_state(env_str("NOVEL_BROWSER_PROXY_WAIT_SELECTOR_STATE")),
    )


def validate_target_url(url: str, *, allowed_hosts: set[str]) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("target url scheme must be http or https")
    host = (parsed.hostname or "").lower()
    if not host or not is_allowed_target_host(host, allowed_hosts):
        raise ValueError("target url host is not allowed")
    return url


def is_allowed_target_host(host: str, allowed_hosts: set[str]) -> bool:
    normalized = host.strip().lower().strip(".")
    if not normalized:
        return False
    if "*" in allowed_hosts:
        return not is_private_or_local_host(normalized)
    for pattern in allowed_hosts:
        normalized_pattern = pattern.strip().lower().strip(".")
        if not normalized_pattern:
            continue
        if normalized_pattern == normalized:
            return True
        if normalized_pattern.startswith("*.") and normalized.endswith(normalized_pattern[1:]):
            return normalized != normalized_pattern[2:]
        if normalized_pattern.startswith(".") and (
            normalized == normalized_pattern[1:] or normalized.endswith(normalized_pattern)
        ):
            return True
    return False


def is_private_or_local_host(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def looks_like_browser_challenge(html: str) -> bool:
    lowered = html[:5000].lower()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


def request_headers_for_target(config: BrowserFetchConfig, url: str) -> dict[str, str]:
    headers = dict(config.extra_http_headers)
    headers.pop("referer", None)
    headers.pop("Referer", None)

    referer = (config.referer or "").strip()
    if not referer:
        return headers
    if referer.lower() == "none":
        return headers
    if referer.lower() in {"auto", "origin"}:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            headers["referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    else:
        headers["referer"] = referer

    for key, value in (config.target_headers or {}).items():
        normalized = key.strip()
        if not normalized or normalized.lower() in SKIPPED_TARGET_HEADER_NAMES:
            continue
        headers[normalized] = value
    if config.target_body is not None and config.target_method in HTTP_METHODS_WITH_BODY:
        has_content_type = any(key.lower() == "content-type" for key in headers)
        if not has_content_type:
            headers["content-type"] = "application/json"
    return headers


def apply_request_options(
    config: BrowserFetchConfig,
    *,
    wait_until: str | None = None,
    wait_selector: str | None = None,
    wait_selector_timeout_ms: int | None = None,
    wait_after_selector_ms: int | None = None,
    wait_selector_state: str | None = None,
    referer: str | None = None,
    target_method: str | None = None,
    target_headers: dict[str, str] | None = None,
    target_body: Any = None,
) -> BrowserFetchConfig:
    return replace(
        config,
        wait_until=normalize_wait_until(wait_until) if wait_until else config.wait_until,
        wait_selector=wait_selector.strip() if wait_selector and wait_selector.strip() else config.wait_selector,
        wait_selector_timeout_ms=max(wait_selector_timeout_ms, 100)
        if wait_selector_timeout_ms is not None
        else config.wait_selector_timeout_ms,
        wait_after_selector_ms=max(wait_after_selector_ms, 0)
        if wait_after_selector_ms is not None
        else config.wait_after_selector_ms,
        wait_selector_state=normalize_wait_selector_state(wait_selector_state)
        if wait_selector_state
        else config.wait_selector_state,
        referer=referer.strip() if referer and referer.strip() else config.referer,
        target_method=normalize_target_method(target_method) if target_method else config.target_method,
        target_headers=target_headers if target_headers is not None else config.target_headers,
        target_body=target_body,
    )


async def browser_fetch(url: str, config: BrowserFetchConfig) -> BrowserFetchResult:
    if config.engine == "camoufox":
        return await camoufox_fetch(url, config)
    return await playwright_fetch(url, config)


async def playwright_fetch(url: str, config: BrowserFetchConfig) -> BrowserFetchResult:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - covered by deployment smoke test
        raise RuntimeError("playwright is not installed; run `python -m playwright install chromium` after installing dependencies") from exc

    launch_kwargs = browser_launch_options(config)
    context_headers = request_headers_for_target(config, url)
    timings_ms: dict[str, int] = {}
    total_started_at = time.perf_counter()
    playwright_manager = async_playwright()
    playwright = await measure_stage(timings_ms, "engine_start", playwright_manager.__aenter__)
    browser = None
    context = None
    result_url = url
    status_code = 200
    html = ""
    try:
        if config.user_data_dir:
            context = await measure_stage(
                timings_ms,
                "launch_context",
                lambda: playwright.chromium.launch_persistent_context(
                    user_data_dir=config.user_data_dir,
                    locale="zh-CN",
                    extra_http_headers=context_headers,
                    **launch_kwargs,
                ),
            )
        else:
            browser = await measure_stage(timings_ms, "launch_browser", lambda: playwright.chromium.launch(**launch_kwargs))
            context = await measure_stage(
                timings_ms,
                "new_context",
                lambda: browser.new_context(locale="zh-CN", extra_http_headers=context_headers),
            )
        page = context.pages[0] if context.pages else await measure_stage(timings_ms, "new_page", context.new_page)
        await measure_stage(timings_ms, "prepare_request", lambda: prepare_navigation_request(page, config, context_headers))
        response = await measure_stage(
            timings_ms,
            "goto",
            lambda: page.goto(url, wait_until=config.wait_until, timeout=config.timeout_ms),
        )
        status_code = response.status if response is not None else 200
        await wait_for_page_ready(page, config, status_code=status_code, timings_ms=timings_ms)
        html = await measure_stage(timings_ms, "content", page.content)
        result_url = page.url
    finally:
        if context is not None:
            await measure_stage(timings_ms, "close_context", context.close)
        if browser is not None:
            await measure_stage(timings_ms, "close_browser", browser.close)
        await measure_stage(timings_ms, "engine_close", lambda: playwright_manager.__aexit__(None, None, None))
        timings_ms["total"] = int((time.perf_counter() - total_started_at) * 1000)
    return BrowserFetchResult(
        url=result_url,
        status_code=status_code,
        html=html,
        timings_ms=timings_ms,
    )


async def camoufox_fetch(url: str, config: BrowserFetchConfig) -> BrowserFetchResult:
    timings_ms: dict[str, int] = {}
    total_started_at = time.perf_counter()
    target_headers = request_headers_for_target(config, url)
    browser = await reusable_camoufox_browser(config, timings_ms)
    result_url = url
    status_code = 200
    html = ""
    context = None
    try:
        context = await measure_stage(
            timings_ms,
            "new_context",
            lambda: browser.new_context(locale="zh-CN", extra_http_headers=target_headers),
        )
        page = await measure_stage(timings_ms, "new_page", context.new_page)
        await measure_stage(timings_ms, "prepare_request", lambda: prepare_navigation_request(page, config, target_headers))
        response = await measure_stage(
            timings_ms,
            "goto",
            lambda: page.goto(url, wait_until=config.wait_until, timeout=config.timeout_ms),
        )
        status_code = response.status if response is not None else 200
        await wait_for_page_ready(page, config, status_code=status_code, timings_ms=timings_ms)
        html = await measure_stage(timings_ms, "content", page.content)
        result_url = page.url
    except Exception:
        if context is None:
            await close_browser_resources()
        raise
    finally:
        if context is not None:
            await measure_stage(timings_ms, "close_context", context.close)
        timings_ms["total"] = int((time.perf_counter() - total_started_at) * 1000)
    return BrowserFetchResult(
        url=result_url,
        status_code=status_code,
        html=html,
        timings_ms=timings_ms,
    )


async def reusable_camoufox_browser(config: BrowserFetchConfig, timings_ms: dict[str, int]) -> Any:
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise RuntimeError("camoufox is not installed; install backend requirements before using NOVEL_BROWSER_PROXY_ENGINE=camoufox") from exc

    global _CAMOUFOX_BROWSER
    launch_options = camoufox_launch_options(config)
    key = _freeze_browser_options(launch_options)
    async with _CAMOUFOX_BROWSER_LOCK:
        if _CAMOUFOX_BROWSER is not None and _CAMOUFOX_BROWSER.key == key:
            timings_ms["engine_reused"] = 1
            return _CAMOUFOX_BROWSER.browser
        await _close_camoufox_browser_unlocked()
        manager = AsyncCamoufox(**launch_options)
        browser = await measure_stage(timings_ms, "engine_start", manager.__aenter__)
        _CAMOUFOX_BROWSER = ReusableCamoufoxBrowser(key=key, manager=manager, browser=browser)
        return browser


async def close_browser_resources() -> None:
    async with _CAMOUFOX_BROWSER_LOCK:
        await _close_camoufox_browser_unlocked()


async def warm_browser_resources() -> None:
    try:
        config = load_config()
        if config.engine == "camoufox":
            await reusable_camoufox_browser(config, {})
    except Exception:
        return


async def _close_camoufox_browser_unlocked() -> None:
    global _CAMOUFOX_BROWSER
    browser = _CAMOUFOX_BROWSER
    _CAMOUFOX_BROWSER = None
    if browser is not None:
        await browser.manager.__aexit__(None, None, None)


def _freeze_browser_options(options: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted((key, _freeze_browser_option(value)) for key, value in options.items()))


def _freeze_browser_option(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze_browser_option(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze_browser_option(item) for item in value)
    return value


async def prepare_navigation_request(page: object, config: BrowserFetchConfig, headers: dict[str, str]) -> None:
    if config.target_method == "GET" and config.target_body is None:
        return

    async def route_once(route: object) -> None:
        await route.continue_(
            method=config.target_method,
            headers=headers,
            post_data=target_post_data(config),
        )

    await page.route("**/*", route_once, times=1)


def target_post_data(config: BrowserFetchConfig) -> str | None:
    if config.target_method not in HTTP_METHODS_WITH_BODY or config.target_body is None:
        return None
    if isinstance(config.target_body, str):
        return config.target_body
    if is_form_urlencoded_headers(config.target_headers or {}):
        return form_urlencoded_body(config.target_body)
    return json.dumps(config.target_body, ensure_ascii=False)


def form_urlencoded_body(body: Any) -> str:
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        return urlencode(
            {str(key): normalize_form_value(value) for key, value in body.items()},
            doseq=True,
        )
    return str(body)


def normalize_form_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return [normalize_form_value(item) for item in value]
    return str(value)


def is_form_urlencoded_headers(headers: dict[str, str]) -> bool:
    return "application/x-www-form-urlencoded" in header_value(headers, "content-type").lower()


def header_value(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


async def wait_for_page_ready(
    page: object,
    config: BrowserFetchConfig,
    *,
    status_code: int,
    timings_ms: dict[str, int] | None = None,
) -> None:
    timings = timings_ms if timings_ms is not None else {}
    if status_code >= 400:
        timings["wait_skipped_status"] = status_code
        return

    extra_wait_ms = config.wait_after_load_ms
    extra_wait_stage = "wait_after_load"
    if config.wait_selector:
        try:
            await measure_stage(
                timings,
                "wait_selector",
                lambda: page.wait_for_selector(
                    config.wait_selector,
                    state=config.wait_selector_state,
                    timeout=config.wait_selector_timeout_ms,
                ),
            )
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            raise RuntimeError(
                "wait_selector failed "
                f"after {config.wait_selector_timeout_ms}ms "
                f"for {config.wait_selector!r} "
                f"state={config.wait_selector_state}: {message}"
            ) from exc
        extra_wait_ms = config.wait_after_selector_ms
        extra_wait_stage = "wait_after_selector"
    if extra_wait_ms > 0:
        await measure_stage(timings, extra_wait_stage, lambda: page.wait_for_timeout(extra_wait_ms))


def browser_launch_options(config: BrowserFetchConfig) -> dict[str, object]:
    launch_kwargs: dict[str, object] = {"headless": config.headless}
    if config.proxy:
        launch_kwargs["proxy"] = {"server": config.proxy}
    if config.channel:
        launch_kwargs["channel"] = config.channel
    return launch_kwargs


def camoufox_launch_options(config: BrowserFetchConfig) -> dict[str, object]:
    launch_kwargs: dict[str, object] = {
        "headless": config.headless,
        "humanize": False,
        "geoip": False,
        "i_know_what_im_doing": True,
        "block_webrtc": True,
        "disable_coop": True,
    }
    if config.proxy:
        launch_kwargs["proxy"] = {"server": config.proxy}
    if config.camoufox_os:
        launch_kwargs["os"] = config.camoufox_os
    return launch_kwargs


def create_app(*, fetcher: BrowserFetcher = browser_fetch) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        warmup_task = asyncio.create_task(warm_browser_resources()) if fetcher is browser_fetch else None
        try:
            yield
        finally:
            if warmup_task is not None and not warmup_task.done():
                warmup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await warmup_task
            await close_browser_resources()

    app = FastAPI(title="Novel Browser Fetch Proxy", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def fetch_with_config(target_url: str, config: BrowserFetchConfig) -> HTMLResponse:
        if len(target_url) < 8 or len(target_url) > 8000:
            raise HTTPException(status_code=400, detail="target url length is invalid")
        try:
            validated_url = validate_target_url(target_url, allowed_hosts=config.allowed_hosts)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            result = await fetcher(validated_url, config)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"browser fetch failed: {exc}") from exc

        if result.status_code in {403, 429} and looks_like_browser_challenge(result.html):
            raise HTTPException(
                status_code=result.status_code,
                detail=(
                    f"浏览器访问仍被 Cloudflare 挑战拦截: {result.url}；"
                    "请切换代理出口，或配置已通过验证的浏览器 Cookie/API 来源。"
                ),
            )
        return HTMLResponse(
            result.html,
            status_code=result.status_code,
            headers=browser_response_headers(result),
        )

    @app.get("/fetch", response_class=HTMLResponse)
    async def fetch(
        url: Annotated[str, Query(min_length=8, max_length=8000)],
        wait_until: Annotated[str | None, Query(max_length=32)] = None,
        wait_selector: Annotated[str | None, Query(max_length=1000)] = None,
        wait_selector_timeout_ms: Annotated[int | None, Query(ge=100, le=120000)] = None,
        wait_after_selector_ms: Annotated[int | None, Query(ge=0, le=120000)] = None,
        wait_selector_state: Annotated[str | None, Query(max_length=32)] = None,
        referer: Annotated[str | None, Query(max_length=2000)] = None,
    ) -> HTMLResponse:
        try:
            config = apply_request_options(
                load_config(),
                wait_until=wait_until,
                wait_selector=wait_selector,
                wait_selector_timeout_ms=wait_selector_timeout_ms,
                wait_after_selector_ms=wait_after_selector_ms,
                wait_selector_state=wait_selector_state,
                referer=referer,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await fetch_with_config(url, config)

    @app.post("/fetch", response_class=HTMLResponse)
    async def fetch_with_payload(
        request: Request,
        payload: Annotated[Any, Body()] = None,
        url: Annotated[str | None, Query(min_length=8, max_length=8000)] = None,
        wait_until: Annotated[str | None, Query(max_length=32)] = None,
        wait_selector: Annotated[str | None, Query(max_length=1000)] = None,
        wait_selector_timeout_ms: Annotated[int | None, Query(ge=100, le=120000)] = None,
        wait_after_selector_ms: Annotated[int | None, Query(ge=0, le=120000)] = None,
        wait_selector_state: Annotated[str | None, Query(max_length=32)] = None,
        referer: Annotated[str | None, Query(max_length=2000)] = None,
    ) -> HTMLResponse:
        wrapped_payload = isinstance(payload, dict) and bool(str(payload.get("url") or "").strip())
        try:
            if wrapped_payload:
                target_url = str(payload.get("url") or "").strip()
                target_headers = payload.get("headers") or {}
                if not isinstance(target_headers, dict):
                    raise HTTPException(status_code=400, detail="headers must be a JSON object")
                request_options = {
                    "wait_until": _payload_str(payload, "wait_until", "waitUntil"),
                    "wait_selector": _payload_str(payload, "wait_selector", "waitSelector"),
                    "wait_selector_timeout_ms": _payload_int(
                        payload,
                        "wait_selector_timeout_ms",
                        "waitSelectorTimeoutMs",
                    ),
                    "wait_after_selector_ms": _payload_int(
                        payload,
                        "wait_after_selector_ms",
                        "waitAfterSelectorMs",
                    ),
                    "wait_selector_state": _payload_str(payload, "wait_selector_state", "waitSelectorState"),
                    "referer": _payload_str(payload, "referer"),
                    "target_method": _payload_str(payload, "method"),
                    "target_headers": {str(key): str(value) for key, value in target_headers.items() if str(key).strip()},
                    "target_body": payload.get("body"),
                }
            else:
                target_url = str(url or "").strip()
                request_options = {
                    "wait_until": wait_until,
                    "wait_selector": wait_selector,
                    "wait_selector_timeout_ms": wait_selector_timeout_ms,
                    "wait_after_selector_ms": wait_after_selector_ms,
                    "wait_selector_state": wait_selector_state,
                    "referer": referer,
                    "target_method": "POST",
                    "target_headers": target_headers_from_request(request),
                    "target_body": payload,
                }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            config = apply_request_options(
                load_config(),
                **request_options,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await fetch_with_config(target_url, config)

    return app


def browser_response_headers(result: BrowserFetchResult) -> dict[str, str]:
    headers = {"x-novel-browser-url": result.url}
    if result.timings_ms:
        headers["x-novel-browser-timing-ms"] = json.dumps(
            result.timings_ms,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        total_ms = result.timings_ms.get("total")
        if total_ms is not None:
            headers["x-novel-browser-total-ms"] = str(total_ms)
    return headers


def target_headers_from_request(request: Request) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in request.headers.items()
        if key.strip() and key.lower() not in SKIPPED_TARGET_HEADER_NAMES
    }


def _payload_str(payload: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = payload.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _payload_int(payload: dict[str, Any], *names: str) -> int | None:
    raw = _payload_str(payload, *names)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        joined = "/".join(names)
        raise ValueError(f"{joined} must be an integer") from exc


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.services.novel_browser_proxy:app",
        host=os.getenv("NOVEL_BROWSER_PROXY_HOST", DEFAULT_HOST),
        port=env_int("NOVEL_BROWSER_PROXY_PORT", DEFAULT_PORT),
        reload=False,
    )


if __name__ == "__main__":
    main()
