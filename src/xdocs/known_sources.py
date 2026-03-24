"""Validate known_sources URLs in the exchange registry.

Content-aware validation: checks not just HTTP reachability but that the response
matches the expected format for the source type (e.g., llms.txt must not be HTML).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .httpfetch import create_session
from .registry import KnownSources, Registry
from .url_sanitize import sanitize_url

_log = logging.getLogger(__name__)

# Source types where HTML response is a definitive SPA shell indicator.
_TEXT_ONLY_SOURCES = frozenset({"llms_txt", "llms_full_txt"})

# Source types where response should be XML.
_XML_SOURCES = frozenset({"rss_feed"})


@dataclass(frozen=True, slots=True)
class SourceCheckResult:
    source_type: str
    url: str
    ok: bool
    http_status: int | None
    final_url: str | None
    content_type: str | None
    is_html: bool
    word_count: int
    error: str | None
    reason: str  # ok, http_404, spa_shell, not_xml, redirect, network_error, empty_response


def _is_html_response(body: str, content_type: str | None) -> bool:
    """Detect if a response is HTML (SPA shell indicator for text-only sources)."""
    if content_type and "text/html" in content_type.lower():
        return True
    stripped = body.lstrip("\ufeff \t\r\n")  # strip BOM + whitespace
    lower = stripped[:100].lower()
    return lower.startswith("<!doctype") or lower.startswith("<html")


def _is_xml_response(body: str, content_type: str | None) -> bool:
    """Detect if a response is XML (for RSS/Atom feeds)."""
    if content_type:
        ct = content_type.lower()
        if "xml" in ct or "rss" in ct or "atom" in ct:
            return True
    stripped = body.lstrip("\ufeff \t\r\n")
    lower = stripped[:100].lower()
    return lower.startswith("<?xml") or lower.startswith("<rss") or lower.startswith("<feed")


def _check_one(
    session: Any,
    source_type: str,
    url: str,
    timeout_s: float,
) -> SourceCheckResult:
    """Validate a single known-source URL."""
    # URL format check.
    san = sanitize_url(url)
    if not san.accepted:
        return SourceCheckResult(
            source_type=source_type, url=url, ok=False, http_status=None,
            final_url=None, content_type=None, is_html=False, word_count=0,
            error=f"URL rejected: {san.reason}", reason=f"bad_url:{san.reason}",
        )

    try:
        resp = session.get(url, timeout=timeout_s, allow_redirects=True)
    except Exception as exc:
        return SourceCheckResult(
            source_type=source_type, url=url, ok=False, http_status=None,
            final_url=None, content_type=None, is_html=False, word_count=0,
            error=str(exc)[:200], reason="network_error",
        )

    status = resp.status_code
    ct = resp.headers.get("content-type")
    body = resp.text or ""
    final_url = str(resp.url) if str(resp.url) != url else None
    is_html = _is_html_response(body, ct)
    wc = len(body.split())

    # HTTP error.
    if status >= 400:
        return SourceCheckResult(
            source_type=source_type, url=url, ok=False, http_status=status,
            final_url=final_url, content_type=ct, is_html=is_html, word_count=wc,
            error=None, reason=f"http_{status}",
        )

    # SPA shell detection for text-only sources.
    if source_type in _TEXT_ONLY_SOURCES and is_html:
        return SourceCheckResult(
            source_type=source_type, url=url, ok=False, http_status=status,
            final_url=final_url, content_type=ct, is_html=True, word_count=wc,
            error="Response is HTML, not plain text — likely SPA shell",
            reason="spa_shell",
        )

    # XML format check for RSS/Atom.
    if source_type in _XML_SOURCES and not _is_xml_response(body, ct):
        return SourceCheckResult(
            source_type=source_type, url=url, ok=False, http_status=status,
            final_url=final_url, content_type=ct, is_html=is_html, word_count=wc,
            error="Response is not XML — expected RSS/Atom feed",
            reason="not_xml",
        )

    # Empty response.
    if wc == 0:
        return SourceCheckResult(
            source_type=source_type, url=url, ok=False, http_status=status,
            final_url=final_url, content_type=ct, is_html=is_html, word_count=0,
            error="Empty response body", reason="empty_response",
        )

    # Redirect (informational, still ok).
    reason = "redirect" if final_url else "ok"

    return SourceCheckResult(
        source_type=source_type, url=url, ok=True, http_status=status,
        final_url=final_url, content_type=ct, is_html=is_html, word_count=wc,
        error=None, reason=reason,
    )


def validate_known_sources(
    *,
    registry: Registry,
    exchange_id: str | None = None,
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    """Validate all known_sources URLs for one or all exchanges.

    Returns machine-readable JSON-compatible dict with per-URL results.
    """
    session = create_session()
    exchanges = (
        [registry.get_exchange(exchange_id)] if exchange_id
        else registry.exchanges
    )

    all_results: list[dict[str, Any]] = []
    total = 0
    passed = 0
    failed = 0

    for ex in exchanges:
        urls = ex.known_sources.all_urls()
        if not urls:
            continue

        ex_results: list[dict[str, Any]] = []
        for source_type, url in urls.items():
            total += 1
            result = _check_one(session, source_type, url, timeout_s)
            if result.ok:
                passed += 1
            else:
                failed += 1
            ex_results.append({
                "source_type": result.source_type,
                "url": result.url,
                "ok": result.ok,
                "http_status": result.http_status,
                "final_url": result.final_url,
                "content_type": result.content_type,
                "is_html": result.is_html,
                "word_count": result.word_count,
                "error": result.error,
                "reason": result.reason,
            })

        all_results.append({
            "exchange_id": ex.exchange_id,
            "results": ex_results,
        })

    return {
        "ok": failed == 0,
        "total": total,
        "passed": passed,
        "failed": failed,
        "exchanges": all_results,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
