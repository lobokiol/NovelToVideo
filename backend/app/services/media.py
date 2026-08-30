from __future__ import annotations

"""统一媒体中枢服务。

项目内一切图像/视频/音频产物（生成或上传）的唯一读写入口：
- 通用层：媒体行创建、对象存储落盘、内容/缩略图分发、列举与删除；
- 生成层：图像与视频生成的同步执行体（供异步任务子项调用），生成参数、
  种子、用量与失败原因内嵌媒体行，状态机 pending → processing → ready/failed；
- 资产闭环：资产结构化字段 → 专业提示词合成 → 生图 → 封面回写的既有链路，
  迁移到媒体中枢承载（scope_type=asset）。

provider 级媒体生成以归一化的 MediaGenerationOutput 为契约；本服务不感知
具体供应商，真实出图/出片由 provider 适配层实现。
"""

import base64
import json
import re
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import BASE_DIR, settings
from app.core.tasks.engine import default_async_task_engine
from app.models.asset import ASSET_RELATION_CHILD_OF, Asset, AssetRelation
from app.models.media import (
    MEDIA_ROLE_FINAL,
    MEDIA_ROLE_GENERATED,
    MEDIA_ROLE_REFERENCE,
    MEDIA_SCOPE_ASSET,
    MEDIA_SOURCE_GENERATION,
    MEDIA_SOURCE_UPLOAD,
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_TYPE_AUDIO,
    MEDIA_TYPE_IMAGE,
    MEDIA_TYPE_VIDEO,
    MediaAsset,
)
from app.schemas.tasks import TaskItemCreate, TaskJobCreate, TaskJobDetail
from app.services import asset as asset_service
from app.services import project as project_service
from app.services.agent_gateway import (
    MediaGenerationOutput,
    ProviderModelGateway,
    ProviderModelGatewayError,
)
from app.services.media_storage import (
    MediaStorage,
    MediaStorageError,
    get_media_storage,
)
from app.services.prompt_registry import PromptRegistry, PromptRegistryError


ASSET_IMAGE_PROMPT_TASK_TYPE = "asset.image_prompt"
ASSET_IMAGE_GENERATION_TASK_TYPE = "asset.image_generation"
MEDIA_VIDEO_GENERATION_TASK_TYPE = "media.video_generation"

MEDIA_GENERATION_QUEUE_NAME = "media"

_IMAGE_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
_VIDEO_MIME_EXT = {
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "video/x-msvideo": "avi",
}
_AUDIO_MIME_EXT = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
}
_MIME_EXT_BY_TYPE = {
    MEDIA_TYPE_IMAGE: _IMAGE_MIME_EXT,
    MEDIA_TYPE_VIDEO: _VIDEO_MIME_EXT,
    MEDIA_TYPE_AUDIO: _AUDIO_MIME_EXT,
}
_DEFAULT_EXT_BY_TYPE = {
    MEDIA_TYPE_IMAGE: "png",
    MEDIA_TYPE_VIDEO: "mp4",
    MEDIA_TYPE_AUDIO: "mp3",
}
_DEFAULT_MIME_BY_TYPE = {
    MEDIA_TYPE_IMAGE: "image/png",
    MEDIA_TYPE_VIDEO: "video/mp4",
    MEDIA_TYPE_AUDIO: "audio/mpeg",
}

_REFERENCE_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_REFERENCE_IMAGE_MAX_BYTES = 20 * 1024 * 1024
_UPLOAD_MAX_BYTES = {
    MEDIA_TYPE_IMAGE: 20 * 1024 * 1024,
    MEDIA_TYPE_VIDEO: 512 * 1024 * 1024,
    MEDIA_TYPE_AUDIO: 100 * 1024 * 1024,
}
_UPLOAD_MAX_LABEL = {
    MEDIA_TYPE_IMAGE: "20MB",
    MEDIA_TYPE_VIDEO: "512MB",
    MEDIA_TYPE_AUDIO: "100MB",
}

_THUMBNAIL_PREFIX = "thumbnails"
_THUMBNAIL_MAX_EDGE = 512
_THUMBNAIL_JPEG_QUALITY = 85

_STYLE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")

_VIDEO_REFERENCE_MAX_COUNT = 4


class MediaServiceError(Exception):
    """媒体服务业务错误；result 携带可回写任务结果的诊断信息。

    retryable=False 表示确定性失败（参数/前置状态问题），任务系统不应重试。
    """

    def __init__(self, message: str, *, result: dict[str, Any] | None = None, retryable: bool = True) -> None:
        super().__init__(message)
        self.result = result or {}
        self.retryable = bool(retryable)


class MediaNotFoundError(MediaServiceError):
    """媒体不存在或无权访问。"""


class _MediaTiming:
    """收集媒体生成各阶段的服务端耗时。"""

    def __init__(self) -> None:
        self.started_at = perf_counter()
        self.stages: list[dict[str, int | str]] = []

    def mark(self, name: str, started_at: float, ended_at: float | None = None) -> None:
        ended_at = ended_at if ended_at is not None else perf_counter()
        self.stages.append(
            {
                "name": name,
                "durationMs": _duration_ms(started_at, ended_at),
                "startedAtMs": _duration_ms(self.started_at, started_at),
                "endedAtMs": _duration_ms(self.started_at, ended_at),
            }
        )

    def payload(self) -> dict[str, Any]:
        return {
            "totalMs": _duration_ms(self.started_at, perf_counter()),
            "stages": [dict(stage) for stage in self.stages],
        }


def _duration_ms(started_at: float, ended_at: float) -> int:
    return max(0, int((ended_at - started_at) * 1000))


def _generation_timeout_for(media_type: str) -> float:
    if media_type == MEDIA_TYPE_VIDEO:
        return settings.video_generation_timeout_seconds
    if media_type == MEDIA_TYPE_IMAGE:
        return settings.image_generation_timeout_seconds
    return settings.media_generation_timeout_seconds


def build_media_gateway(media_type: str = MEDIA_TYPE_IMAGE) -> ProviderModelGateway:
    """按媒体类型构建生成网关（超时不同），便于测试替换。"""

    return ProviderModelGateway(timeout=_generation_timeout_for(media_type))


# ---------------------------------------------------------------------------
# 存储键 / URL / 字节归一
# ---------------------------------------------------------------------------

def _content_url(project_public_id: str, media_public_id: str) -> str:
    """构建可直接给浏览器 <img>/<video> src 的内容访问 URL。"""

    api_prefix = settings.api_prefix.strip()
    if api_prefix and not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"
    api_prefix = api_prefix.rstrip("/")
    return f"{api_prefix}/projects/{project_public_id}/media/{media_public_id}/content"


def _ext_for(media_type: str, mime: str, url: str = "") -> str:
    mime_map = _MIME_EXT_BY_TYPE.get(media_type, _IMAGE_MIME_EXT)
    ext = mime_map.get((mime or "").strip().lower())
    if ext:
        return ext
    tail = url.rsplit("?", 1)[0].rsplit(".", 1)[-1].lower() if "." in url else ""
    if tail and tail in set(mime_map.values()):
        return tail
    if media_type == MEDIA_TYPE_IMAGE and tail in {"png", "jpg", "jpeg", "webp", "gif"}:
        return "jpg" if tail == "jpeg" else tail
    return _DEFAULT_EXT_BY_TYPE.get(media_type, "bin")


def _storage_key_for(project_public_id: str, media_type: str, media_public_id: str, ext: str) -> str:
    return f"{project_public_id}/{media_type}/{media_public_id}.{ext}"


def _thumbnail_key(storage_key: str) -> str:
    stem = storage_key.rsplit(".", 1)[0] if "." in storage_key.rsplit("/", 1)[-1] else storage_key
    return f"{_THUMBNAIL_PREFIX}/{stem}.jpg"


async def _store_media_bytes(
    storage: MediaStorage,
    media: MediaAsset,
    *,
    project_public_id: str,
    data: bytes,
    ext: str,
) -> None:
    """把媒体字节写入对象存储并回填行上的存储与访问字段。"""

    key = _storage_key_for(project_public_id, media.media_type, media.public_id, ext)
    try:
        stored = await storage.put(key, data, content_type=media.mime_type or "application/octet-stream")
    except MediaStorageError as exc:
        raise MediaServiceError(f"媒体落盘失败：{exc}") from exc
    media.storage_backend = stored.backend
    media.storage_key = stored.key
    media.file_size = stored.size
    media.url = storage.public_url(stored.key) or _content_url(project_public_id, media.public_id)


async def _delete_stored_media(storage: MediaStorage, media: MediaAsset) -> None:
    """删除媒体对象及其缩略图；存储层异常不阻断行删除。"""

    if not media.storage_key:
        return
    try:
        await storage.delete(media.storage_key)
    except MediaStorageError:
        pass
    try:
        await storage.delete(_thumbnail_key(media.storage_key))
    except MediaStorageError:
        pass


def _strip_data_uri(value: str) -> str:
    text = value.strip()
    if text.startswith("data:") and "," in text:
        return text.split(",", 1)[1]
    return text


async def _resolve_media_bytes(output: MediaGenerationOutput, *, timeout: float) -> bytes:
    """把媒体结果归一为字节：data > b64 > url 下载。"""

    if output.data:
        return output.data
    if output.b64:
        try:
            return base64.b64decode(_strip_data_uri(output.b64))
        except (ValueError, TypeError) as exc:
            raise MediaServiceError("媒体 base64 解码失败") from exc
    if output.url:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(output.url)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            raise MediaServiceError(f"下载生成媒体失败：{exc}") from exc
    raise MediaServiceError("生成结果不含可用媒体数据")


def _cost_tokens_from_usage(usage: dict[str, Any] | None) -> int:
    if not isinstance(usage, dict):
        return 0
    for key in ("total_tokens", "totalTokens"):
        value = usage.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return 0


def _dump_params(params: dict[str, Any] | None) -> str:
    return json.dumps(params or {}, ensure_ascii=False)


def _parse_params(media: MediaAsset) -> dict[str, Any]:
    try:
        value = json.loads(media.params or "{}")
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _dedupe_text_list(values: list[str] | None) -> list[str]:
    """清理字符串列表并保持顺序去重。"""

    if not isinstance(values, list):
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


def _image_dimensions(data: bytes) -> tuple[int, int]:
    """读取图片字节的真实像素尺寸。"""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - 取决于部署环境依赖
        raise MediaServiceError("图片尺寸校验需要安装 pillow 依赖", retryable=False) from exc
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
    except (OSError, ValueError) as exc:
        raise MediaServiceError("参考图无法解析或文件已损坏", retryable=False) from exc
    if width <= 0 or height <= 0:
        raise MediaServiceError("参考图像素尺寸无效", retryable=False)
    return int(width), int(height)


def _normalize_image_payload(payload: dict[str, Any], *, width: int, height: int) -> dict[str, Any]:
    """把首尾帧按目标像素居中裁切，并返回不修改原对象的新载荷。"""

    target_width = int(width or 0)
    target_height = int(height or 0)
    if target_width <= 0 or target_height <= 0:
        raise MediaServiceError("目标视频像素尺寸无效", retryable=False)
    raw_data = payload.get("data")
    if not isinstance(raw_data, (bytes, bytearray)) or not raw_data:
        raise MediaServiceError("参考图内容为空", retryable=False)
    data = bytes(raw_data)
    source_width, source_height = _image_dimensions(data)
    normalized = dict(payload)
    normalized.update(
        {
            "source_width": source_width,
            "source_height": source_height,
            "width": target_width,
            "height": target_height,
        }
    )
    if (source_width, source_height) == (target_width, target_height):
        return normalized

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - 取决于部署环境依赖
        raise MediaServiceError("首尾帧规格化需要安装 pillow 依赖", retryable=False) from exc
    try:
        with Image.open(BytesIO(data)) as image:
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            converted = image.convert("RGBA" if has_alpha else "RGB")
            fitted = ImageOps.fit(
                converted,
                (target_width, target_height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            buffer = BytesIO()
            fitted.save(buffer, format="PNG")
    except (OSError, ValueError) as exc:
        raise MediaServiceError("首尾帧居中裁切失败", retryable=False) from exc

    filename = str(payload.get("filename") or "frame").rsplit(".", 1)[0]
    normalized.update(
        {
            "filename": f"{filename}.png",
            "mime_type": "image/png",
            "data": buffer.getvalue(),
        }
    )
    return normalized


# ---------------------------------------------------------------------------
# 媒体行加载 / 列举 / 内容分发 / 缩略图 / 删除
# ---------------------------------------------------------------------------

async def _load_media_or_raise(
    session: AsyncSession, project_id: int, user_public_id: str, media_public_id: str
) -> MediaAsset:
    statement = select(MediaAsset).where(
        MediaAsset.public_id == media_public_id,
        MediaAsset.project_id == project_id,
        MediaAsset.user_public_id == user_public_id,
        MediaAsset.disabled_at.is_(None),
    )
    media = (await session.exec(statement)).first()
    if media is None:
        raise MediaNotFoundError("媒体不存在或无权访问")
    return media


async def get_media_asset(
    session: AsyncSession, project_public_id: str, user_public_id: str, media_public_id: str
) -> MediaAsset:
    """读取项目内单个媒体行（鉴权访问）。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    return await _load_media_or_raise(session, int(project.id), user_public_id, media_public_id)


async def select_media_as_final(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    media_public_id: str,
) -> MediaAsset:
    """把候选媒体择优设为选定：同挂靠对象同类型的其他选定媒体自动降级为普通生成。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    media = await _load_media_or_raise(session, int(project.id), user_public_id, media_public_id)
    if media.status != MEDIA_STATUS_READY:
        raise MediaServiceError("仅就绪状态的媒体可设为选定", retryable=False)
    if not media.scope_type.strip() or not media.scope_public_id.strip():
        raise MediaServiceError("仅挂靠业务对象的媒体可参与择优选定", retryable=False)

    siblings = (
        await session.exec(
            select(MediaAsset).where(
                MediaAsset.project_id == int(project.id),
                MediaAsset.scope_type == media.scope_type,
                MediaAsset.scope_public_id == media.scope_public_id,
                MediaAsset.media_type == media.media_type,
                MediaAsset.media_role == MEDIA_ROLE_FINAL,
                MediaAsset.id != media.id,
                MediaAsset.disabled_at.is_(None),
            )
        )
    ).all()
    for sibling in siblings:
        sibling.media_role = MEDIA_ROLE_GENERATED
        session.add(sibling)
    media.media_role = MEDIA_ROLE_FINAL
    session.add(media)
    await session.flush()
    return media


async def list_media_assets(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    media_type: str = "",
    status: str = "",
    source: str = "",
    scope_type: str = "",
    scope_public_id: str = "",
    media_role: str = "",
    limit: int = 200,
    offset: int = 0,
) -> list[MediaAsset]:
    """按条件列举项目媒体，创建时间倒序。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    statement = select(MediaAsset).where(
        MediaAsset.project_id == int(project.id),
        MediaAsset.user_public_id == user_public_id,
        MediaAsset.disabled_at.is_(None),
    )
    if media_type.strip():
        statement = statement.where(MediaAsset.media_type == media_type.strip())
    if status.strip():
        statement = statement.where(MediaAsset.status == status.strip())
    if source.strip():
        statement = statement.where(MediaAsset.source == source.strip())
    if scope_type.strip():
        statement = statement.where(MediaAsset.scope_type == scope_type.strip())
    if scope_public_id.strip():
        statement = statement.where(MediaAsset.scope_public_id == scope_public_id.strip())
    if media_role.strip():
        statement = statement.where(MediaAsset.media_role == media_role.strip())
    statement = (
        statement.order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
        .offset(max(0, int(offset)))
        .limit(max(1, min(500, int(limit))))
    )
    return list((await session.exec(statement)).all())


async def get_media_content(
    session: AsyncSession, media_public_id: str, *, storage: MediaStorage | None = None
) -> tuple[MediaAsset, Path | None]:
    """按公开 ID 取媒体行与本地文件路径（uuid 即访问凭据，供内容路由公开服务）。

    本地后端返回文件路径供 FileResponse 直传；非本地后端返回 None，
    由调用方经 read_media_bytes 走字节流。
    """

    media = (
        await session.exec(
            select(MediaAsset).where(
                MediaAsset.public_id == media_public_id,
                MediaAsset.disabled_at.is_(None),
            )
        )
    ).first()
    if media is None or not media.storage_key:
        raise MediaNotFoundError("媒体不存在")
    resolved_storage = storage or get_media_storage()
    path = resolved_storage.local_path(media.storage_key)
    if path is not None and not path.exists():
        raise MediaNotFoundError("媒体文件不存在")
    return media, path


async def read_media_bytes(media: MediaAsset, *, storage: MediaStorage | None = None) -> bytes:
    """读取媒体完整字节（非本地后端的内容分发回退路径）。"""

    resolved_storage = storage or get_media_storage()
    try:
        return await resolved_storage.get(media.storage_key)
    except MediaStorageError as exc:
        raise MediaNotFoundError("媒体文件不存在") from exc


def _build_thumbnail_bytes(data: bytes, *, max_edge: int) -> bytes:
    """用 Pillow 生成 JPEG 缩略图字节；非法图像数据抛 MediaServiceError。"""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - 取决于部署环境依赖
        raise MediaServiceError("缩略图功能需安装 pillow 依赖") from exc
    try:
        with Image.open(BytesIO(data)) as image:
            converted = image.convert("RGB")
            converted.thumbnail((max_edge, max_edge))
            buffer = BytesIO()
            converted.save(buffer, format="JPEG", quality=_THUMBNAIL_JPEG_QUALITY)
            return buffer.getvalue()
    except (OSError, ValueError) as exc:
        raise MediaServiceError("缩略图生成失败：无法解析图像数据") from exc


async def get_media_thumbnail(
    session: AsyncSession,
    media_public_id: str,
    *,
    max_edge: int = _THUMBNAIL_MAX_EDGE,
    storage: MediaStorage | None = None,
) -> tuple[bytes, str]:
    """取图像媒体缩略图字节，懒生成后写回存储供后续命中。"""

    media, _ = await get_media_content(session, media_public_id, storage=storage)
    if media.media_type != MEDIA_TYPE_IMAGE:
        raise MediaServiceError("该媒体类型暂不支持缩略图")
    resolved_storage = storage or get_media_storage()
    thumb_key = _thumbnail_key(media.storage_key)
    try:
        return await resolved_storage.get(thumb_key), "image/jpeg"
    except MediaStorageError:
        pass
    original = await read_media_bytes(media, storage=resolved_storage)
    thumbnail = _build_thumbnail_bytes(original, max_edge=max_edge)
    try:
        await resolved_storage.put(thumb_key, thumbnail, content_type="image/jpeg")
    except MediaStorageError:
        pass
    return thumbnail, "image/jpeg"


async def delete_media_asset(
    session: AsyncSession, project_public_id: str, user_public_id: str, media_public_id: str
) -> None:
    """删除单个媒体：清存储对象（含缩略图）并删行。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    media = await _load_media_or_raise(session, int(project.id), user_public_id, media_public_id)
    await _delete_stored_media(get_media_storage(), media)
    await session.delete(media)
    await session.flush()


async def delete_media_for_scope(
    session: AsyncSession,
    *,
    scope_type: str,
    scope_public_ids: list[str],
) -> None:
    """删除一组业务对象挂靠的全部媒体（行 + 存储对象），用于级联清理。"""

    ids = _dedupe_text_list(scope_public_ids)
    if not ids:
        return
    rows = (
        await session.exec(
            select(MediaAsset).where(
                MediaAsset.scope_type == scope_type,
                MediaAsset.scope_public_id.in_(ids),
            )
        )
    ).all()
    storage = get_media_storage()
    for media in rows:
        await _delete_stored_media(storage, media)
        await session.delete(media)
    await session.flush()


# ---------------------------------------------------------------------------
# 通用上传
# ---------------------------------------------------------------------------

def _media_type_from_mime(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return MEDIA_TYPE_IMAGE
    if mime_type.startswith("video/"):
        return MEDIA_TYPE_VIDEO
    if mime_type.startswith("audio/"):
        return MEDIA_TYPE_AUDIO
    return ""


async def upload_media(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    media_type: str = "",
    scope_type: str = "",
    scope_public_id: str = "",
    media_role: str = MEDIA_ROLE_REFERENCE,
) -> MediaAsset:
    """上传媒体文件入中枢：校验类型与大小 → 落存储 → 写行（status=ready）。"""

    mime_type = (content_type or "").split(";", 1)[0].strip().lower()
    resolved_type = (media_type or "").strip() or _media_type_from_mime(mime_type)
    if resolved_type not in (MEDIA_TYPE_IMAGE, MEDIA_TYPE_VIDEO, MEDIA_TYPE_AUDIO):
        raise MediaServiceError("仅支持上传图像、视频或音频文件")
    if resolved_type == MEDIA_TYPE_IMAGE and mime_type not in _REFERENCE_IMAGE_MIME_TYPES:
        raise MediaServiceError("图片仅支持 PNG/JPEG/WebP")
    if not data:
        raise MediaServiceError("上传内容为空")
    max_bytes = _UPLOAD_MAX_BYTES[resolved_type]
    if len(data) > max_bytes:
        raise MediaServiceError(f"文件过大，最大支持 {_UPLOAD_MAX_LABEL[resolved_type]}")
    image_width, image_height = _image_dimensions(data) if resolved_type == MEDIA_TYPE_IMAGE else (0, 0)

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    media = MediaAsset(
        project_id=int(project.id),
        user_public_id=user_public_id,
        media_type=resolved_type,
        source=MEDIA_SOURCE_UPLOAD,
        status=MEDIA_STATUS_READY,
        scope_type=scope_type.strip(),
        scope_public_id=scope_public_id.strip(),
        media_role=(media_role or MEDIA_ROLE_REFERENCE).strip() or MEDIA_ROLE_REFERENCE,
        mime_type=mime_type or _DEFAULT_MIME_BY_TYPE[resolved_type],
        width=image_width,
        height=image_height,
        params=_dump_params({"filename": filename}),
    )
    session.add(media)
    await session.flush()

    await _store_media_bytes(
        get_media_storage(),
        media,
        project_public_id=project_public_id,
        data=data,
        ext=_ext_for(resolved_type, mime_type, filename),
    )
    session.add(media)
    await session.flush()
    return media


# ---------------------------------------------------------------------------
# 通用生成执行体：视频
# ---------------------------------------------------------------------------

async def _load_media_file_payload(
    session: AsyncSession,
    *,
    project_id: int,
    user_public_id: str,
    media_public_id: str,
    storage: MediaStorage,
) -> dict[str, Any]:
    """读取一张就绪图片媒体为 {filename, mime_type, data} 载荷（帧图/参考图）。"""

    media = await _load_media_or_raise(session, project_id, user_public_id, media_public_id)
    if media.media_type != MEDIA_TYPE_IMAGE:
        raise MediaServiceError("参考媒体必须是图片", retryable=False)
    if media.status != MEDIA_STATUS_READY or not media.storage_key:
        raise MediaServiceError("参考图尚未就绪", retryable=False)
    mime_type = (media.mime_type or "image/png").strip().lower()
    if mime_type not in _REFERENCE_IMAGE_MIME_TYPES:
        raise MediaServiceError("参考图仅支持 PNG/JPEG/WebP", retryable=False)
    try:
        data = await storage.get(media.storage_key)
    except MediaStorageError as exc:
        raise MediaNotFoundError("参考图文件不存在") from exc
    if not data:
        raise MediaServiceError("参考图内容为空", retryable=False)
    width, height = _image_dimensions(data)
    return {
        "media_public_id": media.public_id,
        "filename": media.storage_key.rsplit("/", 1)[-1],
        "mime_type": mime_type,
        "data": data,
        "width": width,
        "height": height,
    }


async def get_image_media_dimensions(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    media_public_id: str,
) -> tuple[int, int]:
    """读取项目内一张就绪图片的真实像素尺寸。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    payload = await _load_media_file_payload(
        session,
        project_id=int(project.id),
        user_public_id=user_public_id,
        media_public_id=media_public_id,
        storage=get_media_storage(),
    )
    return int(payload["width"]), int(payload["height"])


async def generate_video_media(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    prompt: str,
    params: dict[str, Any] | None = None,
    first_frame_media_public_id: str = "",
    last_frame_media_public_id: str = "",
    reference_media_public_ids: list[str] | None = None,
    expected_width: int = 0,
    expected_height: int = 0,
    generation_mode: str = "",
    scope_type: str = "",
    scope_public_id: str = "",
    media_role: str = MEDIA_ROLE_GENERATED,
    task_job_public_id: str = "",
    task_item_public_id: str = "",
    gateway: Any | None = None,
) -> dict[str, Any]:
    """生成一段视频：写处理中媒体行 → 解析帧图 → 调网关 → 落盘置就绪。

    失败时媒体行置 failed 并抛 MediaServiceError；是否保留失败行由调用方事务
    决定（异步任务处理器回滚不留半行，失败详情由任务子项结果承载）。
    params 中的生成参数（时长、分辨率、比例、是否同生音频、种子等）原样
    透传网关并持久化在媒体行上。
    """

    timing = _MediaTiming()
    stage_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    timing.mark("project_lookup", stage_started_at)

    resolved_model_id = str(model_id or project.video_model or "").strip()
    if not resolved_model_id:
        raise MediaServiceError("项目未绑定视频模型，请先在项目设置中选择视频模型", retryable=False)
    final_prompt = (prompt or "").strip()
    if not final_prompt:
        raise MediaServiceError("视频生成提示词不能为空", retryable=False)

    storage = get_media_storage()
    generation_params = dict(params or {})
    target_width = int(expected_width or 0)
    target_height = int(expected_height or 0)
    if (target_width <= 0) != (target_height <= 0):
        raise MediaServiceError("目标视频宽高必须同时提供", retryable=False)
    reference_ids = _dedupe_text_list(reference_media_public_ids)[:_VIDEO_REFERENCE_MAX_COUNT]
    first_frame_id = (first_frame_media_public_id or "").strip()
    last_frame_id = (last_frame_media_public_id or "").strip()

    stage_started_at = perf_counter()
    first_frame = None
    last_frame = None
    references: list[dict[str, Any]] = []
    if first_frame_id:
        first_frame = await _load_media_file_payload(
            session,
            project_id=int(project.id),
            user_public_id=user_public_id,
            media_public_id=first_frame_id,
            storage=storage,
        )
    if last_frame_id:
        last_frame = await _load_media_file_payload(
            session,
            project_id=int(project.id),
            user_public_id=user_public_id,
            media_public_id=last_frame_id,
            storage=storage,
        )
    for reference_id in reference_ids:
        references.append(
            await _load_media_file_payload(
                session,
                project_id=int(project.id),
                user_public_id=user_public_id,
                media_public_id=reference_id,
                storage=storage,
            )
        )
    if target_width > 0 and target_height > 0:
        if first_frame is not None:
            first_frame = _normalize_image_payload(first_frame, width=target_width, height=target_height)
        if last_frame is not None:
            last_frame = _normalize_image_payload(last_frame, width=target_width, height=target_height)
    if first_frame_id or last_frame_id or reference_ids:
        timing.mark("frame_media", stage_started_at)

    source_payload = first_frame or (references[0] if references else last_frame)
    source_width = int(source_payload.get("source_width") or source_payload.get("width") or 0) if source_payload else 0
    source_height = (
        int(source_payload.get("source_height") or source_payload.get("height") or 0) if source_payload else 0
    )
    persisted_params = {
        **generation_params,
        "first_frame_media_public_id": first_frame_id,
        "last_frame_media_public_id": last_frame_id,
        "reference_media_public_ids": reference_ids,
        "generation_mode": (generation_mode or "").strip(),
        "source_width": source_width,
        "source_height": source_height,
        "expected_width": target_width,
        "expected_height": target_height,
    }
    media = MediaAsset(
        project_id=int(project.id),
        user_public_id=user_public_id,
        media_type=MEDIA_TYPE_VIDEO,
        source=MEDIA_SOURCE_GENERATION,
        status=MEDIA_STATUS_PROCESSING,
        scope_type=scope_type.strip(),
        scope_public_id=scope_public_id.strip(),
        media_role=(media_role or MEDIA_ROLE_GENERATED).strip() or MEDIA_ROLE_GENERATED,
        model_id=resolved_model_id,
        prompt=final_prompt,
        params=_dump_params(persisted_params),
        task_job_public_id=task_job_public_id.strip(),
        task_item_public_id=task_item_public_id.strip(),
    )
    session.add(media)
    await session.flush()

    resolved_gateway = gateway or build_media_gateway(MEDIA_TYPE_VIDEO)
    gen_kwargs: dict[str, Any] = {key: value for key, value in generation_params.items() if value not in (None, "")}
    if first_frame is not None:
        gen_kwargs["first_frame"] = first_frame
    if last_frame is not None:
        gen_kwargs["last_frame"] = last_frame
    if references:
        gen_kwargs["references"] = references

    try:
        stage_started_at = perf_counter()
        output: MediaGenerationOutput = await resolved_gateway.generate_video(
            model_id=resolved_model_id,
            prompt=final_prompt,
            **gen_kwargs,
        )
        timing.mark("video_model", stage_started_at)
        if target_width > 0 and target_height > 0 and (output.width, output.height) != (
            target_width,
            target_height,
        ):
            raise MediaServiceError(
                "生成视频尺寸与正式分镜图不一致："
                f"期望 {target_width}x{target_height}，实际 {int(output.width or 0)}x{int(output.height or 0)}"
            )
        stage_started_at = perf_counter()
        data = await _resolve_media_bytes(output, timeout=_generation_timeout_for(MEDIA_TYPE_VIDEO))
        timing.mark("media_bytes", stage_started_at)

        media.mime_type = (output.mime_type or "").strip().lower() or _DEFAULT_MIME_BY_TYPE[MEDIA_TYPE_VIDEO]
        media.width = int(output.width or 0)
        media.height = int(output.height or 0)
        media.duration_ms = int(output.duration_ms or 0)
        media.seed = str(output.seed or "")
        media.usage = json.dumps({"usage": output.usage, "cost": output.cost}, ensure_ascii=False)
        media.cost_tokens = _cost_tokens_from_usage(output.usage)
        stage_started_at = perf_counter()
        await _store_media_bytes(
            storage,
            media,
            project_public_id=project_public_id,
            data=data,
            ext=_ext_for(MEDIA_TYPE_VIDEO, media.mime_type, output.url),
        )
        media.status = MEDIA_STATUS_READY
        session.add(media)
        await session.flush()
        timing.mark("media_write", stage_started_at)
    except (ProviderModelGatewayError, MediaServiceError) as exc:
        media.status = MEDIA_STATUS_FAILED
        media.error_message = str(exc)
        session.add(media)
        await session.flush()
        raise MediaServiceError(
            f"视频生成失败：{exc}",
            result={
                "media_public_id": media.public_id,
                "model_id": resolved_model_id,
                "prompt": final_prompt,
                "media_timing": timing.payload(),
            },
        ) from exc

    output_summary = {
        "media_public_id": media.public_id,
        "url": media.url,
        "mime_type": media.mime_type,
        "width": media.width,
        "height": media.height,
        "duration_ms": media.duration_ms,
        "seed": media.seed,
        "usage": output.usage,
        "cost": output.cost,
        "first_frame_media_public_id": first_frame_id,
        "last_frame_media_public_id": last_frame_id,
        "reference_media_public_ids": reference_ids,
    }
    output_text = json.dumps(output_summary, ensure_ascii=False)
    return {
        "media": media,
        "media_public_id": media.public_id,
        "model_id": resolved_model_id,
        "prompt": final_prompt,
        "url": media.url,
        "raw_output": output_text,
        "output_text": output_text,
        "media_timing": timing.payload(),
    }


async def build_video_generation_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    prompt: str,
    params: dict[str, Any] | None = None,
    first_frame_media_public_id: str = "",
    last_frame_media_public_id: str = "",
    reference_media_public_ids: list[str] | None = None,
    scope_type: str = "",
    scope_public_id: str = "",
    count: int = 1,
) -> list[TaskItemCreate]:
    """构造视频生成任务子项；count 段 → count 个子项独立执行与计费。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    resolved_model_id = str(model_id or project.video_model or "").strip()
    if not resolved_model_id:
        raise MediaServiceError("项目未绑定视频模型，请先在项目设置中选择视频模型", retryable=False)
    final_prompt = (prompt or "").strip()
    if not final_prompt:
        raise MediaServiceError("视频生成提示词不能为空", retryable=False)
    normalized_count = max(1, min(4, int(count)))
    scope_key = scope_public_id.strip() or "project"
    items: list[TaskItemCreate] = []
    for index in range(normalized_count):
        items.append(
            TaskItemCreate(
                item_type=MEDIA_VIDEO_GENERATION_TASK_TYPE,
                item_key=f"media-video:{scope_key}:{index}",
                payload={
                    "project_public_id": project_public_id,
                    "current_user_public_id": user_public_id,
                    "model_id": resolved_model_id,
                    "prompt": final_prompt,
                    "params": dict(params or {}),
                    "first_frame_media_public_id": first_frame_media_public_id.strip(),
                    "last_frame_media_public_id": last_frame_media_public_id.strip(),
                    "reference_media_public_ids": _dedupe_text_list(reference_media_public_ids),
                    "scope_type": scope_type.strip(),
                    "scope_public_id": scope_public_id.strip(),
                },
            )
        )
    return items


async def submit_video_generation_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str = "",
    prompt: str,
    params: dict[str, Any] | None = None,
    first_frame_media_public_id: str = "",
    last_frame_media_public_id: str = "",
    reference_media_public_ids: list[str] | None = None,
    scope_type: str = "",
    scope_public_id: str = "",
    count: int = 1,
    name: str = "",
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交视频生成异步任务；一个 job 可含多段候选子项。"""

    items = await build_video_generation_task_items(
        session,
        project_public_id,
        user_public_id,
        model_id=model_id,
        prompt=prompt,
        params=params,
        first_frame_media_public_id=first_frame_media_public_id,
        last_frame_media_public_id=last_frame_media_public_id,
        reference_media_public_ids=reference_media_public_ids,
        scope_type=scope_type,
        scope_public_id=scope_public_id,
        count=count,
    )
    job_name = name.strip() or ("视频生成" if len(items) == 1 else f"视频候选生成：{len(items)} 段")
    resolved_engine = engine or default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=MEDIA_VIDEO_GENERATION_TASK_TYPE,
            queue_name=MEDIA_GENERATION_QUEUE_NAME,
            name=job_name,
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": str(items[0].payload.get("model_id") or ""),
                "count": len(items),
                "scope_type": scope_type.strip(),
                "scope_public_id": scope_public_id.strip(),
            },
            items=items,
        ),
    )


# ---------------------------------------------------------------------------
# 资产生图闭环：提示词合成
# ---------------------------------------------------------------------------

def load_asset_image_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取资产生图专业提示词合成提示词。"""

    prompt_name = settings.asset_image_prompt_name.strip()
    if not prompt_name:
        raise asset_service.AssetServiceError("资产生图提示词名称未配置")
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(prompt_name)
    except PromptRegistryError as exc:
        raise asset_service.AssetServiceError(str(exc)) from exc


def build_asset_image_prompt(asset: Asset) -> str:
    """从资产结构化字段拼接题材中立的图像生成提示词。"""

    parts: list[str] = []
    name = (asset.name or "").strip()
    if name:
        parts.append(name)
    summary = (asset.summary or "").strip()
    if summary:
        parts.append(summary)
    for field_name in ("description", "details", "accessories"):
        mapping = asset_service._parse_object_field(getattr(asset, field_name))
        rendered = "，".join(
            f"{key}：{value}" for key, value in mapping.items() if str(value or "").strip()
        )
        if rendered:
            parts.append(rendered)
    colors = (asset.colors or "").strip()
    if colors:
        parts.append(f"色彩：{colors}")
    keyword = (asset.keyword or "").strip()
    if keyword:
        parts.append(f"风格：{keyword}")
    return "。".join(parts).strip()


def _build_derivative_edit_prompt(prompt: str, *, asset: Asset, reference_count: int) -> str:
    """为衍生资产编辑图补充父级参考图一致性约束。"""

    base_prompt = (prompt or "").strip()
    name = str(getattr(asset, "name", "") or "").strip()
    variant_label = str(getattr(asset, "variant_label", "") or "").strip()
    summary = str(getattr(asset, "summary", "") or "").strip()
    asset_bits = [item for item in (name, variant_label, summary) if item]
    asset_context = "；".join(asset_bits) if asset_bits else "当前衍生资产"
    count_text = max(1, int(reference_count))

    return (
        "你正在基于父级参考图生成同一资产的衍生状态图。"
        f"已提供 {count_text} 张父级参考图，这些图片是强约束，不是普通灵感参考。\n\n"
        "必须保留父级参考图中的主体身份、物体结构或场景布局，以及五官/脸型、体型比例、发型、"
        "服装轮廓、配饰、主色、材质、构图语言和整体画风的一致性。\n"
        "只允许根据当前衍生资产描述调整变体差异，例如表情、姿态、伤痕、战损、服装细节、"
        "道具状态、年龄阶段或环境状态、环境延伸、镜头变化。不要创建全新角色、全新物体，不能出现无关道具、人物或场景。\n"
        "当文字描述与父级参考图冲突时，以父级参考图的视觉身份和设定为准，文字只用于表达衍生差异。\n\n"
        f"当前衍生资产：{asset_context}\n\n"
        f"当前衍生资产提示词：\n{base_prompt}"
    ).strip()


def _image_edit_parameters_for_model(model_id: str) -> dict[str, Any]:
    """返回当前模型适用的图片编辑增强参数；仅 GPT Image 1 系列需要显式高保真。"""

    normalized = (model_id or "").strip().lower()
    if normalized == "gpt-image-1" or normalized.startswith(("gpt-image-1-", "gpt-image-1.")):
        return {"input_fidelity": "high"}
    return {}


def _asset_prompt_payload(asset: Asset) -> dict[str, Any]:
    """把资产结构化字段整理为提示词合成输入。"""

    return {
        "assetType": asset.asset_type,
        "name": asset.name,
        "summary": asset.summary or "",
        "keyword": asset.keyword or "",
        "colors": asset.colors or "",
        "description": asset_service._parse_object_field(asset.description),
        "details": asset_service._parse_object_field(asset.details),
        "accessories": asset_service._parse_object_field(asset.accessories),
    }


def _target_sheet_label(asset_type: str) -> str:
    """按资产类型给出设定图目标。"""

    if asset_type == "scene":
        return "场景四视图设定图"
    if asset_type == "role":
        return "人物三视图设定图"
    if asset_type == "prop":
        return "道具多视图设定图"
    if asset_type == "faction":
        return "势力视觉设定图"
    return "资产设定图"


def _strip_prompt_fence(text: str) -> str:
    """清理模型偶发输出的代码围栏，只保留提示词文本。"""

    value = (text or "").strip()
    fenced = re.fullmatch(r"```(?:text|markdown|md)?\s*(.*?)```", value, re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    return value


def _resolve_art_style_text(project: Any) -> str:
    """读取项目 art_style 对应视觉风格 Markdown 内容；缺失或非法时返回空文本。"""

    style_path = str(getattr(project, "art_style", "") or "").strip()
    if not style_path or not _STYLE_PATH_PATTERN.fullmatch(style_path) or style_path in {".", ".."}:
        return ""
    configured = Path(settings.visual_style_root).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    root = root.resolve()
    style_dir = (root / style_path).resolve()
    try:
        style_dir.relative_to(root)
    except ValueError:
        return ""
    if not style_dir.is_dir():
        return ""
    contents: list[str] = []
    readme = style_dir / "README.md"
    paths = [readme] if readme.is_file() else []
    paths.extend(path for path in sorted(style_dir.glob("*.md")) if path.is_file() and path != readme)
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if content:
            contents.append(f"## {path.name}\n{content}")
    return "\n\n".join(contents)


def build_asset_image_prompt_messages(
    *,
    asset: Asset,
    image_model_id: str,
    art_style_id: str,
    art_style_text: str,
) -> list[dict[str, str]]:
    """构建资产生图专业提示词合成消息。"""

    system = load_asset_image_prompt()
    asset_block = json.dumps(_asset_prompt_payload(asset), ensure_ascii=False, indent=2)
    user = (
        f"## 输出目标\n{_target_sheet_label(asset.asset_type)}\n\n"
        f"## 图像模型ID：{image_model_id}\n\n"
        f"## 艺术风格ID：{art_style_id or '未配置'}\n\n"
        f"## 艺术风格手册\n{art_style_text.strip() or '（未找到艺术风格手册）'}\n\n"
        f"## 当前资产结构化信息\n{asset_block}\n\n"
        "请只输出一条可直接提交给图像模型的专业正向提示词文本。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def synthesize_asset_image_prompt(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    gateway: Any | None = None,
) -> str:
    """使用项目绑定文本模型，为单个资产合成专业生图提示词。"""

    result = await synthesize_asset_image_prompt_detail(
        session,
        project_public_id,
        user_public_id,
        asset_public_id=asset_public_id,
        gateway=gateway,
    )
    return str(result.get("prompt") or "")


async def synthesize_asset_image_prompt_detail(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    gateway: Any | None = None,
) -> dict[str, Any]:
    """使用项目绑定文本模型，为单个资产合成专业生图提示词并返回诊断信息。"""

    timing = _MediaTiming()
    stage_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    timing.mark("project_lookup", stage_started_at)
    text_model_id = str(project.text_model or "").strip()
    image_model_id = str(project.image_model or "").strip()
    if not text_model_id:
        raise asset_service.AssetServiceError("项目未绑定文本模型，请先在项目设置中选择文本模型", retryable=False)
    if not image_model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型", retryable=False)

    stage_started_at = perf_counter()
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    timing.mark("asset_lookup", stage_started_at)

    stage_started_at = perf_counter()
    art_style_id = str(project.art_style or "").strip()
    messages = build_asset_image_prompt_messages(
        asset=asset,
        image_model_id=image_model_id,
        art_style_id=art_style_id,
        art_style_text=_resolve_art_style_text(project),
    )
    prompt_trace = asset_service._model_prompt_trace(model_id=text_model_id, messages=messages)
    timing.mark("prompt_build", stage_started_at)

    resolved_gateway = gateway or asset_service.build_asset_gateway()
    try:
        stage_started_at = perf_counter()
        output = await asset_service._generate_full_text(resolved_gateway, model_id=text_model_id, messages=messages)
        timing.mark("prompt_model", stage_started_at)
    except ProviderModelGatewayError as exc:
        timing.mark("prompt_model", stage_started_at)
        raise asset_service.AssetServiceError(
            f"资产生图提示词合成失败：{exc}",
            result={
                **prompt_trace,
                "asset_public_id": asset_public_id,
                "image_model_id": image_model_id,
                "art_style_id": art_style_id,
                "asset_timing": timing.payload(),
            },
        ) from exc

    stage_started_at = perf_counter()
    prompt = _strip_prompt_fence(output)
    timing.mark("prompt_parse", stage_started_at)
    result = {
        **prompt_trace,
        "asset_public_id": asset_public_id,
        "asset_name": asset.name,
        "model_id": text_model_id,
        "image_model_id": image_model_id,
        "art_style_id": art_style_id,
        "prompt": prompt,
        "raw_output": output,
        "output_text": prompt,
        "asset_timing": timing.payload(),
    }
    if not prompt:
        raise asset_service.AssetServiceError("资产生图提示词合成结果为空", result=result)
    return result


# ---------------------------------------------------------------------------
# 资产生图闭环：参考图 / 生成 / 封面 / 列举
# ---------------------------------------------------------------------------

async def _load_reference_media_files(
    session: AsyncSession,
    *,
    project_id: int,
    user_public_id: str,
    media_public_ids: list[str],
    storage: MediaStorage | None = None,
) -> list[dict[str, Any]]:
    """读取任务引用的参考图，供 images/edits multipart 调用。"""

    resolved_storage = storage or get_media_storage()
    images: list[dict[str, Any]] = []
    for media_public_id in _dedupe_text_list(media_public_ids):
        images.append(
            await _load_media_file_payload(
                session,
                project_id=project_id,
                user_public_id=user_public_id,
                media_public_id=media_public_id,
                storage=resolved_storage,
            )
        )
    return images


async def _parent_asset_id_for(session: AsyncSession, *, asset_id: int) -> int | None:
    """查找衍生资产绑定的主资产 ID。"""

    relation = (
        await session.exec(
            select(AssetRelation).where(
                AssetRelation.source_asset_id == asset_id,
                AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
            )
        )
    ).first()
    if relation is None:
        return None
    try:
        return int(relation.target_asset_id)
    except (TypeError, ValueError):
        return None


async def _latest_asset_image_media_public_ids(
    session: AsyncSession,
    *,
    project_id: int,
    user_public_id: str,
    asset_public_id: str,
    limit: int = 1,
) -> list[str]:
    """取指定资产可作为编辑参考的图片媒体，封面优先，其次最近生成图，最多 limit 张。"""

    rows = (
        await session.exec(
            select(MediaAsset)
            .where(
                MediaAsset.project_id == project_id,
                MediaAsset.scope_type == MEDIA_SCOPE_ASSET,
                MediaAsset.scope_public_id == asset_public_id,
                MediaAsset.user_public_id == user_public_id,
                MediaAsset.media_type == MEDIA_TYPE_IMAGE,
                MediaAsset.status == MEDIA_STATUS_READY,
                MediaAsset.media_role != MEDIA_ROLE_REFERENCE,
                MediaAsset.disabled_at.is_(None),
            )
            .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
        )
    ).all()
    if not rows:
        return []
    cover = next((media for media in rows if media.media_role == MEDIA_ROLE_FINAL), None)
    ordered = ([cover] if cover else []) + [media for media in rows if media is not cover]
    return [media.public_id for media in ordered[: max(limit, 1)]]


async def upload_asset_reference_image(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> MediaAsset:
    """上传本地参考图并保存为资产 reference 媒体。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    mime_type = (content_type or "").split(";", 1)[0].strip().lower()
    if mime_type not in _REFERENCE_IMAGE_MIME_TYPES:
        raise asset_service.AssetServiceError("参考图仅支持 PNG/JPEG/WebP")
    if not data:
        raise asset_service.AssetServiceError("参考图内容为空")
    if len(data) > _REFERENCE_IMAGE_MAX_BYTES:
        raise asset_service.AssetServiceError("参考图过大，最大支持 20MB")
    try:
        return await upload_media(
            session,
            project_public_id,
            user_public_id,
            filename=filename,
            content_type=mime_type,
            data=data,
            media_type=MEDIA_TYPE_IMAGE,
            scope_type=MEDIA_SCOPE_ASSET,
            scope_public_id=asset.public_id,
            media_role=MEDIA_ROLE_REFERENCE,
        )
    except MediaServiceError as exc:
        raise asset_service.AssetServiceError(str(exc)) from exc


async def generate_asset_image(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    model_id: str,
    prompt: str = "",
    aspect_ratio: str = "",
    image_size: str = "",
    reference_media_public_ids: list[str] | None = None,
    make_cover: bool = True,
    task_job_public_id: str = "",
    task_item_public_id: str = "",
    gateway: Any | None = None,
) -> dict[str, Any]:
    """为单个资产生成图像：写处理中媒体行 → 调网关 → 落盘置就绪 → 设封面。"""

    timing = _MediaTiming()
    stage_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    timing.mark("project_lookup", stage_started_at)
    model_id = str(model_id or project.image_model or "").strip()
    if not model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型", retryable=False)

    stage_started_at = perf_counter()
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    timing.mark("asset_lookup", stage_started_at)

    resolved_gateway = gateway or build_media_gateway(MEDIA_TYPE_IMAGE)
    final_prompt = (prompt or "").strip()
    prompt_trace: dict[str, Any] = {
        "model_id": model_id,
        "messages": [],
        "composed_prompt": final_prompt,
        "prompt": final_prompt,
    }
    if not final_prompt:
        stage_started_at = perf_counter()
        prompt_result = await synthesize_asset_image_prompt_detail(
            session,
            project_public_id,
            user_public_id,
            asset_public_id=asset_public_id,
        )
        final_prompt = str(prompt_result.get("prompt") or "").strip()
        prompt_trace = {
            "model_id": model_id,
            "messages": prompt_result.get("messages") or [],
            "composed_prompt": str(prompt_result.get("composed_prompt") or ""),
            "prompt": final_prompt,
            "prompt_model_id": str(prompt_result.get("model_id") or ""),
            "image_model_id": str(prompt_result.get("image_model_id") or model_id),
        }
        timing.mark("prompt_synthesis", stage_started_at)
    if not final_prompt:
        raise asset_service.AssetServiceError(
            "资产信息不足以生成图像提示词",
            result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
                retryable=False,
        )

    # 衍生判定以 child_of 父绑定为唯一事实来源：main_asset 标记由抽取模型输出、
    # 缺失时默认 False，不能让未绑定父级的普通资产被误判为衍生而无法生图。
    parent_asset_id = await _parent_asset_id_for(session, asset_id=int(asset.id))
    is_derivative_asset = parent_asset_id is not None
    reference_media_ids = _dedupe_text_list(reference_media_public_ids) if is_derivative_asset else []
    if is_derivative_asset and not reference_media_ids:
        stage_started_at = perf_counter()
        parent_asset = await session.get(Asset, parent_asset_id)
        if parent_asset is None:
            raise asset_service.AssetServiceError(
                "衍生资产绑定的主资产不存在",
                result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
                retryable=False,
            )
        reference_media_ids = await _latest_asset_image_media_public_ids(
            session,
            project_id=int(project.id),
            user_public_id=user_public_id,
            asset_public_id=parent_asset.public_id,
        )
        timing.mark("parent_reference_media", stage_started_at)
        if not reference_media_ids:
            raise asset_service.AssetServiceError(
                "请先为主资产生成配图，再生成衍生资产图",
                result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
                retryable=False,
            )
    reference_images: list[dict[str, Any]] = []
    if reference_media_ids:
        stage_started_at = perf_counter()
        try:
            reference_images = await _load_reference_media_files(
                session,
                project_id=int(project.id),
                user_public_id=user_public_id,
                media_public_ids=reference_media_ids,
            )
        except MediaServiceError as exc:
            raise asset_service.AssetServiceError(
                str(exc),
                result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
                retryable=exc.retryable,
            ) from exc
        timing.mark("reference_media", stage_started_at)
        if not reference_images:
            raise asset_service.AssetServiceError(
                "请选择至少一张参考图",
                result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
                retryable=False,
            )

    model_prompt = final_prompt
    edit_parameters = _image_edit_parameters_for_model(model_id) if reference_images else {}
    if reference_images and is_derivative_asset:
        model_prompt = _build_derivative_edit_prompt(
            final_prompt,
            asset=asset,
            reference_count=len(reference_images),
        )
        prompt_trace = {
            **prompt_trace,
            "base_prompt": final_prompt,
            "prompt": model_prompt,
            "reference_prompt_mode": "derivative_edit",
        }

    stage_started_at = perf_counter()
    generation_mode = "edit" if reference_images else "generate"
    media = MediaAsset(
        project_id=int(project.id),
        user_public_id=user_public_id,
        media_type=MEDIA_TYPE_IMAGE,
        source=MEDIA_SOURCE_GENERATION,
        status=MEDIA_STATUS_PROCESSING,
        scope_type=MEDIA_SCOPE_ASSET,
        scope_public_id=asset.public_id,
        media_role=MEDIA_ROLE_GENERATED,
        model_id=model_id,
        prompt=model_prompt,
        params=_dump_params(
            {
                "aspect_ratio": aspect_ratio.strip(),
                "image_size": image_size.strip(),
                "mode": generation_mode,
                "reference_media_public_ids": reference_media_ids,
                **edit_parameters,
            }
        ),
        task_job_public_id=task_job_public_id.strip(),
        task_item_public_id=task_item_public_id.strip(),
    )
    session.add(media)
    await session.flush()
    timing.mark("media_record", stage_started_at)

    gen_kwargs: dict[str, Any] = {}
    if aspect_ratio.strip():
        gen_kwargs["aspect_ratio"] = aspect_ratio.strip()
    if image_size.strip():
        gen_kwargs["image_size"] = image_size.strip()
    try:
        stage_started_at = perf_counter()
        if reference_images:
            output = await resolved_gateway.edit_image(
                model_id=model_id,
                prompt=model_prompt,
                images=reference_images,
                **edit_parameters,
                **gen_kwargs,
            )
        else:
            output = await resolved_gateway.generate_image(model_id=model_id, prompt=model_prompt, **gen_kwargs)
        timing.mark("image_model", stage_started_at)
        stage_started_at = perf_counter()
        data = await _resolve_media_bytes(output, timeout=_generation_timeout_for(MEDIA_TYPE_IMAGE))
        timing.mark("media_bytes", stage_started_at)

        media.mime_type = (output.mime_type or "").strip().lower() or "image/png"
        media.width = int(output.width or 0)
        media.height = int(output.height or 0)
        media.seed = str(output.seed or "")
        media.usage = json.dumps({"usage": output.usage, "cost": output.cost}, ensure_ascii=False)
        media.cost_tokens = _cost_tokens_from_usage(output.usage)
        stage_started_at = perf_counter()
        await _store_media_bytes(
            get_media_storage(),
            media,
            project_public_id=project_public_id,
            data=data,
            ext=_ext_for(MEDIA_TYPE_IMAGE, media.mime_type, output.url),
        )
        media.status = MEDIA_STATUS_READY
        session.add(media)
        await session.flush()
        timing.mark("media_write", stage_started_at)
    except (ProviderModelGatewayError, MediaServiceError, asset_service.AssetServiceError) as exc:
        media.status = MEDIA_STATUS_FAILED
        media.error_message = str(exc)
        session.add(media)
        await session.flush()
        raise asset_service.AssetServiceError(
            f"图像生成失败：{exc}",
            result={
                **prompt_trace,
                "asset_public_id": asset_public_id,
                "media_public_id": media.public_id,
                "asset_timing": timing.payload(),
            },
        ) from exc

    if make_cover:
        stage_started_at = perf_counter()
        await _lock_asset_cover_row(session, asset_public_id=asset.public_id)
        existing_cover = (
            await session.exec(
                select(MediaAsset).where(
                    MediaAsset.scope_type == MEDIA_SCOPE_ASSET,
                    MediaAsset.scope_public_id == asset.public_id,
                    MediaAsset.media_role == MEDIA_ROLE_FINAL,
                    MediaAsset.public_id != media.public_id,
                    MediaAsset.disabled_at.is_(None),
                )
            )
        ).first()
        if existing_cover is None:
            await _set_cover_media(session, asset_public_id=asset.public_id, media=media)
        timing.mark("cover_update", stage_started_at)

    output_summary = {
        "media_public_id": media.public_id,
        "url": media.url,
        "mime_type": media.mime_type,
        "width": media.width,
        "height": media.height,
        "duration_ms": output.duration_ms,
        "seed": output.seed,
        "usage": output.usage,
        "cost": output.cost,
        "mode": generation_mode,
        "reference_media_public_ids": reference_media_ids,
    }
    output_text = json.dumps(output_summary, ensure_ascii=False)
    return {
        "media": media,
        **prompt_trace,
        "model_id": model_id,
        "asset_public_id": asset_public_id,
        "media_public_id": media.public_id,
        "reference_media_public_ids": reference_media_ids,
        "url": media.url,
        "raw_output": output_text,
        "output_text": output_text,
        "asset_timing": timing.payload(),
    }


async def _lock_asset_cover_row(session: AsyncSession, *, asset_public_id: str) -> None:
    """封面互斥：锁定资产行，串行化并发任务子项的封面查改。

    同一 job 的多个生图子项由 worker 并发执行，check-then-act 查封面存在
    双写竞态；PostgreSQL 下行锁强制串行，SQLite 无行锁但单写者天然串行。
    """

    await session.exec(select(Asset).where(Asset.public_id == asset_public_id).with_for_update())


async def _set_cover_media(session: AsyncSession, *, asset_public_id: str, media: MediaAsset) -> None:
    """把指定 media 设为资产封面（media_role=final），同资产其它封面降级。"""

    existing = (
        await session.exec(
            select(MediaAsset).where(
                MediaAsset.scope_type == MEDIA_SCOPE_ASSET,
                MediaAsset.scope_public_id == asset_public_id,
                MediaAsset.media_role == MEDIA_ROLE_FINAL,
            )
        )
    ).all()
    for item in existing:
        if item.public_id != media.public_id:
            item.media_role = MEDIA_ROLE_GENERATED
            session.add(item)
    media.media_role = MEDIA_ROLE_FINAL
    session.add(media)
    await session.flush()


async def set_asset_cover(
    session: AsyncSession, project_public_id: str, user_public_id: str, media_public_id: str
) -> MediaAsset:
    """把指定媒体设为其所属资产的封面。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    media = await _load_media_or_raise(session, int(project.id), user_public_id, media_public_id)
    if media.scope_type != MEDIA_SCOPE_ASSET or not media.scope_public_id:
        raise MediaServiceError("该媒体未挂靠资产，无法设为封面")
    if media.media_type != MEDIA_TYPE_IMAGE or media.status != MEDIA_STATUS_READY:
        raise MediaServiceError("仅已就绪的图片可设为封面")
    await _lock_asset_cover_row(session, asset_public_id=media.scope_public_id)
    await _set_cover_media(session, asset_public_id=media.scope_public_id, media=media)
    return media


async def list_asset_media(
    session: AsyncSession, project_public_id: str, user_public_id: str, asset_public_id: str
) -> list[MediaAsset]:
    """列出某资产的就绪媒体，按创建时间倒序。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    statement = (
        select(MediaAsset)
        .where(
            MediaAsset.scope_type == MEDIA_SCOPE_ASSET,
            MediaAsset.scope_public_id == asset.public_id,
            MediaAsset.user_public_id == user_public_id,
            MediaAsset.status == MEDIA_STATUS_READY,
            MediaAsset.disabled_at.is_(None),
        )
        .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
    )
    return list((await session.exec(statement)).all())


async def delete_asset_media(
    session: AsyncSession, project_public_id: str, user_public_id: str, media_public_id: str
) -> None:
    """删除单个资产媒体：清存储对象并删行。"""

    await delete_media_asset(session, project_public_id, user_public_id, media_public_id)


async def delete_media_for_assets(session: AsyncSession, asset_public_ids: list[str]) -> None:
    """删除一组资产挂靠的全部媒体（用于资产级联删除）。"""

    await delete_media_for_scope(
        session,
        scope_type=MEDIA_SCOPE_ASSET,
        scope_public_ids=asset_public_ids,
    )


async def cover_urls_for(
    session: AsyncSession, project_id: int, user_public_id: str, assets: list[Asset]
) -> dict[str, str]:
    """批量取每个资产的封面 url（final 优先，回退最近一张图像），避免 N+1。"""

    result: dict[str, str] = {}
    asset_public_ids = [a.public_id for a in assets if a.public_id]
    if not asset_public_ids:
        return result
    rows = (
        await session.exec(
            select(MediaAsset)
            .where(
                MediaAsset.project_id == project_id,
                MediaAsset.scope_type == MEDIA_SCOPE_ASSET,
                MediaAsset.scope_public_id.in_(asset_public_ids),
                MediaAsset.user_public_id == user_public_id,
                MediaAsset.media_type == MEDIA_TYPE_IMAGE,
                MediaAsset.status == MEDIA_STATUS_READY,
                MediaAsset.media_role != MEDIA_ROLE_REFERENCE,
                MediaAsset.disabled_at.is_(None),
            )
            .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
        )
    ).all()
    by_asset: dict[str, list[MediaAsset]] = {}
    for media in rows:
        by_asset.setdefault(media.scope_public_id, []).append(media)
    for asset_public_id, medias in by_asset.items():
        cover = next((m for m in medias if m.media_role == MEDIA_ROLE_FINAL), medias[0])
        if cover.url:
            result[asset_public_id] = cover.url
    return result


# ---------------------------------------------------------------------------
# 资产生图闭环：异步任务提交
# ---------------------------------------------------------------------------

async def build_image_prompt_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
) -> list[TaskItemCreate]:
    """为单个资产构造生图专业提示词合成子项。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    text_model_id = str(project.text_model or "").strip()
    image_model_id = str(project.image_model or "").strip()
    if not text_model_id:
        raise asset_service.AssetServiceError("项目未绑定文本模型，请先在项目设置中选择文本模型", retryable=False)
    if not image_model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型", retryable=False)
    normalized_asset_public_id = str(asset_public_id or "").strip()
    if not normalized_asset_public_id:
        raise asset_service.AssetServiceError("缺少资产 ID", retryable=False)
    asset = await asset_service.load_asset_or_raise(
        session,
        int(project.id),
        user_public_id,
        normalized_asset_public_id,
    )
    return [
        TaskItemCreate(
            item_type=ASSET_IMAGE_PROMPT_TASK_TYPE,
            item_key=f"asset-image-prompt:{normalized_asset_public_id}",
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": text_model_id,
                "image_model_id": image_model_id,
                "asset_public_id": normalized_asset_public_id,
                "asset_name": asset.name,
            },
        )
    ]


async def submit_asset_image_prompt_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交单个资产的生图专业提示词合成异步任务。"""

    items = await build_image_prompt_task_items(
        session,
        project_public_id,
        user_public_id,
        asset_public_id=asset_public_id,
    )
    item_payload = items[0].payload
    asset_name = str(item_payload.get("asset_name") or "").strip()
    resolved_engine = engine or default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=ASSET_IMAGE_PROMPT_TASK_TYPE,
            queue_name=MEDIA_GENERATION_QUEUE_NAME,
            name=f"资产生图提示词生成：{asset_name}" if asset_name else "资产生图提示词生成",
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": str(item_payload.get("model_id") or ""),
                "asset_public_id": str(item_payload.get("asset_public_id") or ""),
            },
            items=items,
        ),
    )


async def build_image_generation_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    asset_public_ids: list[str],
    prompt: str = "",
    aspect_ratio: str = "",
    image_size: str = "",
    reference_media_public_ids: list[str] | None = None,
    count: int = 1,
) -> list[TaskItemCreate]:
    """按资产构造图像生成子项，逐个校验资产存在；count 张 → 每资产 count 个子项。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    resolved_model_id = str(model_id or project.image_model or "").strip()
    if not resolved_model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型", retryable=False)
    normalized_count = max(1, min(4, int(count)))
    reference_media_ids = _dedupe_text_list(reference_media_public_ids)
    resolved_asset_public_ids = asset_service._dedupe_public_ids(asset_public_ids)
    # 显式参考图属于单个衍生资产的父级图，复制进多个资产子项会交叉污染出图；
    # 多资产批量提交时各子项在执行期各自回退父级参考图。
    if reference_media_ids and len(resolved_asset_public_ids) > 1:
        raise asset_service.AssetServiceError("显式参考图仅支持单个资产提交，批量生成请清空参考图选择", retryable=False)
    items: list[TaskItemCreate] = []
    for asset_public_id in resolved_asset_public_ids:
        asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
        for index in range(normalized_count):
            items.append(
                TaskItemCreate(
                    item_type=ASSET_IMAGE_GENERATION_TASK_TYPE,
                    item_key=f"asset-image:{asset_public_id}:{index}",
                    payload={
                        "project_public_id": project_public_id,
                        "current_user_public_id": user_public_id,
                        "model_id": resolved_model_id,
                        "asset_public_id": asset_public_id,
                        "asset_name": asset.name,
                        "prompt": prompt,
                        "aspect_ratio": aspect_ratio,
                        "image_size": image_size,
                        "reference_media_public_ids": reference_media_ids,
                    },
                )
            )
    return items


async def submit_asset_image_generation_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    asset_public_ids: list[str],
    prompt: str = "",
    aspect_ratio: str = "",
    image_size: str = "",
    reference_media_public_ids: list[str] | None = None,
    count: int = 1,
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交资产图像生成异步任务；一个 job 可含多个资产 × 多张子项。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    model_id = str(model_id or project.image_model or "").strip()
    if not model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型", retryable=False)
    reference_media_ids = _dedupe_text_list(reference_media_public_ids)
    items = await build_image_generation_task_items(
        session,
        project_public_id,
        user_public_id,
        model_id=model_id,
        asset_public_ids=asset_public_ids,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        reference_media_public_ids=reference_media_ids,
        count=count,
    )
    if not items:
        raise asset_service.AssetServiceError("没有可用于图像生成的资产")

    job_name = "资产配图生成" if len(items) == 1 else f"资产批量配图：{len(items)} 张"
    resolved_engine = engine or default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=ASSET_IMAGE_GENERATION_TASK_TYPE,
            queue_name=MEDIA_GENERATION_QUEUE_NAME,
            name=job_name,
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": model_id,
                "asset_count": len(items),
                "reference_media_count": len(reference_media_ids),
            },
            items=items,
        ),
    )