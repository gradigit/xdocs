"""Cross-encoder reranking via jina-reranker-v3-mlx (Apple Silicon MLX).

Lazy-loads the model on first use. Requires ``pip install cex-api-docs[reranker]``
which installs ``mlx`` and ``mlx-lm``. The model weights (~1.2 GB) are downloaded
from HuggingFace on first use and cached locally.

License: CC BY-NC 4.0 (acceptable for internal tooling).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ID = "jinaai/jina-reranker-v3-mlx"
_reranker = None


def _require_reranker():
    """Lazy-load the jina-reranker-v3-mlx model."""
    global _reranker
    if _reranker is not None:
        return _reranker

    try:
        import mlx  # noqa: F401 — verify mlx is installed
    except ImportError:
        raise ImportError(
            "mlx is not installed. Run: pip install cex-api-docs[reranker]"
        )

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is not installed. Run: pip install huggingface_hub"
        )

    logger.info("Downloading jina-reranker-v3-mlx model (first use may take a few minutes)...")
    model_dir = snapshot_download(_REPO_ID)

    # The rerank.py module is bundled inside the downloaded model repo.
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)

    try:
        from rerank import MLXReranker  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            f"Could not import MLXReranker from downloaded model at {model_dir}: {e}"
        )

    logger.info("Loading jina-reranker-v3-mlx model...")
    _reranker = MLXReranker(
        model_path=model_dir,
        projector_path=f"{model_dir}/projector.safetensors",
    )
    return _reranker


def rerank(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int = 5,
    text_key: str = "text",
) -> list[dict[str, Any]]:
    """Rerank search results using jina-reranker-v3-mlx cross-encoder.

    Args:
        query: The search query.
        results: List of result dicts, each containing a text field.
        top_n: Number of top results to return.
        text_key: Key in result dicts containing the document text.

    Returns:
        Reranked list of result dicts (top_n), each augmented with ``rerank_score``.
    """
    if not results:
        return []

    reranker = _require_reranker()

    documents = [r.get(text_key, "") for r in results]

    # Score all documents against the query.
    ranked = reranker.rerank(query, documents, top_n=top_n)

    # Map back to original result dicts, adding rerank_score.
    output: list[dict[str, Any]] = []
    for item in ranked:
        idx = item["index"]
        result_copy = dict(results[idx])
        result_copy["rerank_score"] = item["relevance_score"]
        output.append(result_copy)

    return output
