from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from app import main as main_module
from app.core import config as config_module
from app.core import database as database_module
from app.routers import api as api_module
from app.routers import user as user_router_module
from app.services import user as user_service_module
from app.tests.base import EnvTestBase


class TestUserRouter(EnvTestBase):
    def _set_sqlite_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        db_path: str,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": db_path,
            },
        )

    def _reload_app_modules(self):
        return self.reload_modules(
            config_module,
            database_module,
            user_service_module,
            user_router_module,
            api_module,
            main_module,
        )

    @pytest.mark.anyio
    async def test_user_router_runs_with_async_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self._set_sqlite_env(monkeypatch, str(tmp_path / "router.db"))

        _, database, _, _, _, main = self._reload_app_modules()

        app = main.create_app()
        transport = ASGITransport(app=app)

        await database.create_db_and_tables()
        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_response = await client.post(
                    "/api/users/",
                    json={
                        "username": "moluo",
                        "nickname": "Moluo",
                        "email": "moluo@example.com",
                        "password": "password123",
                        "repassword": "password123",
                    },
                )
                assert create_response.status_code == 201
                created_user = create_response.json()
                public_id = created_user["public_id"]

                list_response = await client.get("/api/users/")
                assert list_response.status_code == 200
                assert [user["username"] for user in list_response.json()] == ["moluo"]

                detail_response = await client.get(f"/api/users/{public_id}")
                assert detail_response.status_code == 200
                assert detail_response.json()["email"] == "moluo@example.com"

                update_response = await client.put(
                    f"/api/users/{public_id}",
                    json={"nickname": "Moluo Updated"},
                )
                assert update_response.status_code == 200
                assert update_response.json()["nickname"] == "Moluo Updated"

                disable_response = await client.patch(f"/api/users/{public_id}/disable")
                assert disable_response.status_code == 200
                assert disable_response.json()["disabled_at"] is not None

                delete_response = await client.delete(f"/api/users/{public_id}")
                assert delete_response.status_code == 204

                missing_response = await client.get(f"/api/users/{public_id}")
                assert missing_response.status_code == 404
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_login_user_returns_tokens_and_updates_last_login(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self._set_sqlite_env(monkeypatch, str(tmp_path / "login-success.db"))
        _, database, user_service, user_router, _, main = self._reload_app_modules()

        token_calls: list[tuple[str, str]] = []

        async def fake_create_login_tokens(public_id: str, username: str) -> dict[str, str | int]:
            token_calls.append((public_id, username))
            return {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 900,
            }

        monkeypatch.setattr(user_router, "create_login_tokens", fake_create_login_tokens)

        app = main.create_app()
        transport = ASGITransport(app=app)

        await database.create_db_and_tables()
        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_response = await client.post(
                    "/api/users/",
                    json={
                        "username": "moluo",
                        "nickname": "Moluo",
                        "email": "moluo@example.com",
                        "password": "password123",
                        "repassword": "password123",
                    },
                )
                assert create_response.status_code == 201
                created_user = create_response.json()

                login_response = await client.post(
                    "/api/users/login",
                    json={"username": "moluo", "password": "password123"},
                )

            assert login_response.status_code == 200
            response_data = login_response.json()
            assert response_data == {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "token_type": "bearer",
                "expires_in": 900,
                "user": {
                    "public_id": created_user["public_id"],
                    "username": "moluo",
                    "nickname": "Moluo",
                },
            }
            assert token_calls == [(created_user["public_id"], "moluo")]

            async with database.async_session_maker() as session:
                logged_in_user = await user_service.get_user_by_username(session, "moluo")

            assert logged_in_user is not None
            assert logged_in_user.last_login_at is not None
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_login_user_rejects_invalid_password(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self._set_sqlite_env(monkeypatch, str(tmp_path / "login-invalid-password.db"))
        _, database, _, user_router, _, main = self._reload_app_modules()

        token_calls: list[tuple[str, str]] = []

        async def fake_create_login_tokens(public_id: str, username: str) -> dict[str, str | int]:
            token_calls.append((public_id, username))
            return {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 900,
            }

        monkeypatch.setattr(user_router, "create_login_tokens", fake_create_login_tokens)

        app = main.create_app()
        transport = ASGITransport(app=app)

        await database.create_db_and_tables()
        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_response = await client.post(
                    "/api/users/",
                    json={
                        "username": "moluo",
                        "nickname": "Moluo",
                        "email": "moluo@example.com",
                        "password": "password123",
                        "repassword": "password123",
                    },
                )
                assert create_response.status_code == 201

                login_response = await client.post(
                    "/api/users/login",
                    json={"username": "moluo", "password": "wrong-password"},
                )

            assert login_response.status_code == 401
            assert login_response.json() == {"detail": "用户名或密码错误"}
            assert token_calls == []
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_login_user_rejects_disabled_user(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self._set_sqlite_env(monkeypatch, str(tmp_path / "login-disabled.db"))
        _, database, _, user_router, _, main = self._reload_app_modules()

        token_calls: list[tuple[str, str]] = []

        async def fake_create_login_tokens(public_id: str, username: str) -> dict[str, str | int]:
            token_calls.append((public_id, username))
            return {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 900,
            }

        monkeypatch.setattr(user_router, "create_login_tokens", fake_create_login_tokens)

        app = main.create_app()
        transport = ASGITransport(app=app)

        await database.create_db_and_tables()
        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_response = await client.post(
                    "/api/users/",
                    json={
                        "username": "moluo",
                        "nickname": "Moluo",
                        "email": "moluo@example.com",
                        "password": "password123",
                        "repassword": "password123",
                    },
                )
                assert create_response.status_code == 201
                public_id = create_response.json()["public_id"]

                disable_response = await client.patch(f"/api/users/{public_id}/disable")
                assert disable_response.status_code == 200

                login_response = await client.post(
                    "/api/users/login",
                    json={"username": "moluo", "password": "password123"},
                )

            assert login_response.status_code == 403
            assert login_response.json() == {"detail": "用户已被禁用"}
            assert token_calls == []
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
