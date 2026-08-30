"""Agent 本地 ONNX embedding 底层服务。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings, project_path, settings

try:  # pragma: no cover - 依赖缺失由 diagnostics 覆盖。
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover
    np = None

try:  # pragma: no cover - 依赖缺失由 diagnostics 覆盖。
    import onnxruntime as ort
except ModuleNotFoundError:  # pragma: no cover
    ort = None

try:  # pragma: no cover - 依赖缺失由 diagnostics 覆盖。
    from tokenizers import Tokenizer
    from tokenizers.models import WordPiece
    from tokenizers.normalizers import BertNormalizer
    from tokenizers.pre_tokenizers import Whitespace
    from tokenizers.processors import TemplateProcessing
except ModuleNotFoundError:  # pragma: no cover
    Tokenizer = None
    WordPiece = None
    BertNormalizer = None
    Whitespace = None
    TemplateProcessing = None


class AgentEmbeddingError(Exception):
    """Agent 本地 embedding 服务失败。"""


@dataclass(frozen=True)
class AgentEmbeddingDiagnostics:
    """本地 ONNX embedding 与向量库运行状态。"""

    model_name: str
    model_dir: str
    model_path: str
    vector_store_dir: str
    embedding_dim: int
    max_tokens: int
    batch_size: int
    tokenizer_path: str | None
    assets_ready: bool
    mode: str
    runtime: str
    vector_store: str
    failure_reason: str | None = None


@dataclass(frozen=True)
class AgentEmbeddingConfig:
    """Agent 本地 embedding 配置。"""

    model_name: str
    model_dir: Path
    vector_store_dir: Path
    embedding_dim: int
    max_tokens: int
    batch_size: int = 8

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise AgentEmbeddingError("model_name is required")
        if self.embedding_dim <= 0:
            raise AgentEmbeddingError("embedding_dim must be a positive integer")
        if self.max_tokens <= 0:
            raise AgentEmbeddingError("max_tokens must be a positive integer")
        if self.batch_size <= 0:
            raise AgentEmbeddingError("batch_size must be a positive integer")

    @classmethod
    def from_settings(cls, current: Settings | None = None) -> "AgentEmbeddingConfig":
        config = current or settings
        return cls(
            model_name=config.agent_embedding_model_name,
            model_dir=project_path(config.agent_embedding_model_dir),
            vector_store_dir=project_path(config.agent_vector_store_dir),
            embedding_dim=config.agent_embedding_dim,
            max_tokens=config.agent_embedding_max_tokens,
            batch_size=config.agent_embedding_batch_size,
        )


class LocalOnnxEmbeddingService:
    """本地 ONNX embedding 资产检查与推理服务。"""

    def __init__(self, config: AgentEmbeddingConfig) -> None:
        self.config = config
        self._session: Any | None = None
        self._tokenizer: Any | None = None
        self._tokenizer_path: Path | None = None

    def assets_ready(self) -> bool:
        """返回模型、tokenizer 与运行时依赖是否齐备。"""
        return self.diagnostics().assets_ready

    def diagnostics(self) -> AgentEmbeddingDiagnostics:
        """返回本地 embedding 运行状态。"""
        model_path, model_error = self._resolve_model_path()
        tokenizer_path, tokenizer_error = self._resolve_tokenizer_path()
        failures: list[str] = []
        if np is None:
            failures.append("numpy is not installed")
        if ort is None:
            failures.append("onnxruntime is not installed")
        if Tokenizer is None:
            failures.append("tokenizers is not installed")
        if model_error is not None:
            failures.append(model_error)
        if tokenizer_error is not None:
            failures.append(tokenizer_error)

        assets_ready = not failures
        return AgentEmbeddingDiagnostics(
            model_name=self.config.model_name,
            model_dir=str(self.config.model_dir),
            model_path=str(model_path or self.config.model_dir / "onnx" / "model.onnx"),
            vector_store_dir=str(self.config.vector_store_dir),
            embedding_dim=self.config.embedding_dim,
            max_tokens=self.config.max_tokens,
            batch_size=self.config.batch_size,
            tokenizer_path=str(tokenizer_path) if tokenizer_path is not None else None,
            assets_ready=assets_ready,
            mode="onnx_chroma" if assets_ready else "lexical_fallback",
            runtime="onnxruntime",
            vector_store="chroma",
            failure_reason=None if assets_ready else "; ".join(failures),
        )

    def validate_assets(self) -> None:
        """资产缺失时抛出可诊断异常。"""
        diagnostics = self.diagnostics()
        if not diagnostics.assets_ready:
            raise AgentEmbeddingError(
                f"Local embedding assets are not ready: {diagnostics.failure_reason}"
            )

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """使用本地 ONNX 模型编码一批文本。"""
        if not texts:
            return []
        if np is None:
            raise AgentEmbeddingError("numpy is not installed")

        self.validate_assets()
        tokenizer = self._load_tokenizer()
        session = self._load_session()

        encodings = [tokenizer.encode(text or "") for text in texts]
        if not any(min(len(encoding.ids), self.config.max_tokens) > 0 for encoding in encodings):
            raise AgentEmbeddingError("分词结果为空，无法生成向量")

        embeddings: list[list[float]] = []
        for start in range(0, len(encodings), self.config.batch_size):
            batch_encodings = encodings[start : start + self.config.batch_size]
            embeddings.extend(self._embed_encoding_batch(session, batch_encodings))
        return embeddings

    def _embed_encoding_batch(self, session: Any, encodings: Sequence[Any]) -> list[list[float]]:
        if np is None:
            raise AgentEmbeddingError("numpy is not installed")

        max_length = max((min(len(encoding.ids), self.config.max_tokens) for encoding in encodings), default=0)
        if max_length <= 0:
            raise AgentEmbeddingError("分词结果为空，无法生成向量")

        input_ids = np.zeros((len(encodings), max_length), dtype=np.int64)
        attention_mask = np.zeros((len(encodings), max_length), dtype=np.int64)
        token_type_ids = np.zeros((len(encodings), max_length), dtype=np.int64)

        for row_index, encoding in enumerate(encodings):
            ids = list(encoding.ids)[:max_length]
            mask = self._fit_sequence(list(encoding.attention_mask or []), len(ids), 1)
            type_ids = self._fit_sequence(list(encoding.type_ids or []), len(ids), 0)
            input_ids[row_index, : len(ids)] = np.asarray(ids, dtype=np.int64)
            attention_mask[row_index, : len(mask)] = np.asarray(mask, dtype=np.int64)
            token_type_ids[row_index, : len(type_ids)] = np.asarray(type_ids, dtype=np.int64)

        input_names = {input_meta.name for input_meta in session.get_inputs()}
        missing_inputs = {"input_ids", "attention_mask"} - input_names
        if missing_inputs:
            raise AgentEmbeddingError(
                "ONNX model missing required inputs: " + ", ".join(sorted(missing_inputs))
            )

        ort_inputs: dict[str, Any] = {}
        for input_meta in session.get_inputs():
            if input_meta.name == "input_ids":
                ort_inputs[input_meta.name] = input_ids
            elif input_meta.name == "attention_mask":
                ort_inputs[input_meta.name] = attention_mask
            elif input_meta.name == "token_type_ids":
                ort_inputs[input_meta.name] = token_type_ids

        try:
            outputs = session.run(None, ort_inputs)
        except Exception as exc:
            raise AgentEmbeddingError(f"ONNX embedding inference failed: {exc}") from exc
        if not outputs:
            raise AgentEmbeddingError("ONNX 模型未返回任何输出")

        embedding = np.asarray(self._select_embedding_output(session, outputs), dtype=np.float32)
        if embedding.ndim == 3:
            if embedding.shape[:2] != attention_mask.shape:
                raise AgentEmbeddingError(
                    "ONNX model output sequence shape does not match tokenizer attention_mask"
                )
            pooled = self._mean_pool(embedding, attention_mask)
        elif embedding.ndim == 2:
            pooled = embedding
        else:
            raise AgentEmbeddingError(f"不支持的模型输出维度: {embedding.ndim}")

        expected_shape = (len(encodings), self.config.embedding_dim)
        if pooled.shape != expected_shape:
            raise AgentEmbeddingError(f"ONNX embedding output must be {expected_shape}, got {pooled.shape}")

        return self._normalize(pooled).tolist()

    def _load_session(self) -> Any:
        if ort is None:
            raise AgentEmbeddingError("onnxruntime is not installed")
        model_path, model_error = self._resolve_model_path()
        if model_path is None:
            raise AgentEmbeddingError(model_error or "missing model asset")
        if self._session is None:
            self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        return self._session

    def _resolve_model_path(self) -> tuple[Path | None, str | None]:
        for candidate in self._supported_model_candidates():
            if candidate.is_file():
                return candidate, None
        expected = " or ".join(str(path) for path in self._supported_model_candidates())
        return None, f"missing model asset: expected {expected}"

    def _supported_model_candidates(self) -> tuple[Path, Path]:
        return (
            self.config.model_dir / "onnx" / "model.onnx",
            self.config.model_dir / "model.onnx",
        )

    def _load_tokenizer(self) -> Any:
        if self._tokenizer is not None:
            return self._tokenizer
        tokenizer_path, tokenizer_error = self._resolve_tokenizer_path()
        if tokenizer_path is None:
            raise AgentEmbeddingError(tokenizer_error or "missing usable tokenizer asset")
        if self._tokenizer is None:
            raise AgentEmbeddingError("tokenizer load failed without a cached tokenizer")
        return self._tokenizer

    def _resolve_tokenizer_path(self) -> tuple[Path | None, str | None]:
        if self._tokenizer is not None and self._tokenizer_path is not None:
            return self._tokenizer_path, None
        if Tokenizer is None:
            return None, None

        errors: list[str] = []
        for candidate in self._supported_tokenizer_candidates():
            if not candidate.is_file():
                continue
            try:
                tokenizer = self._load_tokenizer_from_path(candidate)
            except Exception as exc:
                errors.append(f"{candidate.name}: {exc}")
                continue
            self._tokenizer = tokenizer
            self._tokenizer_path = candidate
            return candidate, None

        unsupported = [
            candidate.name
            for candidate in self._unsupported_tokenizer_candidates()
            if candidate.is_file()
        ]
        if unsupported:
            return None, (
                "unsupported tokenizer asset(s): "
                + ", ".join(unsupported)
                + "; supported assets are tokenizer.json or vocab.txt"
            )
        if errors:
            return None, "invalid tokenizer asset(s): " + "; ".join(errors)
        return None, f"missing tokenizer asset in {self.config.model_dir}: expected tokenizer.json or vocab.txt"

    def _supported_tokenizer_candidates(self) -> tuple[Path, Path]:
        return (
            self.config.model_dir / "tokenizer.json",
            self.config.model_dir / "vocab.txt",
        )

    def _unsupported_tokenizer_candidates(self) -> tuple[Path, ...]:
        return (
            self.config.model_dir / "tokenizer.model",
            self.config.model_dir / "sentencepiece.bpe.model",
            self.config.model_dir / "spiece.model",
        )

    def _load_tokenizer_from_path(self, tokenizer_path: Path) -> Any:
        if Tokenizer is None:
            raise AgentEmbeddingError("tokenizers is not installed")
        if tokenizer_path.name == "tokenizer.json":
            return Tokenizer.from_file(str(tokenizer_path))
        if tokenizer_path.name == "vocab.txt":
            if WordPiece is None or BertNormalizer is None or Whitespace is None or TemplateProcessing is None:
                raise AgentEmbeddingError("tokenizers is not installed")
            tokenizer = Tokenizer(WordPiece.from_file(str(tokenizer_path), unk_token="[UNK]"))
            tokenizer.normalizer = BertNormalizer(lowercase=False)
            tokenizer.pre_tokenizer = Whitespace()
            cls_id = tokenizer.token_to_id("[CLS]")
            sep_id = tokenizer.token_to_id("[SEP]")
            unk_id = tokenizer.token_to_id("[UNK]")
            if cls_id is None or sep_id is None or unk_id is None:
                raise AgentEmbeddingError("vocab.txt must include [UNK], [CLS], and [SEP]")
            tokenizer.post_processor = TemplateProcessing(
                single="[CLS] $A [SEP]",
                pair="[CLS] $A [SEP] $B:1 [SEP]:1",
                special_tokens=[("[CLS]", cls_id), ("[SEP]", sep_id)],
            )
            return tokenizer
        raise AgentEmbeddingError(f"Unsupported tokenizer asset: {tokenizer_path.name}")

    def _select_embedding_output(self, session: Any, outputs: Sequence[Any]) -> Any:
        get_outputs = getattr(session, "get_outputs", None)
        if callable(get_outputs):
            output_names = [str(output_meta.name) for output_meta in get_outputs()]
            for index, output_name in enumerate(output_names):
                if output_name == "sentence_embedding" and index < len(outputs):
                    return outputs[index]

        for output in outputs:
            candidate = np.asarray(output, dtype=np.float32)
            if candidate.ndim == 2 and candidate.shape[1] == self.config.embedding_dim:
                return output
        return outputs[0]

    @staticmethod
    def _fit_sequence(values: list[int], length: int, fill_value: int) -> list[int]:
        if len(values) < length:
            values = [*values, *([fill_value] * (length - len(values)))]
        return values[:length]

    @staticmethod
    def _mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
        if np is None:
            raise AgentEmbeddingError("numpy is not installed")
        mask = attention_mask.astype(np.float32)[..., None]
        summed = (last_hidden_state * mask).sum(axis=1)
        denominator = np.clip(mask.sum(axis=1), 1e-6, None)
        return summed / denominator

    @staticmethod
    def _normalize(embedding: Any) -> Any:
        if np is None:
            raise AgentEmbeddingError("numpy is not installed")
        norm = np.linalg.norm(embedding, axis=1, keepdims=True)
        return embedding / np.clip(norm, 1e-12, None)
