from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class SanitizeResult:
    url: str
    accepted: bool
    reason: str | None  # None if accepted; rejection reason if not


# Non-HTTP schemes to reject.
_BAD_SCHEMES = frozenset(("javascript", "mailto", "tel", "data", "ftp"))

# Template artifact patterns.
_TEMPLATE_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\$\{.*?\}")

# CDN / admin path segments to reject.
_CDN_ADMIN_SEGMENTS = ("/cdn-cgi/", "/wp-admin/")

# Non-doc resource extensions (lowercase, with leading dot).
_IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"))
_BINARY_EXTS = frozenset((".pdf", ".zip", ".tar", ".gz", ".exe", ".dmg", ".deb", ".rpm"))
_STATIC_EXTS = frozenset((".css", ".woff", ".woff2", ".ttf", ".eot"))
_JS_ASSET_EXTS = frozenset((".js", ".mjs", ".cjs"))
_RESOURCE_EXTS = _IMAGE_EXTS | _BINARY_EXTS | _STATIC_EXTS

# Paths that indicate a JS bundle/asset rather than a doc page.
# e.g. /assets/main.abc123.js, /static/chunk.js, /_next/static/...js
_JS_ASSET_PATH_RE = re.compile(
    r"(?:/assets/|/static/|/_next/|/dist/|/build/|/chunks?/|/bundle)",
    re.IGNORECASE,
)

# Control characters (C0 range excluding tab/lf/cr which are harmless in URLs).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_MAX_URL_LEN = 4096


def _path_ext(path: str) -> str:
    """Return lowercase extension from the URL path (ignoring query/fragment)."""
    # Strip query params that might be appended to the path.
    p = path.split("?", 1)[0].split("#", 1)[0]
    dot = p.rfind(".")
    if dot == -1:
        return ""
    return p[dot:].lower()


def sanitize_url(url: str) -> SanitizeResult:
    """Check a single URL and return acceptance/rejection with reason."""
    # Empty / whitespace-only.
    u = (url or "").strip()
    if not u:
        return SanitizeResult(url=url, accepted=False, reason="empty")

    # Fragment-only (e.g. "#section").
    if u.startswith("#"):
        return SanitizeResult(url=url, accepted=False, reason="fragment_only")

    # Control characters.
    if _CONTROL_RE.search(u):
        return SanitizeResult(url=url, accepted=False, reason="control_chars")

    # Length check.
    if len(u) > _MAX_URL_LEN:
        return SanitizeResult(url=url, accepted=False, reason="too_long")

    # Template artifacts.
    if _TEMPLATE_RE.search(u):
        return SanitizeResult(url=url, accepted=False, reason="template_artifact")

    # Parse the URL.
    try:
        parts = urlsplit(u)
    except Exception:
        return SanitizeResult(url=url, accepted=False, reason="unparseable")

    # Non-HTTP schemes.
    scheme = (parts.scheme or "").lower()
    if scheme in _BAD_SCHEMES:
        return SanitizeResult(url=url, accepted=False, reason=f"bad_scheme:{scheme}")

    # If there's a scheme but no hostname, reject (e.g. "http://").
    if scheme in ("http", "https") and not parts.hostname:
        return SanitizeResult(url=url, accepted=False, reason="no_hostname")

    path = parts.path or ""

    # CDN / admin paths.
    path_lower = path.lower()
    for seg in _CDN_ADMIN_SEGMENTS:
        if seg in path_lower:
            return SanitizeResult(url=url, accepted=False, reason=f"cdn_admin_path:{seg.strip('/')}")

    # Non-doc resource extensions.
    ext = _path_ext(path)
    if ext in _RESOURCE_EXTS:
        return SanitizeResult(url=url, accepted=False, reason=f"resource_ext:{ext}")

    # JS bundle/asset paths (only reject .js/.mjs/.cjs when the path looks like an asset).
    if ext in _JS_ASSET_EXTS and _JS_ASSET_PATH_RE.search(path_lower):
        return SanitizeResult(url=url, accepted=False, reason=f"js_asset:{ext}")

    return SanitizeResult(url=url, accepted=True, reason=None)


def sanitize_urls(urls: list[str]) -> tuple[list[str], list[SanitizeResult]]:
    """Sanitize a list of URLs. Returns (accepted_urls, all_results)."""
    accepted: list[str] = []
    results: list[SanitizeResult] = []
    for u in urls:
        r = sanitize_url(u)
        results.append(r)
        if r.accepted:
            accepted.append(r.url)
    return accepted, results
