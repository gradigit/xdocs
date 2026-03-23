from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .db import open_db
from .httpfetch import create_session
from .inventory import _walk_sitemaps, _common_sitemap_candidates, _robot_sitemaps, _in_scope, scope_prefixes_from_seeds
from .nav_extract import extract_nav_urls
from .registry import load_registry
from .store import require_store_db
from .url_sanitize import sanitize_url
from .urlcanon import canonicalize_url
from .urlutil import url_host as _host

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DiscoveredUrl:
    url: str
    sources: frozenset[str]  # {"sitemap", "link_follow", "nav_extraction", "wayback"}
    first_seen_via: str


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    exchange_id: str
    section_id: str
    urls: list[DiscoveredUrl]
    method_counts: dict[str, int]
    intersection_count: int      # Found by 2+ methods
    single_source_count: int     # Found by only 1 method
    rejected_urls: list[dict[str, Any]]
    method_errors: dict[str, list[dict[str, Any]]]
    warnings: list[str]


def _host_allowed(host: str, allowed_domains: set[str]) -> bool:
    """Check whether a hostname matches the allowed domains set."""
    host = host.lower()
    for d in allowed_domains:
        dd = d.lower()
        if host == dd or host.endswith("." + dd):
            return True
    return False


def _sanitize_and_filter(
    urls: list[str],
    *,
    allowed_domains: set[str],
    scope_prefixes: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Canonicalize, sanitize, scope-filter a list of URLs.

    Returns (accepted, rejected).
    """
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for u in urls:
        sr = sanitize_url(u)
        if not sr.accepted:
            rejected.append({"url": u, "reason": sr.reason})
            continue

        try:
            canon = canonicalize_url(u)
        except Exception:
            rejected.append({"url": u, "reason": "canonicalize_error"})
            continue

        h = _host(canon)
        if allowed_domains and h and not _host_allowed(h, allowed_domains):
            rejected.append({"url": u, "reason": "domain_not_allowed", "host": h})
            continue

        if not _in_scope(canon, scope_prefixes=scope_prefixes):
            rejected.append({"url": u, "reason": "out_of_scope"})
            continue

        if canon not in seen:
            seen.add(canon)
            accepted.append(canon)

    return accepted, rejected


def _discover_sitemap(
    session: requests.Session,
    *,
    seed_urls: list[str],
    allowed_domains: set[str],
    scope_prefixes: list[str],
    doc_sources: list[dict[str, Any]],
    timeout_s: float,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Discover URLs via sitemaps. Returns (urls, errors)."""
    robot_sms: list[str] = []
    for s in seed_urls[:3]:
        robot_sms.extend(_robot_sitemaps(session, base_url=s, timeout_s=timeout_s))

    ds_sitemaps = [ds["url"] for ds in doc_sources if ds.get("kind") == "sitemap" and ds.get("url")]
    candidates = list(set(robot_sms + ds_sitemaps + _common_sitemap_candidates(seed_urls)))

    visited, raw_urls, errors = _walk_sitemaps(
        session,
        sitemap_urls=candidates,
        allowed_domains=allowed_domains,
        timeout_s=timeout_s,
        max_bytes=50_000_000,
        max_redirects=5,
        retries=1,
    )

    filtered, rejected = _sanitize_and_filter(
        raw_urls,
        allowed_domains=allowed_domains,
        scope_prefixes=scope_prefixes,
    )

    return filtered, errors


def _discover_link_follow(
    session: requests.Session,
    *,
    seed_urls: list[str],
    allowed_domains: set[str],
    scope_prefixes: list[str],
    timeout_s: float,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Discover URLs via first-level link extraction from seed pages."""
    errors: list[dict[str, Any]] = []
    raw_urls: list[str] = []

    for seed in seed_urls:
        try:
            resp = session.get(seed, timeout=timeout_s, allow_redirects=True)
            if resp.status_code >= 400:
                errors.append({"url": seed, "error": f"HTTP {resp.status_code}"})
                continue
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href")
                if not href or not isinstance(href, str):
                    continue
                resolved = urljoin(seed, href)
                parts = urlsplit(resolved)
                if parts.scheme in ("http", "https"):
                    raw_urls.append(resolved)
        except Exception as exc:
            errors.append({"url": seed, "error": f"{type(exc).__name__}: {exc}"})

    filtered, _ = _sanitize_and_filter(
        raw_urls,
        allowed_domains=allowed_domains,
        scope_prefixes=scope_prefixes,
    )

    return filtered, errors


def _discover_nav(
    *,
    seed_urls: list[str],
    allowed_domains: list[str],
    scope_prefixes: list[str],
    timeout_s: float,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Discover URLs via nav extraction."""
    if not seed_urls:
        return [], []

    result = extract_nav_urls(
        seed_url=seed_urls[0],
        allowed_domains=allowed_domains,
        timeout_s=timeout_s,
    )

    filtered, _ = _sanitize_and_filter(
        result.urls,
        allowed_domains=set(d.lower() for d in allowed_domains),
        scope_prefixes=scope_prefixes,
    )

    return filtered, result.errors


def _discover_wayback(
    session: requests.Session,
    *,
    allowed_domains: list[str],
    scope_prefixes: list[str],
    timeout_s: float,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Discover URLs via Wayback Machine CDX API."""
    errors: list[dict[str, Any]] = []
    raw_urls: list[str] = []
    allowed_set = set(d.lower() for d in allowed_domains)

    for domain in allowed_domains:
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url={domain}/*&output=json&fl=original&collapse=urlkey"
        )
        retries = 0
        while retries <= 3:
            try:
                resp = session.get(cdx_url, timeout=timeout_s)
                if resp.status_code == 503:
                    retries += 1
                    if retries > 3:
                        errors.append({"domain": domain, "error": "CDX 503 after 3 retries"})
                        break
                    time.sleep(2 ** retries)
                    continue
                if resp.status_code == 404:
                    break  # Normal empty — no archive data.
                if resp.status_code >= 400:
                    errors.append({"domain": domain, "error": f"CDX HTTP {resp.status_code}"})
                    break
                try:
                    data = resp.json()
                except (ValueError, Exception):
                    errors.append({"domain": domain, "error": "CDX JSON decode error"})
                    break
                # CDX returns a list of lists; first row is header ["original"].
                if isinstance(data, list) and len(data) > 1:
                    for row in data[1:]:
                        if isinstance(row, list) and row:
                            raw_urls.append(row[0])
                break
            except Exception as exc:
                errors.append({"domain": domain, "error": f"{type(exc).__name__}: {exc}"})
                break

        # Rate limit: 1s delay between requests.
        time.sleep(1)

    filtered, _ = _sanitize_and_filter(
        raw_urls,
        allowed_domains=allowed_set,
        scope_prefixes=scope_prefixes,
    )

    return filtered, errors


def _self_check(
    *,
    method_counts: dict[str, int],
    total_urls: int,
    intersection_count: int,
    single_source_count: int,
    store_url_count: int,
) -> list[str]:
    """Run self-check heuristics. Returns warning strings."""
    warnings: list[str] = []

    # All methods returned 0 URLs but store has pages.
    active_methods = [m for m, c in method_counts.items() if c is not None]
    all_zero = all(method_counts.get(m, 0) == 0 for m in active_methods)
    if all_zero and store_url_count > 0:
        warnings.append(
            f"all_methods_failed: All {len(active_methods)} methods returned 0 URLs "
            f"but store has {store_url_count} pages"
        )

    # Method divergence: one method has <20 URLs AND another has >10x more.
    counts = [c for c in method_counts.values() if c is not None and c > 0]
    if len(counts) >= 2:
        min_c = min(counts)
        max_c = max(counts)
        if min_c < 20 and max_c > min_c * 10:
            warnings.append(
                f"method_divergence: Method counts diverge significantly "
                f"(min={min_c}, max={max_c})"
            )

    # Low cross-validation: >50% found by only 1 method AND total < 50.
    if total_urls > 0 and total_urls < 50:
        single_pct = single_source_count / total_urls
        if single_pct > 0.5:
            warnings.append(
                f"low_cross_validation: {single_pct:.0%} of {total_urls} URLs found by only 1 method"
            )

    return warnings


def discover_crawl_targets(
    *,
    exchange_id: str,
    section_id: str,
    registry_path: Path,
    docs_dir: str | None = None,
    enable_nav: bool = False,
    enable_wayback: bool = False,
    timeout_s: float = 30.0,
) -> DiscoveryResult:
    """Multi-method URL discovery for an exchange section.

    Always runs sitemap + link_follow. Optionally runs nav extraction
    and Wayback CDX API.
    """
    registry = load_registry(registry_path)
    exchange = registry.get_exchange(exchange_id)
    section = registry.get_section(exchange_id, section_id)

    allowed_domains = set(d.lower() for d in exchange.allowed_domains)
    seed_urls = section.seed_urls
    scope_prefixes = scope_prefixes_from_seeds(seed_urls)
    doc_sources = [{"kind": ds.kind, "url": ds.url} for ds in section.doc_sources]

    session = create_session()

    # Track per-method results.
    url_sets: dict[str, set[str]] = {}
    method_errors: dict[str, list[dict[str, Any]]] = {}
    all_rejected: list[dict[str, Any]] = []

    # 1. Sitemap.
    sm_urls, sm_errors = _discover_sitemap(
        session,
        seed_urls=seed_urls,
        allowed_domains=allowed_domains,
        scope_prefixes=scope_prefixes,
        doc_sources=doc_sources,
        timeout_s=timeout_s,
    )
    url_sets["sitemap"] = set(sm_urls)
    method_errors["sitemap"] = sm_errors

    # 2. Link-follow.
    lf_urls, lf_errors = _discover_link_follow(
        session,
        seed_urls=seed_urls,
        allowed_domains=allowed_domains,
        scope_prefixes=scope_prefixes,
        timeout_s=timeout_s,
    )
    url_sets["link_follow"] = set(lf_urls)
    method_errors["link_follow"] = lf_errors

    # 3. Nav extraction (optional).
    if enable_nav:
        nav_urls, nav_errors = _discover_nav(
            seed_urls=seed_urls,
            allowed_domains=list(allowed_domains),
            scope_prefixes=scope_prefixes,
            timeout_s=timeout_s,
        )
        url_sets["nav_extraction"] = set(nav_urls)
        method_errors["nav_extraction"] = nav_errors

    # 4. Wayback (optional).
    if enable_wayback:
        wb_urls, wb_errors = _discover_wayback(
            session,
            allowed_domains=list(allowed_domains),
            scope_prefixes=scope_prefixes,
            timeout_s=timeout_s,
        )
        url_sets["wayback"] = set(wb_urls)
        method_errors["wayback"] = wb_errors

    # Union all URLs with provenance tracking.
    all_urls: dict[str, set[str]] = {}  # url -> set of methods
    first_seen: dict[str, str] = {}     # url -> first method

    # Process methods in deterministic order.
    for method in ("sitemap", "link_follow", "nav_extraction", "wayback"):
        if method not in url_sets:
            continue
        for u in url_sets[method]:
            if u not in all_urls:
                all_urls[u] = set()
                first_seen[u] = method
            all_urls[u].add(method)

    # Build result list.
    discovered = [
        DiscoveredUrl(
            url=u,
            sources=frozenset(methods),
            first_seen_via=first_seen[u],
        )
        for u, methods in sorted(all_urls.items())
    ]

    method_counts = {m: len(s) for m, s in url_sets.items()}

    intersection_count = sum(1 for d in discovered if len(d.sources) >= 2)
    single_source_count = sum(1 for d in discovered if len(d.sources) == 1)

    # Get store URL count for self-check.
    store_url_count = 0
    if docs_dir:
        try:
            db_path = require_store_db(docs_dir)
            conn = open_db(db_path)
            try:
                for domain in allowed_domains:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM pages WHERE domain = ? OR domain LIKE ?",
                        (domain, f"%.{domain}"),
                    ).fetchone()
                    store_url_count += int(row[0])
            finally:
                conn.close()
        except Exception:
            pass

    warnings = _self_check(
        method_counts=method_counts,
        total_urls=len(discovered),
        intersection_count=intersection_count,
        single_source_count=single_source_count,
        store_url_count=store_url_count,
    )

    return DiscoveryResult(
        exchange_id=exchange_id,
        section_id=section_id,
        urls=discovered,
        method_counts=method_counts,
        intersection_count=intersection_count,
        single_source_count=single_source_count,
        rejected_urls=all_rejected,
        method_errors=method_errors,
        warnings=warnings,
    )
