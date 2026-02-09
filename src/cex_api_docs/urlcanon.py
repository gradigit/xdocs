from __future__ import annotations

import posixpath
from urllib.parse import SplitResult, urlsplit, urlunsplit


def canonicalize_url(url: str) -> str:
    """
    Canonicalize URL per plan:
    - lowercase scheme + host
    - remove default ports (:80 http, :443 https)
    - remove fragment
    - normalize path dot segments; preserve trailing slash if present (except root)
    - preserve query exactly as received
    """
    parsed = urlsplit(url)
    scheme = (parsed.scheme or "https").lower()

    host = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port
    netloc = host
    if port:
        is_default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        if not is_default:
            netloc = f"{host}:{port}"

    raw_path = parsed.path or "/"
    preserve_trailing_slash = raw_path.endswith("/") and raw_path != "/"
    norm = posixpath.normpath(raw_path)
    if norm == ".":
        norm = "/"
    if not norm.startswith("/"):
        norm = "/" + norm
    if preserve_trailing_slash and norm != "/" and not norm.endswith("/"):
        norm += "/"

    # Preserve query exactly; params are not used with modern URLs.
    recomposed = SplitResult(scheme=scheme, netloc=netloc, path=norm, query=parsed.query, fragment="")
    return urlunsplit(recomposed)

