from __future__ import annotations

import pytest

from app.core import config as config_module
from app.core import database as database_module
from app.schemas.project import ProjectCreate
from app.schemas.user import UserCreate
from app.services import asset as asset_service_module
from app.services import project as project_service_module
from app.services import script as script_service_module
from app.services import user as user_service_module
from app.tests.base import EnvTestBase


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


SCRIPT_CONTENT = """# 示例剧本 EP01：开端

## 剧情梗概

主角在旧院里发现线索，并决定追查真相。

---

1-1 旧院 日/外
时长：30s
人物：主角

△主角推开旧院木门，灰尘在阳光里翻涌。
主角：这里一定留下过什么。
"""


class TestScriptService(EnvTestBase):
    @pytest.mark.anyio
    async def test_sync_workspace_to_plan_updates_existing_plan(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "script-sync.db"),
            },
        )

        _, database, user_service, project_service, script_service = self.reload_modules(
            config_module,
            database_module,
            user_service_module,
            project_service_module,
            script_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await user_service.create_user(
                    session,
                    UserCreate(
                        username="script-owner",
                        nickname="Script Owner",
                        email="script-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Script Project"),
                )

                first_plan = await script_service.sync_workspace_to_plan(
                    session,
                    project.public_id,
                    owner.public_id,
                    script_content=SCRIPT_CONTENT,
                    title="初版剧本",
                )
                await session.commit()

                second_plan = await script_service.sync_workspace_to_plan(
                    session,
                    project.public_id,
                    owner.public_id,
                    script_content=SCRIPT_CONTENT.replace("追查真相", "继续追查真相"),
                    title="新版剧本",
                )
                await session.commit()
                detail_plan, episodes = await script_service.get_plan_detail(
                    session,
                    project.public_id,
                    owner.public_id,
                    second_plan.public_id,
                )

            assert second_plan.public_id == first_plan.public_id
            assert detail_plan.title == "新版剧本"
            assert len(episodes) == 1
            assert episodes[0].version == 2
            assert "继续追查真相" in episodes[0].summary
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_list_project_episodes_includes_main_assets_from_asset_episode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "script-assets.db"),
            },
        )

        _, database, user_service, project_service, script_service, asset_service = self.reload_modules(
            config_module,
            database_module,
            user_service_module,
            project_service_module,
            script_service_module,
            asset_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await user_service.create_user(
                    session,
                    UserCreate(
                        username="script-asset-owner",
                        nickname="Script Asset Owner",
                        email="script-asset-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Script Asset Project"),
                )
                await script_service.sync_workspace_to_plan(
                    session,
                    project.public_id,
                    owner.public_id,
                    script_content=SCRIPT_CONTENT,
                    title="初版剧本",
                )
                await session.commit()

                project_id = int(project.id)
                master, _, derived, _ = await asset_service.write_master_and_derivative(
                    session,
                    project_id,
                    owner.public_id,
                    {
                        "asset_type": "role",
                        "name": "张三",
                        "keyword": "",
                        "colors": "",
                        "summary": "张三是本集主资产摘要",
                        "description": {"状态": "青年"},
                        "details": {},
                        "accessories": {},
                        "episode_indices": set(),
                        "children": [],
                        "variant_label": "",
                    },
                    {1},
                    supplement="",
                )
                await session.commit()

                rows = await script_service.list_project_episodes(session, project.public_id, owner.public_id)

            assert len(rows) == 1
            episode, _, _, assets = rows[0]
            assert episode.episode_index == 1
            assert [asset.public_id for asset in assets] == [master.public_id]
            assert assets[0].summary == "张三是本集主资产摘要"
            assert derived.public_id not in {asset.public_id for asset in assets}
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
