from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from app import main as main_module
from app.core import config as config_module
from app.core import database as database_module
from app.middlewares import common as common_module
from app.routers import api as api_module
from app.routers import project as project_router_module
from app.schemas.project import ProjectCreate, ProjectMemberRead
from app.schemas.user import UserCreate
from app.services import project as project_service_module
from app.services import user as user_service_module
from app.tests.base import EnvTestBase


class TestProjectService(EnvTestBase):
    @pytest.mark.anyio
    async def test_project_member_responses_include_user_email(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "project-members.db"),
            },
        )

        _, database, user_service, project_service = self.reload_modules(
            config_module,
            database_module,
            user_service_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await user_service.create_user(
                    session,
                    UserCreate(
                        username="owner",
                        nickname="Owner",
                        email="owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                editor = await user_service.create_user(
                    session,
                    UserCreate(
                        username="editor",
                        nickname="Editor",
                        email="editor@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Story Project"),
                )

                invited_member = await project_service.invite_project_member(
                    session,
                    project.public_id,
                    editor.public_id,
                    project_service.ProjectMemberRole.EDITOR,
                    owner.public_id,
                )
                members = await project_service.list_project_members(
                    session,
                    project.public_id,
                    owner.public_id,
                )

            assert isinstance(invited_member, ProjectMemberRead)
            assert invited_member.user_email == "editor@example.com"
            assert all(isinstance(member, ProjectMemberRead) for member in members)
            assert {
                (member.user_public_id, member.user_email, member.role)
                for member in members
            } == {
                (owner.public_id, "owner@example.com", project_service.ProjectMemberRole.OWNER),
                (editor.public_id, "editor@example.com", project_service.ProjectMemberRole.EDITOR),
            }
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_list_project_members_route_returns_user_email(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "project-members-route.db"),
            },
        )

        _, database, user_service, project_service, common, _, _, main = self.reload_modules(
            config_module,
            database_module,
            user_service_module,
            project_service_module,
            common_module,
            project_router_module,
            api_module,
            main_module,
        )

        auth_subject = {"public_id": ""}

        async def fake_decode_token(token: str) -> dict[str, str]:
            return {"type": "access", "sub": auth_subject["public_id"]}

        monkeypatch.setattr(common, "decode_token", fake_decode_token)

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await user_service.create_user(
                    session,
                    UserCreate(
                        username="route-owner",
                        nickname="Route Owner",
                        email="route-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                editor = await user_service.create_user(
                    session,
                    UserCreate(
                        username="route-editor",
                        nickname="Route Editor",
                        email="route-editor@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Route Project"),
                )
                await project_service.invite_project_member(
                    session,
                    project.public_id,
                    editor.public_id,
                    project_service.ProjectMemberRole.EDITOR,
                    owner.public_id,
                )

            auth_subject["public_id"] = owner.public_id
            app = main.create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    f"/api/projects/{project.public_id}/members",
                    headers={"Authorization": "Bearer test-token"},
                )

            assert response.status_code == 200
            response_members = response.json()
            assert {
                (member["user_public_id"], member["user_email"], member["role"])
                for member in response_members
            } == {
                (owner.public_id, "route-owner@example.com", "owner"),
                (editor.public_id, "route-editor@example.com", "editor"),
            }
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_visual_style_route_returns_direct_image_urls(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        visual_style_root = tmp_path / "art_list"
        style_dir = visual_style_root / "cinematic"
        images_dir = style_dir / "images"
        images_dir.mkdir(parents=True)
        (style_dir / "README.md").write_text("# Cinematic\n", encoding="utf-8")
        image_bytes = b"image-bytes"
        (images_dir / "reference.png").write_bytes(image_bytes)

        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "visual-styles-route.db"),
                "VISUAL_STYLE_ROOT": str(visual_style_root),
            },
        )

        _, _, common, _, _, _, main = self.reload_modules(
            config_module,
            database_module,
            common_module,
            project_service_module,
            project_router_module,
            api_module,
            main_module,
        )

        async def fake_decode_token(token: str) -> dict[str, str]:
            return {"type": "access", "sub": "admin-public-id"}

        monkeypatch.setattr(common, "decode_token", fake_decode_token)

        app = main.create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/api/projects/visual-styles",
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 200
            visual_styles = response.json()
            image = visual_styles[0]["images"][0]
            assert image["path"] == "images/reference.png"
            assert image["url"] == "/api/projects/visual-styles/cinematic/images/reference.png"

            image_response = await client.get(image["url"])

        assert image_response.status_code == 200
        assert image_response.content == image_bytes
