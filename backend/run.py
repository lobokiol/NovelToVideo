import sys
import asyncio
import os
import socket
import subprocess
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


import uvicorn
from app.core.config import settings


TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}
BACKEND_ROOT = Path(__file__).resolve().parent
DEFAULT_BROWSER_PROXY_HOST = "127.0.0.1"
DEFAULT_BROWSER_PROXY_PORT = 8787


def browser_proxy_auto_start_enabled() -> bool:
    value = os.getenv("NOVEL_BROWSER_PROXY_AUTO_START")
    if value is None or not value.strip():
        return True
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return True


def browser_proxy_host() -> str:
    return os.getenv("NOVEL_BROWSER_PROXY_HOST", DEFAULT_BROWSER_PROXY_HOST).strip() or DEFAULT_BROWSER_PROXY_HOST


def browser_proxy_port() -> int:
    raw = os.getenv("NOVEL_BROWSER_PROXY_PORT", "").strip()
    if not raw:
        return DEFAULT_BROWSER_PROXY_PORT
    return int(raw)


def is_tcp_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def start_browser_proxy_process(
    *,
    popen_factory: type[subprocess.Popen] | object = subprocess.Popen,
) -> subprocess.Popen | None:
    if not browser_proxy_auto_start_enabled():
        return None

    host = browser_proxy_host()
    port = browser_proxy_port()
    if is_tcp_port_open(host, port):
        return None

    command = [sys.executable, "-m", "app.services.novel_browser_proxy"]
    return popen_factory(command, cwd=str(BACKEND_ROOT))


def stop_browser_proxy_process(process: subprocess.Popen | None, *, timeout: float = 5.0) -> None:
    if process is None or process.returncode is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> None:
    browser_proxy_process = start_browser_proxy_process()
    try:
        uvicorn.run("app.main:app", host=settings.host, port=settings.port, loop="none", reload=settings.reload)
    finally:
        stop_browser_proxy_process(browser_proxy_process)


if __name__ == "__main__":
    main()
