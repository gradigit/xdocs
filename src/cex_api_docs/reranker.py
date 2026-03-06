"""Cross-encoder reranking via FlashRank (ONNX, CPU-only, no PyTorch).

Uses ms-marco-MiniLM-L-12-v2 (~34MB, ~80ms for 20 docs on CPU).
Lazy-loads the model on first use. Requires ``pip install cex-api-docs[reranker]``
which installs ``flashrank``.

License: Apache 2.0.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MODEL_NAME = "ms-marco-MiniLM-L-12-v2"
_ranker = None


def _require_ranker():
    """Lazy-load the FlashRank model."""
    global _ranker
    if _ranker is not None:
        return _ranker

    try:
        from flashrank import Ranker
    except ImportError:
        raise ImportError(
            "flashrank is not installed. Run: pip install cex-api-docs[reranker]"
        )

    logger.info("Loading FlashRank model %s (first use downloads ~34MB)...", _MODEL_NAME)
    _ranker = Ranker(model_name=_MODEL_NAME)
    return _ranker


def rerank(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int = 5,
    text_key: str = "text",
) -> list[dict[str, Any]]:
    """Rerank search results using FlashRank cross-encoder.

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

    ranker = _require_ranker()

    # Build passages list for FlashRank.
    # FlashRank expects list of dicts with "id" and "text" keys.
    from flashrank import RerankRequest

    passages = []
    for i, r in enumerate(results):
        passages.append({"id": i, "text": r.get(text_key, "")})

    request = RerankRequest(query=query, passages=passages)
    ranked = ranker.rerank(request)

    # FlashRank returns dicts with "id", "text", "score" keys, sorted by score desc.
    output: list[dict[str, Any]] = []
    for item in ranked[:top_n]:
        idx = int(item["id"])
        result_copy = dict(results[idx])
        result_copy["rerank_score"] = float(item["score"])
        output.append(result_copy)

    return output
