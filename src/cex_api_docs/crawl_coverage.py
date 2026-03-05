from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .crawl_targets import discover_crawl_targets
from .db import open_db
from .lock import acquire_write_lock
from .registry import load_registry
from .store import require_store_db
from .timeutil import now_iso_utc

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SectionCoverage:
    exchange_id: str
    section_id: str
    discovered_urls: int
    stored_urls: int
    missing_urls: list[str]
    stale_urls: list[str]
    coverage_pct: float
    discovery_methods_used: list[str]
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class CoverageAuditResult:
    sections: list[SectionCoverage]
    overall_coverage_pct: float
    total_missing: int
    total_stale: int


def _get_store_urls_for_domains(db_path: Path, domains: list[str]) -> set[str]:
    """Get all canonical_url from pages matching the given domains."""
    conn = open_db(db_path)
    try:
        urls: set[str] = set()
        for domain in domains:
            d = domain.lower()
            rows = conn.execute(
                "SELECT canonical_url FROM pages WHERE domain = ? OR domain LIKE ?",
                (d, f"%.{d}"),
            ).fetchall()
            for row in rows:
                urls.add(row["canonical_url"])
        return urls
    finally:
        conn.close()


def _get_stale_urls(db_path: Path, domains: list[str], stale_days: int = 90) -> list[str]:
    """Get page URLs that haven't been crawled in stale_days."""
    conn = open_db(db_path)
    try:
        stale: list[str] = []
        for domain in domains:
            d = domain.lower()
            rows = conn.execute(
                """
                SELECT canonical_url FROM pages
                WHERE (domain = ? OR domain LIKE ?)
                  AND crawled_at IS NOT NULL
                  AND julianday('now') - julianday(crawled_at) > ?
                """,
                (d, f"%.{d}", stale_days),
            ).fetchall()
            for row in rows:
                stale.append(row["canonical_url"])
        return sorted(set(stale))
    finally:
        conn.close()


def audit_crawl_coverage(
    *,
    docs_dir: str,
    registry_path: Path,
    exchange_id: str | None = None,
    section_id: str | None = None,
    enable_live: bool = False,
    enable_nav: bool = False,
    enable_wayback: bool = False,
    timeout_s: float = 30.0,
) -> CoverageAuditResult:
    """Audit crawl coverage across registry sections.

    For each section: runs discover_crawl_targets(), gets store URLs,
    computes coverage metrics and detects stale pages.
    """
    registry = load_registry(registry_path)
    db_path = require_store_db(docs_dir)

    sections_to_audit: list[tuple[str, str]] = []
    for ex in registry.exchanges:
        if exchange_id and ex.exchange_id != exchange_id:
            continue
        for sec in ex.sections:
            if section_id and sec.section_id != section_id:
                continue
            sections_to_audit.append((ex.exchange_id, sec.section_id))

    section_results: list[SectionCoverage] = []
    total_discovered = 0
    total_stored = 0
    total_missing = 0
    total_stale = 0

    for ex_id, sec_id in sections_to_audit:
        exchange = registry.get_exchange(ex_id)
        allowed_domains = exchange.allowed_domains

        # Discover URLs via multi-method pipeline.
        discovery = discover_crawl_targets(
            exchange_id=ex_id,
            section_id=sec_id,
            registry_path=registry_path,
            docs_dir=docs_dir,
            enable_nav=enable_nav,
            enable_wayback=enable_wayback,
            timeout_s=timeout_s,
        )

        discovered_set = {d.url for d in discovery.urls}
        store_set = _get_store_urls_for_domains(db_path, allowed_domains)
        stale = _get_stale_urls(db_path, allowed_domains)

        missing = sorted(discovered_set - store_set)
        coverage_pct = (
            len(discovered_set & store_set) / len(discovered_set) * 100.0
            if discovered_set
            else 100.0
        )

        warnings = list(discovery.warnings)
        if missing:
            warnings.append(f"{len(missing)} discovered URLs missing from store")
        if stale:
            warnings.append(f"{len(stale)} stored pages are stale (>90 days)")

        section_results.append(SectionCoverage(
            exchange_id=ex_id,
            section_id=sec_id,
            discovered_urls=len(discovered_set),
            stored_urls=len(store_set),
            missing_urls=missing,
            stale_urls=stale,
            coverage_pct=round(coverage_pct, 2),
            discovery_methods_used=sorted(discovery.method_counts.keys()),
            warnings=warnings,
        ))

        total_discovered += len(discovered_set)
        total_stored += len(store_set)
        total_missing += len(missing)
        total_stale += len(stale)

    overall_pct = (
        (total_stored / total_discovered * 100.0)
        if total_discovered > 0
        else 100.0
    )

    return CoverageAuditResult(
        sections=section_results,
        overall_coverage_pct=round(overall_pct, 2),
        total_missing=total_missing,
        total_stale=total_stale,
    )


def backfill_gaps(
    *,
    docs_dir: str,
    exchange_id: str,
    section_id: str,
    missing_urls: list[str],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Insert missing URLs into the latest inventory as 'pending' entries.

    Returns: {"inserted": N, "already_existed": M, "dry_run": bool}
    """
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"

    conn = open_db(db_path)
    try:
        # Find latest inventory for this exchange/section.
        row = conn.execute(
            """
            SELECT id FROM inventories
            WHERE exchange_id = ? AND section_id = ?
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (exchange_id, section_id),
        ).fetchone()

        if row is None:
            return {
                "inserted": 0,
                "already_existed": 0,
                "dry_run": dry_run,
                "error": f"No inventory found for {exchange_id}/{section_id}",
            }

        inventory_id = int(row["id"])
    finally:
        conn.close()

    if dry_run:
        # Count how many already exist without writing.
        conn = open_db(db_path)
        try:
            existing = 0
            for url in missing_urls:
                check = conn.execute(
                    "SELECT 1 FROM inventory_entries WHERE inventory_id = ? AND canonical_url = ?",
                    (inventory_id, url),
                ).fetchone()
                if check:
                    existing += 1
            return {
                "inserted": len(missing_urls) - existing,
                "already_existed": existing,
                "dry_run": True,
                "inventory_id": inventory_id,
            }
        finally:
            conn.close()

    # Write mode: insert missing entries.
    inserted = 0
    already_existed = 0

    with acquire_write_lock(lock_path, timeout_s=10.0):
        conn = open_db(db_path)
        try:
            with conn:
                for url in missing_urls:
                    check = conn.execute(
                        "SELECT 1 FROM inventory_entries WHERE inventory_id = ? AND canonical_url = ?",
                        (inventory_id, url),
                    ).fetchone()
                    if check:
                        already_existed += 1
                        continue
                    conn.execute(
                        """
                        INSERT INTO inventory_entries (inventory_id, canonical_url, status)
                        VALUES (?, ?, 'pending')
                        """,
                        (inventory_id, url),
                    )
                    inserted += 1

                # Update the inventory url_count.
                conn.execute(
                    """
                    UPDATE inventories SET url_count = (
                        SELECT COUNT(*) FROM inventory_entries WHERE inventory_id = ?
                    ) WHERE id = ?
                    """,
                    (inventory_id, inventory_id),
                )
            conn.commit()
        finally:
            conn.close()

    return {
        "inserted": inserted,
        "already_existed": already_existed,
        "dry_run": False,
        "inventory_id": inventory_id,
    }
