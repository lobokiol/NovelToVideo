from __future__ import annotations

import importlib
from types import ModuleType

from fastapi.testclient import TestClient
import pytest

from app.main import create_app

class EnvTestBase:
    """关于环境的测试基类
    
    """
    def set_env(self, monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
        for key, value in values.items():
            monkeypatch.setenv(key, value)

    def reload_modules(self, *modules: ModuleType) -> tuple[ModuleType, ...]:
        return tuple(importlib.reload(module) for module in modules)
    

class ApiTestBase:
    """关于API接口的测试基类
    
    """
    def create_client(self) -> TestClient:
        return TestClient(create_app())