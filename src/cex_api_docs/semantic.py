"""Semantic search via LanceDB (optional, requires `pip install cex-api-docs[semantic]`)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .db import open_db
from .store import require_store_db

logger = logging.getLogger(__name__)

# Lazy imports to avoid hard dependency on lancedb/sentence-transformers.
_lancedb = None
_embedder = None

TABLE_NAME = "pages"


def _require_lancedb():
    global _lancedb
    if _lancedb is None:
        try:
            import lancedb
        except ImportError:
            raise ImportError(
                "lancedb is not installed. Run: pip install cex-api-docs[semantic]"
            )
        _lancedb = lancedb
    return _lancedb


def _get_embedder():
    global _embedder
    if _embedder is None:
        lancedb = _require_lancedb()
        from lancedb.embeddings import get_registry

        _embedder = get_registry().get("sentence-transformers").create()
    return _embedder


def _lance_dir(docs_dir: str) -> str:
    return str(Path(docs_dir) / "lancedb-index")


def build_index(
    *,
    docs_dir: str,
    limit: int = 0,
    exchange: str | None = None,
    batch_size: int = 256,
) -> dict[str, Any]:
    """Build or rebuild the LanceDB semantic index from SQLite pages.

    Args:
        docs_dir: Path to the cex-docs store directory.
        limit: Max pages to embed (0 = all).
        exchange: Optional filter by exchange domain pattern.
        batch_size: Rows per embedding batch.

    Returns:
        Summary dict with counts.
    """
    lancedb = _require_lancedb()
    embedder = _get_embedder()

    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)

    try:
        # Build query.
        sql = """
SELECT
  p.id AS page_id,
  p.canonical_url,
  p.title,
  p.domain,
  p.word_count,
  p.markdown_path
FROM pages p
WHERE p.word_count > 0 AND p.markdown_path IS NOT NULL
"""
        params: list[Any] = []
        if exchange:
            sql += " AND p.domain LIKE ?"
            params.append(f"%{exchange}%")
        sql += " ORDER BY p.id"
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"cmd": "build-index", "pages_embedded": 0, "status": "no_pages"}

    logger.info("Embedding %d pages...", len(rows))

    # Read markdown content and build records.
    records: list[dict[str, Any]] = []
    skipped = 0
    # markdown_path is stored relative to repo root (includes docs_dir prefix),
    # so resolve from the parent of docs_dir.
    docs_path = Path(docs_dir)
    repo_root = docs_path.parent
    for row in rows:
        md_rel = row["markdown_path"]
        md_path = repo_root / md_rel if md_rel.startswith(docs_path.name) else docs_path / md_rel
        if not md_path.exists():
            skipped += 1
            continue
        md_text = md_path.read_text(encoding="utf-8", errors="replace")
        # Truncate to ~2000 chars for embedding (MiniLM has 512 token limit).
        text = md_text[:4000]
        if not text.strip():
            skipped += 1
            continue

        # Derive exchange from domain.
        domain = row["domain"]
        exchange_id = _domain_to_exchange(domain)

        records.append(
            {
                "text": text,
                "page_id": row["page_id"],
                "exchange": exchange_id,
                "domain": domain,
                "url": row["canonical_url"],
                "title": row["title"] or "",
                "word_count": row["word_count"],
            }
        )

    if not records:
        return {"cmd": "build-index", "pages_embedded": 0, "skipped": skipped, "status": "no_content"}

    # Connect to LanceDB and create/overwrite table.
    lance_db = lancedb.connect(_lance_dir(docs_dir))

    from lancedb.pydantic import LanceModel, Vector

    ndims = embedder.ndims()

    class PageEmbedding(LanceModel):
        text: str = embedder.SourceField()
        vector: Vector(ndims) = embedder.VectorField()  # type: ignore[valid-type]
        page_id: int
        exchange: str
        domain: str
        url: str
        title: str
        word_count: int

    # Drop existing table if present.
    try:
        lance_db.drop_table(TABLE_NAME)
    except Exception:
        pass

    # Batch insert.
    table = lance_db.create_table(TABLE_NAME, schema=PageEmbedding)
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        logger.info("  Embedding batch %d-%d / %d", i, i + len(batch), len(records))
        table.add(batch)

    # Create FTS index for hybrid search.
    table.create_fts_index("text", replace=True)

    return {
        "cmd": "build-index",
        "pages_embedded": len(records),
        "skipped": skipped,
        "total_rows": table.count_rows(),
        "lance_dir": _lance_dir(docs_dir),
        "status": "ok",
    }


def semantic_search(
    *,
    docs_dir: str,
    query: str,
    exchange: str | None = None,
    limit: int = 10,
    query_type: str = "hybrid",
) -> list[dict[str, Any]]:
    """Run semantic (vector), FTS, or hybrid search against the LanceDB index.

    Args:
        docs_dir: Path to the cex-docs store directory.
        query: Natural language query string.
        exchange: Optional exchange filter.
        limit: Max results.
        query_type: "vector", "fts", or "hybrid".

    Returns:
        List of result dicts with url, title, score, etc.
    """
    lancedb = _require_lancedb()
    lance_db = lancedb.connect(_lance_dir(docs_dir))
    table = lance_db.open_table(TABLE_NAME)

    search = table.search(query, query_type=query_type).limit(limit)
    if exchange:
        search = search.where(f"exchange = '{exchange}'")

    arrow_table = search.to_arrow()
    results: list[dict[str, Any]] = []
    cols = arrow_table.column_names
    for i in range(arrow_table.num_rows):
        score = 0.0
        if "_relevance_score" in cols:
            score = float(arrow_table.column("_relevance_score")[i].as_py())
        elif "_distance" in cols:
            score = float(arrow_table.column("_distance")[i].as_py())
        results.append(
            {
                "page_id": int(arrow_table.column("page_id")[i].as_py()),
                "url": str(arrow_table.column("url")[i].as_py()),
                "title": str(arrow_table.column("title")[i].as_py()),
                "exchange": str(arrow_table.column("exchange")[i].as_py()),
                "word_count": int(arrow_table.column("word_count")[i].as_py()),
                "score": score,
            }
        )
    return results


def fts5_search(
    *,
    docs_dir: str,
    query: str,
    exchange: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Run SQLite FTS5 BM25 search (baseline for comparison)."""
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        sql = """
SELECT
  p.id AS page_id,
  p.canonical_url AS url,
  p.title,
  p.domain,
  p.word_count,
  bm25(pages_fts) AS rank
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ?
"""
        params: list[Any] = [query]
        if exchange:
            sql += " AND p.domain LIKE ?"
            params.append(f"%{exchange}%")
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        results: list[dict[str, Any]] = []
        for row in conn.execute(sql, params).fetchall():
            results.append(
                {
                    "page_id": row["page_id"],
                    "url": row["url"],
                    "title": row["title"],
                    "exchange": _domain_to_exchange(row["domain"]),
                    "word_count": row["word_count"],
                    "score": row["rank"],
                }
            )
        return results
    finally:
        conn.close()


_DOMAIN_MAP = {
    "developers.binance.com": "binance",
    "binance-docs.github.io": "binance",
    "bybit-exchange.github.io": "bybit",
    "www.kucoin.com": "kucoin",
    "www.okx.com": "okx",
    "www.bitget.com": "bitget",
    "www.gate.com": "gateio",
    "huobiapi.github.io": "htx",
    "exchange-docs.crypto.com": "crypto_com",
    "docs.bitfinex.com": "bitfinex",
    "www.bitstamp.net": "bitstamp",
    "docs.dydx.xyz": "dydx",
    "hyperliquid.gitbook.io": "hyperliquid",
    "docs.upbit.com": "upbit",
    "apidocs.bithumb.com": "bithumb",
    "docs.coinone.co.kr": "coinone",
    "docs.korbit.co.kr": "korbit",
    "raw.githubusercontent.com": "aggregator",
}


def _domain_to_exchange(domain: str) -> str:
    return _DOMAIN_MAP.get(domain, domain)
