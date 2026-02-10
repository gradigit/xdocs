from __future__ import annotations

from urllib.parse import urlsplit


def url_host(url: str) -> str:
    """Extract the lowercase hostname from a URL."""
    return (urlsplit(url).hostname or "").lower()
