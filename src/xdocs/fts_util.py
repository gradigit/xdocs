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

# Code-syntax stopwords: programming tokens stripped from code_snippet queries.
# These pollute FTS queries with language-specific noise instead of domain terms.
CODE_STOPWORDS = frozenset({
    # Python
    "import", "from", "print", "def", "class", "return", "self", "none", "true",
    "false", "lambda", "pass", "break", "continue", "yield", "async", "await",
    # JavaScript/TypeScript
    "const", "let", "var", "function", "require", "module", "exports", "new",
    "console", "log", "then", "catch", "finally", "undefined", "null",
    # Common SDK/framework identifiers
    "ccxt", "exchange", "client", "result", "response", "error", "data",
    "params", "options", "config", "key", "secret", "apikey", "apisecret",
    # Generic code patterns
    "str", "int", "float", "dict", "list", "set", "type", "encode", "decode",
})

# Domain synonym/acronym map for query expansion.
# Each key maps to a list of synonyms that should also be searched.
# Applied AFTER stopword removal but BEFORE building the FTS query.
_SYNONYM_MAP: dict[str, list[str]] = {
    "ws": ["websocket"],
    "websocket": ["ws", "wss"],
    "wss": ["websocket", "ws"],
    "auth": ["authentication", "authorization"],
    "authentication": ["auth"],
    "authorization": ["auth"],
    "perps": ["perpetual", "perpetuals"],
    "perpetual": ["perps"],
    "ohlc": ["candlestick", "kline", "candle"],
    "candlestick": ["ohlc", "kline"],
    "kline": ["ohlc", "candlestick"],
    "candle": ["ohlc", "candlestick", "kline"],
    "orderbook": ["order-book", "depth"],
    "order-book": ["orderbook", "depth"],
    "depth": ["orderbook", "order-book"],
    "subaccount": ["sub-account"],
    "sub-account": ["subaccount"],
    "rest": ["http"],
    "withdraw": ["withdrawal"],
    "withdrawal": ["withdraw"],
    "deposit": ["deposits"],
    "balance": ["balances"],
    "ticker": ["tickers"],
    "symbol": ["symbols"],
    "trade": ["trades", "trading"],
    "trading": ["trade", "trades"],
    # Financial terms
    "leverage": ["margin"],
    "margin": ["leverage"],
    "pnl": ["profit", "unrealized"],
    "profit": ["pnl"],
    "funding": ["funding-rate"],
    "funding-rate": ["funding"],
    "fee": ["commission"],
    "commission": ["fee"],
    "transfer": ["internal-transfer"],
    "position": ["positions"],
    "positions": ["position"],
    # API structure terms
    "listen-key": ["user-data-stream"],
    "user-data-stream": ["listen-key"],
    "market": ["exchange-info", "symbols"],
    "account": ["wallet"],
    "wallet": ["account"],
    "order": ["orders"],
    "orders": ["order"],
}


def sanitize_fts_query(query: str) -> str:
    """Quote FTS5 query terms that contain special characters.

    FTS5 interprets hyphens as NOT operators and colons as column prefixes.
    Wrapping such terms in double quotes forces literal matching.
    """
    tokens = query.split()
    safe: list[str] = []
    for t in tokens:
        if re.search(r'[-:"\'/{}()*?=&+#@!<>;]', t):
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
    operator: str = "auto",
) -> str:
    """Build an FTS5 MATCH query from a list of search terms.

    Default ``operator="auto"`` uses AND for 2+ terms and bare match for 1 term.
    Pass ``operator="or"`` to force OR logic (used by fallback paths).

    All terms are sanitized for FTS5 special characters.
    """
    # Filter FTS5 keywords and empty strings.
    clean = [t for t in terms[:max_terms] if t and t.upper() not in FTS5_KEYWORDS]
    if not clean:
        return ""

    sanitized = [sanitize_fts_query(t) for t in clean]

    if len(sanitized) == 1:
        return sanitized[0]

    if operator == "or":
        return " OR ".join(sanitized)

    # Default: AND for 2+ terms (precision over recall).
    return " AND ".join(sanitized)


def expand_synonyms(terms: list[str], *, max_expansions: int = 3) -> list[str]:
    """Expand terms with domain synonyms/acronyms.

    Returns the original terms plus up to ``max_expansions`` synonym terms,
    deduplicating and preserving order.
    """
    seen = set(terms)
    expanded = list(terms)
    added = 0
    for t in terms:
        for syn in _SYNONYM_MAP.get(t, []):
            if syn not in seen and added < max_expansions:
                expanded.append(syn)
                seen.add(syn)
                added += 1
    return expanded


def extract_search_terms(
    text: str,
    *,
    extra_stopwords: set[str] | None = None,
    synonyms: bool = True,
) -> list[str]:
    """Extract meaningful search terms from a question/query string.

    Strips punctuation (preserving hyphens within words), removes stopwords,
    filters short tokens, and optionally expands domain synonyms.
    """
    # Preserve hyphens within words but strip other punctuation.
    norm = re.sub(r"[^\w\s\-]", " ", text.lower())
    stops = STOPWORDS | (extra_stopwords or set())
    terms = [w for w in norm.split() if len(w) > 2 and w not in stops]
    if synonyms and terms:
        terms = expand_synonyms(terms)
    return terms


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
    weights: list[float] | None = None,
) -> list[dict]:
    """Reciprocal Rank Fusion across multiple ranked result lists.

    RRF_score(d) = SUM over all lists L: weight_L / (k + rank(d, L))

    If ``weights`` is None, all lists have equal weight (1.0).
    Documents are identified by ``key`` field. Returns fused results
    sorted by descending RRF score, each augmented with ``rrf_score``.
    """
    list_weights = weights or [1.0] * len(ranked_lists)
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for list_idx, ranked in enumerate(ranked_lists):
        w = list_weights[list_idx] if list_idx < len(list_weights) else 1.0
        for rank_0, item in enumerate(ranked):
            doc_key = item.get(key, "")
            if not doc_key:
                continue
            scores[doc_key] = scores.get(doc_key, 0.0) + w / (k + rank_0 + 1)
            if doc_key not in items:
                items[doc_key] = item

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result = []
    for doc_key, score in fused:
        entry = dict(items[doc_key])
        entry["rrf_score"] = score
        result.append(entry)
    return result


def cc_fuse(
    fts_results: list[dict],
    sem_results: list[dict],
    *,
    alpha: float = 0.5,
    key: str = "canonical_url",
    bm25_key: str = "bm25_score",
    sem_key: str = "semantic_score",
) -> list[dict]:
    """Score-aware Convex Combination fusion.

    ``final_score = alpha * minmax(bm25) + (1 - alpha) * minmax(semantic)``

    Per-query MinMax normalization maps each score set to [0, 1] before
    combining. Documents appearing in only one list get 0 for the missing
    component. Returns fused results sorted by descending ``cc_score``.
    """
    # Gather raw scores keyed by document identifier.
    bm25_scores: dict[str, float] = {}
    sem_scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for item in fts_results:
        doc_key = item.get(key, "")
        if not doc_key:
            continue
        bm25_scores[doc_key] = item.get(bm25_key, 0.0)
        if doc_key not in items:
            items[doc_key] = item

    for item in sem_results:
        doc_key = item.get(key, "")
        if not doc_key:
            continue
        sem_scores[doc_key] = item.get(sem_key, 0.0)
        if doc_key not in items:
            items[doc_key] = item

    # Per-query MinMax normalization to [0, 1].
    def _minmax(scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        vals = scores.values()
        lo, hi = min(vals), max(vals)
        span = hi - lo
        if span < 1e-9:
            # All equal — normalize to 1.0 (single-result convention per OpenSearch).
            return {k: 1.0 for k in scores}
        return {k: (v - lo) / span for k, v in scores.items()}

    bm25_norm = _minmax(bm25_scores)
    sem_norm = _minmax(sem_scores)

    all_keys = set(bm25_norm) | set(sem_norm)
    fused: list[tuple[str, float, int]] = []
    for doc_key in all_keys:
        b = bm25_norm.get(doc_key, 0.0)
        s = sem_norm.get(doc_key, 0.0)
        cc_score = alpha * b + (1.0 - alpha) * s
        # Tiebreaker: documents in both lists rank higher than single-list.
        in_both = 1 if (doc_key in bm25_norm and doc_key in sem_norm) else 0
        fused.append((doc_key, cc_score, in_both))

    fused.sort(key=lambda x: (x[1], x[2]), reverse=True)
    result = []
    for doc_key, score, _tiebreak in fused:
        entry = dict(items[doc_key])
        entry["cc_score"] = score
        entry["rrf_score"] = score  # Alias for downstream boost functions that read rrf_score.
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
    query_type_hint: str | None = None,
) -> list[dict]:
    """Blend retrieval and reranker scores with position-aware weights.

    Weight schedule (from qmd research):
    - Ranks 1-3: 75% retrieval, 25% reranker
    - Ranks 4-10: 60% retrieval, 40% reranker
    - Ranks 11+: 40% retrieval, 60% reranker

    The ``query_type_hint`` parameter selects weight schedules that give
    the reranker more influence for query types where BM25/vector retrieval
    alone produces noisy results (code_snippet, request_payload).

    Both RRF and reranker scores are normalized to [0,1] before blending
    to ensure the weight schedule has its intended effect. RRF scores are
    max-normalized; reranker scores use sigmoid.
    """
    if not results:
        return []

    # Query-type-aware weight schedules.
    # Default: positions 1-3 favour retrieval (75/25), deeper positions
    # shift toward reranker. For code/payload queries, reranker gets more
    # influence throughout because FTS terms are noisy (BUG-8).
    _DEFAULT_SCHEDULE = ((3, 0.75, 0.25), (10, 0.60, 0.40), (999, 0.40, 0.60))
    _RERANKER_HEAVY = ((3, 0.55, 0.45), (10, 0.40, 0.60), (999, 0.30, 0.70))
    schedule = _DEFAULT_SCHEDULE
    if query_type_hint in ("code_snippet", "request_payload"):
        schedule = _RERANKER_HEAVY

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
            w_ret, w_rer = schedule[-1][1], schedule[-1][2]
            for max_rank, wr, wk in schedule:
                if rank_1based <= max_rank:
                    w_ret, w_rer = wr, wk
                    break
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

    # NOTE: Request parameter names intentionally excluded from search_text.
    # A/B test (M22 Step 6) showed that adding common param names (symbol, side,
    # type) to FTS reduced BM25 discriminative power: request_payload MRR -12.6%.

    return "\n".join(parts)
