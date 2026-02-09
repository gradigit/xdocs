from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

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


def fetch(
    session: requests.Session,
    *,
    url: str,
    timeout_s: float,
    max_bytes: int,
    max_redirects: int,
    retries: int,
) -> FetchResult:
    session.max_redirects = int(max_redirects)
    attempt = 0
    while True:
        try:
            resp = session.get(
                url,
                timeout=timeout_s,
                allow_redirects=True,
                stream=True,
                headers={"User-Agent": USER_AGENT},
            )
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
                final_url=resp.url,
                redirect_chain=[h.url for h in resp.history],
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
