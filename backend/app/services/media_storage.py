"""媒体对象存储抽象层：统一本地磁盘与 S3 兼容 OSS 的 put/get/url/delete。

默认本地磁盘后端零依赖、开箱即用并可单测；S3 后端用于生产横向扩展，
boto3 惰性导入——未安装时仅在选用 S3 后端时报错，不影响其余功能与测试。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.core.config import media_root_path, settings


class MediaStorageError(Exception):
    """媒体存储读写失败。"""


@dataclass(frozen=True)
class StoredObject:
    """存储成功后的对象元信息。"""

    key: str
    backend: str
    size: int
    content_type: str


def normalize_storage_key(key: str) -> str:
    """规整存储键并阻止路径逃逸。"""
    normalized = key.strip().lstrip("/").replace("\\", "/")
    if not normalized:
        raise MediaStorageError("存储键不能为空")
    parts = [segment for segment in normalized.split("/") if segment not in ("", ".")]
    if any(segment == ".." for segment in parts):
        raise MediaStorageError("存储键不能包含上级目录引用")
    return "/".join(parts)


class MediaStorage:
    """媒体存储后端抽象基类。"""

    backend_name = ""
    supports_public_url = False

    async def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> StoredObject:
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    def public_url(self, key: str) -> str:
        """返回可直接访问的公网 URL；不支持时返回空串，由上层回退到内容接口。"""
        return ""

    def local_path(self, key: str) -> Path | None:
        """返回本地文件路径；非本地后端返回 None，由上层改走字节流。"""
        return None


class LocalDiskMediaStorage(MediaStorage):
    """本地磁盘媒体存储：产物落媒体根目录下的相对键路径。"""

    backend_name = "local"

    def __init__(self, root: Path, *, public_base: str = "") -> None:
        self.root = root
        self.public_base = public_base.strip().rstrip("/")
        self.supports_public_url = bool(self.public_base)

    def _path(self, key: str) -> Path:
        path = (self.root / normalize_storage_key(key)).resolve()
        root = self.root.resolve()
        if root != path and root not in path.parents:
            raise MediaStorageError("存储路径逃逸媒体根目录")
        return path

    async def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> StoredObject:
        path = self._path(key)

        def _write() -> int:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return len(data)

        try:
            size = await asyncio.to_thread(_write)
        except OSError as exc:
            raise MediaStorageError(f"写入本地媒体文件失败：{exc}") from exc
        return StoredObject(key=normalize_storage_key(key), backend=self.backend_name, size=size, content_type=content_type)

    async def get(self, key: str) -> bytes:
        path = self._path(key)

        def _read() -> bytes:
            return path.read_bytes()

        try:
            return await asyncio.to_thread(_read)
        except FileNotFoundError as exc:
            raise MediaStorageError("媒体文件不存在") from exc
        except OSError as exc:
            raise MediaStorageError(f"读取本地媒体文件失败：{exc}") from exc

    async def delete(self, key: str) -> None:
        path = self._path(key)

        def _unlink() -> None:
            path.unlink(missing_ok=True)

        await asyncio.to_thread(_unlink)

    async def exists(self, key: str) -> bool:
        path = self._path(key)
        return await asyncio.to_thread(path.exists)

    def public_url(self, key: str) -> str:
        if not self.public_base:
            return ""
        return f"{self.public_base}/{normalize_storage_key(key)}"

    def local_path(self, key: str) -> Path | None:
        try:
            return self._path(key)
        except MediaStorageError:
            return None


class S3MediaStorage(MediaStorage):
    """S3 兼容对象存储：boto3 惰性导入，同步调用包装到线程池。"""

    backend_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str = "",
        region: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        public_base: str = "",
        addressing_style: str = "virtual",
    ) -> None:
        if not bucket.strip():
            raise MediaStorageError("启用 S3 媒体存储必须配置 bucket")
        self.bucket = bucket.strip()
        self.endpoint_url = endpoint_url.strip()
        self.region = region.strip()
        self.access_key_id = access_key_id.strip()
        self.secret_access_key = secret_access_key.strip()
        self.public_base = public_base.strip().rstrip("/")
        self.addressing_style = addressing_style.strip() or "virtual"
        self.supports_public_url = True

    def _build_client(self):
        try:
            import boto3  # 惰性导入：仅 S3 后端需要
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - 取决于部署环境是否安装 boto3
            raise MediaStorageError("启用 S3 媒体存储需安装 boto3 依赖") from exc
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url or None,
            region_name=self.region or None,
            aws_access_key_id=self.access_key_id or None,
            aws_secret_access_key=self.secret_access_key or None,
            config=Config(s3={"addressing_style": self.addressing_style}),
        )

    async def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> StoredObject:
        normalized = normalize_storage_key(key)

        def _upload() -> None:
            client = self._build_client()
            client.put_object(Bucket=self.bucket, Key=normalized, Body=data, ContentType=content_type)

        try:
            await asyncio.to_thread(_upload)
        except MediaStorageError:
            raise
        except Exception as exc:  # pragma: no cover - 取决于线上 S3 可用性
            raise MediaStorageError(f"上传 S3 媒体对象失败：{exc}") from exc
        return StoredObject(key=normalized, backend=self.backend_name, size=len(data), content_type=content_type)

    async def get(self, key: str) -> bytes:
        normalized = normalize_storage_key(key)

        def _download() -> bytes:
            client = self._build_client()
            response = client.get_object(Bucket=self.bucket, Key=normalized)
            return response["Body"].read()

        try:
            return await asyncio.to_thread(_download)
        except MediaStorageError:
            raise
        except Exception as exc:  # pragma: no cover - 取决于线上 S3 可用性
            raise MediaStorageError(f"读取 S3 媒体对象失败：{exc}") from exc

    async def delete(self, key: str) -> None:
        normalized = normalize_storage_key(key)

        def _delete() -> None:
            client = self._build_client()
            client.delete_object(Bucket=self.bucket, Key=normalized)

        try:
            await asyncio.to_thread(_delete)
        except MediaStorageError:
            raise
        except Exception as exc:  # pragma: no cover - 取决于线上 S3 可用性
            raise MediaStorageError(f"删除 S3 媒体对象失败：{exc}") from exc

    async def exists(self, key: str) -> bool:
        normalized = normalize_storage_key(key)

        def _head() -> bool:
            client = self._build_client()
            try:
                client.head_object(Bucket=self.bucket, Key=normalized)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_head)

    def public_url(self, key: str) -> str:
        normalized = normalize_storage_key(key)
        if self.public_base:
            return f"{self.public_base}/{normalized}"
        if self.endpoint_url:
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket}/{normalized}"
        return ""

class OSS2MediaStorage(MediaStorage):
    """阿里云 oss 兼容对象存储：oss2 惰性导入，同步调用包装到线程池。"""

    backend_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str = "",
        region: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        public_base: str = "",
        addressing_style: str = "virtual",
    ) -> None:
        if not bucket.strip():
            raise MediaStorageError("启用 S3 媒体存储必须配置 bucket")
        self.bucket = bucket.strip()
        self.endpoint_url = endpoint_url.strip()
        self.region = region.strip()
        self.access_key_id = access_key_id.strip()
        self.secret_access_key = secret_access_key.strip()
        self.public_base = public_base.strip().rstrip("/")
        self.addressing_style = addressing_style.strip() or "virtual"
        self.supports_public_url = True
        self.oss2 = self._oss2

    @property
    def _oss2(self):
        try:
            import alibabacloud_oss_v2 as oss2  # 惰性导入oss2
        except ImportError as exc:  # pragma: no cover - 取决于部署环境是否安装 boto3
            raise MediaStorageError("启用 oss 媒体存储需安装 alibabacloud_oss_v2 依赖") from exc
        return oss2

    def _build_client(self):
        credentials_provider = self.oss2.credentials.EnvironmentVariableCredentialsProvider()
        cfg = self.oss2.config.load_default()
        cfg.credentials_provider = credentials_provider
        cfg.region = self.region
        if self.endpoint_url is not None:
            cfg.endpoint = self.endpoint_url
        
        return self.oss2.Client(cfg)

    async def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> StoredObject:
        normalized = normalize_storage_key(key)

        def _upload() -> None:
            client = self._build_client()
            client.put_object(
                self.oss2.PutObjectRequest(
                    bucket=self.bucket,    # 存储空间名称
                    key=normalized,        # 对象名称
                    body=data              # 读取文件内容
                )
            )

        try:
            await asyncio.to_thread(_upload)
        except MediaStorageError:
            raise
        except Exception as exc:  # pragma: no cover - 取决于线上 oss 可用性
            raise MediaStorageError(f"上传 oss 媒体对象失败：{exc}") from exc
        return StoredObject(key=normalized, backend=self.backend_name, size=len(data), content_type=content_type)

    async def get(self, key: str) -> bytes:
        normalized = normalize_storage_key(key)

        def _download() -> bytes:
            client = self._build_client()
            response = client.get_object(self.oss2.GetObjectRequest(
                bucket=self.bucket,  # 指定存储空间名称
                key=normalized,  # 指定对象键名
            ))
            with response.body as body_stream:
                return body_stream.read()

        try:
            return await asyncio.to_thread(_download)
        except MediaStorageError:
            raise
        except Exception as exc:  # pragma: no cover - 取决于线上 oss 可用性
            raise MediaStorageError(f"读取 oss 媒体对象失败：{exc}") from exc

    async def delete(self, key: str) -> None:
        normalized = normalize_storage_key(key)

        def _delete() -> None:
            client = self._build_client()
            client.delete_object(self.oss2.DeleteObjectRequest(
                bucket=self.bucket,
                key=normalized,
            ))

        try:
            await asyncio.to_thread(_delete)
        except MediaStorageError:
            raise
        except Exception as exc:  # pragma: no cover - 取决于线上 oss 可用性
            raise MediaStorageError(f"删除 oss 媒体对象失败：{exc}") from exc

    async def exists(self, key: str) -> bool:
        normalized = normalize_storage_key(key)

        def _head() -> bool:
            client = self._build_client()
            return client.is_object_exist(
                bucket=self.bucket,
                key=normalized,
            )

        return await asyncio.to_thread(_head)

    def public_url(self, key: str) -> str:
        normalized = normalize_storage_key(key)
        if self.public_base:
            return f"{self.public_base}/{normalized}"
        if self.endpoint_url:
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket}/{normalized}"
        return ""



def get_media_storage() -> MediaStorage:
    """按配置构建媒体存储后端实例。"""
    backend = (settings.media_storage_backend or "local").strip().lower()
    if backend == "s3":
        return S3MediaStorage(
            bucket=settings.media_s3_bucket,
            endpoint_url=settings.media_s3_endpoint_url,
            region=settings.media_s3_region,
            access_key_id=settings.media_s3_access_key_id,
            secret_access_key=settings.media_s3_secret_access_key,
            public_base=settings.media_s3_public_base_url,
            addressing_style=settings.media_s3_addressing_style,
        )
    elif backend == "oss":
        return OSS2MediaStorage(
            bucket=settings.media_s3_bucket,
            endpoint_url=settings.media_s3_endpoint_url,
            region=settings.media_s3_region,
            access_key_id=settings.media_s3_access_key_id,
            secret_access_key=settings.media_s3_secret_access_key,
            public_base=settings.media_s3_public_base_url,
            addressing_style=settings.media_s3_addressing_style,
        )
    return LocalDiskMediaStorage(media_root_path(), public_base=settings.media_public_base_url)