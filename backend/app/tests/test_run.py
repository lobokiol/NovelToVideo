from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import run


def test_browser_proxy_auto_start_defaults_to_enabled(monkeypatch) -> None:
    monkeypatch.delenv("NOVEL_BROWSER_PROXY_AUTO_START", raising=False)

    assert run.browser_proxy_auto_start_enabled() is True


def test_browser_proxy_auto_start_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_BROWSER_PROXY_AUTO_START", "false")

    assert run.browser_proxy_auto_start_enabled() is False


def test_start_browser_proxy_process_uses_current_python(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeProcess:
        returncode = None

    def fake_popen(command: list[str], **kwargs: Any) -> FakeProcess:
        calls.append({"command": command, **kwargs})
        return FakeProcess()

    monkeypatch.setenv("NOVEL_BROWSER_PROXY_AUTO_START", "true")
    monkeypatch.delenv("NOVEL_BROWSER_PROXY_HOST", raising=False)
    monkeypatch.delenv("NOVEL_BROWSER_PROXY_PORT", raising=False)
    monkeypatch.setattr(run, "is_tcp_port_open", lambda host, port: False)

    process = run.start_browser_proxy_process(popen_factory=fake_popen)

    assert isinstance(process, FakeProcess)
    assert calls == [
        {
            "command": [sys.executable, "-m", "app.services.novel_browser_proxy"],
            "cwd": str(Path(run.__file__).resolve().parent),
        }
    ]


def test_start_browser_proxy_process_skips_existing_listener(monkeypatch) -> None:
    def fake_popen(command: list[str], **kwargs: Any) -> object:
        raise AssertionError("proxy process should not start when port is already open")

    monkeypatch.setenv("NOVEL_BROWSER_PROXY_AUTO_START", "true")
    monkeypatch.setattr(run, "is_tcp_port_open", lambda host, port: True)

    assert run.start_browser_proxy_process(popen_factory=fake_popen) is None


def test_stop_browser_proxy_process_terminates_then_kills_after_timeout() -> None:
    class FakeProcess:
        returncode = None

        def __init__(self) -> None:
            self.terminated = False
            self.killed = False

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> None:
            raise subprocess.TimeoutExpired("proxy", timeout)

        def kill(self) -> None:
            self.killed = True

    process = FakeProcess()

    run.stop_browser_proxy_process(process, timeout=0.01)

    assert process.terminated is True
    assert process.killed is True
