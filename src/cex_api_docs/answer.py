from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import logging
import os

from .classify import classify_input
from .db import open_db
from .fts_util import sanitize_fts_query, build_fts_query, extract_search_terms, rrf_fuse, normalize_bm25_score, should_skip_vector_search
from .registry import load_registry
from .resolve_docs_urls import _is_spec_url

logger = logging.getLogger(__name__)

# Feature flag: section-metadata post-fusion boost (default off until validated).
_SECTION_BOOST_ENABLED = os.environ.get("CEX_SECTION_BOOST", "0") == "1"
_SECTION_BOOST_FACTOR = 1.3

# Testnet/sandbox URL patterns to suppress from search results.
_TESTNET_PATTERNS = ("/testnet/", "/sandbox/")

# Page-type boost: promote overview/intro pages for broad questions.
_PAGE_TYPE_BOOST_ENABLED = os.environ.get("CEX_PAGE_TYPE_BOOST", "1") == "1"
_PAGE_TYPE_BOOST_FACTOR = 1.4
_OVERVIEW_URL_PATTERNS = re.compile(
    r"/(intro(?:duction)?|overview|general[_-]?info|getting[_-]?started|"
    r"quick[_-]?start|authentication|request[_-]?security|"
    r"rate[_-]?limit|api[_-]?info|rest-api(?:/|$))"
    r"(?:[^/]*)?$",
    re.IGNORECASE,
)
# Broad question indicators: queries that want overview pages, not specific endpoints.
_BROAD_QUESTION_PATTERNS = re.compile(
    r"\bhow\s+(?:to|do|does|can)\b|\bwhat\s+(?:is|are|does)\b|"
    r"\brate\s+limit|\bpermission|\bauthenticat|\bintro(?:duction)?\b|"
    r"\boverview\b|\bquickstart\b|\bgetting\s+started\b",
    re.IGNORECASE,
)

# Deprecated/abandoned URL patterns to demote in ranking.
_DEPRECATED_URL_PATTERNS = re.compile(
    r"/(abandoned[_-]?endpoints?|deprecated|legacy[_-]?api|obsolete|old[_-]?api)/",
    re.IGNORECASE,
)
_DEPRECATED_DEMOTION_FACTOR = 0.5  # Halve the score for deprecated URLs.


def _is_testnet_url(url: str) -> bool:
    """Return True if URL points to a testnet/sandbox page."""
    lower = url.lower()
    return any(p in lower for p in _TESTNET_PATTERNS)


def _normalize_question(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip()).lower()


# -- Binance section keyword detection --

_BINANCE_SECTION_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bportfolio\s+margin\b"), "portfolio_margin"),
    (re.compile(r"\bcopy\s+trading\b"), "copy_trading"),
    (re.compile(r"\bmargin\s+trading\b"), "margin_trading"),
    (re.compile(r"\bcoin[\-\s]?m\b|\bfutures\s+coinm\b"), "futures_coinm"),
    (re.compile(r"\busd[\-\s]?m\b|\busds\b|\bfutures\s+usdm\b"), "futures_usdm"),
    (re.compile(r"\bfutures\b"), "futures_usdm"),
    (re.compile(r"\boptions?\b"), "options"),
    (re.compile(r"\bmargin\b"), "margin_trading"),
    (re.compile(r"\bwebsocket\b|\bws\b|\bstream\b"), "websocket"),
    (re.compile(r"\bwallet\b"), "wallet"),
    (re.compile(r"\bspot\b"), "spot"),
    (re.compile(r"\bcopy\b"), "copy_trading"),
]


def _detect_binance_section(norm: str) -> str | None:
    """Map query keywords to a Binance section ID."""
    for pattern, section_id in _BINANCE_SECTION_KEYWORDS:
        if pattern.search(norm):
            return section_id
    return None


_EXCHANGE_SECTION_KEYWORDS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "kucoin": [
        (re.compile(r"\bfutures?\b|\bperps?\b|\bperpetual\b"), "futures"),
        (re.compile(r"\bmargin\b"), "margin"),
        (re.compile(r"\bspot\b|\bmarket\s+data\b"), "spot"),
    ],
    "kraken": [
        (re.compile(r"\bfutures?\b|\bperps?\b|\bperpetual\b"), "futures"),
        (re.compile(r"\bspot\b"), "spot"),
    ],
    "coinbase": [
        (re.compile(r"\bprime\b"), "prime"),
        (re.compile(r"\bexchange\b"), "exchange"),
        (re.compile(r"\badvanced\s+trade\b"), "advanced_trade"),
        (re.compile(r"\bintx?\b|\binternational\b"), "intx"),
    ],
    "bitget": [
        (re.compile(r"\bcopy\s*trad\b"), "copy_trading"),
        (re.compile(r"\bmargin\b"), "margin"),
        (re.compile(r"\bearn\b|\bstaking\b"), "earn"),
    ],
    "htx": [
        (re.compile(r"\bcoin[\-\s]?margined?\b|\bcoin[\-\s]?m\b"), "coin_margined_swap"),
        (re.compile(r"\busdt?\s+swap\b|\blinear\b"), "usdt_swap"),
        (re.compile(r"\bfutures?\b|\bderivatives?\b|\bswap\b"), "derivatives"),
        (re.compile(r"\bspot\b"), "spot"),
    ],
    "mexc": [
        (re.compile(r"\bfutures?\b|\bcontract\b|\bperps?\b"), "futures"),
        (re.compile(r"\bspot\b"), "spot"),
    ],
    "bitmart": [
        (re.compile(r"\bfutures?\b|\bcontract\b|\bperps?\b"), "futures"),
        (re.compile(r"\bspot\b"), "spot"),
    ],
    "okx": [
        (re.compile(r"\bwebsocket\b|\bws\b|\bstream\b"), "websocket"),
        (re.compile(r"\brest\b|\bhttp\b|\bapi\b"), "rest"),
    ],
}


def _detect_section_keywords(norm: str, exchange) -> str | None:
    """Detect section from keywords for any multi-section exchange."""
    section_ids = [sec.section_id for sec in exchange.sections]
    if len(section_ids) <= 1:
        return None

    # Exchange-specific keyword maps (more accurate than generic matching).
    ex_id = getattr(exchange, "exchange_id", None)
    if ex_id and ex_id in _EXCHANGE_SECTION_KEYWORDS:
        for pattern, section_id in _EXCHANGE_SECTION_KEYWORDS[ex_id]:
            if section_id in section_ids and pattern.search(norm):
                return section_id

    # Generic fallback: match section_id as a word in the query.
    for sid in section_ids:
        if re.search(r"\b" + re.escape(sid) + r"\b", norm):
            return sid
        spaced = sid.replace("_", " ")
        if spaced != sid and re.search(r"\b" + re.escape(spaced) + r"\b", norm):
            return sid
    return None


def _apply_section_boost(
    results: list[dict], *, section_prefix: str | None,
) -> list[dict]:
    """Boost results whose URL matches the detected section prefix.

    Only applied when CEX_SECTION_BOOST=1 and a section was detected.
    Multiplies rrf_score by _SECTION_BOOST_FACTOR for matching URLs,
    then re-sorts.
    """
    if not _SECTION_BOOST_ENABLED or not section_prefix or not results:
        return results
    boosted = []
    for item in results:
        entry = dict(item)
        url = entry.get("canonical_url", "")
        if url.startswith(section_prefix):
            rrf = entry.get("rrf_score", 0.0)
            entry["rrf_score"] = rrf * _SECTION_BOOST_FACTOR
            entry["section_boosted"] = True
        boosted.append(entry)
    boosted.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    return boosted


def _apply_page_type_boost(
    results: list[dict], *, norm: str,
) -> list[dict]:
    """Boost overview/intro pages for broad questions.

    Broad questions ("how to", "what is", "rate limit", "authentication") often
    want general info pages, but BM25 IDF penalizes common terms that appear
    across many pages — causing specific endpoint pages to rank higher.

    Multiplies rrf_score by _PAGE_TYPE_BOOST_FACTOR for pages whose URL matches
    overview/intro patterns, then re-sorts.
    """
    if not _PAGE_TYPE_BOOST_ENABLED or not results:
        return results
    if not _BROAD_QUESTION_PATTERNS.search(norm):
        return results
    boosted = []
    for item in results:
        entry = dict(item)
        url = entry.get("canonical_url", "")
        if _OVERVIEW_URL_PATTERNS.search(url):
            rrf = entry.get("rrf_score", 0.0)
            entry["rrf_score"] = rrf * _PAGE_TYPE_BOOST_FACTOR
            entry["page_type_boosted"] = True
        boosted.append(entry)
    boosted.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    return boosted


def _apply_deprecated_demotion(results: list[dict]) -> list[dict]:
    """Demote deprecated/abandoned pages so current endpoints rank higher."""
    if not results:
        return results
    demoted = []
    for item in results:
        entry = dict(item)
        url = entry.get("canonical_url", "")
        if _DEPRECATED_URL_PATTERNS.search(url):
            rrf = entry.get("rrf_score", 0.0)
            entry["rrf_score"] = rrf * _DEPRECATED_DEMOTION_FACTOR
            entry["deprecated_demoted"] = True
        demoted.append(entry)
    demoted.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    return demoted


def _sections_present(conn, *, exchange_id: str, seed_prefixes: dict[str, str]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for section_id, prefix in seed_prefixes.items():
        row = conn.execute(
            "SELECT 1 FROM pages WHERE canonical_url LIKE ? LIMIT 1;",
            (prefix + "%",),
        ).fetchone()
        if row is not None:
            options.append({"exchange": exchange_id, "section": section_id})
    return options


def _search_top_page(conn, *, query: str, url_prefix: str) -> dict[str, Any] | None:
    # Prefer matches inside the section prefix.
    row = conn.execute(
        """
SELECT
  p.canonical_url, p.crawled_at, p.content_hash, p.path_hash, p.markdown_path
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ? AND p.canonical_url LIKE ?
ORDER BY rank
LIMIT 1;
""",
        (sanitize_fts_query(query), url_prefix + "%"),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _is_nav_region(md: str, pos: int, window: int = 1000) -> bool:
    """Return True if *pos* falls in a navigation / table-of-contents region.

    Heuristic: in a *window*-char neighbourhood, if >55 % of non-empty lines
    are bullet items or link-only lines we treat the area as navigation.
    Large single-page sites (OKX 225 K words, Gate.io 192 K, HTX 130 K) put a
    dense ToC at the top — the first regex match of a query term lands in that
    ToC rather than in the substantive content below it.
    """
    start = max(0, pos - window // 2)
    end = min(len(md), pos + window // 2)
    region = md[start:end]
    lines = [ln for ln in region.split("\n") if ln.strip()]
    if len(lines) < 4:
        return False
    nav = 0
    for ln in lines:
        s = ln.strip()
        # Bullet list items (ToC entries are usually short)
        if (s.startswith("*") or s.startswith("-") or s.startswith("+")) and len(s) < 140:
            nav += 1
        # Link-only lines: [text](url)
        elif s.startswith("[") and s.endswith(")") and "](" in s:
            nav += 1
    return nav / len(lines) > 0.55


def _make_excerpt(md: str, *, needle_re: re.Pattern[str], target_len: int = 400, hard_max: int = 600) -> tuple[str, int, int]:
    # Find all matches and prefer those outside navigation regions.
    best_match = None
    for m in needle_re.finditer(md):
        if not _is_nav_region(md, m.start()):
            best_match = m
            break
        if best_match is None:
            best_match = m  # keep first match as fallback

    if not best_match:
        # Fallback: first N chars, snapped to boundary.
        end = min(len(md), target_len)
        end = _snap_end_forward(md, end)
        excerpt = _clean_excerpt(md[:end])
        return excerpt, 0, end

    idx = best_match.start()
    start = max(0, idx - target_len // 2)
    end = min(len(md), start + target_len)
    if end - start > hard_max:
        end = start + hard_max

    # Snap start backward to nearest newline or whitespace boundary.
    start = _snap_start_backward(md, start)
    # Snap end forward to nearest sentence end or paragraph break.
    end = _snap_end_forward(md, end)
    # Enforce hard max after snapping.
    if end - start > hard_max:
        end = start + hard_max
        end = _snap_end_forward(md, end)

    excerpt = _clean_excerpt(md[start:end])
    return excerpt, start, end


def _snap_start_backward(md: str, pos: int) -> int:
    """Snap start position backward to nearest newline or word boundary."""
    if pos == 0:
        return 0
    # Look for newline within 50 chars backward.
    search_start = max(0, pos - 50)
    nl = md.rfind("\n", search_start, pos)
    if nl != -1:
        return nl + 1
    # Fall back to word boundary.
    sp = md.rfind(" ", search_start, pos)
    if sp != -1:
        return sp + 1
    return pos


def _snap_end_forward(md: str, pos: int) -> int:
    """Snap end position forward to nearest sentence end or paragraph break."""
    if pos >= len(md):
        return len(md)
    # Look for paragraph break (double newline) within 80 chars.
    para = md.find("\n\n", pos, min(len(md), pos + 80))
    if para != -1:
        return para
    # Look for sentence-ending punctuation followed by space or newline.
    for i in range(pos, min(len(md), pos + 80)):
        if md[i] in ".!?" and (i + 1 >= len(md) or md[i + 1] in " \n\t"):
            return i + 1
    # Fall back to newline.
    nl = md.find("\n", pos, min(len(md), pos + 80))
    if nl != -1:
        return nl
    # Fall back to word boundary.
    sp = md.find(" ", pos, min(len(md), pos + 50))
    if sp != -1:
        return sp
    return pos


def _clean_excerpt(text: str) -> str:
    """Strip zero-width characters and broken markdown fragments."""
    # Remove zero-width chars.
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)
    # Strip leading/trailing whitespace.
    return text.strip()


def _claim(claim_id: str, *, text: str, citation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": claim_id,
        "kind": "SOURCE",
        "text": text,
        "citations": [citation],
    }


def _extract_weight_from_excerpt(excerpt: str) -> int | None:
    # Conservative: require an obvious "weight is 10" / "weight: 10" pattern.
    m = re.search(r"\bweight\b\s*(?:is|=|:)?\s*(\d{1,9})\b", excerpt, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _wants_rate_limit(norm: str) -> bool:
    return bool(re.search(r"\brate\s+limit\b|\bweight\b", norm, flags=re.IGNORECASE))


def _wants_permissions(norm: str) -> bool:
    return bool(re.search(r"\bpermissions?\b|\bapi\s+key\b|\bscopes?\b", norm, flags=re.IGNORECASE))


def _looks_like_permissions_requirement(text: str) -> bool:
    # Stay conservative: do not label something "required_permissions" unless the excerpt
    # is clearly about permissions as a requirement (not merely mentioning API keys).
    return bool(
        re.search(
            r"(?im)^\s*#+\s*permissions?\b|"
            r"\brequired\s+permissions?\b|"
            r"\bpermissions?\s*[:\-]\s*\w|"
            r"\bapi\s+key\s+permissions?\b|"
            r"\bpermission\s+required\b|"
            r"\benable\s+reading\b|"
            r"\benable\s+withdrawals?\b",
            text,
        )
    )


def _search_pages(conn, *, query: str, url_prefix: str, limit: int = 5) -> list[dict[str, Any]]:
    # Fetch extra to compensate for testnet filtering.
    fetch_limit = int(limit) * 2 if "testnet" not in query.lower() else int(limit)
    suppress_testnet = "testnet" not in query.lower()

    def _run_fts(fts_q: str) -> list[dict[str, Any]]:
        cur = conn.execute(
            """
SELECT
  p.canonical_url, p.crawled_at, p.content_hash, p.path_hash, p.markdown_path,
  pages_fts.rank AS fts_rank
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ? AND p.canonical_url LIKE ?
ORDER BY rank
LIMIT ?;
""",
            (fts_q, url_prefix + "%", fetch_limit),
        )
        out = []
        for r in cur.fetchall():
            d = dict(r)
            if suppress_testnet and _is_testnet_url(d.get("canonical_url", "")):
                continue
            d["bm25_score"] = normalize_bm25_score(d.pop("fts_rank", 0.0))
            out.append(d)
        return out

    sanitized = sanitize_fts_query(query)
    results = _run_fts(sanitized)

    # OR fallback: if AND query returns nothing and query has AND, try OR.
    if not results and " AND " in sanitized:
        or_query = sanitized.replace(" AND ", " OR ")
        results = _run_fts(or_query)

    return results


def _search_pages_with_semantic(
    conn: sqlite3.Connection,
    *,
    query: str,
    url_prefix: str,
    limit: int = 5,
    docs_dir: str | None = None,
    exchange: str | None = None,
    query_type_hint: str | None = None,
) -> list[dict[str, Any]]:
    """Search pages via FTS5 + semantic vector search, fused with RRF.

    Uses query_type="vector" for LanceDB (not "hybrid") to avoid double-RRF:
    LanceDB hybrid search already applies RRF k=60 internally. Our outer RRF
    fuses SQLite FTS5 BM25 ranks with LanceDB vector-only ranks.

    Strong-signal BM25 shortcut: skips vector search when FTS5 produces a
    clear high-confidence match (only for ``code_snippet`` and ``error_message``
    types — ``question`` and ``request_payload`` benefit from vector search).
    """
    # FTS5 search — fetch extra candidates for RRF.
    fts_results = _search_pages(conn, query=query, url_prefix=url_prefix, limit=limit * 2)

    # Strong-signal shortcut: skip vector search if BM25 is confident enough.
    # Applies to code_snippet and error_message types only.
    # endpoint_path uses direct routing; request_payload and question benefit from vector search.
    if query_type_hint in ("code_snippet", "error_message") and should_skip_vector_search(fts_results):
        return fts_results[:limit]

    # Semantic vector search (if available).
    sem_results_raw: list[dict[str, Any]] = []
    if docs_dir is not None:
        try:
            from .semantic import semantic_search
            sem_hits = semantic_search(
                docs_dir=docs_dir,
                query=query,
                exchange=exchange,
                limit=limit * 2,
                query_type="vector",  # NOT "hybrid" — avoids double-RRF
                rerank="auto",
            )
            suppress_testnet = "testnet" not in query.lower()
            for sr in sem_hits:
                url = sr.get("url", "")
                if url_prefix and not url.startswith(url_prefix):
                    continue
                if suppress_testnet and _is_testnet_url(url):
                    continue
                row = conn.execute(
                    "SELECT canonical_url, crawled_at, content_hash, path_hash, markdown_path FROM pages WHERE canonical_url = ?;",
                    (url,),
                ).fetchone()
                if row:
                    sem_results_raw.append(dict(row))
        except ImportError:
            pass
        except Exception:
            logger.warning("Semantic search failed (non-fatal)", exc_info=True)

    if not sem_results_raw:
        return fts_results[:limit]
    if not fts_results:
        return sem_results_raw[:limit]

    # RRF fusion: merge FTS5 and vector rankings with query-type-dependent weights.
    # [fts_weight, vector_weight] — tuned via golden QA eval.
    _RRF_WEIGHTS: dict[str | None, list[float]] = {
        "question": [0.7, 1.3],          # vector-favoring — validated via weight sweep on 79 queries
        "endpoint_path": [1.5, 0.5],     # favor keyword match
        "error_message": [1.3, 0.7],     # favor keyword with some semantic
        "code_snippet": [0.7, 1.3],      # favor semantic
        "request_payload": [1.3, 0.7],   # keyword-favoring — exact param names match better in FTS5
    }
    rrf_weights = _RRF_WEIGHTS.get(query_type_hint, [1.0, 1.0])
    fused = rrf_fuse(fts_results, sem_results_raw, key="canonical_url", weights=rrf_weights)
    return fused[:limit]


def _search_endpoints_for_answer(
    conn: sqlite3.Connection,
    *,
    query: str,
    exchange: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search endpoint records and return relevant fields for answer composition."""
    terms = extract_search_terms(query, extra_stopwords={exchange.lower()})
    if not terms:
        terms = [t for t in re.findall(r"[A-Za-z0-9_]+", query) if len(t) > 1]
    fts_query = build_fts_query(terms) if terms else sanitize_fts_query(query)
    if not fts_query.strip():
        return []

    where = ["endpoints_fts MATCH ?", "endpoints_fts.exchange = ?"]
    params: list[Any] = [fts_query, exchange, int(limit)]

    sql = f"""
SELECT
  endpoints_fts.endpoint_id,
  endpoints_fts.exchange,
  endpoints_fts.section,
  endpoints_fts.method,
  endpoints_fts.path,
  snippet(endpoints_fts, 5, '[', ']', '...', 12) AS snippet,
  rank
FROM endpoints_fts
WHERE {' AND '.join(where)}
ORDER BY rank
LIMIT ?;
"""
    try:
        cur = conn.execute(sql, tuple(params))
    except sqlite3.OperationalError:
        return []

    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        # Get the full endpoint record.
        full = conn.execute("SELECT json FROM endpoints WHERE endpoint_id = ?;", (r["endpoint_id"],)).fetchone()
        record = json.loads(full["json"]) if full else {}
        out.append({
            "endpoint_id": r["endpoint_id"],
            "exchange": r["exchange"],
            "section": r["section"],
            "method": r["method"],
            "path": r["path"],
            "snippet": r["snippet"],
            "record": record,
        })
    return out


def _detect_exchange(norm: str, reg) -> list:
    """Match exchange names/IDs in the normalized question text using word boundaries."""
    matches = []
    for ex in reg.exchanges:
        ex_id = ex.exchange_id.lower()
        display = ex.display_name.lower()
        if re.search(rf"\b{re.escape(ex_id)}\b", norm) or re.search(rf"\b{re.escape(display)}\b", norm):
            matches.append(ex)
    return matches


def _resolve_endpoint_citation_url(
    conn: sqlite3.Connection, *, ep: dict[str, Any], exchange,
) -> str | None:
    """Resolve the best citation URL for an endpoint (docs page > spec URL).

    Priority: docs_url column → query-time FTS resolution → sources[0].url.
    """
    # Fast path: check pre-resolved docs_url column.
    try:
        row = conn.execute(
            "SELECT docs_url FROM endpoints WHERE endpoint_id = ?;",
            (ep["endpoint_id"],),
        ).fetchone()
        if row and row["docs_url"]:
            return row["docs_url"]
    except sqlite3.OperationalError:
        pass  # Column may not exist yet (pre-migration).

    # Query-time fallback: FTS resolution.
    path = ep.get("path", "")
    if path:
        try:
            from .resolve_docs_urls import resolve_docs_url

            docs_url = resolve_docs_url(
                conn,
                path=path,
                exchange=ep["exchange"],
                allowed_domains=exchange.allowed_domains or [],
            )
            if docs_url:
                return docs_url
        except Exception:
            pass

    # Last resort: spec URL from sources[] (suppress raw spec URLs).
    record = ep.get("record", {})
    sources = record.get("sources") or []
    if sources and isinstance(sources[0], dict):
        url = sources[0].get("url", "")
        if url and not _is_spec_url(url):
            return url

    return None


def _directory_prefix(url: str) -> str:
    """Extract directory prefix from a URL (strip trailing path segment).

    e.g. 'https://example.com/docs/ws/connect' -> 'https://example.com/docs/ws/'
    This ensures searches match sibling pages, not just the exact seed URL.
    """
    # Strip query/fragment.
    clean = url.split("?")[0].split("#")[0]
    if clean.endswith("/"):
        return clean
    # Strip last path segment.
    last_slash = clean.rfind("/")
    if last_slash > 8:  # after https://
        return clean[:last_slash + 1]
    return clean


def _generic_search_answer(
    conn, *, exchange, question: str, norm: str, docs_dir: str | None = None,
    detected_section_override: str | None = None,
    query_type_hint: str | None = None,
) -> dict[str, Any]:
    """Generic cite-only answer for any exchange: FTS search across all sections."""
    # Use directory prefixes (not exact seed URLs) for broader matching.
    seed_prefixes = {}
    for sec in exchange.sections:
        if sec.seed_urls:
            seed_prefixes[sec.section_id] = _directory_prefix(sec.seed_urls[0])
    # Domain-level fallback — always searched regardless of section results.
    domain_prefixes = [f"https://{d}" for d in (exchange.allowed_domains or [])]

    claims: list[dict[str, Any]] = []
    notes: list[str] = []
    c = 1
    max_claims = 10  # Reduced from 20 for precision.

    # Build FTS query from question terms (strip common words).
    terms = extract_search_terms(norm, extra_stopwords={exchange.exchange_id.lower()})
    fts_query = build_fts_query(terms) if terms else sanitize_fts_query(norm)

    # Detect section from keywords for multi-section exchanges.
    # Use Binance-specific detection for Binance, generic for others.
    detected_section = detected_section_override
    if not detected_section:
        if exchange.exchange_id == "binance":
            detected_section = _detect_binance_section(norm)
        else:
            detected_section = _detect_section_keywords(norm, exchange)

    # Search endpoints for relevant results.
    endpoint_results = _search_endpoints_for_answer(conn, query=fts_query, exchange=exchange.exchange_id, limit=3)
    for ep in endpoint_results:
        record = ep.get("record", {})
        ep_desc = record.get("description", ep.get("snippet", ""))
        rate_limit = record.get("rate_limit")
        field_status = record.get("field_status", {})

        # If rate_limit is unknown, try to infer from page markdown.
        rate_limit_note = ""
        if field_status.get("rate_limit") in ("unknown", "undocumented") and rate_limit is None:
            inferred = _infer_rate_limit_from_pages(conn, exchange=exchange, path=ep.get("path", ""), terms=terms, docs_dir=docs_dir)
            if inferred:
                rate_limit_note = f" [inferred rate limit: {inferred['text']}]"

        text = f"[{ep['exchange']}:{ep['section']}] {ep.get('method', '')} {ep.get('path', '')} — {ep_desc}{rate_limit_note}"
        citation_url = _resolve_endpoint_citation_url(conn, ep=ep, exchange=exchange)
        citations = [{"url": citation_url}] if citation_url else []
        claims.append({
            "id": f"c{c}",
            "kind": "ENDPOINT",
            "text": text,
            "citations": citations,
            "endpoint_id": ep["endpoint_id"],
        })
        c += 1

    # Search each section using directory prefix, collect all candidates.
    # Then apply section boost across the unified list before building claims.
    ordered_sections = list(seed_prefixes.items())
    if detected_section and detected_section in seed_prefixes:
        ordered_sections = [(detected_section, seed_prefixes[detected_section])] + [
            (sid, pfx) for sid, pfx in ordered_sections if sid != detected_section
        ]
    all_section_candidates: list[tuple[str, dict[str, Any]]] = []  # (section_id, candidate)
    seen_section_urls: set[str] = set()  # deduplicate across overlapping section prefixes
    for section_id, prefix in ordered_sections:
        section_limit = 5 if (detected_section and section_id == detected_section) else 3
        candidates = _search_pages_with_semantic(conn, query=fts_query, url_prefix=prefix, limit=section_limit, docs_dir=docs_dir, exchange=exchange.exchange_id, query_type_hint=query_type_hint)
        for cand in candidates:
            curl = cand.get("canonical_url", "")
            if curl in seen_section_urls:
                continue
            seen_section_urls.add(curl)
            all_section_candidates.append((section_id, cand))

    # Apply section boost across all section candidates (reorders by rrf_score).
    boost_prefix = seed_prefixes.get(detected_section) if detected_section else None
    all_cands_flat = [cand for _, cand in all_section_candidates]
    boosted_cands = _apply_section_boost(all_cands_flat, section_prefix=boost_prefix)
    # Rebuild (section_id, cand) mapping after boost reordering.
    url_to_section = {cand.get("canonical_url"): sid for sid, cand in all_section_candidates}
    all_section_candidates = [(url_to_section.get(cand.get("canonical_url"), ""), cand) for cand in boosted_cands]

    # Apply page-type boost: promote overview/intro pages for broad questions.
    page_type_boosted = _apply_page_type_boost([cand for _, cand in all_section_candidates], norm=norm)
    all_section_candidates = [(url_to_section.get(cand.get("canonical_url"), ""), cand) for cand in page_type_boosted]

    for section_id, cand in all_section_candidates:
        if c > max_claims:
            break
        md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
        if not md_path or not md_path.exists():
            continue
        md = md_path.read_text(encoding="utf-8")
        needle_re = re.compile("|".join(re.escape(t) for t in terms[:4]) if terms else re.escape(norm[:30]), re.IGNORECASE)
        excerpt, start, end = _make_excerpt(md, needle_re=needle_re)
        citation = {
            "url": cand["canonical_url"],
            "crawled_at": cand["crawled_at"],
            "content_hash": cand["content_hash"],
            "path_hash": cand["path_hash"],
            "excerpt": excerpt,
            "excerpt_start": start,
            "excerpt_end": end,
        }
        claims.append(_claim(f"c{c}", text=f"[{exchange.exchange_id}:{section_id}] {excerpt}", citation=citation))
        c += 1

    # Always search domain-level too (not just as fallback).
    # This catches pages outside section prefixes.
    seen_urls = {cl["citations"][0]["url"] for cl in claims if cl.get("citations")}
    for dp in domain_prefixes:
        if c > max_claims:
            break
        candidates = _search_pages_with_semantic(conn, query=fts_query, url_prefix=dp, limit=5, docs_dir=docs_dir, exchange=exchange.exchange_id, query_type_hint=query_type_hint)
        # Apply section boost and page-type boost for domain-level results.
        candidates = _apply_section_boost(candidates, section_prefix=boost_prefix)
        candidates = _apply_page_type_boost(candidates, norm=norm)
        for cand in candidates:
            if cand["canonical_url"] in seen_urls:
                continue
            md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
            if not md_path or not md_path.exists():
                continue
            md = md_path.read_text(encoding="utf-8")
            needle_re = re.compile("|".join(re.escape(t) for t in terms[:4]) if terms else re.escape(norm[:30]), re.IGNORECASE)
            excerpt, start, end = _make_excerpt(md, needle_re=needle_re)
            citation = {
                "url": cand["canonical_url"],
                "crawled_at": cand["crawled_at"],
                "content_hash": cand["content_hash"],
                "path_hash": cand["path_hash"],
                "excerpt": excerpt,
                "excerpt_start": start,
                "excerpt_end": end,
            }
            claims.append(_claim(f"c{c}", text=f"[{exchange.exchange_id}] {excerpt}", citation=citation))
            seen_urls.add(cand["canonical_url"])
            c += 1
            if c > max_claims:
                break

    if not claims:
        notes.append(f"No crawled pages found for {exchange.exchange_id} matching the question. Run `cex-api-docs sync --exchange {exchange.exchange_id}` first.")

    return {
        "ok": True,
        "schema_version": "v1",
        "status": "ok" if claims else "unknown",
        "question": question,
        "normalized_question": norm,
        "clarification": None,
        "claims": claims,
        "notes": notes,
    }


def _infer_rate_limit_from_pages(
    conn: sqlite3.Connection,
    *,
    exchange,
    path: str,
    terms: list[str],
    docs_dir: str | None = None,
) -> dict[str, str] | None:
    """Try to infer rate limit from page markdown near the endpoint path."""
    if not path:
        return None
    seed_prefixes = {sec.section_id: _directory_prefix(sec.seed_urls[0]) for sec in exchange.sections if sec.seed_urls}
    path_tail = path.rstrip("/").rsplit("/", 1)[-1] if "/" in path else path

    for _section_id, prefix in seed_prefixes.items():
        candidates = _search_pages_with_semantic(conn, query=f"rate limit {path_tail}", url_prefix=prefix, limit=3, docs_dir=docs_dir, exchange=exchange.exchange_id if hasattr(exchange, 'exchange_id') else None)
        for cand in candidates:
            md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
            if not md_path or not md_path.exists():
                continue
            md = md_path.read_text(encoding="utf-8")
            # Find the endpoint path in the markdown, then look for weight/limit nearby.
            idx = md.lower().find(path_tail.lower())
            if idx == -1:
                continue
            window = md[max(0, idx - 200):min(len(md), idx + 500)]
            weight = _extract_weight_from_excerpt(window)
            if weight is not None:
                return {"text": f"weight {weight} (inferred)", "source_url": cand["canonical_url"]}
    return None


def _binance_answer(
    conn, *, reg, question: str, norm: str, clarification: str | None, docs_dir: str | None = None,
) -> dict[str, Any]:
    """Binance-specific answer logic with rate-limit comparison and permissions heuristics."""
    binance = reg.get_exchange("binance")
    seed_prefixes = {sec.section_id: _directory_prefix(sec.seed_urls[0]) for sec in binance.sections if sec.seed_urls}

    # Detect section from keywords to prioritize relevant results.
    detected_section = _detect_binance_section(norm)

    # Clarification: "unified trading" is ambiguous.
    if "unified trading" in norm and not clarification:
        present = _sections_present(conn, exchange_id="binance", seed_prefixes=seed_prefixes)
        options = [
            {
                "id": f"{o['exchange']}:{o['section']}",
                "label": f"{o['exchange']}:{o['section']}",
                "exchange": o["exchange"],
                "section": o["section"],
            }
            for o in present
        ]
        return {
            "ok": True,
            "schema_version": "v1",
            "status": "needs_clarification",
            "question": question,
            "normalized_question": norm,
            "clarification": {
                "prompt": "What does 'unified trading' refer to in Binance docs for this question?",
                "options": options,
            },
            "claims": [],
            "notes": ["Re-run with `--clarification <id>` (example: binance:portfolio_margin)."],
        }

    unified_section = None
    if clarification:
        # Expect "<exchange_id>:<section_id>".
        parts = clarification.split(":", 1)
        if len(parts) == 2 and parts[0] == "binance":
            unified_section = parts[1]
    if "unified trading" in norm and not unified_section:
        return {
            "ok": True,
            "schema_version": "v1",
            "status": "unknown",
            "question": question,
            "normalized_question": norm,
            "clarification": None,
            "claims": [],
            "notes": ["Missing/invalid clarification for 'unified trading'. Use `--clarification binance:<section_id>`."],
        }

    claims: list[dict[str, Any]] = []
    notes: list[str] = []
    missing: list[str] = []
    c = 1

    wants_rate = _wants_rate_limit(norm)
    wants_perm = _wants_permissions(norm)

    # Part 1: rate-limit comparison between unified section and spot.
    rate_limit_claims: list[tuple[str, str]] = []  # (claim_id, excerpt_text)
    if wants_rate and unified_section:
        for section_id, query in ((unified_section, "rate limit OR weight"), ("spot", "rate limit OR weight")):
            prefix = seed_prefixes.get(section_id)
            if not prefix:
                notes.append(f"No registry seed URL for binance section '{section_id}'.")
                continue
            candidates = _search_pages_with_semantic(conn, query=query, url_prefix=prefix, limit=5, docs_dir=docs_dir, exchange="binance", query_type_hint="question")
            if not candidates:
                notes.append(f"No crawled pages found for query '{query}' under {prefix}.")
                continue
            picked: dict[str, Any] | None = None
            picked_excerpt: tuple[str, int, int] | None = None
            for cand in candidates:
                md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
                if not md_path or not md_path.exists():
                    continue
                md = md_path.read_text(encoding="utf-8")
                if not re.search(r"rate\s+limit|\bweight\b", md, flags=re.IGNORECASE):
                    continue
                picked = cand
                picked_excerpt = _make_excerpt(md, needle_re=re.compile(r"rate\s+limit|\bweight\b", re.IGNORECASE))
                break
            if not picked or not picked_excerpt:
                notes.append(f"No stored markdown under {prefix} contained obvious rate-limit text.")
                continue

            excerpt, start, end = picked_excerpt
            citation = {
                "url": picked["canonical_url"],
                "crawled_at": picked["crawled_at"],
                "content_hash": picked["content_hash"],
                "path_hash": picked["path_hash"],
                "excerpt": excerpt,
                "excerpt_start": start,
                "excerpt_end": end,
                "field_name": "rate_limit",
            }
            claims.append(_claim(f"c{c}", text=f"[{section_id}] {excerpt}", citation=citation))
            rate_limit_claims.append((f"c{c}", excerpt))
            c += 1

        if len(rate_limit_claims) != 2:
            missing.append("rate_limit_comparison")
        else:
            # Derived diff when both excerpts contain an explicit numeric weight.
            w1 = _extract_weight_from_excerpt(rate_limit_claims[0][1])
            w2 = _extract_weight_from_excerpt(rate_limit_claims[1][1])
            if w1 is not None and w2 is not None:
                claims.append(
                    {
                        "id": f"c{c}",
                        "kind": "DERIVED",
                        "text": f"[DERIVED] rate_limit.weight diff (first - second): {w1} - {w2} = {w1 - w2}",
                        "citations": [],
                        "derived": {"op": "diff", "inputs": [{"claim_id": rate_limit_claims[0][0]}, {"claim_id": rate_limit_claims[1][0]}]},
                    }
                )
                c += 1

    # Part 2: API key permissions (only if the question asks).
    if wants_perm:
        pm_prefix = seed_prefixes.get("portfolio_margin")
        prefixes: list[str] = []
        if pm_prefix:
            prefixes.append(pm_prefix)
        # Portfolio margin key permissions are often described in general derivatives onboarding docs.
        prefixes.append("https://developers.binance.com/docs/derivatives/")
        spot_prefix = seed_prefixes.get("spot")
        if spot_prefix:
            prefixes.append(spot_prefix)

        # De-dupe while preserving order.
        seen_p: set[str] = set()
        prefixes = [p for p in prefixes if p and not (p in seen_p or seen_p.add(p))]

        picked: dict[str, Any] | None = None
        picked_excerpt: tuple[str, int, int] | None = None
        picked_prefix: str | None = None

        for prefix in prefixes:
            candidates = _search_pages_with_semantic(
                conn,
                query="permissions OR permission OR \"api key permissions\" OR \"required permissions\" OR \"enable reading\" OR \"enable withdrawals\"",
                url_prefix=prefix,
                limit=10,
                docs_dir=docs_dir,
                exchange="binance",
                query_type_hint="question",
            )
            for cand in candidates:
                md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
                if not md_path or not md_path.exists():
                    continue
                md = md_path.read_text(encoding="utf-8")
                if not _looks_like_permissions_requirement(md):
                    continue
                excerpt, start, end = _make_excerpt(
                    md,
                    needle_re=re.compile(r"permissions?|api\s+key\s+permissions?|required\s+permissions?|enable\s+reading|enable\s+withdrawals?", re.IGNORECASE),
                )
                if not _looks_like_permissions_requirement(excerpt):
                    continue
                picked = cand
                picked_excerpt = (excerpt, start, end)
                picked_prefix = prefix
                break
            if picked and picked_excerpt:
                break

        if not picked or not picked_excerpt:
            notes.append("No crawled Binance docs page contained an explicit API key permissions requirement in local store.")
            missing.append("required_permissions")
        else:
            excerpt, start, end = picked_excerpt
            citation = {
                "url": picked["canonical_url"],
                "crawled_at": picked["crawled_at"],
                "content_hash": picked["content_hash"],
                "path_hash": picked["path_hash"],
                "excerpt": excerpt,
                "excerpt_start": start,
                "excerpt_end": end,
                "field_name": "required_permissions",
            }
            label = "portfolio_margin" if (picked_prefix == pm_prefix) else "binance_docs"
            claims.append(_claim(f"c{c}", text=f"[{label}] {excerpt}", citation=citation))
            c += 1

    # If no specialized logic triggered, fall through to generic search.
    if not claims and not unified_section:
        return _generic_search_answer(conn, exchange=binance, question=question, norm=norm, docs_dir=docs_dir, detected_section_override=detected_section)

    # Status policy: only "ok" when every requested part is cite-backed.
    if wants_rate and unified_section and "rate_limit_comparison" in missing:
        status = "unknown"
    elif wants_perm and "required_permissions" in missing:
        status = "unknown"
    else:
        status = "ok" if claims else "unknown"

    return {
        "ok": True,
        "schema_version": "v1",
        "status": status,
        "question": question,
        "normalized_question": norm,
        "clarification": None,
        "claims": claims,
        "notes": notes,
        "missing": missing,
    }


def _direct_route(
    conn: sqlite3.Connection,
    *,
    classification,
    exchange,
    docs_dir: str,
    question: str,
    norm: str,
) -> dict[str, Any] | None:
    """Direct routing for high-confidence typed queries.

    For endpoint_path and error_message with confidence >= 0.7, skip the
    expensive FTS+vector search and go straight to the targeted lookup.
    Returns None if the direct route produces no results (falls through
    to generic search).
    """
    claims: list[dict[str, Any]] = []
    notes: list[str] = []
    c = 1

    if classification.input_type == "endpoint_path":
        path = classification.signals.get("path", "")
        method = classification.signals.get("method")
        if path:
            try:
                from .lookup import lookup_endpoint_by_path
                path_results = lookup_endpoint_by_path(
                    docs_dir=docs_dir,
                    path=path,
                    method=method,
                    exchange=exchange.exchange_id,
                )
                for record in path_results[:5]:
                    http = record.get("http", {})
                    docs_url = record.get("docs_url", "")
                    # Suppress spec and changelog URLs.
                    if docs_url and _is_spec_url(docs_url):
                        docs_url = ""
                    if docs_url:
                        url_lower = docs_url.lower()
                        if any(ind in url_lower for ind in ("change-log", "changelog", "release-note")):
                            docs_url = ""
                    # Fallback: resolve docs_url at query time if missing.
                    if not docs_url:
                        ep_data = {
                            "endpoint_id": record.get("endpoint_id", ""),
                            "exchange": exchange.exchange_id,
                            "path": http.get("path", ""),
                            "record": record,
                        }
                        resolved = _resolve_endpoint_citation_url(conn, ep=ep_data, exchange=exchange)
                        if resolved:
                            docs_url = resolved
                    claims.append({
                        "id": f"c{c}",
                        "kind": "ENDPOINT",
                        "text": f"[{exchange.exchange_id}:{record.get('section', '')}] {http.get('method', '')} {http.get('path', '')} — {record.get('description', '')}",
                        "citations": [{"url": docs_url}] if docs_url else [],
                        "endpoint_id": record.get("endpoint_id", ""),
                    })
                    c += 1
            except Exception:
                logger.debug("Direct endpoint_path route failed for %s", path, exc_info=True)

    elif classification.input_type == "error_message":
        error_codes = classification.signals.get("error_codes", [])
        for ec_info in error_codes[:3]:
            code = ec_info.get("code", "")
            if not code:
                continue
            try:
                from .lookup import search_error_code
                error_results = search_error_code(
                    docs_dir=docs_dir,
                    error_code=code,
                    exchange=exchange.exchange_id,
                    limit=5,
                )
                # Verify results actually contain the error code in their text.
                # This prevents false positives for nonexistent error codes.
                code_str = code.lstrip("-")  # Strip minus for matching
                for er in error_results:
                    snippet = er.get("snippet", "")
                    # Check if the error code appears in the snippet text.
                    if code_str not in snippet and code not in snippet:
                        continue  # Skip results that don't actually mention this error code.
                    if er.get("source_type") == "page":
                        url = er.get("canonical_url", "")
                        claims.append({
                            "id": f"c{c}",
                            "kind": "SOURCE",
                            "text": f"[{exchange.exchange_id}:error] {snippet}",
                            "citations": [{"url": url}] if url else [],
                        })
                        c += 1
                    elif er.get("source_type") == "endpoint":
                        claims.append({
                            "id": f"c{c}",
                            "kind": "ENDPOINT",
                            "text": f"[{exchange.exchange_id}:{er.get('section', '')}] {er.get('method', '')} {er.get('path', '')} — {snippet}",
                            "citations": [],
                            "endpoint_id": er.get("endpoint_id", ""),
                        })
                        c += 1
            except Exception:
                logger.debug("Direct error_message route failed for %s", code, exc_info=True)

    if not claims:
        return None  # Fall through to generic search.

    return {
        "ok": True,
        "schema_version": "v1",
        "status": "ok",
        "question": question,
        "normalized_question": norm,
        "clarification": None,
        "claims": claims,
        "notes": notes,
        "routing": "direct",
    }


def _augment_with_classification(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    *,
    classification,
    exchange,
    docs_dir: str,
) -> dict[str, Any]:
    """Augment answer with classification-specific search results.

    Classification is used as AUGMENTATION: if error_message, prepend error
    search results; if endpoint_path, prepend path lookup. The generic search
    results are always preserved (F4: augment, not replace).
    """
    if classification.confidence < 0.5:
        return result

    existing_ids = {cl.get("endpoint_id") for cl in result.get("claims", []) if cl.get("endpoint_id")}
    existing_urls = set()
    for cl in result.get("claims", []):
        for cit in cl.get("citations", []):
            if cit.get("url"):
                existing_urls.add(cit["url"])

    augmented_claims: list[dict[str, Any]] = []
    c_start = len(result.get("claims", [])) + 1

    if classification.input_type == "error_message":
        # Prepend error code search results.
        error_codes = classification.signals.get("error_codes", [])
        for ec_info in error_codes[:2]:  # Max 2 error codes.
            code = ec_info.get("code", "")
            if not code:
                continue
            try:
                from .lookup import search_error_code
                error_results = search_error_code(
                    docs_dir=docs_dir,
                    error_code=code,
                    exchange=exchange.exchange_id,
                    limit=3,
                )
                for er in error_results:
                    if er.get("source_type") == "page":
                        url = er.get("canonical_url", "")
                        if url in existing_urls:
                            continue
                        existing_urls.add(url)
                        augmented_claims.append({
                            "id": f"c{c_start}",
                            "kind": "SOURCE",
                            "text": f"[{exchange.exchange_id}:error] {er.get('snippet', '')}",
                            "citations": [{"url": url}],
                        })
                        c_start += 1
                    elif er.get("source_type") == "endpoint":
                        ep_id = er.get("endpoint_id", "")
                        if ep_id in existing_ids:
                            continue
                        existing_ids.add(ep_id)
                        augmented_claims.append({
                            "id": f"c{c_start}",
                            "kind": "ENDPOINT",
                            "text": f"[{exchange.exchange_id}:{er.get('section', '')}] {er.get('method', '')} {er.get('path', '')} — {er.get('snippet', '')}",
                            "citations": [],
                            "endpoint_id": ep_id,
                        })
                        c_start += 1
            except Exception:
                logger.debug("Error code augmentation failed for %s", code, exc_info=True)

    elif classification.input_type == "request_payload":
        # Search for endpoints matching payload parameter names.
        payload_keys = classification.signals.get("payload_keys", [])
        if payload_keys:
            # Build search terms from significant parameter names (skip common ones).
            _skip_keys = {"timestamp", "recvWindow", "signature", "apiKey"}
            search_keys = [k for k in payload_keys if k not in _skip_keys][:5]
            if search_keys:
                try:
                    # Search endpoints by parameter names.
                    from .endpoints import search_endpoints
                    search_term = " ".join(search_keys[:3])
                    ep_results = search_endpoints(
                        docs_dir=docs_dir,
                        query=search_term,
                        exchange=exchange.exchange_id,
                        limit=5,
                    )
                    for record in ep_results:
                        ep_id = record.get("endpoint_id", "")
                        if ep_id in existing_ids:
                            continue
                        existing_ids.add(ep_id)
                        http = record.get("http", {})
                        docs_url = record.get("docs_url", "")
                        if docs_url and _is_spec_url(docs_url):
                            docs_url = ""
                        augmented_claims.append({
                            "id": f"c{c_start}",
                            "kind": "ENDPOINT",
                            "text": f"[{exchange.exchange_id}:{record.get('section', '')}] {http.get('method', '')} {http.get('path', '')} — {record.get('description', '')}",
                            "citations": [{"url": docs_url}] if docs_url else [],
                            "endpoint_id": ep_id,
                        })
                        c_start += 1
                except Exception:
                    logger.debug("Payload augmentation failed for keys %s", search_keys, exc_info=True)

                # Also search pages for trading/order documentation.
                try:
                    trading_terms = search_term + " order"
                    _url_prefix = f"https://{exchange.allowed_domains[0]}" if exchange.allowed_domains else ""
                    page_results = _search_pages(
                        conn,
                        query=trading_terms,
                        url_prefix=_url_prefix,
                        limit=3,
                    )
                    for pr in page_results:
                        url = pr.get("canonical_url", "")
                        if url in existing_urls or _is_spec_url(url):
                            continue
                        existing_urls.add(url)
                        augmented_claims.append({
                            "id": f"c{c_start}",
                            "kind": "SOURCE",
                            "text": f"[{exchange.exchange_id}:payload] {pr.get('snippet', '')[:200]}",
                            "citations": [{"url": url}],
                        })
                        c_start += 1
                except Exception:
                    logger.debug("Payload page search failed", exc_info=True)

    elif classification.input_type == "code_snippet":
        # Search based on extracted method topics and exchange.
        code_methods = classification.signals.get("code_methods", [])
        if code_methods:
            topics = [m["topic"] for m in code_methods[:2]]
            search_term = " ".join(topics)
            try:
                _url_prefix = f"https://{exchange.allowed_domains[0]}" if exchange.allowed_domains else ""
                page_results = _search_pages(
                    conn,
                    query=search_term,
                    url_prefix=_url_prefix,
                    limit=5,
                )
                for pr in page_results:
                    url = pr.get("canonical_url", "")
                    if url in existing_urls or _is_spec_url(url):
                        continue
                    existing_urls.add(url)
                    augmented_claims.append({
                        "id": f"c{c_start}",
                        "kind": "SOURCE",
                        "text": f"[{exchange.exchange_id}:code] {pr.get('snippet', '')[:200]}",
                        "citations": [{"url": url}],
                    })
                    c_start += 1
            except Exception:
                logger.debug("Code snippet augmentation failed", exc_info=True)

            # Also try endpoint search for specific methods.
            try:
                from .endpoints import search_endpoints
                ep_results = search_endpoints(
                    docs_dir=docs_dir,
                    query=search_term,
                    exchange=exchange.exchange_id,
                    limit=3,
                )
                for record in ep_results:
                    ep_id = record.get("endpoint_id", "")
                    if ep_id in existing_ids:
                        continue
                    existing_ids.add(ep_id)
                    http = record.get("http", {})
                    docs_url = record.get("docs_url", "")
                    if docs_url and _is_spec_url(docs_url):
                        docs_url = ""
                    augmented_claims.append({
                        "id": f"c{c_start}",
                        "kind": "ENDPOINT",
                        "text": f"[{exchange.exchange_id}:{record.get('section', '')}] {http.get('method', '')} {http.get('path', '')} — {record.get('description', '')}",
                        "citations": [{"url": docs_url}] if docs_url else [],
                        "endpoint_id": ep_id,
                    })
                    c_start += 1
            except Exception:
                logger.debug("Code snippet endpoint search failed", exc_info=True)

    elif classification.input_type == "endpoint_path":
        # Prepend endpoint path lookup results.
        path = classification.signals.get("path", "")
        method = classification.signals.get("method")
        if path:
            try:
                from .lookup import lookup_endpoint_by_path
                path_results = lookup_endpoint_by_path(
                    docs_dir=docs_dir,
                    path=path,
                    method=method,
                    exchange=exchange.exchange_id,
                )
                for record in path_results[:3]:
                    ep_id = record.get("endpoint_id", "")
                    if ep_id in existing_ids:
                        continue
                    existing_ids.add(ep_id)
                    http = record.get("http", {})
                    docs_url = record.get("docs_url", "")
                    if docs_url and _is_spec_url(docs_url):
                        docs_url = ""
                    augmented_claims.append({
                        "id": f"c{c_start}",
                        "kind": "ENDPOINT",
                        "text": f"[{exchange.exchange_id}:{record.get('section', '')}] {http.get('method', '')} {http.get('path', '')} — {record.get('description', '')}",
                        "citations": [{"url": docs_url}] if docs_url else [],
                        "endpoint_id": ep_id,
                    })
                    c_start += 1
            except Exception:
                logger.debug("Endpoint path augmentation failed for %s", path, exc_info=True)

    if augmented_claims:
        # Prepend augmented claims (they're more specific) and re-number.
        all_claims = augmented_claims + result.get("claims", [])
        for i, cl in enumerate(all_claims, 1):
            cl["id"] = f"c{i}"
        result["claims"] = all_claims
        if result.get("status") == "unknown" and augmented_claims:
            result["status"] = "ok"

    return result


def answer_question(
    *,
    docs_dir: str,
    question: str,
    clarification: str | None = None,
) -> dict[str, Any]:
    db_path = Path(docs_dir) / "db" / "docs.db"
    if not db_path.exists():
        return {
            "ok": True,
            "schema_version": "v1",
            "status": "unknown",
            "question": question,
            "normalized_question": _normalize_question(question),
            "clarification": None,
            "claims": [],
            "notes": ["Store not initialized. Run `cex-api-docs init` and `cex-api-docs sync` first."],
        }

    norm = _normalize_question(question)
    repo_root = Path(__file__).resolve().parents[2]
    reg = load_registry(repo_root / "data" / "exchanges.yaml")

    # Detect which exchange(s) the question is about.
    matched = _detect_exchange(norm, reg)

    # Fallback: use classification exchange_hint for payloads/code snippets
    # that don't contain exchange names in plain text.
    if not matched:
        classification = classify_input(question)
        hint = classification.signals.get("exchange_hint")
        if hint:
            matched = [ex for ex in reg.exchanges if ex.exchange_id == hint]

    if not matched:
        available = sorted(ex.exchange_id for ex in reg.exchanges)
        return {
            "ok": True,
            "schema_version": "v1",
            "status": "unknown",
            "question": question,
            "normalized_question": norm,
            "clarification": None,
            "claims": [],
            "notes": [
                "Could not determine exchange from question. "
                f"Available exchanges: {', '.join(available)}. "
                "Include the exchange name in your question."
            ],
        }

    if len(matched) > 1:
        # Multiple exchanges mentioned — try classification hint to disambiguate.
        classification = classify_input(question)
        hint = classification.signals.get("exchange_hint")
        if hint and hint != "ccxt":
            hint_matched = [ex for ex in matched if ex.exchange_id == hint]
            if hint_matched:
                matched = hint_matched
        # If still ambiguous, try dropping "ccxt" (reference exchange, not a real exchange).
        if len(matched) > 1:
            non_ccxt = [ex for ex in matched if ex.exchange_id != "ccxt"]
            if len(non_ccxt) == 1:
                matched = non_ccxt

    if len(matched) > 1:
        if clarification:
            parts = clarification.split(":", 1)
            target_ex_id = parts[0]
            matched = [ex for ex in matched if ex.exchange_id == target_ex_id]
            if not matched:
                return {
                    "ok": True,
                    "schema_version": "v1",
                    "status": "unknown",
                    "question": question,
                    "normalized_question": norm,
                    "clarification": None,
                    "claims": [],
                    "notes": [f"Clarification exchange '{target_ex_id}' not found among matched exchanges."],
                }
        else:
            options = [
                {
                    "id": ex.exchange_id,
                    "label": ex.display_name,
                    "exchange": ex.exchange_id,
                }
                for ex in matched
            ]
            return {
                "ok": True,
                "schema_version": "v1",
                "status": "needs_clarification",
                "question": question,
                "normalized_question": norm,
                "clarification": {
                    "prompt": "Multiple exchanges detected. Which exchange is this question about?",
                    "options": options,
                },
                "claims": [],
                "notes": ["Re-run with `--clarification <exchange_id>` or `--clarification <exchange_id>:<section_id>`."],
            }

    exchange = matched[0]

    conn = open_db(db_path)
    try:
        # Classify input to augment search (F4: augment, don't replace).
        classification = classify_input(question)

        # Direct routing: high-confidence endpoint_path or error_message
        # skips the expensive FTS+vector search entirely.
        if classification.confidence >= 0.7 and classification.input_type in ("endpoint_path", "error_message"):
            direct = _direct_route(conn, classification=classification, exchange=exchange, docs_dir=docs_dir, question=question, norm=norm)
            if direct is not None:
                return direct
            # High confidence but no direct match → check if the path/error
            # genuinely doesn't exist before falling through to generic search.
            if classification.confidence >= 0.7:
                should_gate = False
                if classification.input_type == "endpoint_path":
                    # Check if ANY endpoint with a similar path exists in the exchange.
                    # Only gate if the exchange has indexed endpoints (otherwise pages may help).
                    path = classification.signals.get("path", "")
                    if path:
                        ep_count = conn.execute(
                            "SELECT COUNT(*) FROM endpoints WHERE exchange = ?;",
                            (exchange.exchange_id,),
                        ).fetchone()[0]
                        if ep_count > 0:
                            clean_path = re.sub(r"^\{\{\w+\}\}", "", path).split("?", 1)[0]
                            # Use last 2 meaningful path segments for matching.
                            # Gate only when ALL segments are missing from the endpoint DB
                            # (i.e., completely nonexistent path, not just a version mismatch).
                            skip = {"api", "v1", "v2", "v3", "v4", "v5", "rest", "ws"}
                            segments = [s for s in clean_path.split("/") if s and s.lower() not in skip and len(s) > 1]
                            search_segments = segments[-2:] if len(segments) >= 2 else segments
                            if search_segments:
                                all_missing = True
                                for seg in search_segments:
                                    row = conn.execute(
                                        "SELECT 1 FROM endpoints WHERE exchange = ? AND path LIKE ? LIMIT 1;",
                                        (exchange.exchange_id, f"%{seg}%"),
                                    ).fetchone()
                                    if row is not None:
                                        all_missing = False
                                        break
                                if all_missing:
                                    should_gate = True
                elif classification.input_type == "error_message":
                    # Check if any error code from the signals actually exists in pages/endpoints.
                    codes = [ec.get("code", "") for ec in classification.signals.get("error_codes", []) if ec.get("code")]
                    if codes:
                        found_any = False
                        for code in codes:
                            row = conn.execute(
                                "SELECT 1 FROM pages_fts WHERE pages_fts MATCH ? LIMIT 1;",
                                (sanitize_fts_query(code),),
                            ).fetchone()
                            if row:
                                found_any = True
                                break
                        if not found_any:
                            should_gate = True

                if should_gate:
                    path_or_code = (
                        classification.signals.get("path", "")
                        or ", ".join(ec.get("code", "") for ec in classification.signals.get("error_codes", []))
                    )
                    return {
                        "ok": True,
                        "schema_version": "v1",
                        "status": "undocumented",
                        "question": question,
                        "normalized_question": norm,
                        "clarification": None,
                        "claims": [],
                        "notes": [
                            f"No {classification.input_type} match found for '{path_or_code}' "
                            f"in {exchange.exchange_id} docs. The endpoint or error code may "
                            f"not exist, or its documentation has not been indexed."
                        ],
                    }

        # Binance: use richer Binance-specific logic.
        if exchange.exchange_id == "binance":
            result = _binance_answer(conn, reg=reg, question=question, norm=norm, clarification=clarification, docs_dir=docs_dir)
        else:
            # All other exchanges: generic cite-only search.
            result = _generic_search_answer(conn, exchange=exchange, question=question, norm=norm, docs_dir=docs_dir, query_type_hint=classification.input_type)

        # Augment with classification-specific results.
        result = _augment_with_classification(
            conn, result,
            classification=classification,
            exchange=exchange,
            docs_dir=docs_dir,
        )
        return result
    finally:
        conn.close()
