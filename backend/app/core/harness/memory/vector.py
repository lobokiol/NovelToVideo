"""Harness 通用向量记忆层。"""

from __future__ import annotations

import re
import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RetrievedChunk:
    """一次检索命中的文档片段。"""

    document: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorMemory(Protocol):
    """向量记忆协议。"""

    def upsert(
        self,
        isolation_key: str,
        documents: Sequence[str],
        *,
        metadata: Sequence[Mapping[str, Any]] | None = None,
        ids: Sequence[str] | None = None,
    ) -> None:
        """写入或更新一批文档。"""

    def query(self, isolation_key: str, query: str, *, limit: int = 5) -> Sequence[RetrievedChunk]:
        """按查询文本检索相关文档。"""

    def replace_scope(
        self,
        isolation_key: str,
        documents: Sequence[str],
        *,
        metadata: Sequence[Mapping[str, Any]] | None = None,
        ids: Sequence[str] | None = None,
    ) -> None:
        """替换同一隔离范围内的全部文档。"""


class _EmbeddingService(Protocol):
    config: Any

    def assets_ready(self) -> bool:
        """返回本地 embedding 资产是否可用。"""

    def diagnostics(self) -> Any:
        """返回本地 embedding 诊断信息。"""

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """编码一批文本。"""


class _ChromaEmbeddingFunction:
    """把本地 embedding 服务包装成 Chroma embedding function。"""

    def __init__(self, embedding_service: _EmbeddingService) -> None:
        self.embedding_service = embedding_service

    @staticmethod
    def name() -> str:
        return "local_onnx_embedding"

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002 - Chroma API 使用该参数名。
        return self.embedding_service.embed_texts(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:  # noqa: A002 - Chroma API 使用该参数名。
        return self.__call__(input)

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict[str, Any]:
        return {}


class ChromaVectorMemory:
    """基于本地 embedding 和 Chroma 持久库的通用向量记忆。"""

    def __init__(
        self,
        *,
        embedding_service: _EmbeddingService | None = None,
        collection_name: str | None = None,
        vector_store_dir: str | Path | None = None,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        if embedding_service is None:
            from app.core.agent.embedding import AgentEmbeddingConfig, LocalOnnxEmbeddingService

            embedding_service = LocalOnnxEmbeddingService(AgentEmbeddingConfig.from_settings())
        self.embedding_service = embedding_service
        self.collection_name = collection_name or _default_collection_name(embedding_service)
        self._vector_store_dir_override = (
            Path(vector_store_dir).expanduser()
            if vector_store_dir is not None
            else None
        )
        self._client_factory = client_factory or self._create_persistent_client
        self._collection: Any | None = None
        self._vector_ready = False
        self._failure_reason: str | None = None
        self._init_vector_store()

    @property
    def vector_ready(self) -> bool:
        """返回向量检索是否可用。"""
        return self._vector_ready

    def upsert(
        self,
        isolation_key: str,
        documents: Sequence[str],
        *,
        metadata: Sequence[Mapping[str, Any]] | None = None,
        ids: Sequence[str] | None = None,
    ) -> None:
        """写入或更新一批文档；失败时切换到词法检索模式。"""
        docs = [str(document) for document in documents]
        if not docs:
            return
        if not self._vector_ready or self._collection is None:
            return

        resolved_ids = list(ids) if ids is not None else [f"{isolation_key}:{index}" for index in range(len(docs))]
        if len(resolved_ids) != len(docs):
            self._record_failure("Chroma upsert failed: ids length must match documents length")
            return

        if metadata is None:
            resolved_metadata = [{} for _ in docs]
        else:
            resolved_metadata = [dict(item) for item in metadata]
            if len(resolved_metadata) != len(docs):
                self._record_failure("Chroma upsert failed: metadata length must match documents length")
                return
        for item in resolved_metadata:
            item["isolation_key"] = isolation_key

        try:
            self._collection.upsert(ids=resolved_ids, documents=docs, metadatas=resolved_metadata)
        except Exception as exc:
            self._record_failure(f"Chroma upsert failed: {exc}")

    def replace_scope(
        self,
        isolation_key: str,
        documents: Sequence[str],
        *,
        metadata: Sequence[Mapping[str, Any]] | None = None,
        ids: Sequence[str] | None = None,
    ) -> None:
        """删除同一隔离范围内的旧文档后写入新文档，避免已删章节残留。"""
        if not self._vector_ready or self._collection is None:
            return

        try:
            self._collection.delete(where={"isolation_key": isolation_key})
        except Exception as exc:
            self._record_failure(f"Chroma replace scope failed: {exc}")
            return

        if not documents:
            return
        self.upsert(isolation_key, documents, metadata=metadata, ids=ids)

    def existing_metadata_by_id(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """按 id 读取已存在 chunk 的 metadata，用于增量刷新时跳过未变化内容。"""
        if not self._vector_ready or self._collection is None:
            return {}
        resolved_ids = [str(id_value) for id_value in ids if str(id_value)]
        if not resolved_ids:
            return {}
        try:
            result = self._collection.get(ids=resolved_ids, include=["metadatas"])
        except Exception as exc:
            self._record_failure(f"Chroma get metadata failed: {exc}")
            return {}

        result_ids = result.get("ids") if isinstance(result, Mapping) else None
        result_metadatas = result.get("metadatas") if isinstance(result, Mapping) else None
        if not isinstance(result_ids, list) or not isinstance(result_metadatas, list):
            return {}
        metadata_by_id: dict[str, dict[str, Any]] = {}
        for index, id_value in enumerate(result_ids):
            metadata = result_metadatas[index] if index < len(result_metadatas) else None
            metadata_by_id[str(id_value)] = dict(metadata) if isinstance(metadata, dict) else {}
        return metadata_by_id

    def scope_ids(self, isolation_key: str) -> list[str]:
        """列出同一隔离范围内现存 chunk id。"""
        if not self._vector_ready or self._collection is None:
            return []
        try:
            result = self._collection.get(where={"isolation_key": isolation_key}, include=["metadatas"])
        except Exception as exc:
            self._record_failure(f"Chroma list scope ids failed: {exc}")
            return []
        result_ids = result.get("ids") if isinstance(result, Mapping) else None
        if not isinstance(result_ids, list):
            return []
        return [str(id_value) for id_value in result_ids if str(id_value)]

    def delete_ids(self, ids: Sequence[str]) -> None:
        """按 id 删除已不属于当前 scope 刷新的旧 chunk。"""
        if not self._vector_ready or self._collection is None:
            return
        resolved_ids = [str(id_value) for id_value in ids if str(id_value)]
        if not resolved_ids:
            return
        try:
            self._collection.delete(ids=resolved_ids)
        except Exception as exc:
            self._record_failure(f"Chroma delete ids failed: {exc}")

    def query(self, isolation_key: str, query: str, *, limit: int = 5) -> list[RetrievedChunk]:
        """检索相关文档；失败或向量不可用时返回空结果供调用方词法兜底。"""
        if limit <= 0 or not query.strip():
            return []
        if not self._vector_ready or self._collection is None:
            return []

        try:
            result = self._collection.query(
                query_texts=[query],
                n_results=max(1, limit),
                where={"isolation_key": isolation_key},
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            self._record_failure(f"Chroma query failed: {exc}")
            return []
        return self._parse_query_result(result, limit)

    def runtime_metadata(self) -> dict[str, Any]:
        """返回当前向量记忆运行状态。"""
        diagnostics = self._embedding_diagnostics()
        assets_ready = bool(getattr(diagnostics, "assets_ready", False))
        diagnostic_failure = getattr(diagnostics, "failure_reason", None)
        failure_reason = self._failure_reason or (diagnostic_failure if not assets_ready else None)
        return {
            "assetsReady": assets_ready,
            "vectorReady": self._vector_ready,
            "retrievalMode": "vector" if self._vector_ready else "lexical",
            "failureReason": failure_reason,
            "collectionName": self.collection_name,
            "vectorStoreDir": str(self._vector_store_dir()),
        }

    def _init_vector_store(self) -> None:
        diagnostics = self._embedding_diagnostics()
        if not bool(getattr(diagnostics, "assets_ready", False)):
            self._record_failure(getattr(diagnostics, "failure_reason", None) or "embedding assets are not ready")
            return
        try:
            vector_store_dir = self._vector_store_dir()
            vector_store_dir.mkdir(parents=True, exist_ok=True)
            client = self._client_factory(str(vector_store_dir))
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=_ChromaEmbeddingFunction(self.embedding_service),
            )
            self._vector_ready = True
            self._failure_reason = None
        except Exception as exc:
            self._record_failure(f"Chroma init failed: {exc}")

    def _record_failure(self, reason: str) -> None:
        self._collection = None
        self._vector_ready = False
        self._failure_reason = reason

    def _embedding_diagnostics(self) -> Any:
        try:
            return self.embedding_service.diagnostics()
        except Exception as exc:
            return type(
                "EmbeddingDiagnosticsFallback",
                (),
                {"assets_ready": False, "failure_reason": f"embedding diagnostics failed: {exc}"},
            )()

    def _vector_store_dir(self) -> Path:
        if self._vector_store_dir_override is not None:
            return self._vector_store_dir_override
        return Path(self.embedding_service.config.vector_store_dir).expanduser()

    @staticmethod
    def _create_persistent_client(path: str) -> Any:
        import chromadb

        return chromadb.PersistentClient(path=path)

    @staticmethod
    def _parse_query_result(result: Mapping[str, Any], limit: int) -> list[RetrievedChunk]:
        documents = _first_result_list(result.get("documents"))
        metadatas = _first_result_list(result.get("metadatas"))
        distances = _first_result_list(result.get("distances"))
        chunks: list[RetrievedChunk] = []
        result_count = min(limit, max(len(documents), len(metadatas), len(distances)))
        for index in range(result_count):
            document = documents[index] if index < len(documents) else None
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            distance = distances[index] if index < len(distances) else None
            document_text = str(document or metadata.get("document") or metadata.get("event") or "")
            if not document_text:
                continue
            chunks.append(
                RetrievedChunk(
                    document=document_text,
                    score=_distance_to_score(distance),
                    metadata=dict(metadata),
                )
            )
        return chunks


_UNSAFE_COLLECTION_PART_RE = re.compile(r"[^A-Za-z0-9]+")


def _default_collection_name(embedding_service: _EmbeddingService) -> str:
    config = embedding_service.config
    model_name = str(getattr(config, "model_name", "embedding") or "embedding")
    embedding_dim = str(getattr(config, "embedding_dim", "unknown") or "unknown")
    return _safe_collection_name(f"harness-memory-{model_name}-{embedding_dim}d")


def _safe_collection_name(raw_name: str) -> str:
    slug = _UNSAFE_COLLECTION_PART_RE.sub("-", raw_name).strip("-").lower()
    if len(slug) < 3:
        slug = "harness-memory"
    if len(slug) <= 63:
        return slug
    digest = hashlib.sha256(raw_name.encode("utf-8")).hexdigest()[:8]
    prefix = slug[: 63 - len(digest) - 1].strip("-") or "harness-memory"
    return f"{prefix}-{digest}"


def _first_result_list(value: Any) -> list[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return list(value[0])
    return []


def _distance_to_score(distance: Any) -> float:
    try:
        return 1.0 / (1.0 + float(distance or 0.0))
    except (TypeError, ValueError):
        return 0.0


_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")


def lexical_score(query: str, document: str) -> float:
    """词法相关度打分，用于向量不可用时的兜底排序。"""
    query_text = query.strip().lower()
    if not query_text:
        return 0.0
    document_text = document.lower()
    query_tokens = _TOKEN_PATTERN.findall(query_text)
    if not query_tokens:
        return 0.0
    document_tokens = set(_TOKEN_PATTERN.findall(document_text))
    overlap = len(set(query_tokens) & document_tokens)
    phrase_bonus = 3.0 if query_text in document_text else 0.0
    char_bonus = min(
        sum(document_text.count(token) for token in set(query_tokens) if len(token) == 1),
        12,
    ) * 0.1
    return float(overlap + phrase_bonus + char_bonus)
