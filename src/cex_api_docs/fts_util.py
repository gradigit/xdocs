"""Shared FTS5 query utilities.

Consolidates sanitization logic previously duplicated across answer.py and
endpoints.py. All modules that build FTS5 MATCH queries should use these
helpers to avoid FTS5 syntax errors from special characters.
"""

from __future__ import annotations

import re


# FTS5 keywords that must not appear as bare terms in a MATCH expression.
FTS5_KEYWORDS = frozenset({"OR", "AND", "NOT", "NEAR"})

# Common stopwords stripped from search queries.
STOPWORDS = frozenset({
    "the", "and", "for", "what", "how", "does", "this", "that", "with", "from",
    "are", "can", "api", "is", "it", "of", "to", "in", "on", "by", "an", "a",
})


def sanitize_fts_query(query: str) -> str:
    """Quote FTS5 query terms that contain special characters.

    FTS5 interprets hyphens as NOT operators and colons as column prefixes.
    Wrapping such terms in double quotes forces literal matching.
    """
    tokens = query.split()
    safe: list[str] = []
    for t in tokens:
        if re.search(r'[-:"/{}()*?=&+#@!<>]', t):
            # Already quoted — leave alone.
            if t.startswith('"') and t.endswith('"'):
                safe.append(t)
            else:
                # Escape any internal double quotes before wrapping.
                escaped = t.replace('"', '""')
                safe.append(f'"{escaped}"')
        else:
            safe.append(t)
    return " ".join(safe)


def build_fts_query(
    terms: list[str],
    *,
    max_terms: int = 8,
) -> str:
    """Build an FTS5 MATCH query from a list of search terms.

    - 1 term: no operator (implicit match)
    - 2 terms: OR (avoid over-restriction per review finding F5)
    - 3+ terms: AND (precision over recall)

    All terms are sanitized for FTS5 special characters.
    """
    # Filter FTS5 keywords and empty strings.
    clean = [t for t in terms[:max_terms] if t and t.upper() not in FTS5_KEYWORDS]
    if not clean:
        return ""

    sanitized = [sanitize_fts_query(t) for t in clean]

    if len(sanitized) == 1:
        return sanitized[0]
    elif len(sanitized) == 2:
        return " OR ".join(sanitized)
    else:
        return " AND ".join(sanitized)


def extract_search_terms(text: str, *, extra_stopwords: set[str] | None = None) -> list[str]:
    """Extract meaningful search terms from a question/query string.

    Strips punctuation (preserving hyphens within words), removes stopwords,
    and filters short tokens.
    """
    # Preserve hyphens within words but strip other punctuation.
    norm = re.sub(r"[^\w\s\-]", " ", text.lower())
    stops = STOPWORDS | (extra_stopwords or set())
    return [w for w in norm.split() if len(w) > 2 and w not in stops]


def normalize_bm25_score(raw_score: float) -> float:
    """Normalize BM25 score to [0, 1) range using |x|/(1+|x|).

    Adopted from qmd: parameter-free, monotonic, bounded.
    BM25 scores are negative in SQLite FTS5 (more negative = better match).
    """
    x = abs(raw_score)
    return x / (1.0 + x)


def rrf_fuse(
    *ranked_lists: list[dict],
    k: int = 60,
    key: str = "canonical_url",
) -> list[dict]:
    """Reciprocal Rank Fusion across multiple ranked result lists.

    RRF_score(d) = SUM over all lists L: 1 / (k + rank(d, L))

    Documents are identified by ``key`` field. Returns fused results
    sorted by descending RRF score, each augmented with ``rrf_score``.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for ranked in ranked_lists:
        for rank_0, item in enumerate(ranked):
            doc_key = item.get(key, "")
            if not doc_key:
                continue
            scores[doc_key] = scores.get(doc_key, 0.0) + 1.0 / (k + rank_0 + 1)
            if doc_key not in items:
                items[doc_key] = item

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result = []
    for doc_key, score in fused:
        entry = dict(items[doc_key])
        entry["rrf_score"] = score
        result.append(entry)
    return result


import math


def sigmoid(x: float) -> float:
    """Sigmoid normalization for unbounded scores (e.g. FlashRank logits)."""
    return 1.0 / (1.0 + math.exp(-x))


def position_aware_blend(
    results: list[dict],
    *,
    retrieval_score_key: str = "rrf_score",
    reranker_score_key: str = "rerank_score",
) -> list[dict]:
    """Blend retrieval and reranker scores with position-aware weights.

    Weight schedule (from qmd research):
    - Ranks 1-3: 75% retrieval, 25% reranker
    - Ranks 4-10: 60% retrieval, 40% reranker
    - Ranks 11+: 40% retrieval, 60% reranker

    Both RRF and reranker scores are normalized to [0,1] before blending
    to ensure the weight schedule has its intended effect. RRF scores are
    max-normalized; reranker scores use sigmoid.
    """
    if not results:
        return []

    # Max-normalize RRF scores to [0, 1] so they're on the same scale as
    # sigmoid-normalized reranker scores.
    rrf_max = max((item.get(retrieval_score_key, 0.0) for item in results), default=0.0)

    blended = []
    for i, item in enumerate(results):
        entry = dict(item)
        rrf_raw = item.get(retrieval_score_key, 0.0)
        rrf_norm = rrf_raw / rrf_max if rrf_max > 0 else 0.0
        rerank_raw = item.get(reranker_score_key)

        if rerank_raw is not None:
            rerank_norm = sigmoid(rerank_raw)
            rank_1based = i + 1
            if rank_1based <= 3:
                w_ret, w_rer = 0.75, 0.25
            elif rank_1based <= 10:
                w_ret, w_rer = 0.60, 0.40
            else:
                w_ret, w_rer = 0.40, 0.60
            entry["blended_score"] = w_ret * rrf_norm + w_rer * rerank_norm
        else:
            entry["blended_score"] = rrf_norm

        blended.append(entry)

    blended.sort(key=lambda x: x["blended_score"], reverse=True)
    return blended


def should_skip_vector_search(
    fts_results: list[dict],
    *,
    score_key: str = "bm25_score",
    min_top_score: float = 0.7,
    min_gap: float = 0.3,
) -> bool:
    """Check if BM25 results are strong enough to skip vector search.

    Returns True when the normalized top BM25 score >= min_top_score
    and the gap between #1 and #2 >= min_gap, indicating a clear
    high-confidence keyword match.
    """
    if len(fts_results) < 1:
        return False
    top = fts_results[0].get(score_key, 0.0)
    if top < min_top_score:
        return False
    if len(fts_results) < 2:
        return True  # Single strong result — skip vector.
    second = fts_results[1].get(score_key, 0.0)
    return (top - second) >= min_gap


def endpoint_search_text(record: dict) -> str:
    """Build plain-text search content for an endpoint record.

    Extracts only VALUES (description, rate limit text, error code descriptions)
    — no JSON keys. This prevents false positives from key names like
    "error_codes" matching every endpoint.
    """
    parts: list[str] = []

    desc = record.get("description")
    if desc:
        parts.append(str(desc))

    # Rate limit: extract all values from the dict.
    rate_limit = record.get("rate_limit")
    if isinstance(rate_limit, dict):
        for val in rate_limit.values():
            if val is not None:
                parts.append(str(val))
    elif rate_limit is not None:
        parts.append(str(rate_limit))

    # Error codes: extract code + message pairs.
    error_codes = record.get("error_codes")
    if isinstance(error_codes, list):
        for ec in error_codes:
            if isinstance(ec, dict):
                code = ec.get("code")
                msg = ec.get("message") or ec.get("description", "")
                if code is not None:
                    parts.append(str(code))
                if msg:
                    parts.append(str(msg))
            else:
                parts.append(str(ec))
    elif isinstance(error_codes, dict):
        for code, msg in error_codes.items():
            parts.append(str(code))
            if msg:
                parts.append(str(msg))

    # Required permissions.
    perms = record.get("required_permissions")
    if isinstance(perms, list):
        parts.extend(str(p) for p in perms)
    elif isinstance(perms, str) and perms:
        parts.append(perms)

    return "\n".join(parts)
