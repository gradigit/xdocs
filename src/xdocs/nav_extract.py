from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .url_sanitize import sanitize_url
from .urlutil import url_host as _host

log = logging.getLogger(__name__)

# CSS selectors targeting typical doc site navigation elements.
NAV_SELECTORS = [
    "nav a[href]",
    "aside a[href]",
    '[role="navigation"] a[href]',
    ".sidebar a[href]",
    ".toc a[href]",
    ".docs-nav a[href]",
    ".menu a[href]",
    ".docusaurus-sidebar a[href]",
    ".api-sidebar a[href]",
    ".doc-sidebar a[href]",
]

# Combined selector for both JS execution and BeautifulSoup.
_COMBINED_SELECTOR = ", ".join(NAV_SELECTORS)

# Browser-like UA for HTTP fallback (same as httpfetch.py).
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class NavNode:
    """A single navigation link extracted from a doc site."""
    url: str
    text: str
    depth: int  # nesting level in nav tree


@dataclass(frozen=True, slots=True)
class NavExtractionResult:
    """Result of extracting navigation URLs from a doc site."""
    seed_url: str
    urls: list[str]
    nav_nodes: list[NavNode]
    errors: list[dict[str, Any]]
    method: str  # "agent_browser" | "http_fallback"


def _run_agent_browser(
    args: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """Run agent-browser subprocess, capturing output."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _domain_allowed(url: str, allowed_domains: list[str]) -> bool:
    """Check whether url's host matches the allowed domains list."""
    h = _host(url)
    if not h:
        return False
    for d in allowed_domains:
        dd = d.lower()
        if h == dd or h.endswith("." + dd):
            return True
    return False


def _process_raw_links(
    raw_links: list[dict[str, str]],
    *,
    seed_url: str,
    allowed_domains: list[str],
) -> tuple[list[str], list[NavNode]]:
    """Resolve, sanitize, and filter raw extracted links.

    Returns (unique_urls, nav_nodes).
    """
    seen: set[str] = set()
    urls: list[str] = []
    nav_nodes: list[NavNode] = []

    for item in raw_links:
        href = (item.get("href") or "").strip()
        text = (item.get("text") or "").strip()
        depth = int(item.get("depth", 0))

        if not href:
            continue

        # Resolve relative URLs against the seed.
        resolved = urljoin(seed_url, href)

        # Only keep http(s) URLs.
        parts = urlsplit(resolved)
        if parts.scheme not in ("http", "https"):
            continue

        # Strip fragment — we only care about the page URL, not anchors.
        if parts.fragment:
            resolved = parts._replace(fragment="").geturl()

        # Sanitize.
        sr = sanitize_url(resolved)
        if not sr.accepted:
            continue

        # Filter by allowed domains.
        if allowed_domains and not _domain_allowed(resolved, allowed_domains):
            continue

        nav_nodes.append(NavNode(url=resolved, text=text, depth=depth))

        if resolved not in seen:
            seen.add(resolved)
            urls.append(resolved)

    return urls, nav_nodes


def _extract_via_agent_browser(
    *,
    seed_url: str,
    allowed_domains: list[str],
    timeout_s: float,
) -> NavExtractionResult:
    """Primary extraction: use agent-browser to render JS and query nav links."""
    bin_path = shutil.which("agent-browser")
    if bin_path is None:
        raise FileNotFoundError("agent-browser CLI not found on PATH")

    errors: list[dict[str, Any]] = []
    subprocess_timeout = timeout_s + 15

    # 1. Open / navigate to the URL.
    result = _run_agent_browser(
        [bin_path, "open", seed_url],
        timeout=subprocess_timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"agent-browser open failed: {result.stderr.strip()[:500]}")

    # 2. Wait for page load.
    _run_agent_browser(
        [bin_path, "wait", "--load", "networkidle"],
        timeout=subprocess_timeout,
    )

    # 3. Execute JS to extract nav links.
    # Build a JS expression that queries all nav selectors and returns JSON.
    js_code = (
        "JSON.stringify("
        "Array.from(document.querySelectorAll("
        f"'{_COMBINED_SELECTOR}'"
        ")).map(function(a) {"
        "  var depth = 0;"
        "  var el = a;"
        "  while (el.parentElement) {"
        "    if (el.parentElement.tagName === 'UL' || el.parentElement.tagName === 'OL') depth++;"
        "    el = el.parentElement;"
        "  }"
        "  return {href: a.getAttribute('href'), text: (a.textContent || '').trim(), depth: depth};"
        "}))"
    )

    eval_result = _run_agent_browser(
        [bin_path, "eval", js_code],
        timeout=subprocess_timeout,
    )

    if eval_result.returncode != 0:
        errors.append({
            "stage": "eval",
            "stderr": eval_result.stderr.strip()[:500],
        })
        return NavExtractionResult(
            seed_url=seed_url,
            urls=[],
            nav_nodes=[],
            errors=errors,
            method="agent_browser",
        )

    # 4. Parse the JSON output.
    try:
        raw_links = json.loads(eval_result.stdout.strip())
    except (json.JSONDecodeError, ValueError) as exc:
        errors.append({
            "stage": "json_parse",
            "error": str(exc),
            "stdout_preview": eval_result.stdout.strip()[:200],
        })
        return NavExtractionResult(
            seed_url=seed_url,
            urls=[],
            nav_nodes=[],
            errors=errors,
            method="agent_browser",
        )

    # 5. Close browser (best-effort).
    try:
        _run_agent_browser([bin_path, "close"], timeout=15)
    except Exception:
        pass

    urls, nav_nodes = _process_raw_links(
        raw_links,
        seed_url=seed_url,
        allowed_domains=allowed_domains,
    )

    return NavExtractionResult(
        seed_url=seed_url,
        urls=urls,
        nav_nodes=nav_nodes,
        errors=errors,
        method="agent_browser",
    )


def _extract_via_http(
    *,
    seed_url: str,
    allowed_domains: list[str],
    timeout_s: float,
) -> NavExtractionResult:
    """Fallback extraction: HTTP GET + BeautifulSoup with nav selectors."""
    errors: list[dict[str, Any]] = []

    try:
        resp = requests.get(
            seed_url,
            timeout=timeout_s,
            headers={"User-Agent": _BROWSER_UA},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        errors.append({
            "stage": "http_fetch",
            "error": f"{type(exc).__name__}: {exc}",
        })
        return NavExtractionResult(
            seed_url=seed_url,
            urls=[],
            nav_nodes=[],
            errors=errors,
            method="http_fallback",
        )

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    raw_links: list[dict[str, str]] = []
    for el in soup.select(_COMBINED_SELECTOR):
        href = el.get("href")
        if not href or not isinstance(href, str):
            continue

        # Compute nesting depth by counting ancestor UL/OL elements.
        depth = 0
        parent = el.parent
        while parent:
            if parent.name in ("ul", "ol"):
                depth += 1
            parent = parent.parent

        text = el.get_text(strip=True) or ""
        raw_links.append({"href": href, "text": text, "depth": str(depth)})

    urls, nav_nodes = _process_raw_links(
        raw_links,
        seed_url=seed_url,
        allowed_domains=allowed_domains,
    )

    return NavExtractionResult(
        seed_url=seed_url,
        urls=urls,
        nav_nodes=nav_nodes,
        errors=errors,
        method="http_fallback",
    )


def extract_nav_urls(
    *,
    seed_url: str,
    allowed_domains: list[str],
    timeout_s: float = 30.0,
) -> NavExtractionResult:
    """Extract navigation URLs from a doc site.

    Primary: agent-browser renders JS, runs DOM query for nav selectors.
    Fallback: HTTP fetch + BeautifulSoup parses same selectors from static HTML.
    """
    # Try agent-browser first.
    try:
        result = _extract_via_agent_browser(
            seed_url=seed_url,
            allowed_domains=allowed_domains,
            timeout_s=timeout_s,
        )
        if result.urls:
            return result
        # If agent-browser returned zero URLs (e.g. blank page, JS error),
        # fall through to HTTP fallback.
        log.info("agent-browser returned 0 URLs for %s, trying HTTP fallback", seed_url)
    except (FileNotFoundError, subprocess.TimeoutExpired, RuntimeError) as exc:
        log.info("agent-browser unavailable (%s), using HTTP fallback for %s", exc, seed_url)
    except Exception as exc:
        log.warning("agent-browser unexpected error (%s), using HTTP fallback for %s", exc, seed_url)

    # HTTP fallback.
    return _extract_via_http(
        seed_url=seed_url,
        allowed_domains=allowed_domains,
        timeout_s=timeout_s,
    )
