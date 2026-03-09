"""Cross-encoder reranking with backend selection and OS auto-detection.

Backends (selected via CEX_RERANKER_BACKEND env var):
  - ``cross-encoder``: sentence-transformers CrossEncoder (PyTorch, CUDA/CPU/MPS).
    Model set via CEX_RERANKER_MODEL (default: cross-encoder/ms-marco-MiniLM-L-12-v2).
  - ``qwen3``: Qwen3-Reranker-0.6B via seq-cls conversion (sentence-transformers
    CrossEncoder, MTEB-R 65.80). Uses ``tomaarsen/Qwen3-Reranker-0.6B-seq-cls``.
  - ``jina-v3``: Jina Reranker v3 (Qwen3-based, custom architecture).
    Uses native ``JinaForRanking.rerank()`` method. On macOS with MLX,
    loads the MLX variant automatically.
  - ``flashrank``: FlashRank ONNX runtime (CPU-only, ~34MB).
  - ``auto`` (default): detects platform and picks the best available backend.
    macOS with MLX: jina-v3-mlx → jina-v3 → cross-encoder → flashrank.
    Linux/other: jina-v3 → cross-encoder → flashrank.

Lazy-loads models on first use.
"""

from __future__ import annotations

import logging
import os
import platform
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND = os.environ.get("CEX_RERANKER_BACKEND", "auto")
_MODEL = os.environ.get("CEX_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-12-v2")

_QWEN3_MODEL = os.environ.get(
    "CEX_RERANKER_QWEN3_MODEL", "tomaarsen/Qwen3-Reranker-0.6B-seq-cls"
)

_cross_encoder = None
_qwen3_encoder = None
_flash_ranker = None
_jina_v3_model = None


def _is_mlx_available() -> bool:
    """Check if MLX is available (macOS Apple Silicon)."""
    if platform.system() != "Darwin":
        return False
    try:
        import mlx.core  # noqa: F401
        return True
    except ImportError:
        return False


def _load_cross_encoder():
    """Lazy-load a sentence-transformers CrossEncoder."""
    global _cross_encoder
    if _cross_encoder is not None:
        return _cross_encoder

    from sentence_transformers import CrossEncoder

    logger.info("Loading CrossEncoder model %s ...", _MODEL)
    _cross_encoder = CrossEncoder(_MODEL)
    return _cross_encoder


def _load_qwen3_seq_cls():
    """Lazy-load Qwen3-Reranker-0.6B via seq-cls conversion."""
    global _qwen3_encoder
    if _qwen3_encoder is not None:
        return _qwen3_encoder

    from sentence_transformers import CrossEncoder

    logger.info("Loading Qwen3 seq-cls reranker %s ...", _QWEN3_MODEL)
    _qwen3_encoder = CrossEncoder(_QWEN3_MODEL)
    return _qwen3_encoder


_QWEN3_INSTRUCTION = (
    "Given a web search query, retrieve relevant passages that answer the query"
)

_QWEN3_QUERY_PREFIX = (
    "<|im_start|>system\n"
    "Judge whether the Document meets the requirements based on the Query "
    "and the Instruct provided. Note that the answer can only be "
    '"yes" or "no".<|im_end|>\n'
    "<|im_start|>user\n"
)

_QWEN3_DOC_SUFFIX = (
    "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
)


def _format_qwen3_query(query: str) -> str:
    return (
        f"{_QWEN3_QUERY_PREFIX}<Instruct>: {_QWEN3_INSTRUCTION}\n"
        f"<Query>: {query}\n"
    )


def _format_qwen3_doc(doc: str) -> str:
    return f"<Document>: {doc}{_QWEN3_DOC_SUFFIX}"


def _load_flashrank():
    """Lazy-load FlashRank."""
    global _flash_ranker
    if _flash_ranker is not None:
        return _flash_ranker

    from flashrank import Ranker

    flash_model = "ms-marco-MiniLM-L-12-v2"
    logger.info("Loading FlashRank model %s (first use downloads ~34MB)...", flash_model)
    _flash_ranker = Ranker(model_name=flash_model)
    return _flash_ranker


def _load_jina_v3():
    """Lazy-load Jina Reranker v3 via PyTorch (custom JinaForRanking)."""
    global _jina_v3_model
    if _jina_v3_model is not None:
        return _jina_v3_model

    import torch
    from transformers import AutoConfig, AutoModel

    repo = "jinaai/jina-reranker-v3"
    logger.info("Loading Jina Reranker v3 (%s)...", repo)

    config = AutoConfig.from_pretrained(repo, trust_remote_code=True)
    config.tie_word_embeddings = False  # Fix Identity/weight conflict

    device = "cpu"
    dtype = None
    if torch.cuda.is_available():
        device = "cuda"
        dtype = torch.bfloat16
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
        dtype = torch.bfloat16

    kwargs: dict[str, Any] = {"config": config, "trust_remote_code": True}
    if dtype is not None:
        kwargs["dtype"] = dtype

    model = AutoModel.from_pretrained(repo, **kwargs)
    _jina_v3_model = model.to(device).eval()
    return _jina_v3_model


def _load_jina_v3_mlx():
    """Lazy-load Jina Reranker v3 MLX variant (macOS only)."""
    global _jina_v3_model
    if _jina_v3_model is not None:
        return _jina_v3_model

    from huggingface_hub import snapshot_download
    import importlib.util as ilu

    repo = "jinaai/jina-reranker-v3-mlx"
    logger.info("Loading Jina Reranker v3 MLX (%s)...", repo)

    try:
        model_dir = snapshot_download(repo, local_files_only=True)
    except Exception:
        model_dir = snapshot_download(repo)

    # Load custom model code from the repo
    # The MLX variant uses rerank.py with MLXReranker class
    for modfile in ("rerank.py", "modeling.py"):
        modpath = os.path.join(model_dir, modfile)
        if os.path.exists(modpath):
            break
    else:
        raise ImportError(f"Cannot find rerank.py or modeling.py in {model_dir}")

    spec = ilu.spec_from_file_location("jina_reranker_v3_mlx", modpath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {modpath}")
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # MLXReranker (current) or JinaForRanking (legacy)
    cls = getattr(mod, "MLXReranker", None) or getattr(mod, "JinaForRanking", None)
    if cls is None:
        raise ImportError(f"No MLXReranker or JinaForRanking class in {modpath}")

    if modfile == "rerank.py":
        projector = os.path.join(model_dir, "projector.safetensors")
        _jina_v3_model = cls(model_path=model_dir, projector_path=projector)
    else:
        _jina_v3_model = cls.from_pretrained(model_dir, trust_remote_code=True)
    return _jina_v3_model


def _rerank_cross_encoder(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int,
    text_key: str,
) -> list[dict[str, Any]]:
    """Rerank using sentence-transformers CrossEncoder."""
    ce = _load_cross_encoder()
    pairs = [(query, r.get(text_key, "")) for r in results]
    scores = ce.predict(pairs)

    scored = list(zip(results, scores))
    scored.sort(key=lambda x: float(x[1]), reverse=True)

    output: list[dict[str, Any]] = []
    for item, score in scored[:top_n]:
        entry = dict(item)
        entry["rerank_score"] = float(score)
        output.append(entry)
    return output


def _rerank_qwen3(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int,
    text_key: str,
) -> list[dict[str, Any]]:
    """Rerank using Qwen3-Reranker-0.6B seq-cls (via CrossEncoder)."""
    ce = _load_qwen3_seq_cls()
    fq = _format_qwen3_query(query)
    pairs = [(fq, _format_qwen3_doc(r.get(text_key, ""))) for r in results]
    scores = ce.predict(pairs)

    scored = list(zip(results, scores))
    scored.sort(key=lambda x: float(x[1]), reverse=True)

    output: list[dict[str, Any]] = []
    for item, score in scored[:top_n]:
        entry = dict(item)
        entry["rerank_score"] = float(score)
        output.append(entry)
    return output


def _rerank_flashrank(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int,
    text_key: str,
) -> list[dict[str, Any]]:
    """Rerank using FlashRank ONNX."""
    ranker = _load_flashrank()
    from flashrank import RerankRequest

    passages = [{"id": i, "text": r.get(text_key, "")} for i, r in enumerate(results)]
    request = RerankRequest(query=query, passages=passages)
    ranked = ranker.rerank(request)

    output: list[dict[str, Any]] = []
    for item in ranked[:top_n]:
        idx = int(item["id"])
        entry = dict(results[idx])
        entry["rerank_score"] = float(item["score"])
        output.append(entry)
    return output


def _rerank_jina_v3(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int,
    text_key: str,
    use_mlx: bool = False,
) -> list[dict[str, Any]]:
    """Rerank using Jina Reranker v3 (native .rerank() method)."""
    model = _load_jina_v3_mlx() if use_mlx else _load_jina_v3()
    docs = [r.get(text_key, "") for r in results]
    ranked = model.rerank(query, docs, top_n=top_n)

    output: list[dict[str, Any]] = []
    for item in ranked:
        idx = item["index"]
        entry = dict(results[idx])
        entry["rerank_score"] = float(item["relevance_score"])
        output.append(entry)
    return output


def rerank(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int = 5,
    text_key: str = "text",
) -> list[dict[str, Any]]:
    """Rerank search results using the configured backend.

    Returns reranked list (top_n), each augmented with ``rerank_score``.
    """
    if not results:
        return []

    backend = _BACKEND

    if backend == "cross-encoder":
        return _rerank_cross_encoder(query, results, top_n=top_n, text_key=text_key)
    elif backend == "qwen3":
        return _rerank_qwen3(query, results, top_n=top_n, text_key=text_key)
    elif backend == "flashrank":
        return _rerank_flashrank(query, results, top_n=top_n, text_key=text_key)
    elif backend == "jina-v3":
        return _rerank_jina_v3(query, results, top_n=top_n, text_key=text_key)
    elif backend == "jina-v3-mlx":
        return _rerank_jina_v3(query, results, top_n=top_n, text_key=text_key, use_mlx=True)
    elif backend == "auto":
        return _auto_rerank(query, results, top_n=top_n, text_key=text_key)
    else:
        raise ValueError(
            f"Unknown reranker backend: {backend!r}. "
            "Use: auto, cross-encoder, qwen3, jina-v3, jina-v3-mlx, flashrank"
        )


def _auto_rerank(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int,
    text_key: str,
) -> list[dict[str, Any]]:
    """Auto-detect the best available backend.

    macOS + MLX: jina-v3-mlx → jina-v3 → cross-encoder → flashrank
    Linux/other: jina-v3 → cross-encoder → flashrank

    M10 benchmark (163 queries, paired permutation test):
      Jina v3: MRR=0.556 (+15.6% over MiniLM, p=0.0014, significant)
      MiniLM CrossEncoder: MRR=0.481, 76ms (CUDA)
      Jina v3 latency: 218ms — well within acceptable range.
    """
    backends: list[str] = []

    if _is_mlx_available():
        backends.append("jina-v3-mlx")

    backends.extend(["jina-v3", "cross-encoder", "flashrank"])

    last_exc: Exception | None = None
    for name in backends:
        try:
            if name == "jina-v3-mlx":
                return _rerank_jina_v3(query, results, top_n=top_n, text_key=text_key, use_mlx=True)
            elif name == "jina-v3":
                return _rerank_jina_v3(query, results, top_n=top_n, text_key=text_key)
            elif name == "qwen3":
                return _rerank_qwen3(query, results, top_n=top_n, text_key=text_key)
            elif name == "cross-encoder":
                return _rerank_cross_encoder(query, results, top_n=top_n, text_key=text_key)
            elif name == "flashrank":
                return _rerank_flashrank(query, results, top_n=top_n, text_key=text_key)
        except (ImportError, Exception) as exc:
            logger.info("Reranker backend %s unavailable (%s), trying next", name, exc)
            last_exc = exc

    raise ImportError(
        "No reranker backend available. Install: uv pip install -e '.[semantic-query]'"
    ) from last_exc
