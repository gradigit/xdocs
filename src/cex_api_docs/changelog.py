"""Structured changelog extraction from stored doc pages.

Parses changelog pages into dated entries for drift detection.
Supports Binance-style (### YYYY-MM-DD headings), single-entry pages
(Bithumb, Coinone), and Coinbase-style (## heading with dates inline).

Extracted entries are stored in the changelog_entries table. Running
extract-changelogs again is idempotent — duplicates are skipped via
UNIQUE(source_url, content_hash).
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from .db import open_db
from .store import require_store_db
from .timeutil import now_iso_utc

log = logging.getLogger(__name__)

# Matches ### 2026-02-24, ## 2025-12-01, etc.
_HEADING_DATE_RE = re.compile(r"^#{1,4}\s+(\d{4}-\d{2}-\d{2})", re.MULTILINE)
# Matches a bare ISO date at the start of a heading: ### YYYY-MM-DD ...
_HEADING_RE = re.compile(r"^(#{1,4}\s+.+)$", re.MULTILINE)
# ISO date anywhere in text
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_markdown(docs_dir: Path, markdown_path: str) -> str | None:
    """Read a stored markdown file relative to docs_dir."""
    # markdown_path may start with the docs_dir name (e.g. "cex-docs/pages/...")
    p = docs_dir / markdown_path
    if not p.exists():
        # Try stripping the first component if it matches docs_dir name
        parts = Path(markdown_path).parts
        if len(parts) > 1:
            p = docs_dir.parent / markdown_path
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _split_by_date_headings(markdown: str) -> list[tuple[str | None, str]]:
    """
    Split a markdown document into (date, text) chunks at ### YYYY-MM-DD headings.

    Returns a list of (date_str_or_None, chunk_text) pairs. The first chunk
    may have no date if there is preamble before the first dated heading.
    """
    positions = list(_HEADING_DATE_RE.finditer(markdown))
    if not positions:
        return [(None, markdown.strip())]

    chunks: list[tuple[str | None, str]] = []
    # Preamble before first dated heading (skip if empty)
    preamble = markdown[: positions[0].start()].strip()
    if preamble:
        chunks.append((None, preamble))

    for i, m in enumerate(positions):
        date_str = m.group(1)
        start = m.start()
        end = positions[i + 1].start() if i + 1 < len(positions) else len(markdown)
        chunk = markdown[start:end].strip()
        if chunk:
            chunks.append((date_str, chunk))

    return chunks


def _extract_date_from_page(url: str, markdown: str) -> str | None:
    """
    For single-entry pages (Bithumb, Coinone), extract the best date.
    Tries: URL slug, first ISO date in markdown, first heading text.
    """
    # Try URL slug
    m = _ISO_DATE_RE.search(url)
    if m:
        return m.group(1)
    # Try markdown content
    m = _ISO_DATE_RE.search(markdown)
    if m:
        return m.group(1)
    return None


def _entries_from_page(
    markdown: str,
    url: str,
    *,
    has_date_headings: bool,
) -> list[tuple[str | None, str]]:
    """
    Extract (date, entry_text) pairs from a single changelog page.

    For pages with ### YYYY-MM-DD headings, splits by heading.
    For single-entry pages (or pages with no dated headings), treats the
    whole page as one entry.
    """
    if has_date_headings:
        return _split_by_date_headings(markdown)

    # Single-entry page: whole page is one entry
    date = _extract_date_from_page(url, markdown)
    text = markdown.strip()
    if not text:
        return []
    return [(date, text)]


def extract_changelogs(
    *,
    docs_dir: str,
    exchange: str | None = None,
    limit_pages: int = 0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Extract structured changelog entries from stored changelog pages.

    Scans all pages whose URL contains 'changelog' or 'change-log', parses
    dated entries, and upserts them into changelog_entries. Idempotent.

    Args:
        docs_dir: Path to the local store root.
        exchange: If set, only process pages for this exchange.
        limit_pages: If > 0, process at most this many pages (for testing).
        dry_run: If True, parse but do not write to DB.

    Returns JSON-serialisable result dict.
    """
    db_path = require_store_db(docs_dir=docs_dir)
    conn = open_db(db_path)
    docs_path = Path(docs_dir)

    url_filter = "%" if exchange is None else f"%{exchange}%"
    query = """
        SELECT p.canonical_url, p.markdown_path,
               COALESCE(iso.owner_exchange_id, '') AS exchange_id,
               COALESCE(iso.owner_section_id, '') AS section_id
        FROM pages p
        LEFT JOIN inventory_scope_ownership iso ON iso.canonical_url = p.canonical_url
        WHERE (p.canonical_url LIKE '%changelog%' OR p.canonical_url LIKE '%change-log%'
               OR p.canonical_url LIKE '%changes%')
          AND p.markdown_path IS NOT NULL
          AND p.word_count > 20
    """
    params: list[Any] = []
    if exchange is not None:
        query += " AND p.canonical_url LIKE ?"
        params.append(f"%{exchange}%")
    query += " ORDER BY p.canonical_url"
    if limit_pages > 0:
        query += f" LIMIT {int(limit_pages)}"

    rows = conn.execute(query, params).fetchall()

    pages_processed = 0
    entries_new = 0
    entries_skipped = 0
    errors: list[dict[str, Any]] = []
    now = now_iso_utc()

    for row in rows:
        url = row["canonical_url"]
        md_path = row["markdown_path"]
        exchange_id = row["exchange_id"] or _guess_exchange(url)
        section_id = row["section_id"] or ""

        markdown = _read_markdown(docs_path, md_path)
        if not markdown:
            errors.append({"url": url, "error": "markdown file not found"})
            continue

        pages_processed += 1
        has_date_headings = bool(_HEADING_DATE_RE.search(markdown))
        entries = _entries_from_page(markdown, url, has_date_headings=has_date_headings)

        for date_str, entry_text in entries:
            content_hash = _sha256(entry_text)
            if dry_run:
                entries_new += 1
                continue
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO changelog_entries
                      (exchange_id, section_id, source_url, entry_date,
                       entry_text, content_hash, extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (exchange_id, section_id, url, date_str,
                     entry_text, content_hash, now),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    entries_new += 1
                else:
                    entries_skipped += 1
            except Exception as e:
                errors.append({"url": url, "error": str(e)})
                log.warning("changelog insert failed for %s: %s", url, e)

    if not dry_run:
        conn.commit()
        # Rebuild FTS index for new entries.
        try:
            conn.execute(
                "INSERT INTO changelog_entries_fts(changelog_entries_fts) VALUES('rebuild')"
            )
            conn.commit()
        except Exception as e:
            log.warning("FTS rebuild failed: %s", e)

    conn.close()

    return {
        "ok": True,
        "dry_run": dry_run,
        "pages_processed": pages_processed,
        "entries_new": entries_new,
        "entries_skipped": entries_skipped,
        "errors": errors,
        "schema_version": "v1",
    }


def list_changelogs(
    *,
    docs_dir: str,
    exchange: str | None = None,
    section: str | None = None,
    since: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    List extracted changelog entries, newest first.

    Args:
        docs_dir: Path to the local store root.
        exchange: Filter to exchange_id.
        section: Filter to section_id.
        since: ISO date string (YYYY-MM-DD); only return entries >= this date.
        limit: Maximum number of entries to return.
    """
    db_path = require_store_db(docs_dir=docs_dir)
    conn = open_db(db_path)

    # Check table exists (may not if migration hasn't run yet).
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "changelog_entries" not in tables:
        conn.close()
        return {
            "ok": False,
            "error": "changelog_entries table not found — run 'cex-api-docs init' first",
            "entries": [],
            "schema_version": "v1",
        }

    where: list[str] = []
    params: list[Any] = []
    if exchange:
        where.append("exchange_id = ?")
        params.append(exchange)
    if section:
        where.append("section_id = ?")
        params.append(section)
    if since:
        where.append("(entry_date IS NULL OR entry_date >= ?)")
        params.append(since)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(int(limit))
    rows = conn.execute(
        f"""
        SELECT id, exchange_id, section_id, source_url, entry_date,
               substr(entry_text, 1, 300) AS entry_preview,
               extracted_at
        FROM changelog_entries
        {where_sql}
        ORDER BY entry_date DESC NULLS LAST, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    # Total count for context.
    count_params = params[:-1]
    total = conn.execute(
        f"SELECT COUNT(*) FROM changelog_entries {where_sql}", count_params
    ).fetchone()[0]

    conn.close()

    return {
        "ok": True,
        "total": total,
        "returned": len(rows),
        "entries": [
            {
                "id": r["id"],
                "exchange_id": r["exchange_id"],
                "section_id": r["section_id"],
                "source_url": r["source_url"],
                "entry_date": r["entry_date"],
                "entry_preview": r["entry_preview"],
                "extracted_at": r["extracted_at"],
            }
            for r in rows
        ],
        "schema_version": "v1",
    }


def _guess_exchange(url: str) -> str:
    """Heuristically map a URL to an exchange_id."""
    url_l = url.lower()
    mapping = {
        "binance": "binance",
        "bybit": "bybit",
        "okx": "okx",
        "bitget": "bitget",
        "kucoin": "kucoin",
        "bithumb": "bithumb",
        "coinbase": "coinbase",
        "coinone": "coinone",
        "korbit": "korbit",
        "kraken": "kraken",
        "bitmex": "bitmex",
        "bitfinex": "bitfinex",
        "gate.io": "gateio",
        "gateio": "gateio",
        "htx": "htx",
        "upbit": "upbit",
        "bitstamp": "bitstamp",
        "crypto.com": "cryptocom",
        "dydx": "dydx",
        "hyperliquid": "hyperliquid",
        "drift": "drift",
        "aevo": "aevo",
        "gmx": "gmx",
        "paradex": "paradex",
        "asterdex": "aster",
        "apex": "apex",
        "grvt": "grvt",
        "bitbank": "bitbank",
        "bitmart": "bitmart",
        "whitebit": "whitebit",
        "mercadobitcoin": "mercadobitcoin",
        "ccxt": "ccxt",
    }
    for key, exchange_id in mapping.items():
        if key in url_l:
            return exchange_id
    return "unknown"
