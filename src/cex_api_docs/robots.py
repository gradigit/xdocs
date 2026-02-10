from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .timeutil import now_iso_utc


USER_AGENT = "cex-api-docs"

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    policy: str  # allow_all|disallow_all|parsed
    robots_url: str
    fetched_at: str
    http_status: int | None
    error: str | None


def fetch_robots_policy(session: requests.Session, *, url: str, timeout_s: float) -> tuple[Callable[[str], bool], RobotsDecision]:
    """
    RFC9309-aligned error posture:
    - 2xx: parse and apply
    - 4xx: allow
    - 5xx/network error/timeout: disallow
    """
    parsed = urlsplit(url)
    scheme = parsed.scheme or "https"
    host = parsed.hostname or ""
    port = parsed.port
    netloc = host
    if port:
        is_default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        if not is_default:
            netloc = f"{host}:{port}"
    robots_url = f"{scheme}://{netloc}/robots.txt"

    fetched_at = now_iso_utc()
    try:
        resp = session.get(robots_url, timeout=timeout_s, headers={"User-Agent": USER_AGENT})
        # Some sites return 403 for certain UA strings; retry with other common UAs.
        if int(resp.status_code) == 403:
            try:
                resp.close()
            except Exception:
                pass
            resp = session.get(robots_url, timeout=timeout_s)
        if int(resp.status_code) == 403:
            try:
                resp.close()
            except Exception:
                pass
            resp = session.get(robots_url, timeout=timeout_s, headers={"User-Agent": _BROWSER_UA})
    except Exception as e:
        return (lambda _u: False), RobotsDecision(
            policy="disallow_all",
            robots_url=robots_url,
            fetched_at=fetched_at,
            http_status=None,
            error=f"{type(e).__name__}: {e}",
        )

    status = int(resp.status_code)
    if 200 <= status < 300:
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())

        def can_fetch(u: str) -> bool:
            return bool(rp.can_fetch(USER_AGENT, u))

        return can_fetch, RobotsDecision(
            policy="parsed",
            robots_url=robots_url,
            fetched_at=fetched_at,
            http_status=status,
            error=None,
        )

    if 400 <= status < 500:
        return (lambda _u: True), RobotsDecision(
            policy="allow_all",
            robots_url=robots_url,
            fetched_at=fetched_at,
            http_status=status,
            error=None,
        )

    return (lambda _u: False), RobotsDecision(
        policy="disallow_all",
        robots_url=robots_url,
        fetched_at=fetched_at,
        http_status=status,
        error=None,
    )
