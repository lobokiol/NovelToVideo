from __future__ import annotations

"""资产抽取服务测试。

覆盖：
- episodes 由程序按当前抽取分集写入，忽略模型返回的集号；
- 主资产 / 衍生资产写入模型（首次写 2 条；再现累加主资产剧集；同状态合并衍生、新状态新增衍生）。
"""

import json
from typing import Any

import pytest
from sqlmodel import select

from app.core import config as config_module
from app.core import database as database_module
from app.models.asset import ASSET_RELATION_CHILD_OF, AssetEpisode, AssetRelation
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


class _StubRagContext:
    """RAG 上下文桩：返回空文本，促使补全环节走 no_rag_context 分支不调用模型。"""

    text = ""
    runtime: dict[str, Any] = {}


class _StubRagPreparation:
    """RAG 准备结果桩。"""

    context = _StubRagContext()


async def _stub_prepare_rag_context(*args: Any, **kwargs: Any) -> _StubRagPreparation:
    return _StubRagPreparation()


class _StubGateway:
    """文本模型网关桩：按序返回预置输出，并记录被调用次数。"""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: list[list[dict[str, str]]] = []

    async def generate_stream(self, *, model_id: str, messages: list[dict[str, str]]):
        self.calls.append(messages)
        text = self._outputs.pop(0) if self._outputs else ""
        yield text


def _role_item(name: str, state: str = "") -> dict[str, Any]:
    """构造一个解析后的人物资产项；state 写入 description 状态字段。"""

    description: dict[str, Any] = {"性别": "男"}
    if state:
        description["状态"] = state
    return {
        "asset_type": "role",
        "name": name,
        "keyword": "关键词",
        "colors": "",
        "summary": "概述",
        "description": description,
        "details": {},
        "accessories": {},
        "episode_indices": set(),
        "children": [],
        "variant_label": "",
    }


class TestAssetEpisodes(EnvTestBase):
    def test_infer_asset_state_uses_state_phrase_not_long_description(self) -> None:
        """衍生资产状态标签应优先使用状态类词组，不能把外观长文当状态。"""

        item = {
            "asset_type": "scene",
            "name": "旧庙",
            "description": {
                "场景类型": "属于旧庙场景的衍生资产",
                "外观描述": "村东的破败旧庙，庙门残旧，庙堂昏暗，内有残破蒲团，最终被战斗摧毁成为废墟",
            },
        }

        assert asset_service_module._infer_asset_state(item) == "衍生资产"

    def test_parse_extracted_assets_ignores_model_episodes(self) -> None:
        """解析阶段必须忽略模型返回的 episodes，集号留空交由程序写入。"""

        raw = json.dumps(
            [
                {
                    "assetType": "role",
                    "name": "测试角色",
                    "keyword": "",
                    "colors": "",
                    "summary": "",
                    "description": {},
                    "details": {},
                    "accessories": {},
                    "episodes": [5, 6],
                },
                {
                    "assetType": "scene",
                    "name": "主场景",
                    "description": {"场景类型": "主场景"},
                    "episodes": [7],
                    "children": [
                        {
                            "assetType": "scene",
                            "name": "衍生场景",
                            "description": {"场景类型": "属于主场景场景的衍生资产"},
                            "episodes": [8],
                        }
                    ],
                },
            ],
            ensure_ascii=False,
        )

        parsed = asset_service_module.parse_extracted_assets(raw)

        assert len(parsed) == 2
        for item in parsed:
            assert item["episode_indices"] == set()
        scene = next(item for item in parsed if item["asset_type"] == "scene")
        assert scene["children"]
        assert scene["children"][0]["episode_indices"] == set()

    @pytest.mark.anyio
    async def test_extract_assets_writes_master_and_derivative(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """首次抽取产生 1 主 + 1 衍生；落库 episodes 等于当前抽取分集，忽略模型集号。"""

        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "asset-extract.db"),
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
        monkeypatch.setattr(asset_service, "load_asset_extraction_prompt", lambda *a, **k: "资产抽取测试提示词")
        monkeypatch.setattr(asset_service, "prepare_rag_context", _stub_prepare_rag_context)

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await user_service.create_user(
                    session,
                    UserCreate(
                        username="asset-owner",
                        nickname="Asset Owner",
                        email="asset-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Asset Project"),
                )
                plan = await script_service.sync_workspace_to_plan(
                    session,
                    project.public_id,
                    owner.public_id,
                    script_content=SCRIPT_CONTENT,
                    title="初版剧本",
                )
                await session.commit()

                _, episodes = await script_service.get_plan_detail(
                    session,
                    project.public_id,
                    owner.public_id,
                    plan.public_id,
                )
                assert episodes
                target_index = episodes[0].episode_index
                episode_public_id = episodes[0].public_id
                wrong_episode = target_index + 99

                raw_output = json.dumps(
                    [
                        {
                            "assetType": "role",
                            "name": "测试角色",
                            "keyword": "关键词",
                            "colors": "",
                            "summary": "概述",
                            "description": {"性别": "男", "状态": "青年"},
                            "details": {},
                            "accessories": {},
                            "episodes": [wrong_episode],
                        }
                    ],
                    ensure_ascii=False,
                )
                gateway = _StubGateway([raw_output])

                result = await asset_service.extract_assets(
                    session,
                    project.public_id,
                    owner.public_id,
                    model_id="test-model",
                    episode_public_ids=[episode_public_id],
                    gateway=gateway,
                )
                await session.commit()

                assert result["created"] == 2
                assets = result["assets"]
                assert len(assets) == 2
                masters = [a for a in assets if a.main_asset]
                deriveds = [a for a in assets if not a.main_asset]
                assert len(masters) == 1
                assert len(deriveds) == 1
                master = masters[0]
                derived = deriveds[0]
                assert master.name == "测试角色"
                assert master.variant_label == ""
                assert derived.name == "测试角色·青年"
                assert derived.variant_label == "青年"
                relation = (
                    await session.exec(
                        select(AssetRelation).where(
                            AssetRelation.source_asset_id == int(derived.id),
                            AssetRelation.target_asset_id == int(master.id),
                            AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
                        )
                    )
                ).first()
                assert relation is not None
                episode_links = list((await session.exec(select(AssetEpisode))).all())
                assert {(link.asset_id, link.episode_index) for link in episode_links} == {
                    (int(master.id), target_index),
                    (int(derived.id), target_index),
                }
                assert wrong_episode not in {link.episode_index for link in episode_links}
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_master_and_derivative_lifecycle(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """主/衍生写入全生命周期：首次 2 条；再现累加主资产剧集；同状态合并衍生、新状态新增衍生。"""

        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "asset-lifecycle.db"),
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
                        username="asset-life-owner",
                        nickname="Asset Life Owner",
                        email="asset-life-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Asset Life Project"),
                )
                multi_episode_content = "\n\n".join(
                    [
                        SCRIPT_CONTENT.replace("EP01", "EP05").replace("1-1", "5-1"),
                        SCRIPT_CONTENT.replace("EP01", "EP08").replace("1-1", "8-1"),
                        SCRIPT_CONTENT.replace("EP01", "EP10").replace("1-1", "10-1"),
                    ]
                )
                await script_service.sync_workspace_to_plan(
                    session,
                    project.public_id,
                    owner.public_id,
                    script_content=multi_episode_content,
                    title="多集剧本",
                )
                await session.commit()
                project_id = int(project.id)

                # 首次（第 5 集，状态“青年”）→ 主 + 衍生各 1 条
                m1, m1_new, d1, d1_new = await asset_service.write_master_and_derivative(
                    session, project_id, owner.public_id, _role_item("张三", "青年"), {5}, supplement="",
                )
                assert m1_new is True and d1_new is True
                assert m1.name == "张三" and m1.main_asset is True and m1.variant_label == ""
                assert d1.name == "张三·青年" and d1.main_asset is False
                master_public_id = m1.public_id
                derived_qingnian_public_id = d1.public_id

                # 再现（第 8 集，状态“受伤”）→ 主资产累加剧集；新增受伤衍生
                m2, m2_new, d2, d2_new = await asset_service.write_master_and_derivative(
                    session, project_id, owner.public_id, _role_item("张三", "受伤"), {8}, supplement="",
                )
                assert m2_new is False and d2_new is True
                assert m2.public_id == master_public_id

                # 再现（第 10 集，状态“青年”）→ 命中已有青年衍生，合并剧集；主资产继续累加
                m3, m3_new, d3, d3_new = await asset_service.write_master_and_derivative(
                    session, project_id, owner.public_id, _role_item("张三", "青年"), {10}, supplement="",
                )
                assert m3_new is False and d3_new is False
                assert d3.public_id == derived_qingnian_public_id

                relations = list((await session.exec(select(AssetRelation))).all())
                assert len(relations) == 2
                assert {relation.relation_type for relation in relations} == {ASSET_RELATION_CHILD_OF}
                relation_pairs = {(relation.source_asset_id, relation.target_asset_id) for relation in relations}
                assert (int(d1.id), int(m1.id)) in relation_pairs
                assert (int(d2.id), int(m1.id)) in relation_pairs

                episode_links = list((await session.exec(select(AssetEpisode))).all())
                assert {(link.asset_id, link.episode_index) for link in episode_links} == {
                    (int(m1.id), 5),
                    (int(d1.id), 5),
                    (int(m1.id), 8),
                    (int(d2.id), 8),
                    (int(m1.id), 10),
                    (int(d1.id), 10),
                }
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()



    @pytest.mark.anyio
    async def test_extract_assets_links_children_to_parent_scene(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """Model children should be linked to their parent asset through AssetRelation."""

        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "asset-children.db"),
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
        monkeypatch.setattr(asset_service, "load_asset_extraction_prompt", lambda *a, **k: "asset extraction test prompt")
        monkeypatch.setattr(asset_service, "prepare_rag_context", _stub_prepare_rag_context)

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await user_service.create_user(
                    session,
                    UserCreate(
                        username="asset-child-owner",
                        nickname="Asset Child Owner",
                        email="asset-child-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Asset Child Project"),
                )
                plan = await script_service.sync_workspace_to_plan(
                    session,
                    project.public_id,
                    owner.public_id,
                    script_content=SCRIPT_CONTENT,
                    title="Initial Script",
                )
                await session.commit()
                _, episodes = await script_service.get_plan_detail(session, project.public_id, owner.public_id, plan.public_id)
                episode = episodes[0]

                raw_output = json.dumps(
                    [
                        {
                            "assetType": "scene",
                            "name": "ParentScene",
                            "summary": "parent scene",
                            "description": {"sceneType": "main"},
                            "details": {},
                            "accessories": {},
                            "children": [
                                {
                                    "assetType": "scene",
                                    "name": "ChildScene",
                                    "summary": "derived child scene",
                                    "description": {"sceneType": "derived from ParentScene"},
                                    "details": {},
                                    "accessories": {},
                                }
                            ],
                        }
                    ],
                    ensure_ascii=False,
                )

                result = await asset_service.extract_assets(
                    session,
                    project.public_id,
                    owner.public_id,
                    model_id="test-model",
                    episode_public_ids=[episode.public_id],
                    gateway=_StubGateway([raw_output]),
                )
                await session.commit()

                parent = next(asset for asset in result["assets"] if asset.name == "ParentScene")
                child = next(asset for asset in result["assets"] if asset.name == "ChildScene")
                relation = (
                    await session.exec(
                        select(AssetRelation).where(
                            AssetRelation.source_asset_id == int(child.id),
                            AssetRelation.target_asset_id == int(parent.id),
                            AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
                        )
                    )
                ).first()
                assert relation is not None
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_existing_asset_merges_missing_fields_without_overwrite(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """Existing same-name assets should fill missing fields without overwriting existing content."""

        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "asset-merge.db"),
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
                        username="asset-merge-owner",
                        nickname="Asset Merge Owner",
                        email="asset-merge-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Asset Merge Project"),
                )
                await script_service.sync_workspace_to_plan(
                    session,
                    project.public_id,
                    owner.public_id,
                    script_content=SCRIPT_CONTENT,
                    title="Initial Script",
                )
                await session.commit()

                first, first_new = await asset_service._upsert_asset(
                    session,
                    int(project.id),
                    owner.public_id,
                    ("role", "MergeRole"),
                    item={
                        "asset_type": "role",
                        "name": "MergeRole",
                        "keyword": "old-keyword",
                        "colors": "",
                        "summary": "old-summary",
                        "description": {"gender": "male", "age": ""},
                        "details": {},
                        "accessories": {},
                        "main_asset": True,
                        "variant_label": "",
                    },
                    incoming_indices={1},
                )
                assert first_new is True
                second, second_new = await asset_service._upsert_asset(
                    session,
                    int(project.id),
                    owner.public_id,
                    ("role", "MergeRole"),
                    item={
                        "asset_type": "role",
                        "name": "MergeRole",
                        "keyword": "new-keyword",
                        "colors": "black",
                        "summary": "new-summary",
                        "description": {"gender": "female", "age": "20", "height": "180"},
                        "details": {"clothes": "black"},
                        "accessories": {},
                        "main_asset": True,
                        "variant_label": "",
                    },
                    incoming_indices={1},
                )
                await session.commit()

                assert second.public_id == first.public_id
                assert second_new is False
                assert second.keyword == "old-keyword"
                assert second.summary == "old-summary"
                assert second.colors == "black"
                description = asset_service._parse_object_field(second.description)
                assert description["gender"] == "male"
                assert description["age"] == "20"
                assert description["height"] == "180"
                assert asset_service._parse_object_field(second.details) == {"clothes": "black"}
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_build_extract_task_items_one_per_episode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """每个分集生成一个子任务，且子任务 payload 的 episodes 范围限定为该单集。"""

        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "asset-task.db"),
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
                        username="asset-task-owner",
                        nickname="Asset Task Owner",
                        email="asset-task-owner@example.com",
                        password="password123",
                        repassword="password123",
                    ),
                )
                project = await project_service.create_project(
                    session,
                    owner.public_id,
                    ProjectCreate(name="Asset Task Project"),
                )
                plan = await script_service.sync_workspace_to_plan(
                    session,
                    project.public_id,
                    owner.public_id,
                    script_content=SCRIPT_CONTENT,
                    title="初版剧本",
                )
                await session.commit()

                _, episodes = await script_service.get_plan_detail(
                    session,
                    project.public_id,
                    owner.public_id,
                    plan.public_id,
                )
                episode_public_ids = [episode.public_id for episode in episodes]

                items = await asset_service.build_extract_task_items(
                    session,
                    project.public_id,
                    owner.public_id,
                    model_id="test-model",
                    episode_public_ids=episode_public_ids,
                )

                assert len(items) == len(episode_public_ids)
                for item, episode_public_id in zip(items, episode_public_ids):
                    assert item.item_key == f"episode:{episode_public_id}"
                    assert item.payload["episode_public_ids"] == [episode_public_id]
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
