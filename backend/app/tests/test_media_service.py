from __future__ import annotations

"""媒体服务资产生图链路测试。

覆盖：
- 衍生图编辑提示词与模型编辑增强参数（纯函数）；
- 多张显式参考图完整透传图像编辑接口（S1）；
- 未绑定父级的资产按主资产走文生图，不再被衍生判定阻断（M6）；
- 多资产批量提交携带显式参考图时拒绝，防止交叉污染（M3）。
"""

from typing import Any

import pytest

from app.core import config as config_module
from app.core import database as database_module
from app.models.asset import ASSET_RELATION_CHILD_OF, Asset, AssetRelation
from app.schemas.project import ProjectCreate
from app.schemas.user import UserCreate
from app.services import media as media_service_module
from app.services import project as project_service_module
from app.services import user as user_service_module
from app.services.agent_gateway import MediaGenerationOutput
from app.services.media import _build_derivative_edit_prompt, _image_edit_parameters_for_model
from app.services.media_storage import MediaStorageError, StoredObject
from app.tests.base import EnvTestBase


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_build_derivative_edit_prompt_preserves_parent_reference_identity() -> None:
    """衍生图编辑应把父级参考图作为强视觉约束。"""

    asset = Asset(
        project_id=1,
        user_public_id="user-1",
        asset_type="role",
        name="张三·受伤状态",
        summary="同一名少年角色，只增加战斗后的受伤状态。",
        variant_label="受伤状态",
    )

    prompt = _build_derivative_edit_prompt(
        "少年角色设定图，黑色长衫，正面站姿。",
        asset=asset,
        reference_count=2,
    )

    assert "父级参考图" in prompt
    assert "强约束" in prompt
    assert "主体身份" in prompt
    assert "不要创建全新角色" in prompt
    assert "张三·受伤状态" in prompt
    assert "少年角色设定图，黑色长衫，正面站姿。" in prompt


def test_image_edit_parameters_enable_high_fidelity_only_for_supported_openai_models() -> None:
    """仅 GPT Image 1 系列需要显式传入 input_fidelity=high。"""

    assert _image_edit_parameters_for_model("gpt-image-1") == {"input_fidelity": "high"}
    assert _image_edit_parameters_for_model("gpt-image-1.5") == {"input_fidelity": "high"}
    assert _image_edit_parameters_for_model("gpt-image-1-mini") == {"input_fidelity": "high"}
    assert _image_edit_parameters_for_model("gpt-image-2") == {}
    assert _image_edit_parameters_for_model("other-image-model") == {}


class _MemoryMediaStorage:
    """内存对象存储桩：避免测试落盘真实文件。"""

    backend_name = "memory"
    supports_public_url = False

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> StoredObject:
        self.objects[key] = bytes(data)
        return StoredObject(key=key, backend=self.backend_name, size=len(data), content_type=content_type)

    async def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise MediaStorageError("媒体文件不存在")
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.objects

    def public_url(self, key: str) -> str:
        return ""

    def local_path(self, key: str) -> None:
        return None


class _StubMediaGateway:
    """图像网关桩：记录调用并返回可解码的 b64 输出。"""

    def __init__(self) -> None:
        self.edit_calls: list[dict[str, Any]] = []
        self.generate_calls: list[dict[str, Any]] = []

    def _output(self) -> MediaGenerationOutput:
        return MediaGenerationOutput.from_raw(
            {"data": [{"b64_json": "ZmFrZS1pbWFnZQ==", "mime_type": "image/png", "width": 16, "height": 9}]}
        )

    async def edit_image(
        self, *, model_id: str, prompt: str = "", images: list[Any] | None = None, **kwargs: Any
    ) -> MediaGenerationOutput:
        self.edit_calls.append({"model_id": model_id, "prompt": prompt, "images": list(images or []), "kwargs": kwargs})
        return self._output()

    async def generate_image(self, *, model_id: str, prompt: str = "", **kwargs: Any) -> MediaGenerationOutput:
        self.generate_calls.append({"model_id": model_id, "prompt": prompt, "kwargs": kwargs})
        return self._output()


class TestAssetImageGeneration(EnvTestBase):
    def _reload(self, monkeypatch: pytest.MonkeyPatch, tmp_path, db_name: str):
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / db_name),
            },
        )
        return self.reload_modules(
            config_module,
            database_module,
            user_service_module,
            project_service_module,
            media_service_module,
        )

    async def _create_owner_and_project(self, session, user_service, project_service):
        owner = await user_service.create_user(
            session,
            UserCreate(
                username="media-owner",
                nickname="Media Owner",
                email="media-owner@example.com",
                password="password123",
                repassword="password123",
            ),
        )
        project = await project_service.create_project(
            session,
            owner.public_id,
            ProjectCreate(name="Media Project"),
        )
        return owner, project

    def _make_asset(self, project_id: int, user_public_id: str, name: str, *, main_asset: bool) -> Asset:
        return Asset(
            project_id=project_id,
            user_public_id=user_public_id,
            asset_type="role",
            name=name,
            main_asset=main_asset,
        )

    @pytest.mark.anyio
    async def test_generate_asset_image_sends_all_reference_images_to_edit(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """S1：衍生资产多张显式参考图必须全部透传图像编辑接口，不允许静默丢图。"""

        _, database, user_service, project_service, media_service = self._reload(
            monkeypatch, tmp_path, "media-multi-ref.db"
        )
        storage = _MemoryMediaStorage()
        monkeypatch.setattr(media_service, "get_media_storage", lambda: storage)

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner, project = await self._create_owner_and_project(session, user_service, project_service)
                parent = self._make_asset(int(project.id), owner.public_id, "主角", main_asset=True)
                child = self._make_asset(int(project.id), owner.public_id, "主角·受伤", main_asset=False)
                session.add(parent)
                session.add(child)
                await session.flush()
                session.add(
                    AssetRelation(
                        source_asset_id=int(child.id),
                        target_asset_id=int(parent.id),
                        relation_type=ASSET_RELATION_CHILD_OF,
                    )
                )
                await session.flush()

                reference_ids: list[str] = []
                for index in range(3):
                    media = await media_service.upload_media(
                        session,
                        project.public_id,
                        owner.public_id,
                        filename=f"reference-{index}.png",
                        content_type="image/png",
                        data=b"reference-bytes-%d" % index,
                        scope_type="asset",
                        scope_public_id=child.public_id,
                    )
                    reference_ids.append(media.public_id)
                await session.commit()

                gateway = _StubMediaGateway()
                result = await media_service.generate_asset_image(
                    session,
                    project.public_id,
                    owner.public_id,
                    asset_public_id=child.public_id,
                    model_id="test-image-model",
                    prompt="受伤状态设定图",
                    reference_media_public_ids=reference_ids,
                    gateway=gateway,
                )
                await session.commit()

                assert len(gateway.edit_calls) == 1
                assert gateway.generate_calls == []
                call = gateway.edit_calls[0]
                sent_ids = [image["media_public_id"] for image in call["images"]]
                assert sent_ids == reference_ids
                assert "父级参考图" in call["prompt"]
                media = result["media"]
                assert media.status == "ready"
                assert result["reference_media_public_ids"] == reference_ids
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_generate_asset_image_without_parent_binding_uses_text_to_image(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """M6：未绑定父级的资产即使 main_asset=False，也按主资产走文生图而非报错。"""

        _, database, user_service, project_service, media_service = self._reload(
            monkeypatch, tmp_path, "media-no-parent.db"
        )
        storage = _MemoryMediaStorage()
        monkeypatch.setattr(media_service, "get_media_storage", lambda: storage)

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner, project = await self._create_owner_and_project(session, user_service, project_service)
                orphan = self._make_asset(int(project.id), owner.public_id, "未标记主资产", main_asset=False)
                session.add(orphan)
                await session.commit()

                gateway = _StubMediaGateway()
                result = await media_service.generate_asset_image(
                    session,
                    project.public_id,
                    owner.public_id,
                    asset_public_id=orphan.public_id,
                    model_id="test-image-model",
                    prompt="普通角色设定图",
                    reference_media_public_ids=["ignored-reference"],
                    gateway=gateway,
                )
                await session.commit()

                assert len(gateway.generate_calls) == 1
                assert gateway.edit_calls == []
                assert result["media"].status == "ready"
                assert result["reference_media_public_ids"] == []
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_build_image_generation_task_items_rejects_reference_for_multiple_assets(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """M3：多资产批量提交携带显式参考图必须拒绝，防止参考图交叉污染出图。"""

        _, database, user_service, project_service, media_service = self._reload(
            monkeypatch, tmp_path, "media-multi-asset.db"
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner, project = await self._create_owner_and_project(session, user_service, project_service)
                project.image_model = "test-image-model"
                session.add(project)
                first = self._make_asset(int(project.id), owner.public_id, "资产甲", main_asset=True)
                second = self._make_asset(int(project.id), owner.public_id, "资产乙", main_asset=True)
                session.add(first)
                session.add(second)
                await session.commit()

                from app.services import asset as asset_service

                with pytest.raises(asset_service.AssetServiceError, match="显式参考图仅支持单个资产提交"):
                    await media_service.build_image_generation_task_items(
                        session,
                        project.public_id,
                        owner.public_id,
                        model_id="test-image-model",
                        asset_public_ids=[first.public_id, second.public_id],
                        prompt="批量出图",
                        reference_media_public_ids=["some-reference"],
                    )
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
