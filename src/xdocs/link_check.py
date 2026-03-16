"""Stored page URL reachability checks (HEAD requests, read-only)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from .db import open_db
from .store import require_store_db
from .timeutil import now_iso_utc

logger = logging.getLogger(__name__)

# Per-domain rate limiting state.
_domain_last_request: dict[str, float] = {}
_domain_locks: dict[str, Lock] = {}
_global_lock = Lock()


def _get_domain_lock(domain: str) -> Lock:
    """Get or create a per-domain lock (thread-safe)."""
    with _global_lock:
        if domain not in _domain_locks:
            _domain_locks[domain] = Lock()
        return _domain_locks[domain]


def _wait_for_domain(domain: str, delay_s: float) -> None:
    """Enforce per-domain rate limiting."""
    lock = _get_domain_lock(domain)
    with lock:
        last = _domain_last_request.get(domain, 0.0)
        now = time.monotonic()
        wait = delay_s - (now - last)
        if wait > 0:
            time.sleep(wait)
        _domain_last_request[domain] = time.monotonic()


@dataclass(frozen=True, slots=True)
class LinkCheckResult:
    url: str
    http_status: int | None
    error: str | None
    redirect_url: str | None
    response_time_ms: float


@dataclass(frozen=True, slots=True)
class LinkCheckReport:
    checked: int
    ok: int
    redirect: int
    client_error: int
    server_error: int
    network_error: int
    results: list[LinkCheckResult]  # Only non-2xx
    checked_at: str


def _make_result(
    url: str, t0: float, *, http_status: int | None = None,
    error: str | None = None, redirect_url: str | None = None,
) -> LinkCheckResult:
    return LinkCheckResult(
        url=url, http_status=http_status, error=error,
        redirect_url=redirect_url,
        response_time_ms=round((time.monotonic() - t0) * 1000, 1),
    )


def _check_one_url(url: str, *, timeout_s: float, delay_s: float) -> LinkCheckResult:
    """HEAD a single URL with GET fallback on 405."""
    import urllib.request
    import urllib.error

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return LinkCheckResult(
            url=url, http_status=None,
            error=f"Skipped non-HTTP scheme: {parsed.scheme}",
            redirect_url=None, response_time_ms=0.0,
        )

    domain = parsed.netloc
    _wait_for_domain(domain, delay_s)

    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "xdocs-link-checker/1.0")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            redirect_url = resp.url if resp.url != url else None
            return _make_result(url, t0, http_status=resp.status, redirect_url=redirect_url)
    except urllib.error.HTTPError as e:
        if e.code == 405:
            # HEAD not allowed — retry with GET.
            try:
                req2 = urllib.request.Request(url, method="GET")
                req2.add_header("User-Agent", "xdocs-link-checker/1.0")
                with urllib.request.urlopen(req2, timeout=timeout_s) as resp2:
                    redirect_url2 = resp2.url if resp2.url != url else None
                    return _make_result(url, t0, http_status=resp2.status, redirect_url=redirect_url2)
            except urllib.error.HTTPError as e2:
                return _make_result(url, t0, http_status=e2.code, error=str(e2.reason))
            except Exception as e2:
                return _make_result(url, t0, error=f"{type(e2).__name__}: {e2}")
        return _make_result(url, t0, http_status=e.code, error=str(e.reason))
    except Exception as e:
        return _make_result(url, t0, error=f"{type(e).__name__}: {e}")


def check_stored_links(
    *,
    docs_dir: str,
    exchange: str | None = None,
    sample: int = 0,
    timeout_s: float = 10.0,
    concurrency: int = 4,
    delay_s: float = 0.5,
) -> LinkCheckReport:
    """Check reachability of stored page URLs via HEAD requests.

    Read-only — no store modifications.

    Args:
        docs_dir: Path to the cex-docs store directory.
        exchange: Optional filter by exchange domain pattern.
        sample: If > 0, randomly sample this many URLs.
        timeout_s: HTTP timeout per request.
        concurrency: Max concurrent workers.
        delay_s: Per-domain rate limiting delay.

    Returns:
        LinkCheckReport with aggregate counts and non-2xx results.
    """
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        sql = "SELECT canonical_url FROM pages WHERE canonical_url IS NOT NULL"
        params: list[Any] = []
        if exchange:
            sql += " AND domain LIKE ?"
            params.append(f"%{exchange}%")
        if sample > 0:
            sql += " ORDER BY RANDOM() LIMIT ?"
            params.append(sample)
        else:
            sql += " ORDER BY canonical_url"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    urls = [row["canonical_url"] for row in rows]
    if not urls:
        return LinkCheckReport(
            checked=0, ok=0, redirect=0, client_error=0,
            server_error=0, network_error=0, results=[], checked_at=now_iso_utc(),
        )

    logger.info("Checking %d stored page URLs (concurrency=%d)...", len(urls), concurrency)

    all_results: list[LinkCheckResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_check_one_url, url, timeout_s=timeout_s, delay_s=delay_s): url
            for url in urls
        }
        for future in as_completed(futures):
            all_results.append(future.result())

    ok = 0
    redirect = 0
    client_error = 0
    server_error = 0
    network_error = 0
    non_ok: list[LinkCheckResult] = []

    for r in all_results:
        if r.http_status is None:
            network_error += 1
            non_ok.append(r)
        elif 200 <= r.http_status < 300:
            if r.redirect_url:
                # urlopen followed redirects transparently — final status is 2xx
                # but URL changed, so this is a redirect.
                redirect += 1
                non_ok.append(r)
            else:
                ok += 1
        elif 400 <= r.http_status < 500:
            client_error += 1
            non_ok.append(r)
        else:
            server_error += 1
            non_ok.append(r)

    return LinkCheckReport(
        checked=len(all_results),
        ok=ok,
        redirect=redirect,
        client_error=client_error,
        server_error=server_error,
        network_error=network_error,
        results=non_ok,
        checked_at=now_iso_utc(),
    )
