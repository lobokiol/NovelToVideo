from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import config as config_module
from app.core import database as database_module
from app.models.novel import NovelCrawlSource
from app.schemas.novel import CrawlSearchPayload
from app.schemas.novel import NovelChapterImport, NovelChapterImportItem
from app.schemas.project import ProjectCreate
from app.schemas.user import UserCreate
from app.services import novel as novel_service_module
from app.services import project as project_service_module
from app.services import user as user_service_module
from app.tests.base import EnvTestBase


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class TestNovelService(EnvTestBase):
    @pytest.mark.anyio
    async def test_search_crawl_books_reports_non_empty_message_for_empty_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class EmptyMessageError(Exception):
            def __str__(self) -> str:
                return ""

        async def fake_get_project_with_id(
            session: object,
            project_public_id: str,
            current_user_public_id: str,
        ) -> object:
            return SimpleNamespace(id=1)

        async def fake_get_visible_crawl_source_or_raise(
            session: object,
            project_id: int,
            key: str,
        ) -> NovelCrawlSource:
            return NovelCrawlSource(key=key, name="Rule Source", source_type="rule")

        async def fake_search_books(source: NovelCrawlSource, query: str) -> list[object]:
            raise EmptyMessageError()

        monkeypatch.setattr(novel_service_module, "_get_project_with_id", fake_get_project_with_id)
        monkeypatch.setattr(
            novel_service_module,
            "_get_visible_crawl_source_or_raise",
            fake_get_visible_crawl_source_or_raise,
        )
        monkeypatch.setattr(novel_service_module.novel_crawler, "search_books", fake_search_books)

        with pytest.raises(novel_service_module.NovelCrawlSourceValidationError) as exc_info:
            await novel_service_module.search_crawl_books(
                object(),
                "project-public",
                "user-public",
                CrawlSearchPayload(source_key="rule", query="Target Book"),
            )

        assert str(exc_info.value) == "爬取请求失败: EmptyMessageError"

    @pytest.mark.anyio
    async def test_clean_chapter_for_task_uses_payload_model_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeSession:
            def add(self, value: object) -> None:
                self.added = value

            async def commit(self) -> None:
                self.committed = True

            async def refresh(self, value: object) -> None:
                self.refreshed = value

        project = SimpleNamespace(id=1, text_model="project-model")
        chapter = SimpleNamespace(
            id=10,
            public_id="chapter-public",
            event_state=1,
            event="{}",
            error_reason=None,
            updated_at=None,
        )
        seen: dict[str, str] = {}

        async def fake_get_project_with_id(
            session: object,
            project_public_id: str,
            current_user_public_id: str,
        ) -> object:
            return project

        async def fake_get_chapter_model_or_raise(
            session: object,
            project_id: int,
            chapter_id: int,
        ) -> object:
            return chapter

        async def fake_apply_chapter_event_extraction(
            target_chapter: object,
            text_model: str,
        ) -> dict[str, str]:
            seen["model_id"] = text_model
            return {"model_id": text_model, "composed_prompt": "prompt"}

        monkeypatch.setattr(novel_service_module, "_get_project_with_id", fake_get_project_with_id)
        monkeypatch.setattr(novel_service_module, "_get_chapter_model_or_raise", fake_get_chapter_model_or_raise)
        monkeypatch.setattr(
            novel_service_module,
            "_apply_chapter_event_extraction",
            fake_apply_chapter_event_extraction,
        )

        result = await novel_service_module.clean_chapter_for_task(
            FakeSession(),
            "project-public",
            10,
            "user-public",
            model_id="payload-model",
        )

        assert seen["model_id"] == "payload-model"
        assert result["model_id"] == "payload-model"

    @pytest.mark.anyio
    async def test_import_chapters_accepts_preview_drafts(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "novel-import.db"),
            },
        )

        _, database, user_service, project_service, novel_service = self.reload_modules(
            config_module,
            database_module,
            user_service_module,
            project_service_module,
            novel_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await user_service.create_user(
                    session,
                    UserCreate(
                        username="novel-owner",
                        nickname="Novel Owner",
                        email="novel-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Novel Import Project"),
                )

                imported = await novel_service.import_chapters(
                    session,
                    project.public_id,
                    owner.public_id,
                    NovelChapterImport(
                        chapters=[
                            NovelChapterImportItem(
                                reel="\u7b2c\u4e00\u96c6",
                                chapter="\u5e8f\u7ae0",
                                chapter_data="\u5e8f\u7ae0\u6b63\u6587",
                            ),
                            NovelChapterImportItem(
                                reel="\u7b2c\u4e00\u96c6",
                                chapter="\u7b2c\u4e00\u7ae0 \u9752\u4e91",
                                chapter_data="\u9752\u4e91\u6b63\u6587",
                            ),
                        ],
                    ),
                )

            assert [item.chapter_index for item in imported] == [1, 2]
            assert [item.reel for item in imported] == ["\u7b2c\u4e00\u96c6", "\u7b2c\u4e00\u96c6"]
            assert [item.chapter for item in imported] == [
                "\u5e8f\u7ae0",
                "\u7b2c\u4e00\u7ae0 \u9752\u4e91",
            ]
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
