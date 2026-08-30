"""剧本创作聊天 RAG 运行时编排。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import database
from app.core.config import Settings, project_path, settings
from app.core.rag import RagDocument
from app.core.rag.constants import DEFAULT_SCREENWRITING_RAG_RETRIEVE_LIMIT
from app.services import project as project_service
from app.services.screenwriting.rag_documents import (
    iter_screenwriting_knowledge_document_batches,
    load_screenwriting_knowledge_documents,
)
from app.services.screenwriting.query_intent import (
    ScreenwritingQueryIntent,
    parse_screenwriting_query_intent,
)
from app.services.screenwriting.query_intent_llm import (
    parse_screenwriting_query_intent_with_llm,
)
from app.services.screenwriting.rag_index import (
    ScreenwritingRagContext,
    ScreenwritingRagHit,
    ScreenwritingRagIndex,
)


@dataclass(frozen=True)
class ScreenwritingRagPreparation:
    """单轮聊天已准备好的 RAG 上下文。"""

    context: ScreenwritingRagContext
    document_count: int


@dataclass(frozen=True)
class ScreenwritingRagWarmupSchedule:
    """项目级 RAG 向量索引预热调度结果。"""

    status: str
    rag_isolation_key: str


class ScreenwritingRagRuntime:
    """管理 RAG 索引复用、文档指纹失效和运行时序列化。"""

    def __init__(
        self,
        *,
        session_maker: Callable[[], Any] | None = None,
        intent_gateway: Any | None = None,
        config: Settings | None = None,
    ) -> None:
        self._lock = RLock()
        self._indexes: dict[str, Any] = {}
        self._index_factory_id: int | None = None
        self._indexed_document_fingerprints: dict[str, str] = {}
        self._warmup_tasks: dict[str, asyncio.Task[None]] = {}
        self._session_maker = session_maker or database.async_session_maker
        self._intent_gateway = intent_gateway
        self._config = config or settings

    async def prepare_context(
        self,
        session: AsyncSession,
        project: Any,
        project_public_id: str,
        current_user_public_id: str,
        query: str,
    ) -> ScreenwritingRagPreparation:
        """准备本轮 RAG 上下文；失败时不阻断聊天主链路。

        聊天请求路径绝不同步构建向量索引：文档指纹与缓存不一致时仅调度
        后台增量刷新，本轮直接基于现有持久化索引和内存检索作答。
        """
        document_count = 0
        rag_isolation_key = build_project_rag_isolation_key(project_public_id)
        try:
            rag_documents, query_intent = await asyncio.gather(
                load_screenwriting_knowledge_documents(session, project),
                self._resolve_query_intent(project, query),
            )
            document_count = len(rag_documents)
            rag_index = await asyncio.to_thread(
                self._get_index,
                project_public_id,
                rag_isolation_key,
            )
            fingerprint = await asyncio.to_thread(_rag_documents_fingerprint, rag_documents)
            index_cache_hit = self._fingerprint_matches(rag_isolation_key, fingerprint)
            index_refresh_scheduled = False
            if not index_cache_hit:
                self._invalidate_stale_fingerprint(rag_isolation_key, fingerprint)
                schedule = self.schedule_index_warmup(project_public_id, current_user_public_id)
                index_refresh_scheduled = schedule.status in {"started", "running"}
            rag_context = await asyncio.to_thread(
                rag_index.retrieve_context,
                rag_isolation_key,
                query,
                rag_documents,
                limit=self._retrieve_limit(),
                query_intent=query_intent,
            )
            return ScreenwritingRagPreparation(
                context=_rag_context_with_runtime(
                    rag_context,
                    _rag_scope_runtime(
                        rag_isolation_key,
                        index_cache_hit=index_cache_hit,
                        index_refresh_scheduled=index_refresh_scheduled,
                    ),
                ),
                document_count=document_count,
            )
        except Exception as exc:
            return ScreenwritingRagPreparation(
                context=_rag_context_with_runtime(
                    empty_rag_context(f"RAG preparation failed: {exc}"),
                    _rag_scope_runtime(rag_isolation_key, index_cache_hit=False),
                ),
                document_count=document_count,
            )

    def _fingerprint_matches(self, rag_isolation_key: str, fingerprint: str) -> bool:
        with self._lock:
            return self._indexed_document_fingerprints.get(rag_isolation_key) == fingerprint

    def _invalidate_stale_fingerprint(self, rag_isolation_key: str, fingerprint: str) -> None:
        """仅当已记录指纹与当前指纹不同（陈旧）时移除记录，让后台预热得以重新调度。"""
        with self._lock:
            stored = self._indexed_document_fingerprints.get(rag_isolation_key)
            if stored is not None and stored != fingerprint:
                self._indexed_document_fingerprints.pop(rag_isolation_key, None)

    def _retrieve_limit(self) -> int:
        configured = getattr(
            self._config,
            "screenwriting_rag_retrieve_limit",
            DEFAULT_SCREENWRITING_RAG_RETRIEVE_LIMIT,
        )
        return max(1, int(configured))

    async def _resolve_query_intent(
        self,
        project: Any,
        query: str,
    ) -> ScreenwritingQueryIntent:
        """优先用大模型解析查询意图，未启用或缺模型时走确定性兜底。"""
        if not self._config.screenwriting_rag_intent_enabled:
            return parse_screenwriting_query_intent(query)
        model_id = str(getattr(project, "text_model", "") or "").strip()
        if not model_id:
            return parse_screenwriting_query_intent(query)
        return await parse_screenwriting_query_intent_with_llm(
            query,
            model_id=model_id,
            gateway=self._intent_gateway,
            timeout_seconds=self._config.screenwriting_rag_intent_timeout_seconds,
        )

    def clear_cache(self) -> None:
        """清理已缓存的 RAG 索引实例和文档指纹。"""
        with self._lock:
            warmup_tasks = list(self._warmup_tasks.values())
            self._warmup_tasks.clear()
            self._indexes.clear()
            self._index_factory_id = None
            self._indexed_document_fingerprints.clear()
        for task in warmup_tasks:
            if not task.done():
                task.cancel()

    def schedule_index_warmup(
        self,
        project_public_id: str,
        current_user_public_id: str,
    ) -> ScreenwritingRagWarmupSchedule:
        """异步调度当前项目的 RAG 向量索引预热构建。"""
        rag_isolation_key = build_project_rag_isolation_key(project_public_id)
        with self._lock:
            task = self._warmup_tasks.get(rag_isolation_key)
            if task is not None and not task.done():
                return ScreenwritingRagWarmupSchedule(status="running", rag_isolation_key=rag_isolation_key)
            if task is not None:
                self._warmup_tasks.pop(rag_isolation_key, None)
            if rag_isolation_key in self._indexed_document_fingerprints:
                return ScreenwritingRagWarmupSchedule(status="ready", rag_isolation_key=rag_isolation_key)
            task = asyncio.create_task(
                self._warmup_project_index(
                    project_public_id,
                    current_user_public_id,
                    rag_isolation_key,
                )
            )
            self._warmup_tasks[rag_isolation_key] = task
            task.add_done_callback(lambda finished: self._discard_warmup_task(rag_isolation_key, finished))
            return ScreenwritingRagWarmupSchedule(status="started", rag_isolation_key=rag_isolation_key)

    def _get_index(self, project_public_id: str, rag_isolation_key: str) -> Any:
        factory_id = id(ScreenwritingRagIndex)
        with self._lock:
            if self._index_factory_id != factory_id:
                self._indexes.clear()
                self._indexed_document_fingerprints.clear()
                self._index_factory_id = factory_id
            index = self._indexes.get(rag_isolation_key)
            if index is not None:
                return index
        new_index = ScreenwritingRagIndex(
            vector_store_dir=build_project_rag_vector_store_dir(project_public_id)
        )
        with self._lock:
            if self._index_factory_id != factory_id:
                self._indexes.clear()
                self._indexed_document_fingerprints.clear()
                self._index_factory_id = factory_id
            existing_index = self._indexes.get(rag_isolation_key)
            if existing_index is not None:
                return existing_index
            self._indexes[rag_isolation_key] = new_index
            return new_index

    async def _warmup_project_index(
        self,
        project_public_id: str,
        current_user_public_id: str,
        rag_isolation_key: str,
    ) -> None:
        started_at = perf_counter()
        document_count = 0
        chunk_count = 0
        stale_chunk_count = 0
        index_cache_hit = False
        fingerprint_builder = _RagDocumentsFingerprintBuilder()
        async with self._session_maker() as session:
            project = await project_service.get_project_or_raise(
                session,
                project_public_id,
                current_user_public_id,
            )
            rag_index = await asyncio.to_thread(
                self._get_index,
                project_public_id,
                rag_isolation_key,
            )
            incremental_refresh = bool(getattr(rag_index, "incremental_refresh_ready", False))
            indexed_ids: set[str] | None = set() if incremental_refresh else None
            if not incremental_refresh:
                await asyncio.to_thread(rag_index.clear_scope, rag_isolation_key)
            async for rag_documents in iter_screenwriting_knowledge_document_batches(session, project):
                if not rag_documents:
                    continue
                document_count += len(rag_documents)
                fingerprint_builder.update_many(rag_documents)
                if incremental_refresh:
                    chunk_count += await asyncio.to_thread(
                        rag_index.upsert_documents,
                        rag_isolation_key,
                        rag_documents,
                        skip_unchanged=True,
                        indexed_ids=indexed_ids,
                    )
                else:
                    chunk_count += await asyncio.to_thread(
                        rag_index.upsert_documents,
                        rag_isolation_key,
                        rag_documents,
                    )
            if incremental_refresh and indexed_ids is not None:
                stale_chunk_count = await asyncio.to_thread(
                    rag_index.delete_stale_documents,
                    rag_isolation_key,
                    indexed_ids,
                )
                index_cache_hit = chunk_count == 0 and stale_chunk_count == 0
            with self._lock:
                if self._indexes.get(rag_isolation_key) is rag_index:
                    self._indexed_document_fingerprints[rag_isolation_key] = fingerprint_builder.hexdigest()
        duration_ms = max(0, int((perf_counter() - started_at) * 1000))
        print(
            "Screenwriting RAG warmup: "
            f"status=completed project_public_id={project_public_id} "
            f"rag_isolation_key={rag_isolation_key} "
            f"vector_store_dir={build_project_rag_vector_store_dir(project_public_id)} "
            f"document_count={document_count} "
            f"chunk_count={chunk_count} "
            f"stale_chunk_count={stale_chunk_count} "
            f"index_cache_hit={index_cache_hit} "
            f"duration_ms={duration_ms}",
            flush=True,
        )

    def _discard_warmup_task(self, rag_isolation_key: str, task: asyncio.Task[None]) -> None:
        with self._lock:
            if self._warmup_tasks.get(rag_isolation_key) is task:
                self._warmup_tasks.pop(rag_isolation_key, None)
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            print(
                "Screenwriting RAG warmup: "
                f"status=failed rag_isolation_key={rag_isolation_key} "
                f"error={exc}",
                flush=True,
            )


_RAG_RUNTIME = ScreenwritingRagRuntime()
_PROJECT_VECTOR_STORE_PART_RE = re.compile(r"[^A-Za-z0-9_-]+")


async def prepare_rag_context(
    session: AsyncSession,
    project: Any,
    project_public_id: str,
    current_user_public_id: str,
    query: str,
) -> ScreenwritingRagPreparation:
    """准备单轮聊天可用的 RAG 上下文。"""
    return await _RAG_RUNTIME.prepare_context(
        session,
        project,
        project_public_id,
        current_user_public_id,
        query,
    )


def schedule_rag_index_warmup(
    project_public_id: str,
    current_user_public_id: str,
) -> ScreenwritingRagWarmupSchedule:
    """调度默认 RAG runtime 的项目级向量索引预热。"""
    return _RAG_RUNTIME.schedule_index_warmup(project_public_id, current_user_public_id)


def build_project_rag_isolation_key(project_public_id: str) -> str:
    """生成项目级章节资料 RAG 隔离键。"""
    return f"screenwriting:rag:project:{project_public_id}:chapters"


def build_project_rag_vector_store_dir(
    project_public_id: str,
    *,
    config: Settings | None = None,
) -> Path:
    """生成项目级 RAG ChromaDB 持久化目录。"""
    current = config or settings
    chroma_root = project_path(current.screenwriting_rag_vector_store_root)
    rag_root = chroma_root if chroma_root.name == "screenwriting-rag" else chroma_root / "screenwriting-rag"
    return rag_root / "projects" / _safe_project_vector_store_name(project_public_id)


def clear_rag_runtime_cache() -> None:
    """清理默认 RAG 运行时缓存，供测试和热切换使用。"""
    _RAG_RUNTIME.clear_cache()


def build_system_prompt_with_rag(base_prompt: str, rag_context: ScreenwritingRagContext) -> str:
    """把本轮 RAG 召回资料注入系统提示词。"""
    if not rag_context.text.strip():
        return base_prompt
    return (
        f"{base_prompt}\n\n"
        "## RAG 检索上下文\n"
        "本轮已经检索到以下项目资料。回答用户涉及章节、人物、剧情、设定或视听风格的问题时，"
        "必须优先依据这些资料作答；只有资料未覆盖问题或互相冲突时，才说明限制。\n"
        f"{rag_context.text.strip()}"
    )


def build_rag_tools(rag_context: ScreenwritingRagContext) -> list[Callable[..., Any]]:
    """构建当前聊天轮次可用的 RAG 工具。"""

    def get_rag_context() -> dict[str, Any]:
        """读取本轮剧本创作 RAG 检索上下文。"""
        return {
            "text": rag_context.text,
            "runtime": dict(rag_context.runtime),
            "hits": [_rag_hit_to_dict(hit, include_details=True) for hit in rag_context.hits],
        }

    return [get_rag_context]


def rag_runtime_payload(rag_context: ScreenwritingRagContext, *, document_count: int) -> dict[str, Any]:
    """生成对外返回和 Agent metadata 使用的 RAG runtime 摘要。"""
    return {
        "runtime": dict(rag_context.runtime),
        "hitCount": len(rag_context.hits),
        "documentCount": max(0, int(document_count)),
        "hits": [_rag_hit_to_dict(hit) for hit in rag_context.hits],
    }


def empty_rag_context(failure_reason: str | None = None) -> ScreenwritingRagContext:
    """生成失败兜底或无资料时的空 RAG 上下文。"""
    return ScreenwritingRagContext(
        hits=[],
        text="",
        runtime={
            "assetsReady": False,
            "vectorReady": False,
            "retrievalMode": "lexical_fallback",
            "failureReason": failure_reason,
            "hitCount": 0,
            "indexCacheHit": False,
        },
    )


def _rag_documents_fingerprint(rag_documents: Sequence[RagDocument]) -> str:
    fingerprint_builder = _RagDocumentsFingerprintBuilder()
    fingerprint_builder.update_many(rag_documents)
    return fingerprint_builder.hexdigest()


class _RagDocumentsFingerprintBuilder:
    """增量计算顺序无关的 RAG 文档指纹。

    每个文档先独立哈希，聚合时按 digest 排序后再整体哈希，
    保证指纹只取决于文档集合内容，与加载顺序和分批策略解耦，
    使预热（分批交错）与聊天（全量加载）两条路径产出一致指纹。
    """

    def __init__(self) -> None:
        self._document_digests: list[bytes] = []

    def update_many(self, rag_documents: Sequence[RagDocument]) -> None:
        for document in rag_documents:
            self.update(document)

    def update(self, document: RagDocument) -> None:
        encoded = json.dumps(
            {
                "source_id": document.source_id,
                "source_type": document.source_type,
                "title": document.title,
                "content": document.content,
                "metadata": document.metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
        self._document_digests.append(hashlib.sha256(encoded).digest())

    def hexdigest(self) -> str:
        hasher = hashlib.sha256()
        for digest in sorted(self._document_digests):
            hasher.update(digest)
        return hasher.hexdigest()


def _rag_context_with_runtime(rag_context: ScreenwritingRagContext, runtime: dict[str, Any]) -> ScreenwritingRagContext:
    return ScreenwritingRagContext(
        hits=rag_context.hits,
        text=rag_context.text,
        runtime={**rag_context.runtime, **runtime},
    )


def _rag_scope_runtime(
    rag_isolation_key: str,
    *,
    index_cache_hit: bool,
    index_refresh_scheduled: bool = False,
) -> dict[str, Any]:
    return {
        "indexScope": "project",
        "ragIsolationKey": rag_isolation_key,
        "indexCacheHit": index_cache_hit,
        "indexRefreshScheduled": index_refresh_scheduled,
    }


def _rag_hit_to_dict(hit: ScreenwritingRagHit, *, include_details: bool = False) -> dict[str, Any]:
    data = {
        "sourceId": hit.document.source_id,
        "sourceType": hit.document.source_type,
        "title": hit.document.title,
        "score": round(float(hit.score), 6),
    }
    if include_details:
        data["chunkText"] = hit.chunk_text
        data["metadata"] = dict(hit.metadata)
    return data


def _safe_project_vector_store_name(project_public_id: str) -> str:
    raw_value = str(project_public_id or "").strip()
    slug = _PROJECT_VECTOR_STORE_PART_RE.sub("-", raw_value).strip("-").lower()
    if not slug:
        if not raw_value:
            return "unknown-project"
        digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:12]
        return f"project-{digest}"
    if len(slug) <= 80:
        return slug
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:8]
    prefix = slug[: 80 - len(digest) - 1].strip("-") or "project"
    return f"{prefix}-{digest}"
