from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .db import open_db
from .errors import CexApiDocsError
from .store import require_store_db


def lookup_endpoint_by_path(
    *,
    docs_dir: str,
    path: str,
    method: str | None = None,
    exchange: str | None = None,
    section: str | None = None,
) -> list[dict[str, Any]]:
    """Look up endpoints by HTTP path using SQL LIKE (not FTS5 — paths tokenize badly)."""
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        # Normalize: strip Postman {{url}} prefix from the search path.
        clean_path = re.sub(r"^\{\{url\}\}", "", path)

        where = ["(e.path LIKE ? OR e.path LIKE ?)"]
        params: list[Any] = [clean_path, "%{{url}}" + clean_path]

        if method:
            where.append("UPPER(e.method) = UPPER(?)")
            params.append(method)
        if exchange:
            where.append("e.exchange = ?")
            params.append(exchange)
        if section:
            where.append("e.section = ?")
            params.append(section)

        sql = f"""
SELECT e.endpoint_id, e.exchange, e.section, e.protocol,
       e.method, e.path, e.base_url, e.api_version,
       e.description, e.json, e.updated_at
FROM endpoints e
WHERE {' AND '.join(where)}
ORDER BY e.exchange, e.section, e.method;
"""
        cur = conn.execute(sql, tuple(params))
        out: list[dict[str, Any]] = []
        for r in cur.fetchall():
            record = json.loads(r["json"])
            out.append(record)
        return out
    finally:
        conn.close()


def search_error_code(
    *,
    docs_dir: str,
    error_code: str,
    exchange: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search for an error code across endpoints and pages."""
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        results: list[dict[str, Any]] = []

        # Phase 1: Search endpoints_fts for the error code string.
        results.extend(
            _search_error_in_endpoints(conn, error_code=error_code, exchange=exchange, limit=limit)
        )

        # Phase 2: Search pages_fts for the error code string.
        remaining = max(0, limit - len(results))
        if remaining > 0:
            results.extend(
                _search_error_in_pages(conn, error_code=error_code, exchange=exchange, limit=remaining)
            )

        return results[:limit]
    finally:
        conn.close()


def _search_error_in_endpoints(
    conn: sqlite3.Connection,
    *,
    error_code: str,
    exchange: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    # Sanitize the error code for FTS5 — strip non-alphanumeric except minus.
    sanitized = re.sub(r"[^\w\-]", " ", error_code).strip()
    if not sanitized:
        return []

    # FTS5 treats leading minus as NOT operator; quote it.
    fts_query = f'"{sanitized}"'

    where = ["endpoints_fts MATCH ?"]
    params: list[Any] = [fts_query]
    if exchange:
        where.append("endpoints_fts.exchange = ?")
        params.append(exchange)
    params.append(int(limit))

    sql = f"""
SELECT
  endpoints_fts.endpoint_id,
  endpoints_fts.exchange,
  endpoints_fts.section,
  endpoints_fts.method,
  endpoints_fts.path,
  snippet(endpoints_fts, 5, '[', ']', '...', 12) AS snippet,
  bm25(endpoints_fts) AS rank
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
        out.append({
            "source_type": "endpoint",
            "endpoint_id": r["endpoint_id"],
            "exchange": r["exchange"],
            "section": r["section"],
            "method": r["method"],
            "path": r["path"],
            "snippet": r["snippet"],
            "rank": r["rank"],
        })
    return out


def _search_error_in_pages(
    conn: sqlite3.Connection,
    *,
    error_code: str,
    exchange: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    sanitized = re.sub(r"[^\w\-]", " ", error_code).strip()
    if not sanitized:
        return []

    fts_query = f'"{sanitized}"'

    where = ["pages_fts MATCH ?"]
    params: list[Any] = [fts_query]
    if exchange:
        where.append("p.canonical_url LIKE ?")
        params.append(f"%{exchange}%")
    params.append(int(limit))

    sql = f"""
SELECT
  p.canonical_url,
  p.title,
  p.markdown_path,
  p.word_count,
  snippet(pages_fts, 2, '[', ']', '...', 12) AS snippet,
  bm25(pages_fts) AS rank
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
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
        out.append({
            "source_type": "page",
            "canonical_url": r["canonical_url"],
            "title": r["title"],
            "markdown_path": r["markdown_path"],
            "word_count": r["word_count"],
            "snippet": r["snippet"],
            "rank": r["rank"],
        })
    return out
