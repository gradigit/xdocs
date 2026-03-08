"""Embedding backend selection for semantic search.

Default model: ``jina-embeddings-v5-text-small`` (1024 dims, EuroBERT backbone).
Upgraded from v5-text-nano (768d) after M11 pre-rebuild validation confirmed
+12.5% Hit@5 improvement with safe memory/VRAM usage.

Backend auto-detection:
- macOS Apple Silicon: Jina MLX loader (``jina-embeddings-v5-text-small-mlx``).
- Linux/CUDA: SentenceTransformers with CUDA acceleration.
- Other: SentenceTransformers on CPU.

Override via env vars:
- CEX_EMBEDDING_BACKEND: auto | jina-mlx | sentence-transformers
- CEX_EMBEDDING_MODEL: MLX repo ID (macOS path)
- CEX_EMBEDDING_FALLBACK_MODEL: SentenceTransformers model name (Linux path)
- CEX_JINA_MLX_REVISION: Pin HuggingFace revision for MLX model
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

DEFAULT_JINA_MLX_REPO = "jinaai/jina-embeddings-v5-text-small-mlx"
DEFAULT_ST_MODEL = "jinaai/jina-embeddings-v5-text-small"
DEFAULT_BACKEND = "auto"  # auto | jina-mlx | sentence-transformers

# Pinned revision of jinaai/jina-embeddings-v5-text-small-mlx.
# Update deliberately after testing new versions.
_JINA_MLX_REVISION = os.getenv("CEX_JINA_MLX_REVISION", "main")


class Embedder(Protocol):
    backend_name: str
    model_name: str

    def embed_texts(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]: ...

    def ndims(self) -> int: ...


@dataclass(slots=True)
class JinaMlxEmbedder:
    repo_id: str
    max_length: int = 512
    backend_name: str = "jina-mlx"
    model_name: str = ""  # set to repo_id after load
    _multi_model: object | None = None
    _ndims: int | None = None
    _call_count: int = 0

    def _ensure_loaded(self):
        if self._multi_model is not None:
            return self._multi_model

        import importlib.util as ilu

        from huggingface_hub import snapshot_download  # type: ignore[import-not-found]

        revision = _JINA_MLX_REVISION
        try:
            model_dir = snapshot_download(self.repo_id, local_files_only=True, revision=revision)
        except Exception:
            logger.info("Downloading Jina MLX model: %s (rev=%s)", self.repo_id, revision)
            model_dir = snapshot_download(self.repo_id, revision=revision)

        spec = ilu.spec_from_file_location(
            "jina_mlx_utils", os.path.join(model_dir, "utils.py")
        )
        utils_mod = ilu.module_from_spec(spec)
        spec.loader.exec_module(utils_mod)  # type: ignore[union-attr]

        multi_model = utils_mod.load_model(model_dir)  # type: ignore[attr-defined]
        multi_model.switch_task("retrieval")
        self._multi_model = multi_model
        self.model_name = self.repo_id
        return multi_model

    def embed_texts(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        if not texts:
            return []

        import mlx.core as mx  # type: ignore[import-not-found]

        model = self._ensure_loaded()
        task_type = "retrieval.query" if is_query else "retrieval.passage"
        # encode() accepts max_length via **kwargs; returns mx.array (already mx.eval'd + L2-normalized)
        result = model.encode(texts, task_type=task_type, max_length=self.max_length)

        if isinstance(result, mx.array):
            mx.eval(result)  # Belt-and-suspenders (outer wrapper already evals)
            vectors = result.tolist()
        else:
            vectors = result.tolist() if hasattr(result, "tolist") else list(result)

        if self._ndims is None and vectors:
            self._ndims = len(vectors[0])

        # Periodically clear Metal cache to prevent memory bloat (mlx#2254).
        self._call_count += 1
        if self._call_count % 50 == 0:
            mx.clear_cache()
        return vectors

    def ndims(self) -> int:
        if self._ndims is None:
            probe = self.embed_texts(["dimension probe"])
            self._ndims = len(probe[0]) if probe else 0
        return self._ndims


@dataclass(slots=True)
class SentenceTransformerEmbedder:
    model_name: str
    backend_name: str = "sentence-transformers"
    _model: object | None = None
    _ndims: int | None = None

    def _ensure_loaded(self):
        if self._model is not None:
            return self._model
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        device = None
        model_kwargs: dict = {"default_task": "retrieval"}
        try:
            import torch  # type: ignore[import-not-found]

            if torch.cuda.is_available():
                device = "cuda"
                logger.info("Using CUDA device for SentenceTransformer")
                model_kwargs["dtype"] = torch.bfloat16
            elif torch.backends.mps.is_available():
                device = "mps"
                logger.info("Using MPS (Metal) device for SentenceTransformer")
                model_kwargs["dtype"] = torch.bfloat16
        except Exception:
            pass

        logger.info("Loading SentenceTransformer: %s", self.model_name)
        self._model = SentenceTransformer(
            self.model_name,
            device=device,
            trust_remote_code=True,
            model_kwargs=model_kwargs,
        )
        try:
            self._ndims = int(self._model.get_sentence_embedding_dimension())  # type: ignore[union-attr]
        except Exception:
            pass
        return self._model

    def embed_texts(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_loaded()
        arr = model.encode(  # type: ignore[union-attr]
            texts,
            prompt_name="query" if is_query else "document",
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=128,
        )
        vectors = arr.tolist()
        if self._ndims is None and vectors:
            self._ndims = len(vectors[0])
        return vectors

    def ndims(self) -> int:
        if self._ndims is None:
            probe = self.embed_texts(["dimension probe"])
            self._ndims = len(probe[0]) if probe else 0
        return self._ndims


_embedder_singleton: Embedder | None = None


def get_embedder() -> Embedder:
    """Return configured embedder with OS-aware backend selection.

    Auto-detection:
    - macOS + MLX available: Jina MLX loader (native Apple Silicon, fastest)
    - Linux + CUDA / other: SentenceTransformers (PyTorch, CUDA/CPU)
    """
    global _embedder_singleton
    if _embedder_singleton is not None:
        return _embedder_singleton

    backend = os.getenv("CEX_EMBEDDING_BACKEND", DEFAULT_BACKEND).strip().lower()
    jina_mlx_repo = os.getenv("CEX_EMBEDDING_MODEL", DEFAULT_JINA_MLX_REPO).strip()
    st_model = os.getenv("CEX_EMBEDDING_FALLBACK_MODEL", DEFAULT_ST_MODEL).strip()

    tried: list[str] = []

    if backend in {"auto", "jina-mlx", "jina_mlx"}:
        try:
            _embedder_singleton = JinaMlxEmbedder(repo_id=jina_mlx_repo)
            # Warm-up probe to fail fast on unsupported model/runtime.
            _embedder_singleton.ndims()
            return _embedder_singleton
        except Exception as e:
            tried.append(f"jina-mlx ({jina_mlx_repo}): {e}")
            if backend in {"jina-mlx", "jina_mlx"}:
                raise ImportError(
                    "Jina MLX embedding backend requested but unavailable. "
                    "Install extras: pip install cex-api-docs[semantic]"
                ) from e
            logger.warning("Jina MLX embedding backend unavailable; falling back: %s", e)

    if backend in {"auto", "sentence-transformers", "sentence_transformers", "st"}:
        try:
            _embedder_singleton = SentenceTransformerEmbedder(model_name=st_model)
            _embedder_singleton.ndims()
            return _embedder_singleton
        except Exception as e:
            tried.append(f"sentence-transformers ({st_model}): {e}")
            raise ImportError(
                "No embedding backend available. "
                "Install extras: pip install cex-api-docs[semantic]"
            ) from e

    raise ValueError(
        f"Unsupported CEX_EMBEDDING_BACKEND={backend!r}. "
        "Use one of: auto, jina-mlx, sentence-transformers. "
        f"Tried backends: {tried}"
    )
