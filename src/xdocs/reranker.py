"""Jina Reranker v3 — single backend, OS auto-detection.

macOS with MLX: loads jinaai/jina-reranker-v3-mlx (fast, native Apple Silicon).
Linux/other: loads jinaai/jina-reranker-v3 via PyTorch (CUDA/CPU).

M10 benchmark (163 queries, paired permutation test):
  Jina v3: MRR=0.556 (+15.6% over MiniLM, p=0.0014).

Lazy-loads model on first use.
"""

from __future__ import annotations

import logging
import os
import platform
from typing import Any

logger = logging.getLogger(__name__)

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

    cls = getattr(mod, "MLXReranker", None) or getattr(mod, "JinaForRanking", None)
    if cls is None:
        raise ImportError(f"No MLXReranker or JinaForRanking class in {modpath}")

    if modfile == "rerank.py":
        projector = os.path.join(model_dir, "projector.safetensors")
        _jina_v3_model = cls(model_path=model_dir, projector_path=projector)
    else:
        _jina_v3_model = cls.from_pretrained(model_dir, trust_remote_code=True)
    return _jina_v3_model


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
    """Rerank search results using Jina Reranker v3.

    Returns reranked list (top_n), each augmented with ``rerank_score``.
    macOS: MLX backend (no PyTorch fallback — fix the MLX path if it breaks).
    Linux: PyTorch backend via transformers.
    """
    if not results:
        return []

    if _is_mlx_available():
        return _rerank_jina_v3(query, results, top_n=top_n, text_key=text_key, use_mlx=True)

    return _rerank_jina_v3(query, results, top_n=top_n, text_key=text_key)
