"""Structured changelog extraction from stored doc pages.

Parses changelog pages into dated entries for drift detection.
Supports Binance-style (### YYYY-MM-DD headings), prose date headings
(Orderly-style "December 23rd, 2025"), single-entry pages (Bithumb,
Coinone), and Coinbase-style (## heading with dates inline).

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
# Matches headings with prose dates: ## December 23, 2025 or ##\u200b\nDecember 23rd, 2025
_PROSE_HEADING_RE = re.compile(
    r"^#{1,4}\s*[\u200b\u200c]?\s*\n?"
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
    re.MULTILINE | re.IGNORECASE,
)
# Matches a bare ISO date at the start of a heading: ### YYYY-MM-DD ...
_HEADING_RE = re.compile(r"^(#{1,4}\s+.+)$", re.MULTILINE)
# ISO date anywhere in text
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# Month name → number mapping for prose date parsing (no dateutil dependency).
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
_PROSE_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})",
    re.IGNORECASE,
)
_PROSE_MONTH_YEAR_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})",
    re.IGNORECASE,
)


def _parse_prose_date(text: str) -> str | None:
    """Parse a prose date string into ISO format (YYYY-MM-DD).

    Handles: "December 23rd, 2025", "January 15, 2026", "February 2026",
    "2025-12-23" (passthrough), and "December 23rd, 2025 - Major Update".
    Returns None if no date found.
    """
    if not text:
        return None
    # ISO passthrough
    m = _ISO_DATE_RE.search(text)
    if m:
        return m.group(1)
    # Full prose date: Month Day, Year
    m = _PROSE_DATE_RE.search(text)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        day = int(m.group(2))
        year = int(m.group(3))
        if month and 1 <= day <= 31 and 2000 <= year <= 2099:
            return f"{year:04d}-{month:02d}-{day:02d}"
    # Month + Year only
    m = _PROSE_MONTH_YEAR_RE.search(text)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        year = int(m.group(2))
        if month and 2000 <= year <= 2099:
            return f"{year:04d}-{month:02d}-01"
    return None


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
    Split a markdown document into (date, text) chunks at dated headings.

    Supports both ISO (### 2026-01-15) and prose (## December 23, 2025)
    date formats, including zero-width-space headings (Orderly).

    Returns a list of (date_str_or_None, chunk_text) pairs. The first chunk
    may have no date if there is preamble before the first dated heading.
    """
    # Try ISO headings first (most common, most reliable).
    positions = list(_HEADING_DATE_RE.finditer(markdown))
    if positions:
        return _split_at_positions(markdown, positions, iso=True)

    # Fallback: try prose date headings (M36: Orderly, CoinEx, Nado, etc.).
    prose_positions = list(_PROSE_HEADING_RE.finditer(markdown))
    if prose_positions:
        return _split_at_positions(markdown, prose_positions, iso=False)

    return [(None, markdown.strip())]


def _split_at_positions(
    markdown: str,
    positions: list[re.Match],
    *,
    iso: bool,
) -> list[tuple[str | None, str]]:
    """Split markdown at matched heading positions."""
    chunks: list[tuple[str | None, str]] = []
    preamble = markdown[: positions[0].start()].strip()
    if preamble:
        chunks.append((None, preamble))

    for i, m in enumerate(positions):
        if iso:
            date_str = m.group(1)
        else:
            date_str = _parse_prose_date(m.group(1))
        start = m.start()
        end = positions[i + 1].start() if i + 1 < len(positions) else len(markdown)
        chunk = markdown[start:end].strip()
        if chunk:
            chunks.append((date_str, chunk))

    return chunks


def _extract_date_from_page(url: str, markdown: str) -> str | None:
    """
    For single-entry pages (Bithumb, Coinone), extract the best date.
    Tries: URL slug ISO date, markdown ISO date, prose date in markdown.
    """
    # Try URL slug
    m = _ISO_DATE_RE.search(url)
    if m:
        return m.group(1)
    # Try markdown ISO date
    m = _ISO_DATE_RE.search(markdown)
    if m:
        return m.group(1)
    # M36: try prose date in markdown (e.g., "March 12, 2024")
    return _parse_prose_date(markdown[:500])


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
               OR p.canonical_url LIKE '%release-note%' OR p.canonical_url LIKE '%release_note%')
          AND p.markdown_path IS NOT NULL
          AND p.word_count > 50
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
            "error": "changelog_entries table not found — run 'xdocs init' first",
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
