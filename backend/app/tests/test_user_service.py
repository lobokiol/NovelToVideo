from __future__ import annotations

import pytest

from app.core import config as config_module
from app.core import database as database_module
from app.schemas.user import UserCreate, UserUpdate
from app.services import user as user_service_module
from app.tests.base import EnvTestBase


class TestUserService(EnvTestBase):
    @pytest.mark.anyio
    async def test_user_service_crud_flow_uses_async_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "service.db"),
            },
        )

        _, database, user_service = self.reload_modules(
            config_module,
            database_module,
            user_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                created_user = await user_service.create_user(
                    session,
                    UserCreate(
                        username="moluo",
                        nickname="Moluo",
                        email="moluo@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )

                assert created_user.id is not None
                assert created_user.password_hash != "password123"

                fetched_user = await user_service.get_user_by_username(session, "moluo")
                assert fetched_user is not None
                assert fetched_user.public_id == created_user.public_id

                updated_user = await user_service.update_user(
                    session,
                    created_user.public_id,
                    UserUpdate(nickname="Moluo Updated"),
                )
                assert updated_user.nickname == "Moluo Updated"

                disabled_user = await user_service.disable_user(session, created_user.public_id)
                assert disabled_user.disabled_at is not None

                users = await user_service.list_users(session)
                assert [user.username for user in users] == ["moluo"]

                await user_service.delete_user(session, created_user.public_id)
                assert await user_service.get_user_by_public_id(session, created_user.public_id) is None
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_ensure_default_admin_creates_admin_when_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "admin.db"),
            },
        )

        config, database, user_service = self.reload_modules(
            config_module,
            database_module,
            user_service_module,
        )

        await database.create_db_and_tables()
        try:
            await user_service.ensure_default_admin()

            async with database.async_session_maker() as session:
                admin_user = await user_service.get_user_by_username(
                    session,
                    config.settings.user_default_admin_name,
                )

            assert admin_user is not None
            assert admin_user.is_superuser is True
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_ensure_default_admin_promotes_existing_default_user(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "regular-user.db"),
            },
        )

        config, database, user_service = self.reload_modules(
            config_module,
            database_module,
            user_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                await user_service.create_user(
                    session,
                    UserCreate(
                        username=config.settings.user_default_admin_name,
                        nickname=config.settings.user_default_admin_name,
                        email="admin@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )

            await user_service.ensure_default_admin()

            async with database.async_session_maker() as session:
                admin_user = await user_service.get_user_by_username(
                    session,
                    config.settings.user_default_admin_name,
                )

            assert admin_user is not None
            assert admin_user.is_superuser is True
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
