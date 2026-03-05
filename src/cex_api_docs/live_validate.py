from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import open_db
from .nav_extract import extract_nav_urls
from .registry import load_registry
from .store import require_store_db
from .urlcanon import canonicalize_url

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LiveValidationResult:
    exchange_id: str
    section_id: str
    live_urls: list[str]
    store_urls: list[str]
    missing_from_store: list[str]
    missing_from_live: list[str]
    overlap: list[str]
    coverage_pct: float
    nav_method: str
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]


def _get_store_urls(db_path: Path, allowed_domains: list[str]) -> list[str]:
    """Query the store for all page canonical_urls matching the given domains."""
    conn = open_db(db_path)
    try:
        urls: list[str] = []
        for domain in allowed_domains:
            domain_lower = domain.lower()
            # Match exact domain and subdomains via LIKE.
            rows = conn.execute(
                "SELECT canonical_url FROM pages WHERE domain = ? OR domain LIKE ?",
                (domain_lower, f"%.{domain_lower}"),
            ).fetchall()
            for row in rows:
                urls.append(row["canonical_url"])
        return sorted(set(urls))
    finally:
        conn.close()


def validate_live_site(
    *,
    exchange_id: str,
    section_id: str,
    registry_path: Path,
    docs_dir: str,
    timeout_s: float = 30.0,
) -> LiveValidationResult:
    """Compare live site navigation URLs against the stored page set.

    Uses nav_extract to discover live URLs and queries the store DB for
    existing page URLs. Returns set differences and coverage metrics.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    # Load registry for exchange/section config.
    registry = load_registry(registry_path)
    exchange = registry.get_exchange(exchange_id)
    section = registry.get_section(exchange_id, section_id)

    allowed_domains = exchange.allowed_domains
    seed_urls = section.seed_urls

    if not seed_urls:
        warnings.append({
            "type": "no_seeds",
            "message": f"No seed URLs configured for {exchange_id}/{section_id}",
        })
        return LiveValidationResult(
            exchange_id=exchange_id,
            section_id=section_id,
            live_urls=[],
            store_urls=[],
            missing_from_store=[],
            missing_from_live=[],
            overlap=[],
            coverage_pct=0.0,
            nav_method="none",
            errors=errors,
            warnings=warnings,
        )

    # Extract live nav URLs from the first seed.
    nav_result = extract_nav_urls(
        seed_url=seed_urls[0],
        allowed_domains=allowed_domains,
        timeout_s=timeout_s,
    )

    errors.extend(nav_result.errors)

    # Canonicalize live URLs for comparison.
    live_canon: set[str] = set()
    for u in nav_result.urls:
        try:
            live_canon.add(canonicalize_url(u))
        except Exception:
            continue

    # Get store URLs.
    db_path = require_store_db(docs_dir)
    store_urls_list = _get_store_urls(db_path, allowed_domains)
    store_canon: set[str] = set(store_urls_list)

    # Compute set differences.
    overlap = sorted(live_canon & store_canon)
    missing_from_store = sorted(live_canon - store_canon)
    missing_from_live = sorted(store_canon - live_canon)

    # Coverage: what fraction of live URLs are in the store.
    coverage_pct = (len(overlap) / len(live_canon) * 100.0) if live_canon else 0.0

    if missing_from_store:
        warnings.append({
            "type": "missing_from_store",
            "count": len(missing_from_store),
            "message": f"{len(missing_from_store)} live URLs not in store",
        })

    if not live_canon and store_canon:
        warnings.append({
            "type": "nav_extraction_empty",
            "message": "Nav extraction returned 0 URLs but store has pages; nav may not reflect full site",
        })

    return LiveValidationResult(
        exchange_id=exchange_id,
        section_id=section_id,
        live_urls=sorted(live_canon),
        store_urls=store_urls_list,
        missing_from_store=missing_from_store,
        missing_from_live=missing_from_live,
        overlap=overlap,
        coverage_pct=round(coverage_pct, 2),
        nav_method=nav_result.method,
        errors=errors,
        warnings=warnings,
    )
