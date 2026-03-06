"""Resolve official docs page URLs for endpoints imported from specs.

Links endpoints (imported from OpenAPI/Postman specs) to the official docs
pages that describe them, so citations point to human-readable URLs instead
of raw YAML/JSON spec blobs.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Substrings that indicate a URL is a raw spec, not an official docs page.
_SPEC_INDICATORS = (
    "raw.githubusercontent.com",
    "swagger",
    "openapi",
    "postman",
)

_SPEC_EXTENSIONS = (".yaml", ".yml")


def _is_spec_url(url: str) -> bool:
    """Return True if *url* looks like a raw spec rather than an official docs page."""
    lower = url.lower()
    for ind in _SPEC_INDICATORS:
        if ind in lower:
            return True
    # Only treat .yaml/.yml as spec if they're at the end of the path (before query/fragment).
    path_part = lower.split("?", 1)[0].split("#", 1)[0]
    for ext in _SPEC_EXTENSIONS:
        if path_part.endswith(ext):
            return True
    return False


def _path_segments(path: str) -> list[str]:
    """Extract meaningful path segments for FTS search, skipping version prefixes."""
    skip = {"v1", "v2", "v3", "v4", "v5", "api", "rest", "ws", "wss"}
    parts = [p for p in path.split("/") if p and p.lower() not in skip and len(p) > 1]
    return parts


def resolve_docs_url(
    conn: sqlite3.Connection,
    *,
    path: str,
    exchange: str,
    allowed_domains: list[str],
) -> str | None:
    """Find the official docs page URL that describes an endpoint path.

    Strategy:
      1. Build FTS query from last 2 meaningful path segments.
      2. Search ``pages_fts`` for matches within the exchange's allowed domains.
      3. Verify the full endpoint path appears literally in the page markdown.
      4. Return the first verified match (best FTS rank), or ``None``.
    """
    if not path:
        return None

    # Strip Postman {{url}} prefix.
    clean = re.sub(r"^\{\{url\}\}", "", path)

    segments = _path_segments(clean)
    if not segments:
        return None

    # Use last 2 segments for FTS query (most distinctive).
    query_parts = segments[-2:] if len(segments) >= 2 else segments
    fts_query = " ".join(query_parts)
    if not fts_query.strip():
        return None

    # Build domain filter.
    domains = [d for d in allowed_domains if d]
    if not domains:
        return None

    for domain in domains:
        domain_like = f"%{domain}%"
        try:
            rows = conn.execute(
                """
                SELECT p.canonical_url, p.markdown_path
                FROM pages_fts
                JOIN pages p ON pages_fts.rowid = p.id
                WHERE pages_fts MATCH ?
                  AND p.canonical_url LIKE ?
                ORDER BY rank
                LIMIT 10;
                """,
                (fts_query, domain_like),
            ).fetchall()
        except sqlite3.OperationalError:
            continue

        for row in rows:
            url = row["canonical_url"]
            if _is_spec_url(url):
                continue
            md_path = Path(row["markdown_path"]) if row["markdown_path"] else None
            if not md_path or not md_path.exists():
                continue
            try:
                md = md_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if clean in md:
                return url

    return None


def link_endpoints_bulk(
    conn: sqlite3.Connection,
    *,
    exchange: str,
    section: str | None = None,
    allowed_domains: list[str],
    limit: int = 0,
) -> dict[str, Any]:
    """Resolve ``docs_url`` for all endpoints missing it in an exchange/section.

    Returns ``{"resolved": N, "skipped": N, "total": N}``.
    """
    where = ["docs_url IS NULL", "exchange = ?"]
    params: list[Any] = [exchange]
    if section:
        where.append("section = ?")
        params.append(section)

    sql = f"SELECT endpoint_id, exchange, section, method, path FROM endpoints WHERE {' AND '.join(where)}"
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    sql += ";"

    rows = conn.execute(sql, tuple(params)).fetchall()

    resolved = 0
    skipped = 0
    for row in rows:
        ep_path = row["path"]
        if not ep_path:
            skipped += 1
            continue

        docs_url = resolve_docs_url(
            conn,
            path=ep_path,
            exchange=row["exchange"],
            allowed_domains=allowed_domains,
        )
        if docs_url:
            conn.execute(
                "UPDATE endpoints SET docs_url = ? WHERE endpoint_id = ?;",
                (docs_url, row["endpoint_id"]),
            )
            resolved += 1
        else:
            skipped += 1

    conn.commit()
    logger.info(
        "link-endpoints %s: resolved=%d skipped=%d total=%d",
        exchange, resolved, skipped, len(rows),
    )
    return {"resolved": resolved, "skipped": skipped, "total": len(rows)}
