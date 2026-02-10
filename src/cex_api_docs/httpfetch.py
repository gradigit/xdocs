from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

from .errors import CexApiDocsError
from .robots import USER_AGENT


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    final_url: str
    redirect_chain: list[str]
    http_status: int
    content_type: str
    headers: dict[str, str]
    body: bytes


def _selected_headers(resp: requests.Response) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in ("etag", "last-modified", "cache-control", "content-length"):
        v = resp.headers.get(k)
        if v is not None:
            out[k] = v
    return out


def _is_http_url(url: str) -> bool:
    s = urlsplit(url)
    return s.scheme in ("http", "https")


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _host_allowed(host: str, allowed_domains: set[str]) -> bool:
    # Allow exact match, or subdomain match when the registry lists a parent domain.
    host = host.lower()
    for d in allowed_domains:
        dd = d.lower()
        if host == dd or host.endswith("." + dd):
            return True
    return False


def fetch(
    session: requests.Session,
    *,
    url: str,
    timeout_s: float,
    max_bytes: int,
    max_redirects: int,
    retries: int,
    allowed_domains: set[str] | None = None,
) -> FetchResult:
    if not _is_http_url(url):
        raise CexApiDocsError(code="EBADURL", message="Only http/https URLs are supported.", details={"url": url})

    attempt = 0
    while True:
        try:
            redirect_chain: list[str] = []
            seen: set[str] = set()
            current_url = url

            # Strict redirect policy: validate each hop before following.
            redirects_followed = 0
            while True:
                if allowed_domains is not None:
                    h = _host(current_url)
                    if not _host_allowed(h, allowed_domains):
                        raise CexApiDocsError(
                            code="EDOMAIN",
                            message="URL host is outside allowed domain scope.",
                            details={"url": current_url, "host": h, "allowed_domains": sorted(allowed_domains)},
                        )

                # Avoid infinite loops even if max_redirects is large.
                if current_url in seen:
                    raise CexApiDocsError(
                        code="EREDIRECT",
                        message="Redirect loop detected.",
                        details={"url": url, "loop_at": current_url, "redirect_chain": redirect_chain},
                    )
                seen.add(current_url)

                resp = session.get(
                    current_url,
                    timeout=timeout_s,
                    allow_redirects=False,
                    stream=True,
                    headers={"User-Agent": USER_AGENT},
                )

                status = int(resp.status_code)
                if status in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                    if redirects_followed >= int(max_redirects):
                        try:
                            resp.close()
                        except Exception:
                            pass
                        raise CexApiDocsError(
                            code="EREDIRECT",
                            message="Too many redirects.",
                            details={"url": url, "max_redirects": max_redirects, "redirect_chain": redirect_chain},
                        )

                    location = str(resp.headers.get("location", ""))
                    next_url = urljoin(current_url, location)

                    # Validate the redirect target before following.
                    if not _is_http_url(next_url):
                        try:
                            resp.close()
                        except Exception:
                            pass
                        raise CexApiDocsError(
                            code="EREDIRECT",
                            message="Redirect target scheme is not supported.",
                            details={"url": current_url, "location": location, "next_url": next_url},
                        )

                    if allowed_domains is not None:
                        nh = _host(next_url)
                        if not _host_allowed(nh, allowed_domains):
                            try:
                                resp.close()
                            except Exception:
                                pass
                            raise CexApiDocsError(
                                code="EDOMAIN",
                                message="Redirect target host is outside allowed domain scope.",
                                details={
                                    "url": current_url,
                                    "location": location,
                                    "next_url": next_url,
                                    "next_host": nh,
                                    "allowed_domains": sorted(allowed_domains),
                                },
                            )

                    redirect_chain.append(current_url)
                    redirects_followed += 1
                    try:
                        resp.close()
                    except Exception:
                        pass
                    current_url = next_url
                    continue

                # Terminal response (or a redirect without location).
                break

        except CexApiDocsError:
            raise
        except Exception as e:
            if attempt < retries:
                backoff = (2**attempt) + random.random() * 0.25
                time.sleep(backoff)
                attempt += 1
                continue
            raise CexApiDocsError(
                code="ENET",
                message="Network error fetching URL.",
                details={"url": url, "error": f"{type(e).__name__}: {e}"},
            ) from e

        try:
            status = int(resp.status_code)
            if status == 429 or status >= 500:
                if attempt < retries:
                    backoff = (2**attempt) + random.random() * 0.25
                    time.sleep(backoff)
                    attempt += 1
                    continue

            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise CexApiDocsError(
                        code="ETOOBIG",
                        message="Response exceeded max_bytes limit.",
                        details={"url": url, "max_bytes": max_bytes, "received_bytes": total},
                    )

            body = b"".join(chunks)

            content_type = resp.headers.get("content-type", "") or ""
            return FetchResult(
                url=url,
                final_url=str(resp.url),
                redirect_chain=redirect_chain,
                http_status=status,
                content_type=content_type,
                headers=_selected_headers(resp),
                body=body,
            )
        finally:
            try:
                resp.close()
            except Exception:
                pass
