from __future__ import annotations

from typing import Any

from app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure
from app.services import asset as asset_service
from app.services import media as media_service


async def extract_assets_task(context: Any) -> dict[str, Any]:
    """剧本资产抽取子任务处理器。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    episode_public_ids = _payload_str_list(payload.get("episode_public_ids"))
    if not project_public_id or not current_user_public_id or not model_id:
        raise ValueError("资产抽取任务参数不完整")

    try:
        result = await asset_service.extract_assets(
            context.session,
            project_public_id,
            current_user_public_id,
            model_id=model_id,
            episode_public_ids=episode_public_ids or None,
        )
        await context.session.commit()
    except asset_service.AssetServiceError as exc:
        await context.session.rollback()
        failure_result = {
            **exc.result,
            "episode_public_ids": episode_public_ids,
        }
        raise TaskHandlerFailure(
            str(exc),
            error_code="asset_extract_failed",
            result=failure_result,
            retryable=exc.retryable,
        ) from exc

    assets = result["assets"]
    return {
        "created": int(result["created"]),
        "updated": int(result["updated"]),
        "asset_public_ids": [asset.public_id for asset in assets],
        "episode_public_ids": episode_public_ids,
        "model_id": result.get("model_id") or model_id,
        "asset_timing": result.get("asset_timing") or {},
        "asset_enrichment": result.get("asset_enrichment") or [],
        "messages": result.get("messages") or [],
        "composed_prompt": str(result.get("composed_prompt") or ""),
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
    }


def _payload_str_list(value: Any) -> list[str]:
    """把任务 payload 中的列表值清理为字符串列表。"""

    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


async def autocomplete_asset_task(context: Any) -> dict[str, Any]:
    """资产描述补全子任务处理器。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    asset_public_id = str(payload.get("asset_public_id") or "").strip()
    if not project_public_id or not current_user_public_id or not model_id or not asset_public_id:
        raise ValueError("资产补全任务参数不完整")

    try:
        result = await asset_service.autocomplete_asset(
            context.session,
            project_public_id,
            current_user_public_id,
            asset_public_id=asset_public_id,
            model_id=model_id,
        )
        await context.session.commit()
    except asset_service.AssetServiceError as exc:
        await context.session.rollback()
        raise TaskHandlerFailure(
            str(exc),
            error_code="asset_autocomplete_failed",
            result={**exc.result, "asset_public_id": asset_public_id},
            retryable=exc.retryable,
        ) from exc

    return {
        "asset_public_id": result["asset"].public_id,
        "model_id": result.get("model_id") or model_id,
        "messages": result.get("messages") or [],
        "composed_prompt": str(result.get("composed_prompt") or ""),
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
    }


async def image_generation_asset_task(context: Any) -> dict[str, Any]:
    """资产图像生成子任务处理器。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    asset_public_id = str(payload.get("asset_public_id") or "").strip()
    prompt = str(payload.get("prompt") or "")
    aspect_ratio = str(payload.get("aspect_ratio") or "")
    image_size = str(payload.get("image_size") or "")
    reference_media_public_ids = _payload_str_list(payload.get("reference_media_public_ids"))
    if not project_public_id or not current_user_public_id or not model_id or not asset_public_id:
        raise ValueError("资产图像生成任务参数不完整")

    try:
        result = await media_service.generate_asset_image(
            context.session,
            project_public_id,
            current_user_public_id,
            asset_public_id=asset_public_id,
            model_id=model_id,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            reference_media_public_ids=reference_media_public_ids,
            task_job_public_id=context.message.job_public_id,
            task_item_public_id=context.message.item_public_id,
        )
        await context.session.commit()
    except asset_service.AssetServiceError as exc:
        await context.session.rollback()
        raise TaskHandlerFailure(
            str(exc),
            error_code="asset_image_generation_failed",
            result={**exc.result, "asset_public_id": asset_public_id},
            retryable=exc.retryable,
        ) from exc

    media = result["media"]
    # 成功结果只保留前端与追溯消费的字段：raw_output 与 output_text 同值，
    # 完整 prompt_trace 仅在失败路径随 result 留痕。
    return {
        "asset_public_id": asset_public_id,
        "media_public_id": media.public_id,
        "url": media.url,
        "model_id": media.model_id or model_id,
        "prompt": str(result.get("prompt") or ""),
        "composed_prompt": str(result.get("composed_prompt") or ""),
        "output_text": str(result.get("output_text") or ""),
        "asset_timing": result.get("asset_timing") or {},
    }


async def image_prompt_asset_task(context: Any) -> dict[str, Any]:
    """资产生图专业提示词合成子任务处理器。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    asset_public_id = str(payload.get("asset_public_id") or "").strip()
    if not project_public_id or not current_user_public_id or not model_id or not asset_public_id:
        raise ValueError("资产生图提示词任务参数不完整")

    try:
        result = await media_service.synthesize_asset_image_prompt_detail(
            context.session,
            project_public_id,
            current_user_public_id,
            asset_public_id=asset_public_id,
        )
        await context.session.commit()
    except asset_service.AssetServiceError as exc:
        await context.session.rollback()
        raise TaskHandlerFailure(
            str(exc),
            error_code="asset_image_prompt_failed",
            result={**exc.result, "asset_public_id": asset_public_id},
            retryable=exc.retryable,
        ) from exc

    # 成功结果不落 messages（含艺术风格手册全文）与 raw_output（与 output_text
    # 仅差代码围栏）；失败路径的 prompt_trace 仍保留完整消息用于排查。
    return {
        "asset_public_id": asset_public_id,
        "asset_name": str(result.get("asset_name") or ""),
        "model_id": result.get("model_id") or model_id,
        "image_model_id": str(result.get("image_model_id") or ""),
        "art_style_id": str(result.get("art_style_id") or ""),
        "composed_prompt": str(result.get("composed_prompt") or ""),
        "prompt": str(result.get("prompt") or ""),
        "output_text": str(result.get("output_text") or ""),
        "asset_timing": result.get("asset_timing") or {},
    }


ASYNC_TASKS = (
    AsyncTaskDefinition(asset_service.ASSET_EXTRACT_TASK_TYPE, extract_assets_task),
    AsyncTaskDefinition(asset_service.ASSET_AUTOCOMPLETE_TASK_TYPE, autocomplete_asset_task),
    AsyncTaskDefinition(media_service.ASSET_IMAGE_PROMPT_TASK_TYPE, image_prompt_asset_task),
    AsyncTaskDefinition(media_service.ASSET_IMAGE_GENERATION_TASK_TYPE, image_generation_asset_task),
)
