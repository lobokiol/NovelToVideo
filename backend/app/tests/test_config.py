from __future__ import annotations

import pytest

from app.core.config import BASE_DIR, Settings
from app.services.screenwriting.rag_runtime import build_project_rag_vector_store_dir


def test_settings_reads_environment_and_casts_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "APP_NAME": "Test App",
        "PORT": "9000",
        "DB_PORT": "15432",
        "DB_HEALTHCHECK_RETRIES": "9",
        "REDIS_PORT": "16379",
        "REDIS_DB": "2",
    }.items():
        monkeypatch.setenv(key, value)

    settings = Settings()

    assert settings.app_name == "Test App"
    assert settings.port == 9000
    assert settings.db_port == 15432
    assert settings.db_healthcheck_retries == 9
    assert settings.redis_port == 16379
    assert settings.redis_db == 2


def test_settings_defaults_novel_rule_impersonate_to_specific_chrome_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NOVEL_CRAWL_IMPERSONATE", raising=False)

    settings = Settings()

    assert settings.novel_crawl_impersonate == "chrome110"


def test_screenwriting_rag_vector_store_defaults_to_project_dirs_under_local_chroma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCREENWRITING_RAG_VECTOR_STORE_ROOT", raising=False)

    current = Settings()
    vector_store_dir = build_project_rag_vector_store_dir(" Project:ABC/001 ", config=current)

    assert current.screenwriting_rag_vector_store_root == "./data/chroma"
    assert vector_store_dir == (
        BASE_DIR / "data" / "chroma" / "screenwriting-rag" / "projects" / "project-abc-001"
    ).resolve()


def test_screenwriting_rag_vector_store_uses_configured_chroma_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("SCREENWRITING_RAG_VECTOR_STORE_ROOT", str(tmp_path))

    current = Settings()
    vector_store_dir = build_project_rag_vector_store_dir("Project One", config=current)

    assert vector_store_dir == tmp_path / "screenwriting-rag" / "projects" / "project-one"


def test_screenwriting_rag_vector_store_keeps_legacy_rag_root_without_duplication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    legacy_root = tmp_path / "screenwriting-rag"
    monkeypatch.setenv("SCREENWRITING_RAG_VECTOR_STORE_ROOT", str(legacy_root))

    current = Settings()
    vector_store_dir = build_project_rag_vector_store_dir("Project One", config=current)

    assert vector_store_dir == legacy_root / "projects" / "project-one"
