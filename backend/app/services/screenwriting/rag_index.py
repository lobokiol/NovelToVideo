"""剧本创作 RAG 索引与语义检索上下文编排。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings, settings
from app.core.rag.constants import DEFAULT_SCREENWRITING_RAG_INDEX_CHUNK_BATCH_SIZE
from app.core.harness.memory.vector import RetrievedChunk, VectorMemory, lexical_score
from app.core.rag import RagDocument
from app.services.screenwriting.query_intent import (
    EventSelector,
    FieldLookupIntent,
    ScreenwritingQueryIntent,
    normalize_lookup_text,
    parse_screenwriting_query_intent,
)


LEXICAL_CONTEXT_CHARS = 1200
CHUNK_CONTENT_HASH_METADATA_KEY = "chunk_content_hash"
LEXICAL_EXACT_MATCH_BONUS = 20.0
LEXICAL_FIELD_INTENT_BONUS = 60.0
_VECTOR_TOOL_NAMES = frozenset({"chapter_vector_search", "event_vector_search"})


class _RuntimeVectorMemory(VectorMemory, Protocol):
    vector_ready: bool

    def runtime_metadata(self) -> dict[str, Any]:
        """返回向量记忆运行状态。"""


@dataclass(frozen=True)
class ScreenwritingRagHit:
    """一次 RAG 召回命中。"""

    document: RagDocument
    score: float
    chunk_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScreenwritingRagContext:
    """可注入提示词的 RAG 上下文。"""

    hits: list[ScreenwritingRagHit]
    text: str
    runtime: dict[str, Any]


class ScreenwritingRagIndex:
    """基于通用向量记忆的剧本创作 RAG 语义索引。"""

    def __init__(
        self,
        *,
        vector_memory: _RuntimeVectorMemory | None = None,
        chunk_chars: int | None = None,
        chunk_overlap: int | None = None,
        chunk_batch_size: int | None = None,
        min_vector_score: float | None = None,
        vector_store_dir: str | Path | None = None,
        config: Settings | None = None,
    ) -> None:
        if vector_memory is None:
            from app.core.harness.memory.vector import ChromaVectorMemory

            vector_memory = ChromaVectorMemory(vector_store_dir=vector_store_dir)
        current_config = config or settings
        self.vector_memory = vector_memory
        self.chunk_chars = max(1, int(chunk_chars if chunk_chars is not None else current_config.screenwriting_rag_chunk_chars))
        self.chunk_overlap = max(0, int(chunk_overlap if chunk_overlap is not None else current_config.screenwriting_rag_chunk_overlap))
        configured_chunk_batch_size = getattr(
            current_config,
            "screenwriting_rag_index_chunk_batch_size",
            DEFAULT_SCREENWRITING_RAG_INDEX_CHUNK_BATCH_SIZE,
        )
        self.chunk_batch_size = max(
            1,
            int(chunk_batch_size if chunk_batch_size is not None else configured_chunk_batch_size),
        )
        self.min_vector_score = float(min_vector_score if min_vector_score is not None else current_config.screenwriting_rag_min_vector_score)

    @property
    def vector_ready(self) -> bool:
        """返回向量检索是否可用。"""
        return bool(getattr(self.vector_memory, "vector_ready", False))

    def index_documents(self, isolation_key: str, documents: Sequence[RagDocument]) -> None:
        """把 RAG 文档切分后写入向量记忆。"""
        self.clear_scope(isolation_key)
        self.upsert_documents(isolation_key, documents)

    def clear_scope(self, isolation_key: str) -> None:
        """清空同一隔离范围内的旧向量文档。"""
        replace_scope = getattr(self.vector_memory, "replace_scope", None)
        if callable(replace_scope):
            replace_scope(isolation_key, [])

    def upsert_documents(
        self,
        isolation_key: str,
        documents: Sequence[RagDocument],
        *,
        skip_unchanged: bool = False,
        indexed_ids: set[str] | None = None,
    ) -> int:
        """把一批 RAG 文档切分后分批写入向量记忆，返回实际写入的 chunk 数。"""
        chunk_count = 0
        for chunk_documents, chunk_metadata, chunk_ids in _iter_chunk_payload_batches(
            documents,
            isolation_key=isolation_key,
            chunk_chars=self.chunk_chars,
            chunk_overlap=self.chunk_overlap,
            chunk_batch_size=self.chunk_batch_size,
        ):
            if indexed_ids is not None:
                indexed_ids.update(chunk_ids)
            if skip_unchanged:
                chunk_documents, chunk_metadata, chunk_ids = self._changed_chunk_payload(
                    chunk_documents,
                    chunk_metadata,
                    chunk_ids,
                )
                if not chunk_documents:
                    continue
            self.vector_memory.upsert(
                isolation_key,
                chunk_documents,
                metadata=chunk_metadata,
                ids=chunk_ids,
            )
            chunk_count += len(chunk_documents)
        return chunk_count

    @property
    def incremental_refresh_ready(self) -> bool:
        """返回向量记忆是否支持按 id 比对和删除旧 chunk。"""
        return all(
            callable(getattr(self.vector_memory, method_name, None))
            for method_name in ("existing_metadata_by_id", "scope_ids", "delete_ids")
        )

    def delete_stale_documents(self, isolation_key: str, indexed_ids: set[str]) -> int:
        """删除当前刷新过程中没有出现的旧 chunk。"""
        scope_ids = getattr(self.vector_memory, "scope_ids", None)
        delete_ids = getattr(self.vector_memory, "delete_ids", None)
        if not callable(scope_ids) or not callable(delete_ids):
            return 0
        stale_ids = [id_value for id_value in scope_ids(isolation_key) if id_value not in indexed_ids]
        if not stale_ids:
            return 0
        delete_ids(stale_ids)
        return len(stale_ids)

    def _changed_chunk_payload(
        self,
        chunk_documents: list[str],
        chunk_metadata: list[dict[str, Any]],
        chunk_ids: list[str],
    ) -> tuple[list[str], list[dict[str, Any]], list[str]]:
        existing_metadata_by_id = getattr(self.vector_memory, "existing_metadata_by_id", None)
        if not callable(existing_metadata_by_id):
            return chunk_documents, chunk_metadata, chunk_ids
        existing_metadata = existing_metadata_by_id(chunk_ids)
        if not existing_metadata:
            return chunk_documents, chunk_metadata, chunk_ids

        changed_documents: list[str] = []
        changed_metadata: list[dict[str, Any]] = []
        changed_ids: list[str] = []
        for document, metadata, id_value in zip(chunk_documents, chunk_metadata, chunk_ids, strict=True):
            existing = existing_metadata.get(id_value) or {}
            if existing.get(CHUNK_CONTENT_HASH_METADATA_KEY) == metadata.get(CHUNK_CONTENT_HASH_METADATA_KEY):
                continue
            changed_documents.append(document)
            changed_metadata.append(metadata)
            changed_ids.append(id_value)
        return changed_documents, changed_metadata, changed_ids

    def retrieve_context(
        self,
        isolation_key: str,
        query: str,
        documents: Sequence[RagDocument],
        *,
        limit: int = 50,
        query_intent: ScreenwritingQueryIntent | None = None,
    ) -> ScreenwritingRagContext:
        """检索并编排可注入提示词的 RAG 上下文。"""
        safe_limit = max(1, int(limit))
        query_text = query.strip()
        resolved_query_intent = query_intent or parse_screenwriting_query_intent(query_text)
        enabled_tools = {tool.tool for tool in resolved_query_intent.tool_plan.tools}
        run_metadata = not enabled_tools or "metadata_lookup" in enabled_tools
        run_event_json = not enabled_tools or "event_json_search" in enabled_tools
        run_vector = not enabled_tools or bool(_VECTOR_TOOL_NAMES & enabled_tools)
        run_chapter_text_lookup = not enabled_tools or "chapter_text_lookup" in enabled_tools
        vector_runtime = self._runtime_metadata()
        metadata_hits, metadata_strategy = (
            _metadata_exact_hits(resolved_query_intent, documents, limit=safe_limit)
            if run_metadata
            else ([], "none")
        )
        if metadata_hits:
            runtime = {
                **vector_runtime,
                **_intent_runtime(resolved_query_intent),
                "retrievalMode": "metadata",
                "retrievalStrategy": metadata_strategy,
                "failureReason": None,
                "hitCount": len(metadata_hits),
                "vectorHitCount": 0,
                "lexicalHitCount": 0,
                "minVectorScore": self.min_vector_score,
            }
            vector_failure = vector_runtime.get("failureReason")
            if vector_failure:
                runtime["vectorFailureReason"] = vector_failure
            return ScreenwritingRagContext(
                hits=metadata_hits,
                text=_format_context_text(metadata_hits),
                runtime=runtime,
            )

        event_hits = (
            _event_json_metadata_hits(resolved_query_intent, documents, limit=safe_limit)
            if run_event_json
            else []
        )
        if event_hits:
            chapter_text_hits = (
                _chapter_text_lookup_hits(event_hits, documents, limit=max(0, safe_limit - len(event_hits)))
                if run_chapter_text_lookup
                else []
            )
            merged_hits = _merge_ranked_hits(event_hits, chapter_text_hits, limit=safe_limit)
            runtime = {
                **vector_runtime,
                **_intent_runtime(resolved_query_intent),
                "retrievalMode": "metadata",
                "retrievalStrategy": "event_json_exact+chapter_text" if chapter_text_hits else "event_json_exact",
                "failureReason": None,
                "hitCount": len(merged_hits),
                "vectorHitCount": 0,
                "lexicalHitCount": 0,
                "eventHitCount": len(event_hits),
                "chapterTextHitCount": len(chapter_text_hits),
                "minVectorScore": self.min_vector_score,
            }
            vector_failure = vector_runtime.get("failureReason")
            if vector_failure:
                runtime["vectorFailureReason"] = vector_failure
            return ScreenwritingRagContext(
                hits=merged_hits,
                text=_format_context_text(merged_hits),
                runtime=runtime,
            )

        if run_vector:
            vector_hits, vector_failure_reason = self._vector_hits(
                isolation_key,
                query_text,
                documents,
                safe_limit,
                allowed_source_types=_vector_source_types(enabled_tools),
            )
        else:
            vector_hits, vector_failure_reason = [], None
        if vector_hits:
            lexical_hits = _lexical_fallback_hits(
                query_text,
                documents,
                limit=safe_limit,
                require_precise=True,
                query_intent=resolved_query_intent,
            )
            merged_hits = _merge_ranked_hits(vector_hits, lexical_hits, limit=safe_limit)
            runtime = {
                **_runtime_with_failure(vector_runtime, vector_failure_reason),
                **_intent_runtime(resolved_query_intent),
                "retrievalMode": "vector",
                "retrievalStrategy": "semantic+lexical" if lexical_hits else "semantic",
                "hitCount": len(merged_hits),
                "vectorHitCount": len(vector_hits),
                "lexicalHitCount": len(lexical_hits),
                "minVectorScore": self.min_vector_score,
            }
            return ScreenwritingRagContext(
                hits=merged_hits,
                text=_format_context_text(merged_hits),
                runtime=runtime,
            )

        lexical_hits = _lexical_fallback_hits(
            query_text,
            documents,
            limit=safe_limit,
            query_intent=resolved_query_intent,
        )
        if lexical_hits:
            runtime = {
                **_runtime_with_failure(vector_runtime, vector_failure_reason),
                **_intent_runtime(resolved_query_intent),
                "retrievalMode": "lexical_fallback",
                "retrievalStrategy": "lexical_score",
                "hitCount": len(lexical_hits),
                "vectorHitCount": len(vector_hits),
                "lexicalHitCount": len(lexical_hits),
                "minVectorScore": self.min_vector_score,
            }
            return ScreenwritingRagContext(
                hits=lexical_hits,
                text=_format_context_text(lexical_hits),
                runtime=runtime,
            )

        runtime = {
            **_runtime_with_failure(vector_runtime, vector_failure_reason),
            **_intent_runtime(resolved_query_intent),
            "retrievalMode": "empty",
            "retrievalStrategy": "none",
            "hitCount": 0,
            "vectorHitCount": 0,
            "lexicalHitCount": 0,
            "minVectorScore": self.min_vector_score,
        }
        return ScreenwritingRagContext(hits=[], text="", runtime=runtime)

    def _vector_hits(
        self,
        isolation_key: str,
        query: str,
        documents: Sequence[RagDocument],
        limit: int,
        allowed_source_types: set[str] | None = None,
    ) -> tuple[list[ScreenwritingRagHit], str | None]:
        if not query or not self.vector_ready:
            return [], None
        document_by_id = {document.source_id: document for document in documents}
        try:
            chunks = self.vector_memory.query(isolation_key, query, limit=max(limit * 3, limit))
        except Exception as exc:
            return [], f"vector query failed: {exc}"
        hits: list[ScreenwritingRagHit] = []
        seen_source_ids: set[str] = set()
        for chunk in chunks:
            source_id = str(chunk.metadata.get("source_id") or "")
            document = document_by_id.get(source_id)
            if document is None or source_id in seen_source_ids:
                continue
            if float(chunk.score) < self.min_vector_score:
                continue
            source_type = str(chunk.metadata.get("source_type") or document.source_type)
            if source_type != document.source_type:
                continue
            if allowed_source_types is not None and document.source_type not in allowed_source_types:
                continue
            seen_source_ids.add(source_id)
            hits.append(_rag_hit_from_chunk(document, chunk))
            if len(hits) >= limit:
                break
        return hits, None

    def _runtime_metadata(self) -> dict[str, Any]:
        runtime_metadata = getattr(self.vector_memory, "runtime_metadata", None)
        if callable(runtime_metadata):
            return dict(runtime_metadata())
        return {
            "assetsReady": self.vector_ready,
            "vectorReady": self.vector_ready,
            "retrievalMode": "vector" if self.vector_ready else "lexical_fallback",
            "failureReason": None,
        }


def _chunk_documents(
    documents: Sequence[RagDocument],
    *,
    chunk_chars: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    return list(_iter_document_chunks(documents, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap))


def _iter_chunk_payload_batches(
    documents: Sequence[RagDocument],
    *,
    isolation_key: str,
    chunk_chars: int,
    chunk_overlap: int,
    chunk_batch_size: int,
) -> Iterator[tuple[list[str], list[dict[str, Any]], list[str]]]:
    chunk_documents: list[str] = []
    chunk_metadata: list[dict[str, Any]] = []
    chunk_ids: list[str] = []
    for chunk in _iter_document_chunks(documents, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap):
        chunk_documents.append(str(chunk["content"]))
        chunk_metadata.append(dict(chunk["metadata"]))
        chunk_ids.append(f"{isolation_key}:{chunk['chunk_id']}")
        if len(chunk_documents) >= chunk_batch_size:
            yield chunk_documents, chunk_metadata, chunk_ids
            chunk_documents = []
            chunk_metadata = []
            chunk_ids = []
    if chunk_documents:
        yield chunk_documents, chunk_metadata, chunk_ids


def _iter_document_chunks(
    documents: Sequence[RagDocument],
    *,
    chunk_chars: int,
    chunk_overlap: int,
) -> Iterator[dict[str, Any]]:
    for document in documents:
        text_chunks = _chunk_text(document.content, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap)
        chunk_count = len(text_chunks)
        for chunk_index, chunk_text in enumerate(text_chunks):
            yield {
                "chunk_id": _chunk_id(document.source_id, chunk_index),
                "content": chunk_text,
                "metadata": {
                    **document.metadata,
                    "source_id": document.source_id,
                    "source_type": document.source_type,
                    "title": document.title,
                    "chunk_index": chunk_index,
                    "chunk_count": chunk_count,
                    CHUNK_CONTENT_HASH_METADATA_KEY: _chunk_content_hash(chunk_text),
                },
            }


def _chunk_text(text: str, *, chunk_chars: int, chunk_overlap: int) -> list[str]:
    content = text.strip()
    if not content:
        return []
    if len(content) <= chunk_chars:
        return [content]
    overlap = min(max(0, chunk_overlap), max(0, chunk_chars - 1))
    step = max(1, chunk_chars - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(content):
        chunk = content[start : start + chunk_chars].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_chars >= len(content):
            break
        start += step
    return chunks


def _chunk_id(source_id: str, chunk_index: int) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]
    return f"{digest}:{chunk_index}"


def _chunk_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _rag_hit_from_chunk(document: RagDocument, chunk: RetrievedChunk) -> ScreenwritingRagHit:
    return ScreenwritingRagHit(
        document=document,
        score=round(float(chunk.score), 6),
        chunk_text=chunk.document,
        metadata=dict(chunk.metadata),
    )


def _metadata_exact_hits(
    query_intent: ScreenwritingQueryIntent,
    documents: Sequence[RagDocument],
    *,
    limit: int,
) -> tuple[list[ScreenwritingRagHit], str]:
    chapter_hits = _chapter_index_metadata_hits(query_intent, documents, limit=limit)
    if chapter_hits:
        return chapter_hits, "chapter_index_exact"

    field_hits = _field_lookup_metadata_hits(query_intent, documents, limit=limit)
    if field_hits:
        return field_hits, "field_lookup_exact"

    return [], "none"


def _event_json_metadata_hits(
    query_intent: ScreenwritingQueryIntent,
    documents: Sequence[RagDocument],
    *,
    limit: int,
) -> list[ScreenwritingRagHit]:
    selector = query_intent.event_selector
    if selector is None or _event_selector_empty(selector):
        return []

    scored_documents: list[tuple[float, int, RagDocument]] = []
    for position, document in enumerate(documents):
        if document.source_type != "event":
            continue
        score = _event_selector_score(selector, document)
        if score <= 0:
            continue
        scored_documents.append((score, position, document))
    scored_documents.sort(key=lambda item: (-item[0], _source_type_rank(item[2].source_type), item[1]))
    return [
        ScreenwritingRagHit(
            document=document,
            score=round(float(score), 6),
            chunk_text=_fallback_context(document.content),
            metadata=dict(document.metadata),
        )
        for score, _, document in scored_documents[:limit]
    ]


EVENT_SELECTOR_FULL_MATCH_BONUS = 30.0


def _event_selector_score(selector: EventSelector, document: RagDocument) -> float:
    """对事件文档按选择器做部分匹配加权打分。

    组间为加权 OR：任一组有术语命中即可计分，按命中术语数加权累计；
    全部组全部术语命中时叠加完整匹配加成，保证精确查询仍排最前。
    全 AND 策略会让"正派和反派都哪些势力"这类多术语查询整体 miss。
    """
    metadata = document.metadata
    searchable_text = normalize_lookup_text(
        "\n".join(
            str(value)
            for value in (
                document.title,
                document.content,
                metadata.get("summary"),
                metadata.get("conflict"),
                metadata.get("outcome"),
            )
            if value is not None
        )
    )
    score = 120.0
    matched_groups = 0
    requested_groups = 0
    fully_matched_groups = 0
    for terms, metadata_keys, weight in (
        (selector.characters, ("characters",), 18.0),
        (selector.scenes, ("scenes",), 16.0),
        (selector.organizations, ("organizations",), 14.0),
        (selector.event_types, ("event_type",), 12.0),
    ):
        if not terms:
            continue
        requested_groups += 1
        matched_count = _selector_matched_term_count(terms, metadata, metadata_keys, searchable_text)
        if matched_count <= 0:
            continue
        matched_groups += 1
        if matched_count >= len(terms):
            fully_matched_groups += 1
        score += weight * matched_count

    if requested_groups > 0 and fully_matched_groups == requested_groups:
        score += EVENT_SELECTOR_FULL_MATCH_BONUS

    for focus in selector.focus:
        field_name = _event_focus_field(focus)
        if field_name and str(metadata.get(field_name) or "").strip():
            score += 4.0
    return score if matched_groups > 0 else 0.0


def _selector_matched_term_count(
    terms: Sequence[str],
    metadata: Mapping[str, Any],
    metadata_keys: Sequence[str],
    searchable_text: str,
) -> int:
    """统计一组术语在事件 metadata 或可检索文本中的命中数量。"""
    haystacks = [
        normalize_lookup_text(value)
        for key in metadata_keys
        for value in _metadata_values(metadata.get(key))
    ]
    matched_count = 0
    for term in terms:
        normalized_term = normalize_lookup_text(term)
        if not normalized_term:
            continue
        if any(normalized_term in haystack for haystack in haystacks if haystack):
            matched_count += 1
            continue
        if normalized_term in searchable_text:
            matched_count += 1
    return matched_count


def _metadata_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.replace("，", ",").replace("、", ",").split(",") if part.strip())
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),)


def _event_focus_field(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "conflict": "conflict",
        "冲突": "conflict",
        "矛盾": "conflict",
        "outcome": "outcome",
        "result": "outcome",
        "结果": "outcome",
        "影响": "outcome",
        "summary": "summary",
        "摘要": "summary",
    }
    return aliases.get(normalized, "")


def _event_selector_empty(selector: EventSelector) -> bool:
    return not any(
        (
            selector.characters,
            selector.scenes,
            selector.organizations,
            selector.event_types,
            selector.focus,
        )
    )


def _chapter_text_lookup_hits(
    seed_hits: Sequence[ScreenwritingRagHit],
    documents: Sequence[RagDocument],
    *,
    limit: int,
) -> list[ScreenwritingRagHit]:
    if limit <= 0:
        return []
    chapter_documents = [document for document in documents if document.source_type == "chapter"]
    hits: list[ScreenwritingRagHit] = []
    seen_source_ids: set[str] = set()
    for seed in seed_hits:
        chapter = _related_chapter_document(seed, chapter_documents)
        if chapter is None or chapter.source_id in seen_source_ids:
            continue
        seen_source_ids.add(chapter.source_id)
        hits.append(
            ScreenwritingRagHit(
                document=chapter,
                score=round(max(0.0, seed.score - 0.1), 6),
                chunk_text=_fallback_context(chapter.content),
                metadata=dict(chapter.metadata),
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _related_chapter_document(
    seed: ScreenwritingRagHit,
    chapter_documents: Sequence[RagDocument],
) -> RagDocument | None:
    metadata = seed.metadata or seed.document.metadata
    chapter_public_id = str(metadata.get("chapter_public_id") or "").strip()
    chapter_id = str(metadata.get("chapter_id") or "").strip()
    chapter_index = str(metadata.get("chapter_index") or "").strip()
    for document in chapter_documents:
        document_metadata = document.metadata
        if chapter_public_id and str(document_metadata.get("chapter_public_id") or "").strip() == chapter_public_id:
            return document
        if chapter_id and str(document_metadata.get("chapter_id") or "").strip() == chapter_id:
            return document
        if chapter_index and str(document_metadata.get("chapter_index") or "").strip() == chapter_index:
            return document
    return None


def _chapter_index_metadata_hits(
    query_intent: ScreenwritingQueryIntent,
    documents: Sequence[RagDocument],
    *,
    limit: int,
) -> list[ScreenwritingRagHit]:
    bounds = _resolve_chapter_index_bounds(query_intent, documents)
    if bounds is None:
        return []
    start_index, end_index = bounds

    chapter_documents: list[tuple[int, int, RagDocument]] = []
    for position, document in enumerate(documents):
        if document.source_type != "chapter":
            continue
        chapter_index = _metadata_chapter_index(document)
        if chapter_index is None:
            continue
        if start_index <= chapter_index <= end_index:
            chapter_documents.append((chapter_index, position, document))
    chapter_documents.sort(key=lambda item: (item[0], item[1]))
    return [
        ScreenwritingRagHit(
            document=document,
            score=round(100.0 - offset * 0.001, 6),
            chunk_text=_fallback_context(document.content),
            metadata=dict(document.metadata),
        )
        for offset, (_, _, document) in enumerate(chapter_documents[:limit])
    ]


def _resolve_chapter_index_bounds(
    query_intent: ScreenwritingQueryIntent,
    documents: Sequence[RagDocument],
) -> tuple[int, int] | None:
    """把章节范围或尾部章节意图归一化为闭区间 [start, end]。"""
    chapter_range = query_intent.chapter_range
    if chapter_range is not None:
        start_index = chapter_range.start_index
        end_index = chapter_range.end_index
        if start_index <= 0 or end_index <= 0:
            return None
        if start_index > end_index:
            start_index, end_index = end_index, start_index
        return start_index, end_index

    chapter_tail = query_intent.chapter_tail
    if chapter_tail is not None and chapter_tail.count > 0:
        max_index = _max_chapter_index(documents)
        if max_index <= 0:
            return None
        start_index = max(1, max_index - chapter_tail.count + 1)
        return start_index, max_index
    return None


def _max_chapter_index(documents: Sequence[RagDocument]) -> int:
    """取章节文档的最高序号，优先采信 metadata 中的 chapter_max_index。"""
    max_index = 0
    for document in documents:
        if document.source_type != "chapter":
            continue
        try:
            metadata_max = int(document.metadata.get("chapter_max_index"))
        except (TypeError, ValueError):
            metadata_max = 0
        chapter_index = _metadata_chapter_index(document) or 0
        max_index = max(max_index, metadata_max, chapter_index)
    return max_index


def _field_lookup_metadata_hits(
    query_intent: ScreenwritingQueryIntent,
    documents: Sequence[RagDocument],
    *,
    limit: int,
) -> list[ScreenwritingRagHit]:
    if not query_intent.field_lookups:
        return []

    scored_documents: list[tuple[float, int, RagDocument]] = []
    for position, document in enumerate(documents):
        score = _field_lookup_metadata_score(query_intent.field_lookups, document)
        if score <= 0:
            continue
        scored_documents.append((score, position, document))
    scored_documents.sort(
        key=lambda item: (
            -item[0],
            _source_type_rank(item[2].source_type),
            item[1],
        )
    )
    return [
        ScreenwritingRagHit(
            document=document,
            score=round(float(score), 6),
            chunk_text=_fallback_context(document.content),
            metadata=dict(document.metadata),
        )
        for score, _, document in scored_documents[:limit]
    ]


def _field_lookup_metadata_score(
    field_lookups: Sequence[FieldLookupIntent],
    document: RagDocument,
) -> float:
    normalized_document = normalize_lookup_text(f"{document.title}\n{document.content}")
    if not normalized_document:
        return 0.0

    best_score = 0.0
    for lookup in field_lookups:
        if document.source_type != lookup.source_type:
            continue
        markers = tuple(normalize_lookup_text(marker) for marker in lookup.document_markers)
        matched_markers = [marker for marker in markers if marker and marker in normalized_document]
        if not matched_markers:
            continue
        score = 100.0 + len(matched_markers) * 5.0 - _source_type_rank(document.source_type) * 0.01
        best_score = max(best_score, score)
    return best_score


def _metadata_chapter_index(document: RagDocument) -> int | None:
    raw_value = document.metadata.get("chapter_index")
    try:
        chapter_index = int(raw_value)
    except (TypeError, ValueError):
        return None
    return chapter_index if chapter_index > 0 else None


def _lexical_fallback_hits(
    query: str,
    documents: Sequence[RagDocument],
    *,
    limit: int,
    require_precise: bool = False,
    query_intent: ScreenwritingQueryIntent | None = None,
) -> list[ScreenwritingRagHit]:
    if not query:
        return []
    resolved_intent = query_intent or parse_screenwriting_query_intent(query)
    scored: list[tuple[float, int, RagDocument]] = []
    for index, document in enumerate(documents):
        score, precise = _lexical_document_score(query, document, resolved_intent)
        if score <= 0:
            continue
        if require_precise and not precise:
            continue
        scored.append((score, index, document))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        ScreenwritingRagHit(
            document=document,
            score=round(float(score), 6),
            chunk_text=_fallback_context(document.content),
            metadata=dict(document.metadata),
        )
        for score, _, document in scored[:limit]
    ]


RRF_RANK_CONSTANT = 60.0


def _merge_ranked_hits(
    vector_hits: Sequence[ScreenwritingRagHit],
    lexical_hits: Sequence[ScreenwritingRagHit],
    *,
    limit: int,
) -> list[ScreenwritingRagHit]:
    """用 Reciprocal Rank Fusion 融合多路召回。

    向量分数（≈0~1）与词法分数（可达 100+）量纲不同，直接比较会让词法
    通道恒压过向量通道；RRF 只依赖各通道内的排名，天然消除量纲差异。
    命中对象保留原始通道分数用于展示，仅排序依据 RRF 融合分。
    """
    rrf_scores: dict[str, float] = {}
    best_hit_by_source_id: dict[str, ScreenwritingRagHit] = {}
    for channel_hits in (vector_hits, lexical_hits):
        for rank, hit in enumerate(channel_hits, start=1):
            source_id = hit.document.source_id
            rrf_scores[source_id] = rrf_scores.get(source_id, 0.0) + 1.0 / (RRF_RANK_CONSTANT + rank)
            existing = best_hit_by_source_id.get(source_id)
            if existing is None or hit.score > existing.score:
                best_hit_by_source_id[source_id] = hit
    return sorted(
        best_hit_by_source_id.values(),
        key=lambda hit: (
            -rrf_scores[hit.document.source_id],
            _source_type_rank(hit.document.source_type),
            hit.document.source_id,
        ),
    )[:limit]


def _vector_source_types(enabled_tools: set[str]) -> set[str] | None:
    if not enabled_tools:
        return None
    source_types: set[str] = set()
    if "chapter_vector_search" in enabled_tools:
        source_types.add("chapter")
    if "event_vector_search" in enabled_tools:
        source_types.add("event")
    return source_types or None


def _lexical_document_score(
    query: str,
    document: RagDocument,
    query_intent: ScreenwritingQueryIntent,
) -> tuple[float, bool]:
    document_text = f"{document.title}\n{document.content}".strip()
    base_score = lexical_score(query, document_text)
    precision_bonus, precise = _lexical_precision_bonus(query_intent, document, document_text)
    return float(base_score + precision_bonus), precise


def _lexical_precision_bonus(
    query_intent: ScreenwritingQueryIntent,
    document: RagDocument,
    document_text: str,
) -> tuple[float, bool]:
    normalized_document = normalize_lookup_text(document_text)
    if not normalized_document:
        return 0.0, False

    bonus = 0.0
    precise = False
    for term in query_intent.lookup_terms:
        if term and term in normalized_document:
            bonus += LEXICAL_EXACT_MATCH_BONUS + min(len(term), 20) * 0.5
            precise = True
            break

    field_bonus = _field_intent_bonus(query_intent, document, normalized_document)
    if field_bonus > 0:
        bonus += field_bonus
        precise = True
    return bonus, precise


def _field_intent_bonus(
    query_intent: ScreenwritingQueryIntent,
    document: RagDocument,
    normalized_document: str,
) -> float:
    if not query_intent.normalized_query:
        return 0.0
    for intent in query_intent.field_lookups:
        if document.source_type != intent.source_type:
            continue
        markers = tuple(normalize_lookup_text(marker) for marker in intent.document_markers)
        if any(marker and marker in normalized_document for marker in markers):
            return LEXICAL_FIELD_INTENT_BONUS
    return 0.0


def _source_type_rank(source_type: str) -> int:
    priority = {
        "project": 0,
        "novel": 1,
        "event": 2,
        "chapter": 3,
        "art_style": 4,
        "director_manual": 5,
    }
    return priority.get(source_type, 100)


def _fallback_context(content: str) -> str:
    text = content.strip()
    if len(text) <= LEXICAL_CONTEXT_CHARS:
        return text
    return f"{text[:LEXICAL_CONTEXT_CHARS].strip()}..."


def _runtime_with_failure(runtime: Mapping[str, Any], failure_reason: str | None) -> dict[str, Any]:
    resolved = dict(runtime)
    if failure_reason:
        current_failure = str(resolved.get("failureReason") or "")
        resolved["failureReason"] = (
            f"{current_failure}; {failure_reason}"
            if current_failure
            else failure_reason
        )
    return resolved


def _intent_runtime(query_intent: ScreenwritingQueryIntent) -> dict[str, Any]:
    """把意图解析来源和工具计划摘要暴露到运行时诊断，便于排查检索决策。"""
    tool_plan = query_intent.tool_plan
    runtime: dict[str, Any] = {
        "intentSource": tool_plan.source,
        "intentConfidence": round(float(tool_plan.confidence), 6),
        "intentToolPlan": [tool.tool for tool in tool_plan.tools],
    }
    parser = query_intent.diagnostics.get("intentParser")
    if parser:
        runtime["intentParser"] = parser
    parser_failure = query_intent.diagnostics.get("intentParserFailure")
    if parser_failure:
        runtime["intentParserFailure"] = parser_failure
    if tool_plan.answer_focus:
        runtime["intentAnswerFocus"] = tool_plan.answer_focus
    if query_intent.field_lookups:
        runtime["intentFieldLookups"] = [
            {
                "sourceType": intent.source_type,
                "documentMarkers": list(intent.document_markers),
            }
            for intent in query_intent.field_lookups
        ]
    return runtime


def _format_context_text(hits: Sequence[ScreenwritingRagHit]) -> str:
    if not hits:
        return ""
    blocks = []
    for index, hit in enumerate(hits, start=1):
        label = _source_label(hit.document.source_type)
        blocks.append(
            "\n".join(
                part
                for part in (
                    f"[{index}] {label}: {hit.document.title}",
                    f"score: {hit.score:.6f}",
                    hit.chunk_text,
                )
                if part
            )
        )
    return "\n\n".join(blocks)


def _source_label(source_type: str) -> str:
    if source_type == "project":
        return "项目基础信息"
    if source_type == "novel":
        return "小说基础信息"
    if source_type == "chapter":
        return "章节资料"
    if source_type == "event":
        return "章节事件"
    if source_type == "art_style":
        return "视觉风格"
    if source_type == "director_manual":
        return "导演手册"
    return source_type
