from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .errors import XDocsError
from .httpfetch import fetch
from .registry import load_registry
from .sitemaps import SitemapEntry, parse_sitemap_bytes


@dataclass(frozen=True, slots=True)
class SitemapHealth:
    url: str
    reachable: bool
    http_status: int | None
    entry_count: int
    has_lastmod: bool
    stale_entry_count: int  # lastmod > 1 year ago
    error: str | None


@dataclass(frozen=True, slots=True)
class SitemapCrossValidation:
    sitemap_url: str
    in_both: list[str]
    in_sitemap_only: list[str]
    in_store_only: list[str]


@dataclass(frozen=True, slots=True)
class SitemapValidationResult:
    exchange_id: str
    section_id: str
    sitemaps: list[SitemapHealth]
    cross_validation: SitemapCrossValidation | None
    warnings: list[str]


def _count_stale(entries: list[SitemapEntry], *, cutoff_days: int = 365) -> int:
    """Count entries whose lastmod is older than cutoff_days."""
    now = datetime.now(timezone.utc)
    count = 0
    for e in entries:
        if not e.lastmod:
            continue
        try:
            # Parse ISO 8601 date or datetime.
            dt_str = e.lastmod.strip()
            if "T" in dt_str:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            else:
                dt = datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if (now - dt).days > cutoff_days:
                count += 1
        except (ValueError, TypeError):
            continue
    return count


def _check_sitemap(
    session: requests.Session,
    *,
    url: str,
    timeout_s: float,
) -> SitemapHealth:
    """Fetch and parse a single sitemap URL, returning health info."""
    try:
        fr = fetch(
            session,
            url=url,
            timeout_s=timeout_s,
            max_bytes=50_000_000,
            max_redirects=5,
            retries=1,
            allowed_domains=None,
        )
    except XDocsError as e:
        return SitemapHealth(
            url=url,
            reachable=False,
            http_status=None,
            entry_count=0,
            has_lastmod=False,
            stale_entry_count=0,
            error=e.message,
        )
    except Exception as e:
        return SitemapHealth(
            url=url,
            reachable=False,
            http_status=None,
            entry_count=0,
            has_lastmod=False,
            stale_entry_count=0,
            error=f"{type(e).__name__}: {e}",
        )

    status = int(fr.http_status)
    if status < 200 or status >= 300:
        return SitemapHealth(
            url=url,
            reachable=True,
            http_status=status,
            entry_count=0,
            has_lastmod=False,
            stale_entry_count=0,
            error=f"HTTP {status}",
        )

    try:
        parsed = parse_sitemap_bytes(data=fr.body, url=fr.final_url)
    except XDocsError as e:
        return SitemapHealth(
            url=url,
            reachable=True,
            http_status=status,
            entry_count=0,
            has_lastmod=False,
            stale_entry_count=0,
            error=e.message,
        )

    entries = parsed.entries
    has_lastmod = any(e.lastmod for e in entries)
    stale_count = _count_stale(entries) if has_lastmod else 0

    return SitemapHealth(
        url=url,
        reachable=True,
        http_status=status,
        entry_count=len(entries),
        has_lastmod=has_lastmod,
        stale_entry_count=stale_count,
        error=None,
    )


def cross_validate_sitemap(
    *,
    sitemap_urls: list[str],
    store_urls: list[str],
) -> SitemapCrossValidation:
    """Compare sitemap entries against store URLs."""
    sitemap_set = set(sitemap_urls)
    store_set = set(store_urls)

    in_both = sorted(sitemap_set & store_set)
    in_sitemap_only = sorted(sitemap_set - store_set)
    in_store_only = sorted(store_set - sitemap_set)

    # Use the first sitemap URL as label, or empty string.
    label = sitemap_urls[0] if sitemap_urls else ""

    return SitemapCrossValidation(
        sitemap_url=label,
        in_both=in_both,
        in_sitemap_only=in_sitemap_only,
        in_store_only=in_store_only,
    )


def validate_sitemaps(
    *,
    exchange_id: str,
    section_id: str,
    registry_path: Path,
    timeout_s: float = 15.0,
) -> SitemapValidationResult:
    """Validate configured sitemaps for an exchange section."""
    registry = load_registry(registry_path)
    section = registry.get_section(exchange_id, section_id)

    sitemap_urls = [ds.url for ds in section.doc_sources if ds.kind == "sitemap" and ds.url]

    warnings: list[str] = []
    if not sitemap_urls:
        warnings.append(f"No sitemap doc_sources configured for {exchange_id}/{section_id}.")

    session = requests.Session()
    health_results: list[SitemapHealth] = []
    for sm_url in sitemap_urls:
        h = _check_sitemap(session, url=sm_url, timeout_s=timeout_s)
        health_results.append(h)
        if not h.reachable:
            warnings.append(f"Sitemap unreachable: {sm_url}")
        elif h.error:
            warnings.append(f"Sitemap error: {sm_url} -- {h.error}")
        if h.stale_entry_count > 0:
            warnings.append(f"Sitemap has {h.stale_entry_count} stale entries (>1 year): {sm_url}")

    return SitemapValidationResult(
        exchange_id=exchange_id,
        section_id=section_id,
        sitemaps=health_results,
        cross_validation=None,
        warnings=warnings,
    )
