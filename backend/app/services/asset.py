from __future__ import annotations

"""剧本资产抽取服务。

从剧本管理中的分集正文抽取人物、势力、道具、场景资产，
并维护资产与分集的关联关系。
"""

import json
import re
from typing import Any

from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.tasks.engine import default_async_task_engine
from app.models.asset import (
    ASSET_RELATION_CHILD_OF,
    ASSET_STATUS_DRAFT,
    ASSET_STATUS_LOCKED,
    ASSET_TYPE_FACTION,
    ASSET_TYPE_PROP,
    ASSET_TYPE_ROLE,
    ASSET_TYPE_SCENE,
    Asset,
    AssetEpisode,
    AssetRelation,
    AssetVersion,
)
from app.models.novel import NovelChapter
from app.models.script import ScriptEpisode, ScriptPlan
from app.schemas.tasks import TaskItemCreate, TaskJobCreate, TaskJobDetail
from app.services import project as project_service
from app.services import script as script_service
from app.services.agent_gateway import ProviderModelGateway, ProviderModelGatewayError
from app.services.prompt_registry import PromptRegistry
from app.services.screenwriting.rag_runtime import prepare_rag_context
from app.utils.time_tools import utc_now


ASSET_EXTRACT_TASK_TYPE = "asset.extract"
ASSET_EXTRACT_QUEUE_NAME = "asset"
ASSET_AUTOCOMPLETE_TASK_TYPE = "asset.autocomplete"
EXTRACTABLE_ASSET_TYPES = {ASSET_TYPE_ROLE, ASSET_TYPE_FACTION, ASSET_TYPE_PROP, ASSET_TYPE_SCENE}
VALID_ASSET_TYPES = EXTRACTABLE_ASSET_TYPES
ASSET_BATCH_OPERATIONS = {"lock", "unlock", "delete"}
VARIANT_STATE_KEYS = ("状态", "形态", "阶段", "年龄阶段", "变体标签", "状态标签")


class AssetServiceError(Exception):
    """资产服务基础异常。

    retryable=False 表示确定性失败（参数/前置状态问题），任务系统不应重试。
    """

    def __init__(self, message: str, *, result: dict[str, Any] | None = None, retryable: bool = True) -> None:
        super().__init__(message)
        self.result = result or {}
        self.retryable = bool(retryable)


class AssetNotFoundError(AssetServiceError):
    """资产不存在或无权访问。"""


def build_asset_gateway() -> ProviderModelGateway:
    """构建文本模型网关，便于测试替换。"""

    return ProviderModelGateway(timeout=settings.model_request_timeout_seconds)


async def _generate_full_text(gateway: Any, *, model_id: str, messages: list[dict[str, str]]) -> str:
    """以流式方式累计模型完整文本输出。"""

    parts: list[str] = []
    async for chunk in gateway.generate_stream(model_id=model_id, messages=messages):
        text = str(chunk or "")
        if text:
            parts.append(text)
    return "".join(parts).strip()


def parse_extracted_assets(raw: str) -> list[dict[str, Any]]:
    """解析模型返回的资产 JSON 数组。"""

    text = (raw or "").strip()
    if not text:
        return []
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("assetType") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        if asset_type not in EXTRACTABLE_ASSET_TYPES or not name:
            continue
        key = (asset_type, name)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "asset_type": asset_type,
                "name": name[:200],
                "keyword": str(item.get("keyword") or "").strip()[:500],
                "colors": str(item.get("colors") or "").strip()[:1000],
                "summary": str(item.get("summary") or "").strip(),
                "description": _coerce_mapping(item.get("description")),
                "details": _coerce_mapping(item.get("details")),
                "accessories": _coerce_mapping(item.get("accessories")),
                "episode_indices": set(),  # 分集归属由程序按当前抽取分集写入，不取模型返回
                "children": _normalize_asset_children(item.get("children")),
                "variant_label": "",
            }
        )
    return normalized


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """从模型输出中尽力解析出单个 JSON 对象；失败返回 None。"""

    text = (raw or "").strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _coerce_str_map(value: Any) -> dict[str, str]:
    """把对象字段规整为 dict[str, str]：值非字符串则序列化为文本，丢弃空键空值。"""

    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, raw_value in value.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        if isinstance(raw_value, str):
            text = raw_value.strip()
        elif isinstance(raw_value, (dict, list)):
            text = json.dumps(raw_value, ensure_ascii=False)
        else:
            text = str(raw_value or "").strip()
        if text:
            result[normalized_key] = text
    return result


def parse_autocomplete_result(raw: str) -> "AssetAutocompleteResult | None":
    """解析并校验补全输出为 AssetAutocompleteResult；无法解析或全空返回 None。"""

    from app.schemas.asset import AssetAutocompleteResult

    data = _parse_json_object(raw)
    if data is None:
        return None
    result = AssetAutocompleteResult(
        summary=str(data.get("summary") or "").strip(),
        keyword=str(data.get("keyword") or "").strip(),
        colors=str(data.get("colors") or "").strip(),
        description=_coerce_str_map(data.get("description")),
        details=_coerce_str_map(data.get("details")),
        accessories=_coerce_str_map(data.get("accessories")),
    )
    return None if result.is_empty() else result


def _normalize_asset_children(value: Any) -> list[dict[str, Any]]:
    """标准化模型返回的 children 子资产数组。"""

    if not isinstance(value, list):
        return []
    children: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("assetType") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        if asset_type not in EXTRACTABLE_ASSET_TYPES or not name:
            continue
        key = (asset_type, name)
        if key in seen:
            continue
        seen.add(key)
        children.append(
            {
                "asset_type": asset_type,
                "name": name[:200],
                "keyword": str(item.get("keyword") or "").strip()[:500],
                "colors": str(item.get("colors") or "").strip()[:1000],
                "summary": str(item.get("summary") or "").strip(),
                "description": _coerce_mapping(item.get("description")),
                "details": _coerce_mapping(item.get("details")),
                "accessories": _coerce_mapping(item.get("accessories")),
                "episode_indices": set(),  # 分集归属由程序按当前抽取分集写入，不取模型返回
                "children": [],
                "variant_label": "",
            }
        )
    return children


def _coerce_mapping(value: Any) -> dict[str, Any]:
    """把对象字段标准化为字典。"""

    if isinstance(value, dict):
        return value
    return {}


def _dump_object_field(mapping: dict[str, Any]) -> str:
    """把对象字段序列化为数据库存储用 JSON 字符串。"""

    if not mapping:
        return "{}"
    return json.dumps(mapping, ensure_ascii=False)


def _render_object_text(mapping: dict[str, Any]) -> str:
    """把对象字段渲染为可读文本。"""

    parts: list[str] = []
    for key, value in mapping.items():
        text = str(value or "").strip()
        if text:
            parts.append(f"{key}：{text}")
    return "；".join(parts)


async def extract_assets(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    episode_public_ids: list[str] | None = None,
    gateway: Any | None = None,
) -> dict[str, Any]:
    """从剧本分集正文抽取资产并落库。"""

    model_id = model_id.strip()
    if not model_id:
        raise AssetServiceError("缺少抽取所用文本模型 ID")

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    script_context, target_indices = await build_script_context(
        session,
        project_public_id,
        user_public_id,
        episode_public_ids,
    )
    messages = build_extraction_messages(script_context)
    prompt_trace = _model_prompt_trace(model_id=model_id, messages=messages)
    resolved_gateway = gateway or build_asset_gateway()
    try:
        raw = await _generate_full_text(resolved_gateway, model_id=model_id, messages=messages)
    except ProviderModelGatewayError as exc:
        raise AssetServiceError(f"资产抽取失败：{exc}") from exc
    prompt_trace["raw_output"] = raw
    prompt_trace["output_text"] = raw
    parsed = parse_extracted_assets(raw)
    if not parsed:
        raise AssetServiceError(
            "未能从剧本中抽取到有效资产，请检查剧本内容或模型输出",
            result=prompt_trace,
        )

    created = 0
    updated = 0
    results: list[Asset] = []
    enrichments: list[dict[str, Any]] = []
    target_set = set(target_indices)

    work_items: list[dict[str, Any]] = []
    for item in parsed:
        work_items.append({"item": item, "parent_item": None})
        for child in item.get("children") or []:
            work_items.append({"item": child, "parent_item": item})

    enriched_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for record in work_items:
        item = record["item"]
        enrichment = await enrich_asset_description(
            session,
            project,
            user_public_id,
            item,
            target_set,
            model_id=model_id,
            gateway=resolved_gateway,
        )
        enrichments.append(enrichment)
        enriched_records.append((record, enrichment))

    await _lock_asset_keys(
        session,
        int(project.id),
        user_public_id,
        [key for record, _ in enriched_records for key in _asset_keys_for_item(record["item"])],
    )

    masters_by_item_id: dict[int, Asset] = {}
    for record, enrichment in enriched_records:
        item = record["item"]
        master, master_new, derived, derived_new = await write_master_and_derivative(
            session,
            int(project.id),
            user_public_id,
            item,
            target_set,
            supplement=str(enrichment.get("supplement", "") or ""),
        )
        masters_by_item_id[id(item)] = master
        parent_item = record.get("parent_item")
        parent_asset = masters_by_item_id.get(id(parent_item)) if parent_item is not None else None
        if parent_asset is not None:
            await _upsert_child_relation(
                session,
                int(project.id),
                user_public_id,
                parent=parent_asset,
                child=master,
                label=str(master.variant_label or _infer_asset_state(item) or item.get("name") or "")[:120],
            )
        created += int(master_new)
        updated += int(not master_new)
        results.append(master)
        if derived is not None:
            created += int(derived_new)
            updated += int(not derived_new)
            results.append(derived)

    return {"created": created, "updated": updated, "assets": results, "asset_enrichment": enrichments, **prompt_trace}


async def autocomplete_asset(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    model_id: str,
    gateway: Any | None = None,
) -> dict[str, Any]:
    """对单个资产做结构化描述补全：校验 + 失败一次重试 + 合并落库。"""

    model_id = model_id.strip()
    if not model_id:
        raise AssetServiceError("缺少补全所用文本模型 ID")

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    asset = await load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    if asset.status == ASSET_STATUS_LOCKED:
        raise AssetServiceError("资产已锁定，请先解锁再补全")

    episode_items = await get_asset_episode_items(session, project_public_id, user_public_id, asset)
    episode_public_ids = [item["episode_id"] for item in episode_items]
    if episode_public_ids:
        script_context, _ = await build_script_context(
            session, project_public_id, user_public_id, episode_public_ids
        )
    else:
        script_context = ""

    base_kwargs = dict(
        asset_type=asset.asset_type,
        name=asset.name,
        current_summary=asset.summary or "",
        current_keyword=asset.keyword or "",
        current_colors=asset.colors or "",
        current_description=_parse_object_field(asset.description),
        current_details=_parse_object_field(asset.details),
        current_accessories=_parse_object_field(asset.accessories),
        script_context=script_context,
    )

    resolved_gateway = gateway or build_asset_gateway()
    last_raw = ""
    result: "AssetAutocompleteResult | None" = None
    for attempt in range(2):  # 首次 + 失败一次重试
        feedback = "" if attempt == 0 else "上次输出不是合法、含有效字段的 JSON 对象，请只输出符合要求的 JSON 对象。"
        messages = build_autocomplete_messages(**base_kwargs, retry_feedback=feedback)
        try:
            last_raw = await _generate_full_text(resolved_gateway, model_id=model_id, messages=messages)
        except ProviderModelGatewayError as exc:
            raise AssetServiceError(f"资产描述补全失败：{exc}") from exc
        result = parse_autocomplete_result(last_raw)
        if result is not None:
            break

    prompt_trace = _model_prompt_trace(model_id=model_id, messages=messages)
    prompt_trace["raw_output"] = last_raw
    prompt_trace["output_text"] = last_raw

    if result is None:
        raise AssetServiceError(
            "模型未返回可用的补全内容，请重试或更换模型",
            result={**prompt_trace, "asset_public_id": asset_public_id},
        )

    merge_asset_missing_fields(
        asset,
        {
            "keyword": result.keyword,
            "colors": result.colors,
            "summary": result.summary,
            "description": result.description,
            "details": result.details,
            "accessories": result.accessories,
        },
    )
    asset.updated_at = utc_now()
    session.add(asset)
    await session.flush()
    return {"asset": asset, "asset_public_id": asset.public_id, **prompt_trace}


async def build_autocomplete_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    asset_public_ids: list[str],
) -> list[TaskItemCreate]:
    """按资产构造补全任务子项，逐个校验资产存在。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    items: list[TaskItemCreate] = []
    for asset_public_id in _dedupe_public_ids(asset_public_ids):
        asset = await load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
        items.append(
            TaskItemCreate(
                item_type=ASSET_AUTOCOMPLETE_TASK_TYPE,
                item_key=f"asset:{asset_public_id}",
                payload={
                    "project_public_id": project_public_id,
                    "current_user_public_id": user_public_id,
                    "model_id": model_id,
                    "asset_public_id": asset_public_id,
                    "asset_name": asset.name,
                },
            )
        )
    return items


async def submit_autocomplete_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    asset_public_ids: list[str],
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交资产描述补全异步任务；一个 job 可含多个资产子项。"""

    model_id = model_id.strip()
    if not model_id:
        raise AssetServiceError("缺少补全所用文本模型 ID")
    await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    items = await build_autocomplete_task_items(
        session, project_public_id, user_public_id, model_id=model_id, asset_public_ids=asset_public_ids
    )
    if not items:
        raise AssetServiceError("没有可用于描述补全的资产")

    job_name = "资产描述补全" if len(items) == 1 else f"资产描述批量补全：{len(items)} 个资产"
    resolved_engine = engine or default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=ASSET_AUTOCOMPLETE_TASK_TYPE,
            queue_name=ASSET_EXTRACT_QUEUE_NAME,
            name=job_name,
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": model_id,
                "asset_count": len(items),
            },
            items=items,
        ),
    )


async def submit_extract_assets_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    episode_public_ids: list[str] | None = None,
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交剧本资产抽取异步任务。"""

    model_id = model_id.strip()
    if not model_id:
        raise AssetServiceError("缺少抽取所用文本模型 ID")

    await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    items = await build_extract_task_items(
        session,
        project_public_id,
        user_public_id,
        model_id=model_id,
        episode_public_ids=episode_public_ids,
    )
    if not items:
        raise AssetServiceError("没有可用于资产抽取的分集")

    normalized_episode_ids = _dedupe_public_ids(episode_public_ids)
    resolved_engine = engine or default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=ASSET_EXTRACT_TASK_TYPE,
            queue_name=ASSET_EXTRACT_QUEUE_NAME,
            name="剧本资产抽取",
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": model_id,
                "episode_public_ids": normalized_episode_ids,
            },
            items=items,
        ),
    )


async def build_extract_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    episode_public_ids: list[str] | None = None,
) -> list[TaskItemCreate]:
    """按抽取范围构造资产抽取任务子项。"""

    normalized_episode_ids = _dedupe_public_ids(episode_public_ids)
    if not normalized_episode_ids:
        plans = await script_service.list_plans(session, project_public_id, user_public_id)
        if not plans:
            return []
        plan = plans[0]
        _, episodes = await script_service.get_plan_detail(
            session,
            project_public_id,
            user_public_id,
            plan.public_id,
        )
        normalized_episode_ids = [
            str(episode.public_id).strip()
            for episode in episodes
            if str(episode.public_id).strip()
        ]
        if not normalized_episode_ids:
            return []

    items: list[TaskItemCreate] = []
    for episode_public_id in normalized_episode_ids:
        await script_service.get_episode_or_raise(
            session,
            project_public_id,
            user_public_id,
            episode_public_id,
        )
        items.append(
            TaskItemCreate(
                item_type=ASSET_EXTRACT_TASK_TYPE,
                item_key=f"episode:{episode_public_id}",
                payload={
                    "project_public_id": project_public_id,
                    "current_user_public_id": user_public_id,
                    "model_id": model_id,
                    "episode_public_ids": [episode_public_id],
                },
            )
        )
    return items


async def list_assets(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_type: str = "",
) -> list[Asset]:
    """列出当前项目的资产，可按类型过滤。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    statement = select(Asset).where(
        Asset.project_id == project.id,
        Asset.user_public_id == user_public_id,
        Asset.disabled_at.is_(None),
    )
    normalized_type = asset_type.strip().lower()
    if normalized_type:
        if normalized_type not in VALID_ASSET_TYPES:
            raise AssetServiceError(f"不支持的资产类型：{asset_type}")
        statement = statement.where(Asset.asset_type == normalized_type)
    statement = statement.order_by(Asset.asset_type, Asset.name)
    return list((await session.exec(statement)).all())


async def get_asset(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    asset_public_id: str,
) -> Asset:
    """读取单个资产。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    return await load_asset_or_raise(session, project.id, user_public_id, asset_public_id)


async def get_asset_episode_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    asset: Asset,
) -> list[dict[str, str]]:
    """查询资产通过 AssetEpisode 关联的分集，返回展示用的分集 ID 与名称。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    if asset.id is None:
        return []
    statement = (
        select(ScriptEpisode, ScriptPlan)
        .join(AssetEpisode, AssetEpisode.episode_id == ScriptEpisode.id)
        .join(ScriptPlan, ScriptEpisode.plan_id == ScriptPlan.id)
        .where(
            ScriptPlan.project_id == project.id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
            AssetEpisode.asset_id == int(asset.id),
            AssetEpisode.project_id == project.id,
            AssetEpisode.user_public_id == user_public_id,
            ScriptEpisode.disabled_at.is_(None),
        )
        .order_by(ScriptEpisode.episode_index, ScriptEpisode.id)
    )
    rows = list((await session.exec(statement)).all())
    return [
        {
            "episode_id": str(episode.public_id),
            "episode_name": f"第 {episode.episode_index} 集：{episode.title or '未命名分集'}",
        }
        for episode, _ in rows
    ]


async def set_asset_lock(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    asset_public_id: str,
    *,
    locked: bool,
) -> Asset:
    """锁定或解锁资产。"""

    asset = await get_asset(session, project_public_id, user_public_id, asset_public_id)
    asset.status = ASSET_STATUS_LOCKED if locked else ASSET_STATUS_DRAFT
    asset.updated_at = utc_now()
    session.add(asset)
    await session.flush()
    return asset


async def set_episode_assets(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_id: str,
    asset_public_ids: list[str],
) -> dict[str, Any]:
    """覆盖设置指定分集关联的资产列表。"""

    episode, plan = await script_service.get_episode_or_raise(
        session,
        project_public_id,
        user_public_id,
        episode_public_id,
    )
    all_assets = await list_assets(session, project_public_id, user_public_id)
    assets_by_public_id = {asset.public_id: asset for asset in all_assets}
    selected_assets = [assets_by_public_id[public_id] for public_id in dict.fromkeys(asset_public_ids) if public_id in assets_by_public_id]
    selected_asset_ids = {int(asset.id) for asset in selected_assets if asset.id is not None}
    existing_links = list(
        (
            await session.exec(
                select(AssetEpisode).where(
                    AssetEpisode.project_id == int(plan.project_id),
                    AssetEpisode.user_public_id == user_public_id,
                    AssetEpisode.episode_id == int(episode.id),
                )
            )
        ).all()
    )
    existing_asset_ids = {int(link.asset_id) for link in existing_links}
    affected = 0
    for asset in all_assets:
        if asset.id is None:
            continue
        asset_id = int(asset.id)
        has_episode = asset_id in existing_asset_ids
        should_have = asset_id in selected_asset_ids
        if should_have and not has_episode:
            asset.updated_at = utc_now()
            session.add(asset)
            await _sync_asset_episode_links(session, int(plan.project_id), user_public_id, asset, {episode.episode_index})
            affected += 1
        elif has_episode and not should_have:
            asset.updated_at = utc_now()
            session.add(asset)
            await session.exec(
                delete(AssetEpisode).where(
                    AssetEpisode.asset_id == asset_id,
                    AssetEpisode.episode_id == int(episode.id),
                )
            )
            affected += 1
    await session.flush()
    return {"affected": affected, "assets": selected_assets}


async def build_script_context(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_ids: list[str] | None = None,
) -> tuple[str, list[int]]:
    """构建给模型使用的剧本上下文。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    if episode_public_ids:
        episodes = []
        for episode_public_id in dict.fromkeys(episode_public_ids):
            episode, _ = await script_service.get_episode_or_raise(
                session,
                project_public_id,
                user_public_id,
                episode_public_id,
            )
            episodes.append(episode)
        episodes.sort(key=lambda item: item.episode_index)
        title = f"选定 {len(episodes)} 集"
    else:
        plans = await script_service.list_plans(session, project_public_id, user_public_id)
        if not plans:
            raise AssetServiceError("请先在剧本管理中同步或新建剧本，再抽取资产")
        plan = plans[0]
        _, episodes = await script_service.get_plan_detail(
            session,
            project_public_id,
            user_public_id,
            plan.public_id,
        )
        title = plan.title or "未命名剧本"

    if not episodes:
        raise AssetServiceError("当前剧本没有可用于资产抽取的分集内容")

    episode_indices = [episode.episode_index for episode in episodes]
    bound_chapters = await _load_bound_novel_chapters(session, project.id, episodes)
    lines = [f"剧名：{title}", ""]
    for episode in episodes:
        summary = (episode.summary or "").strip() or "（无梗概）"
        body = (episode.body or "").strip() or "（无正文）"
        lines.extend(
            [
                f"## 第 {episode.episode_index} 集：{episode.title or '未命名分集'}",
                f"梗概：{summary}",
                "正文：",
                body,
            ]
        )
        chapters = bound_chapters.get(episode.episode_index) or []
        if chapters:
            lines.append("绑定小说：")
            for chapter in chapters:
                lines.append(format_bound_novel_chapter(chapter))
        lines.append("")
    return "\n".join(lines).strip(), episode_indices


async def _load_bound_novel_chapters(
    session: AsyncSession,
    project_id: int,
    episodes: list[Any],
) -> dict[int, list[NovelChapter]]:
    """读取分集绑定的小说章节。"""

    chapter_indexes_by_episode: dict[int, list[int]] = {}
    unique_indexes: set[int] = set()
    for episode in episodes:
        indexes = parse_chapter_ids(getattr(episode, "novel_chapter_ids", ""))
        if not indexes:
            continue
        chapter_indexes_by_episode[episode.episode_index] = indexes
        unique_indexes.update(indexes)

    if not unique_indexes:
        return {}

    statement = (
        select(NovelChapter)
        .where(
            NovelChapter.project_id == project_id,
            NovelChapter.chapter_index.in_(unique_indexes),
            NovelChapter.disabled_at.is_(None),
        )
        .order_by(NovelChapter.chapter_index, NovelChapter.id)
    )
    rows = list((await session.exec(statement)).all())
    chapters_by_index: dict[int, list[NovelChapter]] = {}
    for chapter in rows:
        chapters_by_index.setdefault(chapter.chapter_index, []).append(chapter)

    result: dict[int, list[NovelChapter]] = {}
    for episode_index, indexes in chapter_indexes_by_episode.items():
        merged: list[NovelChapter] = []
        for index in indexes:
            merged.extend(chapters_by_index.get(index, []))
        if merged:
            result[episode_index] = merged
    return result


def parse_chapter_ids(value: str) -> list[int]:
    """解析逗号分隔的小说章节号。"""

    result: list[int] = []
    seen: set[int] = set()
    for item in (value or "").split(","):
        try:
            number = int(item.strip())
        except ValueError:
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        result.append(number)
    return result


def format_bound_novel_chapter(chapter: NovelChapter) -> str:
    """格式化绑定小说章节。"""

    title = (chapter.title or "").strip() or f"第 {chapter.chapter_index} 章"
    content = (chapter.content or "").strip() or "（无正文）"
    return f"### 小说第 {chapter.chapter_index} 章：{title}\n{content}"


def build_extraction_messages(script_context: str) -> list[dict[str, str]]:
    """构建资产抽取提示词。"""

    system = load_asset_extraction_prompt()
    user = f"## 剧本上下文\n{script_context}\n\n请抽取可用于制作的资产清单。"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def enrich_asset_description(
    session: AsyncSession,
    project: Any,
    user_public_id: str,
    item: dict[str, Any],
    episode_indices: set[int],
    *,
    model_id: str,
    gateway: Any,
) -> dict[str, Any]:
    """用项目 RAG 检索正文细节补全资产描述。"""

    description_text = _render_object_text(_coerce_mapping(item.get("description")))
    asset_type = str(item.get("asset_type") or "").strip()
    name = str(item.get("name") or "").strip()
    if not name:
        return {"name": name, "asset_type": asset_type, "supplement": "", "status": "skipped"}

    query = build_asset_rag_query(item, episode_indices)
    try:
        rag_preparation = await prepare_rag_context(
            session,
            project,
            project.public_id,
            user_public_id,
            query,
        )
    except Exception as exc:
        return {
            "name": name,
            "asset_type": asset_type,
            "supplement": "",
            "status": "rag_failed",
            "error": str(exc),
        }

    rag_context = rag_preparation.context
    rag_text = str(getattr(rag_context, "text", "") or "").strip()
    rag_runtime = dict(getattr(rag_context, "runtime", {}) or {})
    if not rag_text:
        return {
            "name": name,
            "asset_type": asset_type,
            "supplement": "",
            "status": "no_rag_context",
            "rag_runtime": rag_runtime,
        }

    messages = build_asset_enrichment_messages(
        asset_type=asset_type,
        name=name,
        description=description_text,
        episode_indices=episode_indices,
        rag_context=rag_text,
    )
    try:
        enhanced = await _generate_full_text(gateway, model_id=model_id, messages=messages)
    except Exception as exc:
        return {
            "name": name,
            "asset_type": asset_type,
            "supplement": "",
            "status": "llm_failed",
            "error": str(exc),
            "rag_runtime": rag_runtime,
            "llm_called": True,
        }

    return {
        "name": name,
        "asset_type": asset_type,
        "supplement": enhanced,
        "status": "enriched" if enhanced else "empty_enrichment",
        "rag_runtime": rag_runtime,
        "llm_called": True,
    }


def build_asset_rag_query(item: dict[str, Any], episode_indices: set[int]) -> str:
    """为资产详情补全构造 RAG 查询文本。"""

    name = str(item.get("name") or "").strip()
    asset_type = str(item.get("asset_type") or "").strip()
    description = _render_object_text(_coerce_mapping(item.get("description")))
    episodes = "、".join(str(index) for index in sorted(episode_indices)) or "未知"
    return (
        f"资产名称：{name}\n"
        f"资产类型：{asset_type}\n"
        f"关联集数：{episodes}\n"
        f"当前描述：{description}\n"
        "请检索小说正文中与该资产相关的外观、尺寸、位置、关系、用途、势力或衍生场景细节。"
    )


def build_asset_enrichment_messages(
    *,
    asset_type: str,
    name: str,
    description: str,
    episode_indices: set[int],
    rag_context: str,
) -> list[dict[str, str]]:
    """构建资产细节补全提示词。"""

    system = (
        "你是短剧制作资产设定整理助手，只根据提供的 RAG 检索片段补全单个资产的制作细节。"
        "只输出补全后的细节文本，不要输出 JSON、Markdown 或解释。"
        "不得编造检索片段中没有的信息；缺失信息保留原描述或写“未知”。"
        "使用短句和分号分隔，保留资产类型要求中的关键描述维度。"
    )
    episodes = "、".join(str(index) for index in sorted(episode_indices)) or "未知"
    user = (
        f"资产类型：{asset_type}\n"
        f"资产名称：{name}\n"
        f"关联集数：{episodes}\n"
        f"原描述：{description}\n\n"
        "RAG 检索片段：\n"
        f"{rag_context}\n\n"
        "请输出补全后的细节文本。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def write_master_and_derivative(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    item: dict[str, Any],
    incoming_indices: set[int],
    *,
    supplement: str,
) -> tuple[Asset, bool, Asset | None, bool]:
    """写入资产的主记录与衍生记录。

    无明确状态：仅写主资产。
    有明确状态：主资产累加稳定字段；按状态名写入或合并衍生资产。
    返回（主资产, 主是否新建, 衍生资产, 衍生是否新建）。
    """

    asset_type = str(item["asset_type"])
    master_name = str(item["name"]).strip()
    state = _infer_asset_state(item)
    enriched = _with_supplement(item, supplement)

    master_item = _build_master_asset_item(enriched, master_name, state)
    master, master_new = await _upsert_asset(
        session,
        project_id,
        user_public_id,
        (asset_type, master_name),
        item=master_item,
        incoming_indices=incoming_indices,
    )

    if not state.strip():
        return master, master_new, None, False

    derived_name = _derive_variant_asset_name(master_name, state)
    derived_item = _build_derivative_asset_item(enriched, derived_name, state)
    derived, derived_new = await _upsert_asset(
        session,
        project_id,
        user_public_id,
        (asset_type, derived_name),
        item=derived_item,
        incoming_indices=incoming_indices,
    )
    await _upsert_child_relation(
        session,
        project_id,
        user_public_id,
        parent=master,
        child=derived,
        label=state,
    )
    return master, master_new, derived, derived_new


def _asset_keys_for_item(item: dict[str, Any]) -> list[tuple[str, str]]:
    """返回单个抽取项将写入的主资产与衍生资产唯一键。"""

    asset_type = str(item["asset_type"])
    master_name = str(item["name"]).strip()
    if not master_name:
        return []
    keys = [(asset_type, master_name)]
    state = _infer_asset_state(item)
    if state.strip():
        keys.append((asset_type, _derive_variant_asset_name(master_name, state)))
    return keys


async def _lock_asset_keys(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    keys: list[tuple[str, str]],
) -> None:
    """按稳定顺序预取本事务内全部资产锁，避免并发任务交叉等待。"""

    for key in sorted(set(keys), key=lambda item: (item[0], item[1])):
        await _lock_asset_key(session, project_id, user_public_id, key)


async def _upsert_child_relation(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    *,
    parent: Asset,
    child: Asset,
    label: str,
) -> None:
    """写入或更新子资产指向父资产的 child_of 关系，已存在则保持幂等。"""

    if parent.id is None or child.id is None:
        return
    statement = select(AssetRelation).where(
        AssetRelation.source_asset_id == int(child.id),
        AssetRelation.target_asset_id == int(parent.id),
        AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
    )
    relation = (await session.exec(statement)).first()
    relation_label = str(label or child.variant_label or "").strip()[:120]
    if relation is not None:
        if relation_label and relation.relation_label != relation_label:
            relation.relation_label = relation_label
            session.add(relation)
            await session.flush()
        return

    relation = AssetRelation(
        source_asset_id=int(child.id),
        target_asset_id=int(parent.id),
        relation_type=ASSET_RELATION_CHILD_OF,
        relation_label=relation_label,
    )
    session.add(relation)
    await session.flush()


async def _upsert_asset(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    key: tuple[str, str],
    *,
    item: dict[str, Any],
    incoming_indices: set[int],
) -> tuple[Asset, bool]:
    """按 (asset_type, name) 唯一键写入资产：已存在则累加剧集，不存在则新建。返回（资产, 是否新建）。"""

    await _lock_asset_key(session, project_id, user_public_id, key)
    asset = await load_existing_asset_by_key(session, project_id, user_public_id, key)
    if asset is not None:
        await _accumulate_episodes(session, asset, item, incoming_indices)
        await _sync_asset_episode_links(session, project_id, user_public_id, asset, incoming_indices)
        return asset, False

    asset_type, name = key
    asset = Asset(
        project_id=project_id,
        user_public_id=user_public_id,
        asset_type=asset_type,
        name=name,
        main_asset=bool(item.get("main_asset")),
        variant_label=str(item.get("variant_label") or "")[:100],
    )
    apply_asset_record(asset, item, incoming_indices)
    try:
        async with session.begin_nested():
            session.add(asset)
            await session.flush()
    except IntegrityError:
        existing = await load_existing_asset_by_key(session, project_id, user_public_id, key)
        if existing is None:
            raise
        await _accumulate_episodes(session, existing, item, incoming_indices)
        await _sync_asset_episode_links(session, project_id, user_public_id, existing, incoming_indices)
        return existing, False
    await _sync_asset_episode_links(session, project_id, user_public_id, asset, incoming_indices)
    return asset, True


async def _lock_asset_key(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    key: tuple[str, str],
) -> None:
    """PostgreSQL 下按资产唯一键加事务级锁，避免并发插入同名资产死锁。"""

    bind = session.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect_name != "postgresql":
        return
    asset_type, name = key
    lock_key = f"asset:{project_id}:{user_public_id}:{asset_type}:{name}"
    await session.exec(
        text("select pg_advisory_xact_lock(hashtextextended(:lock_key, 0))").bindparams(lock_key=lock_key)
    )


async def _accumulate_episodes(
    session: AsyncSession,
    asset: Asset,
    item: dict[str, Any],
    incoming_indices: set[int],
) -> None:
    """已存在资产：累加剧集并确保 parent 指向主资产，不覆盖其它字段；锁定资产跳过。"""

    if asset.status == ASSET_STATUS_LOCKED:
        return
    merge_asset_missing_fields(asset, item)
    if "main_asset" in item:
        asset.main_asset = bool(item.get("main_asset"))
    if not str(asset.variant_label or "").strip():
        asset.variant_label = str(item.get("variant_label") or "")[:100]
    asset.updated_at = utc_now()
    session.add(asset)
    await session.flush()


async def _sync_asset_episode_links(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    asset: Asset,
    episode_indices: set[int],
) -> None:
    """同步资产与分集的关联记录，按集号补充缺失关联，已存在则跳过。"""

    if asset.id is None or not episode_indices:
        return
    statement = (
        select(ScriptEpisode)
        .join(ScriptPlan, ScriptEpisode.plan_id == ScriptPlan.id)
        .where(
            ScriptPlan.project_id == project_id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
            ScriptEpisode.episode_index.in_(episode_indices),
            ScriptEpisode.disabled_at.is_(None),
        )
    )
    episodes = list((await session.exec(statement)).all())
    for episode in episodes:
        existing_statement = select(AssetEpisode).where(
            AssetEpisode.asset_id == int(asset.id),
            AssetEpisode.episode_id == int(episode.id),
        )
        if (await session.exec(existing_statement)).first() is not None:
            continue
        session.add(
            AssetEpisode(
                project_id=project_id,
                user_public_id=user_public_id,
                asset_id=int(asset.id),
                episode_id=int(episode.id),
                episode_index=int(episode.episode_index),
            )
        )
    await session.flush()


def _infer_asset_state(item: dict[str, Any]) -> str:
    """从 description 推断资产的状态/形态名；无明确状态返回空串。"""

    description = _coerce_mapping(item.get("description"))
    for key in VARIANT_STATE_KEYS:
        text = str(description.get(key) or "").strip()
        if text:
            return _normalize_variant_label(text)
    scene_type = str(description.get("场景类型") or "").strip()
    if "衍生" in scene_type:
        return "衍生资产"
    return ""


def _normalize_variant_label(value: str) -> str:
    """把状态描述压缩为短标签，避免长文进入 variant_label。"""

    text = re.split(r"[，,；;。.\n\r]", str(value or "").strip(), maxsplit=1)[0].strip()
    if len(text) <= 20:
        return text[:100]
    return text[:20]


def _derive_variant_asset_name(master_name: str, state: str) -> str:
    """构造衍生资产名：主名·状态名；无状态名时用固定后缀，避免与主资产撞名。"""

    master_name = (master_name or "").strip()
    state = (state or "").strip()
    suffix = state if state and state != master_name else "衍生"
    return f"{master_name}·{suffix}"[:200]


def _with_supplement(item: dict[str, Any], supplement: str) -> dict[str, Any]:
    """把 RAG 补全文本并入 description 的“细节补全”键。"""

    result = dict(item)
    description = dict(_coerce_mapping(item.get("description")))
    supplement_text = str(supplement or "").strip()
    if supplement_text:
        description["细节补全"] = supplement_text
    result["description"] = description
    return result


def _build_master_asset_item(item: dict[str, Any], master_name: str, state: str) -> dict[str, Any]:
    """构造主资产写入项，仅移除明确的衍生状态字段。"""

    description = _coerce_mapping(item.get("description"))
    details = _coerce_mapping(item.get("details"))
    accessories = _coerce_mapping(item.get("accessories"))
    if state.strip():
        description, _ = _split_explicit_variant_mapping(description, state)
        details, _ = _split_explicit_variant_mapping(details, state)
        accessories, _ = _split_explicit_variant_mapping(accessories, state)
    return {
        **item,
        "name": master_name,
        "description": description,
        "details": details,
        "accessories": accessories,
        "main_asset": True,
        "variant_label": "",
    }


def _build_derivative_asset_item(item: dict[str, Any], derived_name: str, state: str) -> dict[str, Any]:
    """构造衍生资产写入项，只写入明确结构化的状态差异字段。"""

    _, description = _split_explicit_variant_mapping(_coerce_mapping(item.get("description")), state)
    _, details = _split_explicit_variant_mapping(_coerce_mapping(item.get("details")), state)
    _, accessories = _split_explicit_variant_mapping(_coerce_mapping(item.get("accessories")), state)
    state_text = state.strip()
    if not description and state_text:
        description["状态"] = state_text
    return {
        **item,
        "name": derived_name,
        "keyword": "",
        "colors": "",
        "summary": f"{derived_name}，记录相对主资产的{state_text}状态差异。",
        "description": description,
        "details": details,
        "accessories": accessories,
        "main_asset": False,
        "variant_label": state,
    }


def _split_explicit_variant_mapping(mapping: dict[str, Any], state: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """按结构化状态字段拆分主资产字段和衍生字段。"""

    stable: dict[str, Any] = {}
    variant: dict[str, Any] = {}
    for key, value in mapping.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        target = variant if _is_explicit_variant_key(normalized_key, state) else stable
        target[normalized_key] = value
    return stable, variant


def _is_explicit_variant_key(key: str, state: str) -> bool:
    """判断字段名是否明确标识当前衍生状态。"""

    normalized_key = str(key or "").strip()
    normalized_state = str(state or "").strip()
    if normalized_key in VARIANT_STATE_KEYS:
        return True
    if normalized_key == "场景类型" and normalized_state == "衍生资产":
        return True
    return bool(normalized_state and normalized_state in normalized_key)


def merge_asset_missing_fields(asset: Asset, item: dict[str, Any]) -> None:
    """把抽取项字段合并进已有资产，仅补充缺失字段，不覆盖已有内容。"""

    asset.keyword = _prefer_existing_text(asset.keyword, item.get("keyword"))
    asset.colors = _prefer_existing_text(asset.colors, item.get("colors"))
    asset.summary = _prefer_existing_text(asset.summary, item.get("summary"))
    asset.description = _dump_object_field(
        _merge_object_field(_parse_object_field(asset.description), _coerce_mapping(item.get("description")))
    )
    asset.details = _dump_object_field(
        _merge_object_field(_parse_object_field(asset.details), _coerce_mapping(item.get("details")))
    )
    asset.accessories = _dump_object_field(
        _merge_object_field(_parse_object_field(asset.accessories), _coerce_mapping(item.get("accessories")))
    )


def _prefer_existing_text(existing: Any, incoming: Any) -> str:
    existing_text = str(existing or "").strip()
    if existing_text:
        return str(existing or "")
    return str(incoming or "")


def _parse_object_field(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _merge_object_field(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        existing_value = merged.get(normalized_key)
        if isinstance(existing_value, dict) and isinstance(value, dict):
            nested = _merge_object_field(existing_value, value)
            if nested:
                merged[normalized_key] = nested
            continue
        if str(existing_value or "").strip():
            continue
        if isinstance(value, dict):
            if value:
                merged[normalized_key] = value
            continue
        if str(value or "").strip():
            merged[normalized_key] = value
    return merged

def apply_asset_record(asset: Asset, item: dict[str, Any], incoming_indices: set[int]) -> None:
    """把抽取项的字段写入资产记录。"""

    asset.keyword = str(item.get("keyword") or "")
    asset.colors = str(item.get("colors") or "")
    asset.summary = str(item.get("summary") or "")
    asset.description = _dump_object_field(_coerce_mapping(item.get("description")))
    asset.details = _dump_object_field(_coerce_mapping(item.get("details")))
    asset.accessories = _dump_object_field(_coerce_mapping(item.get("accessories")))
    asset.main_asset = bool(item.get("main_asset"))
    asset.variant_label = str(item.get("variant_label") or "")[:100]
    asset.updated_at = utc_now()


def load_asset_extraction_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取资产抽取核心提示词。"""

    prompt_name = settings.asset_extraction_prompt_name.strip()
    if not prompt_name:
        raise AssetServiceError("资产抽取提示词名称未配置")
    prompt_registry = registry or PromptRegistry.from_settings()
    return prompt_registry.skill(prompt_name)


def load_asset_autocomplete_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取资产描述补全核心提示词。"""

    prompt_name = settings.asset_autocomplete_prompt_name.strip()
    if not prompt_name:
        raise AssetServiceError("资产描述补全提示词名称未配置")
    prompt_registry = registry or PromptRegistry.from_settings()
    return prompt_registry.skill(prompt_name)


def build_autocomplete_messages(
    *,
    asset_type: str,
    name: str,
    current_summary: str,
    current_keyword: str,
    current_colors: str,
    current_description: dict[str, Any],
    current_details: dict[str, Any],
    current_accessories: dict[str, Any],
    script_context: str,
    retry_feedback: str = "",
) -> list[dict[str, str]]:
    """构建单个资产描述补全提示词。"""

    system = load_asset_autocomplete_prompt()
    current_block = json.dumps(
        {
            "assetType": asset_type,
            "name": name,
            "summary": current_summary,
            "keyword": current_keyword,
            "colors": current_colors,
            "description": current_description,
            "details": current_details,
            "accessories": current_accessories,
        },
        ensure_ascii=False,
        indent=2,
    )
    user = (
        f"## 资产现有信息\n{current_block}\n\n"
        f"## 关联正文上下文\n{script_context.strip() or '（未找到关联正文）'}\n\n"
        "请输出补全后的资产 JSON 对象。"
    )
    if retry_feedback.strip():
        user += f"\n\n## 上一次输出的问题（必须修正）\n{retry_feedback.strip()}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _model_prompt_trace(*, model_id: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    """记录资产抽取模型调用的提示词信息。"""

    return {
        "model_id": model_id,
        "messages": messages,
        "composed_prompt": _format_model_messages(messages),
    }


def _format_model_messages(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = str(message.get("role") or f"message_{index}").strip()
        content = str(message.get("content") or "").strip()
        if content:
            parts.append(f"{role}：\n{content}")
    return "\n\n".join(parts)


def parse_episode_indices(value: str) -> set[int]:
    """解析数据库中的逗号分隔集号。"""

    indices: set[int] = set()
    for item in (value or "").split(","):
        try:
            number = int(item.strip())
        except ValueError:
            continue
        if number > 0:
            indices.add(number)
    return indices


def join_episode_indices(indices: set[int]) -> str:
    """把集号集合格式化为升序逗号分隔字符串。"""

    return ",".join(str(number) for number in sorted(indices))


def _dedupe_public_ids(values: list[str] | None) -> list[str]:
    """去重并清洗 public_id 列表。"""

    if not values:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


async def get_or_create_asset(
    session: AsyncSession,
    project: Any,
    user_public_id: str,
    asset_type: str,
    name: str,
) -> tuple[Asset, bool]:
    """按唯一键获取或创建资产。"""

    statement = select(Asset).where(
        Asset.project_id == project.id,
        Asset.user_public_id == user_public_id,
        Asset.asset_type == asset_type,
        Asset.name == name,
        Asset.disabled_at.is_(None),
    )
    asset = (await session.exec(statement)).first()
    if asset is not None:
        return asset, False

    asset = Asset(
        project_id=project.id,
        user_public_id=user_public_id,
        asset_type=asset_type,
        name=name,
    )
    session.add(asset)
    await session.flush()
    return asset, True


async def load_existing_asset_by_key(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    key: tuple[str, str],
) -> Asset | None:
    """按资产唯一键读取单个未禁用资产。"""

    asset_type, name = key
    statement = select(Asset).where(
        Asset.project_id == project_id,
        Asset.user_public_id == user_public_id,
        Asset.asset_type == asset_type,
        Asset.name == name,
        Asset.disabled_at.is_(None),
    )
    return (await session.exec(statement)).first()


async def load_asset_or_raise(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    asset_public_id: str,
) -> Asset:
    """读取单个资产，不存在则抛出业务异常。"""

    statement = select(Asset).where(
        Asset.project_id == project_id,
        Asset.user_public_id == user_public_id,
        Asset.public_id == asset_public_id,
        Asset.disabled_at.is_(None),
    )
    asset = (await session.exec(statement)).first()
    if asset is None:
        raise AssetNotFoundError("资产不存在或无权访问")
    return asset


# ---------------------------------------------------------------------------
# 资产管理：分页筛选 / 父子树 / 正文引用 / 手动增改 / 批量与级联删除
# ---------------------------------------------------------------------------

ASSET_TYPE_DISPLAY_ORDER = (
    ASSET_TYPE_ROLE,
    ASSET_TYPE_FACTION,
    ASSET_TYPE_PROP,
    ASSET_TYPE_SCENE,
)


def _asset_read_dict(asset: Asset) -> dict[str, Any]:
    """把资产实体转为响应字典（含子资产/引用前的基础字段）。"""

    return {
        "public_id": asset.public_id,
        "asset_type": asset.asset_type,
        "name": asset.name,
        "keyword": asset.keyword,
        "colors": asset.colors,
        "summary": asset.summary,
        "description": asset.description,
        "details": asset.details,
        "accessories": asset.accessories,
        "status": asset.status,
        "main_asset": asset.main_asset,
        "variant_label": asset.variant_label,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }


def _asset_reference_dict(episode: Any, plan: Any, source: str, snippet: str) -> dict[str, Any]:
    """构造资产引用记录字典。"""

    return {
        "episode_public_id": str(episode.public_id),
        "episode_index": int(episode.episode_index),
        "episode_title": episode.title or "",
        "plan_public_id": str(plan.public_id),
        "plan_title": plan.title or "",
        "source": source,
        "snippet": snippet,
    }


def _reference_snippet(body: str, index: int, length: int) -> str:
    """围绕命中位置截取一小段正文，便于人工核对。"""

    start = max(0, index - 20)
    end = min(len(body), index + length + 20)
    snippet = body[start:end].replace("\n", " ").strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{snippet}{suffix}"


async def find_asset_references(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    assets: list[Asset],
) -> dict[str, list[dict[str, Any]]]:
    """查询资产被剧本分集引用的记录：AssetEpisode 显式关联 + 正文名称命中。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    result: dict[str, list[dict[str, Any]]] = {asset.public_id: [] for asset in assets}
    if not assets:
        return result
    asset_ids = [int(asset.id) for asset in assets if asset.id is not None]
    asset_by_id = {int(asset.id): asset for asset in assets if asset.id is not None}

    ep_statement = (
        select(ScriptEpisode, ScriptPlan)
        .join(ScriptPlan, ScriptEpisode.plan_id == ScriptPlan.id)
        .where(
            ScriptPlan.project_id == project.id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
            ScriptEpisode.disabled_at.is_(None),
        )
        .order_by(ScriptEpisode.episode_index, ScriptEpisode.id)
    )
    ep_rows = list((await session.exec(ep_statement)).all())
    episode_by_id = {int(episode.id): (episode, plan) for episode, plan in ep_rows}

    seen: set[tuple[str, str, str]] = set()
    if asset_ids:
        assoc_statement = select(AssetEpisode).where(
            AssetEpisode.project_id == project.id,
            AssetEpisode.user_public_id == user_public_id,
            AssetEpisode.asset_id.in_(asset_ids),
        )
        for link in (await session.exec(assoc_statement)).all():
            pair = episode_by_id.get(int(link.episode_id))
            asset = asset_by_id.get(int(link.asset_id))
            if pair is None or asset is None:
                continue
            episode, plan = pair
            key = (asset.public_id, str(episode.public_id), "association")
            if key in seen:
                continue
            seen.add(key)
            result[asset.public_id].append(_asset_reference_dict(episode, plan, "association", ""))

    for episode, plan in ep_rows:
        body = episode.body or ""
        if not body:
            continue
        for asset in assets:
            name = (asset.name or "").strip()
            if not name:
                continue
            index = body.find(name)
            if index == -1:
                continue
            key = (asset.public_id, str(episode.public_id), "text")
            if key in seen:
                continue
            seen.add(key)
            result[asset.public_id].append(
                _asset_reference_dict(episode, plan, "text", _reference_snippet(body, index, len(name)))
            )
    return result


async def list_assets_page(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_type: str = "",
    keyword: str = "",
    status: str = "",
    referenced: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """分页 + 筛选列出资产；根资产带 child_of 子资产树与正文引用。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    normalized_type = asset_type.strip().lower()
    if normalized_type and normalized_type not in VALID_ASSET_TYPES:
        raise AssetServiceError(f"不支持的资产类型：{asset_type}")
    normalized_status = status.strip().lower()
    if normalized_status and normalized_status not in {ASSET_STATUS_DRAFT, ASSET_STATUS_LOCKED}:
        raise AssetServiceError(f"不支持的资产状态：{status}")
    normalized_referenced = referenced.strip().lower()
    page = max(1, int(page))
    page_size = min(100, max(1, int(page_size)))

    statement = select(Asset).where(
        Asset.project_id == project.id,
        Asset.user_public_id == user_public_id,
        Asset.disabled_at.is_(None),
    )
    all_assets = list((await session.exec(statement)).all())
    asset_by_id = {int(asset.id): asset for asset in all_assets if asset.id is not None}

    children_by_parent: dict[int, list[Asset]] = {}
    child_ids: set[int] = set()
    if asset_by_id:
        rel_statement = select(AssetRelation).where(
            AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
            AssetRelation.source_asset_id.in_(list(asset_by_id.keys())),
        )
        for relation in (await session.exec(rel_statement)).all():
            child = asset_by_id.get(int(relation.source_asset_id))
            parent = asset_by_id.get(int(relation.target_asset_id))
            if child is None or parent is None:
                continue
            children_by_parent.setdefault(int(parent.id), []).append(child)
            child_ids.add(int(child.id))

    references_map = await find_asset_references(session, project_public_id, user_public_id, all_assets)
    order = {asset_type_name: index for index, asset_type_name in enumerate(ASSET_TYPE_DISPLAY_ORDER)}

    def _match(asset: Asset) -> bool:
        if normalized_status and asset.status != normalized_status:
            return False
        if keyword.strip():
            kw = keyword.strip().lower()
            # 仅匹配名称/关键词/变体标签等"标识字段"，不匹配 summary/description 长文，
            # 否则搜主角名会命中几乎所有资产的描述，等同于没过滤。
            haystack = " ".join(
                [asset.name or "", asset.keyword or "", asset.variant_label or ""]
            ).lower()
            if kw not in haystack:
                return False
        if normalized_referenced in {"with", "without"}:
            has_ref = bool(references_map.get(asset.public_id))
            if normalized_referenced == "with" and not has_ref:
                return False
            if normalized_referenced == "without" and has_ref:
                return False
        return True

    candidates = [asset for asset in all_assets if int(asset.id) not in child_ids]
    if normalized_type:
        candidates = [asset for asset in candidates if asset.asset_type == normalized_type]
    include_children = True

    filtered = [asset for asset in candidates if _match(asset)]
    filtered.sort(key=lambda asset: (order.get(asset.asset_type, 99), asset.name or ""))
    total = len(filtered)
    start = (page - 1) * page_size
    page_items = filtered[start : start + page_size]

    from app.services import media as media_service  # 局部导入避免与媒体服务的循环依赖

    cover_candidates: list[Asset] = list(page_items)
    if include_children:
        for root in page_items:
            cover_candidates.extend(children_by_parent.get(int(root.id), []))
    cover_map = await media_service.cover_urls_for(session, int(project.id), user_public_id, cover_candidates)

    def _build(asset: Asset) -> dict[str, Any]:
        data = _asset_read_dict(asset)
        data["thumbnail_url"] = cover_map.get(asset.public_id, "")
        data["references"] = references_map.get(asset.public_id, [])
        if include_children:
            children = sorted(
                children_by_parent.get(int(asset.id), []),
                key=lambda child: (order.get(child.asset_type, 99), child.name or ""),
            )
            data["children"] = [
                {
                    **_asset_read_dict(child),
                    "thumbnail_url": cover_map.get(child.public_id, ""),
                    "references": references_map.get(child.public_id, []),
                    "children": [],
                }
                for child in children
            ]
        else:
            data["children"] = []
        return data

    pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "items": [_build(asset) for asset in page_items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


async def create_asset(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_type: str,
    name: str,
    keyword: str = "",
    colors: str = "",
    summary: str = "",
    description: str = "",
    details: str = "{}",
    accessories: str = "{}",
    main_asset: bool = True,
    variant_label: str = "",
) -> Asset:
    """手动创建根资产；类型受限于 VALID_ASSET_TYPES，名称唯一。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    normalized_type = asset_type.strip().lower()
    if normalized_type not in VALID_ASSET_TYPES:
        raise AssetServiceError(f"不支持手动创建的资产类型：{asset_type}")
    trimmed_name = name.strip()
    if not trimmed_name:
        raise AssetServiceError("资产名称不能为空")

    key = (normalized_type, trimmed_name)
    await _lock_asset_key(session, int(project.id), user_public_id, key)
    if await load_existing_asset_by_key(session, int(project.id), user_public_id, key) is not None:
        raise AssetServiceError(f"已存在同名资产：{trimmed_name}")

    asset = Asset(
        project_id=int(project.id),
        user_public_id=user_public_id,
        asset_type=normalized_type,
        name=trimmed_name,
        keyword=keyword.strip()[:500],
        colors=colors.strip()[:1000],
        summary=summary,
        description=description or "",
        details=details or "{}",
        accessories=accessories or "{}",
        main_asset=bool(main_asset),
        variant_label=variant_label.strip()[:100],
    )
    session.add(asset)
    await session.flush()
    return asset


async def update_asset(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    asset_public_id: str,
    *,
    fields: dict[str, Any],
) -> Asset:
    """编辑未锁定资产；仅更新提供的字段，重命名需保持唯一。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    asset = await load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    if asset.status == ASSET_STATUS_LOCKED:
        raise AssetServiceError("资产已锁定，请先解锁再编辑")

    new_name = fields.get("name")
    if new_name is not None:
        trimmed = str(new_name).strip()
        if not trimmed:
            raise AssetServiceError("资产名称不能为空")
        if trimmed != asset.name:
            key = (asset.asset_type, trimmed)
            await _lock_asset_key(session, int(project.id), user_public_id, key)
            existing = await load_existing_asset_by_key(session, int(project.id), user_public_id, key)
            if existing is not None and existing.public_id != asset.public_id:
                raise AssetServiceError(f"已存在同名资产：{trimmed}")
            asset.name = trimmed[:200]

    for attr in ("keyword", "colors", "summary", "description", "details", "accessories", "variant_label"):
        value = fields.get(attr)
        if value is not None:
            setattr(asset, attr, value)
    asset.updated_at = utc_now()
    session.add(asset)
    await session.flush()
    return asset


async def set_asset_parent(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    asset_public_id: str,
    *,
    parent_asset_public_id: str | None,
) -> Asset:
    """设置或解除资产父子关系；空父资产表示解绑。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    project_id = int(project.id)
    asset = await load_asset_or_raise(session, project_id, user_public_id, asset_public_id)
    if asset.status == ASSET_STATUS_LOCKED:
        raise AssetServiceError("资产已锁定，请先解锁再调整父子关系")
    if asset.id is None:
        raise AssetServiceError("资产数据异常，无法调整父子关系")

    parent_public_id = str(parent_asset_public_id or "").strip()
    parent: Asset | None = None
    if parent_public_id:
        parent = await load_asset_or_raise(session, project_id, user_public_id, parent_public_id)
        if parent.id is None:
            raise AssetServiceError("父资产数据异常，无法调整父子关系")
        if int(parent.id) == int(asset.id):
            raise AssetServiceError("资产不能绑定为自己的父资产")
        if await _asset_is_descendant(session, ancestor_id=int(asset.id), candidate_id=int(parent.id)):
            raise AssetServiceError("不能绑定到当前资产的子资产，避免形成循环层级")
        existing_parent_relation = (
            await session.exec(
                select(AssetRelation).where(
                    AssetRelation.source_asset_id == int(parent.id),
                    AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
                )
            )
        ).first()
        if existing_parent_relation is not None:
            raise AssetServiceError("当前仅支持一层父子资产结构，不能绑定到子资产")

    await session.exec(
        delete(AssetRelation).where(
            AssetRelation.source_asset_id == int(asset.id),
            AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
        )
    )

    if parent is not None:
        await _upsert_child_relation(
            session,
            project_id,
            user_public_id,
            parent=parent,
            child=asset,
            label=asset.variant_label or asset.name,
        )
    asset.main_asset = parent is None
    asset.updated_at = utc_now()
    session.add(asset)
    await session.flush()
    return asset


async def _asset_is_descendant(session: AsyncSession, *, ancestor_id: int, candidate_id: int) -> bool:
    """判断 candidate 是否为 ancestor 的 child_of 后代。"""

    frontier = [ancestor_id]
    visited: set[int] = set()
    while frontier:
        current = frontier.pop()
        if current in visited:
            continue
        visited.add(current)
        rows = (
            await session.exec(
                select(AssetRelation).where(
                    AssetRelation.target_asset_id == current,
                    AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
                )
            )
        ).all()
        for relation in rows:
            child_id = int(relation.source_asset_id)
            if child_id == candidate_id:
                return True
            if child_id not in visited:
                frontier.append(child_id)
    return False


async def load_assets_by_public_ids(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    public_ids: list[str],
) -> list[Asset]:
    """按请求顺序加载资产，缺失则报错。"""

    result: list[Asset] = []
    for public_id in _dedupe_public_ids(public_ids):
        result.append(await load_asset_or_raise(session, project_id, user_public_id, public_id))
    return result


async def delete_assets_with_children(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    assets: list[Asset],
) -> int:
    """级联硬删除资产及其全部 child_of 后代，并清理关系/分集/版本/媒体/生成记录。"""

    target_ids: set[int] = set()
    frontier = [int(asset.id) for asset in assets if asset.id is not None]
    while frontier:
        current = frontier.pop()
        if current in target_ids:
            continue
        target_ids.add(current)
        rows = (
            await session.exec(
                select(AssetRelation).where(
                    AssetRelation.target_asset_id == current,
                    AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
                )
            )
        ).all()
        for relation in rows:
            child_id = int(relation.source_asset_id)
            if child_id not in target_ids:
                frontier.append(child_id)

    if not target_ids:
        return 0
    id_list = list(target_ids)

    from app.services import media as media_service  # 局部导入避免与媒体服务的循环依赖

    target_public_ids = list(
        (await session.exec(select(Asset.public_id).where(Asset.id.in_(id_list)))).all()
    )
    await media_service.delete_media_for_assets(session, target_public_ids)
    await session.exec(
        delete(AssetRelation).where(
            or_(AssetRelation.source_asset_id.in_(id_list), AssetRelation.target_asset_id.in_(id_list))
        )
    )
    await session.exec(delete(AssetEpisode).where(AssetEpisode.asset_id.in_(id_list)))
    await session.exec(delete(AssetVersion).where(AssetVersion.asset_id.in_(id_list)))
    await session.exec(
        delete(Asset).where(
            Asset.id.in_(id_list),
            Asset.project_id == project_id,
            Asset.user_public_id == user_public_id,
        )
    )
    await session.flush()
    return len(id_list)


async def batch_update_assets(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_ids: list[str],
    operation: str,
) -> dict[str, Any]:
    """批量锁定/解锁/删除资产。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    normalized_op = operation.strip().lower()
    if normalized_op not in ASSET_BATCH_OPERATIONS:
        raise AssetServiceError(f"不支持的批量操作：{operation}")
    assets = await load_assets_by_public_ids(session, int(project.id), user_public_id, asset_public_ids)
    if not assets:
        raise AssetServiceError("没有可操作的资产")

    if normalized_op == "delete":
        affected = await delete_assets_with_children(session, int(project.id), user_public_id, assets)
        return {"affected": affected, "assets": []}

    target_status = ASSET_STATUS_LOCKED if normalized_op == "lock" else ASSET_STATUS_DRAFT
    for asset in assets:
        asset.status = target_status
        asset.updated_at = utc_now()
        session.add(asset)
    await session.flush()
    return {"affected": len(assets), "assets": assets}
