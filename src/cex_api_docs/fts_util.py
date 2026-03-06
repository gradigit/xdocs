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
