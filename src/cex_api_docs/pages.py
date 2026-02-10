from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import open_db
from .errors import CexApiDocsError
from .lock import acquire_write_lock
from .store import require_store_db
from .urlcanon import canonicalize_url


def search_pages(*, docs_dir: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        cur = conn.execute(
            """
SELECT
  p.canonical_url,
  p.title,
  p.domain,
  p.path_hash,
  p.content_hash,
  p.crawled_at,
  snippet(pages_fts, 2, '[', ']', '...', 12) AS snippet,
  bm25(pages_fts) AS rank
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ?
ORDER BY rank
LIMIT ?;
""",
            (query, int(limit)),
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            out.append(
                {
                    "canonical_url": row["canonical_url"],
                    "title": row["title"],
                    "domain": row["domain"],
                    "path_hash": row["path_hash"],
                    "content_hash": row["content_hash"],
                    "crawled_at": row["crawled_at"],
                    "snippet": row["snippet"],
                    "rank": row["rank"],
                }
            )
        return out
    finally:
        conn.close()


def get_page(*, docs_dir: str, url: str) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    canonical = canonicalize_url(url)
    conn = open_db(db_path)
    try:
        row = conn.execute(
            """
SELECT
  canonical_url, title, domain, path_hash, content_hash, crawled_at,
  raw_path, markdown_path, meta_path
FROM pages
WHERE canonical_url = ?;
""",
            (canonical,),
        ).fetchone()
        if row is None:
            raise CexApiDocsError(code="ENOTFOUND", message="Page not found in store.", details={"canonical_url": canonical})

        meta_path = Path(row["meta_path"])
        md_path = Path(row["markdown_path"]) if row["markdown_path"] else None
        raw_path = Path(row["raw_path"]) if row["raw_path"] else None

        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
        markdown = md_path.read_text(encoding="utf-8") if md_path and md_path.exists() else None

        return {
            "canonical_url": row["canonical_url"],
            "title": row["title"],
            "domain": row["domain"],
            "path_hash": row["path_hash"],
            "content_hash": row["content_hash"],
            "crawled_at": row["crawled_at"],
            "paths": {
                "meta_path": str(meta_path),
                "markdown_path": str(md_path) if md_path else None,
                "raw_path": str(raw_path) if raw_path else None,
            },
            "meta": meta,
            "markdown": markdown,
        }
    finally:
        conn.close()


def diff_pages(*, docs_dir: str, crawl_run_id: int | None = None, limit: int = 50) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        if crawl_run_id is None:
            row = conn.execute("SELECT max(id) AS id FROM crawl_runs;").fetchone()
            crawl_run_id = int(row["id"]) if row and row["id"] is not None else None
        if crawl_run_id is None:
            raise CexApiDocsError(code="ENODIFF", message="No crawl runs recorded yet.", details={"docs_dir": docs_dir})

        run_id = int(crawl_run_id)

        def q(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
            cur = conn.execute(sql, params)
            return [{"canonical_url": r["canonical_url"], "title": r["title"], "domain": r["domain"]} for r in cur.fetchall()]

        new_pages = q(
            """
SELECT canonical_url, title, domain
FROM pages
WHERE last_crawl_run_id = ? AND prev_content_hash IS NULL
LIMIT ?;
""",
            (run_id, int(limit)),
        )
        updated_pages = q(
            """
SELECT canonical_url, title, domain
FROM pages
WHERE last_crawl_run_id = ? AND prev_content_hash IS NOT NULL AND prev_content_hash != content_hash
LIMIT ?;
""",
            (run_id, int(limit)),
        )
        stale_pages = q(
            """
SELECT canonical_url, title, domain
FROM pages
WHERE last_crawl_run_id IS NULL OR last_crawl_run_id < ?
LIMIT ?;
""",
            (run_id, int(limit)),
        )

        counts = conn.execute(
            """
SELECT
  SUM(CASE WHEN last_crawl_run_id = ? AND prev_content_hash IS NULL THEN 1 ELSE 0 END) AS new_count,
  SUM(CASE WHEN last_crawl_run_id = ? AND prev_content_hash IS NOT NULL AND prev_content_hash != content_hash THEN 1 ELSE 0 END) AS updated_count,
  SUM(CASE WHEN last_crawl_run_id IS NULL OR last_crawl_run_id < ? THEN 1 ELSE 0 END) AS stale_count
FROM pages;
""",
            (run_id, run_id, run_id),
        ).fetchone()

        return {
            "crawl_run_id": run_id,
            "counts": {
                "new": int(counts["new_count"] or 0),
                "updated": int(counts["updated_count"] or 0),
                "stale": int(counts["stale_count"] or 0),
            },
            "samples": {
                "new": new_pages,
                "updated": updated_pages,
                "stale": stale_pages,
            },
        }
    finally:
        conn.close()


def fts_optimize(*, docs_dir: str, lock_timeout_s: float) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"
    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn = open_db(db_path)
        try:
            conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('optimize');")
            conn.execute("INSERT INTO endpoints_fts(endpoints_fts) VALUES('optimize');")
            conn.commit()
            return {"optimized": True}
        finally:
            conn.close()


def fts_rebuild(*, docs_dir: str, lock_timeout_s: float) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"
    rebuilt_pages = 0
    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn = open_db(db_path)
        try:
            with conn:
                conn.execute("DELETE FROM pages_fts;")
                rows = conn.execute(
                    "SELECT id, canonical_url, title, markdown_path FROM pages WHERE markdown_path IS NOT NULL;"
                ).fetchall()
                for r in rows:
                    md_path = Path(r["markdown_path"])
                    if not md_path.exists():
                        continue
                    md = md_path.read_text(encoding="utf-8")
                    conn.execute(
                        "INSERT INTO pages_fts(rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);",
                        (int(r["id"]), r["canonical_url"], r["title"] or "", md),
                    )
                    rebuilt_pages += 1

                # Endpoints FTS will be populated during endpoint ingestion; keep empty for now.
                conn.execute("DELETE FROM endpoints_fts;")

            conn.commit()
            return {"rebuilt_pages_fts": rebuilt_pages, "rebuilt_endpoints_fts": 0}
        finally:
            conn.close()
