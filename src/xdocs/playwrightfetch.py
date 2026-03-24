from __future__ import annotations

import ipaddress
import random
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .errors import XDocsError
from .httpfetch import FetchResult, _host_allowed, _is_http_url
from .urlutil import url_host as _host


def _is_localhostish(host: str) -> bool:
    host = (host or "").strip().lower()
    return host == "localhost" or host.endswith(".localhost")


def _is_public_ip_literal(host: str) -> bool:
    """
    Return True only for globally-routable IP literals.

    This blocks loopback/private/link-local/reserved/multicast/unspecified ranges.
    """
    try:
        ip = ipaddress.ip_address(host)
    except Exception:
        return False
    return bool(ip.is_global)


def _resolves_to_non_public_ip(host: str) -> bool:
    """
    Best-effort DNS rebinding defense for subresource requests.

    If a hostname resolves to any non-global IP, treat it as unsafe.
    If resolution fails, treat it as unsafe (conservative).
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return True

    for info in infos:
        try:
            addr = info[4][0]
        except Exception:
            continue
        try:
            ip = ipaddress.ip_address(addr)
        except Exception:
            continue
        if not ip.is_global:
            return True
    return False


def _try_import_playwright_sync():
    try:
        from playwright.sync_api import Error as PlaywrightError  # type: ignore
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:  # pragma: no cover
        raise XDocsError(
            code="ENOPLAYWRIGHT",
            message="Playwright is not installed. Install optional deps: `pip install -e '.[playwright]'` and then run `python -m playwright install chromium`.",
            details={"error": f"{type(e).__name__}: {e}"},
        ) from e
    return sync_playwright, PlaywrightError, PlaywrightTimeoutError


@dataclass(slots=True)
class PlaywrightFetcher:
    """
    Single-browser Playwright fetcher for JS-rendered docs.

    Safety posture:
    - only enforce allowed_domains on top-level navigations (document requests)
    - allow subresource requests (scripts/css/images) so docs can render
    """

    allowed_domains: set[str]
    headless: bool = True  # Headless for server environments; headed mode requires display server (xvfb or native)

    _sync_playwright: Any = field(init=False, default=None, repr=False)
    _PlaywrightError: Any = field(init=False, default=None, repr=False)
    _PlaywrightTimeoutError: Any = field(init=False, default=None, repr=False)
    _pw: Any = field(init=False, default=None, repr=False)
    _browser: Any = field(init=False, default=None, repr=False)
    _context: Any = field(init=False, default=None, repr=False)

    def open(self) -> "PlaywrightFetcher":
        sync_playwright, _PlaywrightError, _PlaywrightTimeoutError = _try_import_playwright_sync()
        self._sync_playwright = sync_playwright
        self._PlaywrightError = _PlaywrightError
        self._PlaywrightTimeoutError = _PlaywrightTimeoutError

        self._pw = self._sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=bool(self.headless))
        # Use default Chromium UA; some doc sites block obvious bot UA strings.
        self._context = self._browser.new_context()
        return self

    def close(self) -> None:
        for obj in (self._context, self._browser):
            if obj is None:
                continue
            try:
                obj.close()
            except Exception:
                pass
        self._context = None
        self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._pw = None

    def __enter__(self) -> "PlaywrightFetcher":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def fetch(
        self,
        *,
        url: str,
        timeout_s: float,
        max_bytes: int,
        retries: int,
        wait_for_text_min: int = 100,
        wait_for_text_s: float = 15.0,
    ) -> FetchResult:
        if not _is_http_url(url):
            raise XDocsError(code="EBADURL", message="Only http/https URLs are supported.", details={"url": url})
        if self._context is None:
            raise XDocsError(code="EPLAYWRIGHT", message="Playwright fetcher not initialized.")

        attempt = 0
        while True:
            page = None
            try:
                page = self._context.new_page()
                page.set_default_navigation_timeout(int(timeout_s * 1000))
                page.set_default_timeout(int(timeout_s * 1000))

                nav_chain: list[str] = []
                host_safety_cache: dict[str, bool] = {}

                def _on_frame_nav(frame) -> None:  # pragma: no cover (timing-sensitive)
                    try:
                        if frame == page.main_frame:
                            u = frame.url
                            if u and _is_http_url(u):
                                nav_chain.append(u)
                    except Exception:
                        pass

                page.on("framenavigated", _on_frame_nav)

                def _host_is_safe(h: str) -> bool:
                    h = (h or "").lower()
                    if not h:
                        return True
                    if _is_localhostish(h):
                        return False
                    # IP literal: block anything not globally routable.
                    try:
                        ipaddress.ip_address(h)
                        return _is_public_ip_literal(h)
                    except Exception:
                        pass
                    if h in host_safety_cache:
                        return host_safety_cache[h]
                    ok = not _resolves_to_non_public_ip(h)
                    host_safety_cache[h] = bool(ok)
                    return bool(ok)

                def _route(route, request) -> None:  # pragma: no cover (timing-sensitive)
                    try:
                        # SSRF hardening: block localhost/private/link-local destinations for all requests.
                        # Do not block non-network schemes (data/blob/about) which have no host.
                        req_host = _host(request.url)
                        if req_host and not _host_is_safe(req_host):
                            route.abort()
                            return

                        if request.is_navigation_request():
                            h = _host(request.url)
                            if not _host_allowed(h, self.allowed_domains):
                                route.abort()
                                return
                        route.continue_()
                    except Exception:
                        try:
                            route.abort()
                        except Exception:
                            pass

                page.route("**/*", _route)

                # Some SPA doc sites never reliably fire domcontentloaded (or take too long).
                # Use the earliest stable signal and rely on our own readiness wait.
                resp = page.goto(url, wait_until="commit")
                if resp is None:
                    raise XDocsError(code="ENET", message="No response for navigation.", details={"url": url})

                status = int(resp.status)
                headers = resp.headers or {}
                content_type = str(headers.get("content-type") or "text/html; charset=utf-8")

                # Best-effort readiness: wait for some visible text.
                deadline = time.monotonic() + float(wait_for_text_s)
                while time.monotonic() < deadline:
                    try:
                        n = page.evaluate("() => document.body ? (document.body.innerText || '').length : 0")
                        if isinstance(n, (int, float)) and int(n) >= int(wait_for_text_min):
                            break
                    except Exception:
                        break
                    time.sleep(0.25)

                html = page.content()
                body = html.encode("utf-8", errors="replace")
                if len(body) > int(max_bytes):
                    raise XDocsError(
                        code="ETOOBIG",
                        message="Rendered HTML exceeded max_bytes limit.",
                        details={"url": url, "max_bytes": max_bytes, "received_bytes": len(body)},
                    )

                final_url = page.url or url
                redirect_chain: list[str] = []
                if nav_chain:
                    # Include intermediate navigations; exclude final_url itself when possible.
                    if nav_chain[-1] == final_url:
                        redirect_chain = nav_chain[:-1]
                    else:
                        redirect_chain = nav_chain

                # Enforce final host allowlist.
                fh = _host(final_url)
                if not _host_allowed(fh, self.allowed_domains):
                    raise XDocsError(
                        code="EDOMAIN",
                        message="Final URL host is outside allowed domain scope.",
                        details={"url": url, "final_url": final_url, "final_host": fh, "allowed_domains": sorted(self.allowed_domains)},
                    )

                return FetchResult(
                    url=url,
                    final_url=final_url,
                    redirect_chain=redirect_chain,
                    http_status=status,
                    content_type=content_type,
                    headers=_selected_headers_from_dict(headers),
                    body=body,
                )
            except XDocsError:
                raise
            except self._PlaywrightTimeoutError as e:
                if attempt < retries:
                    backoff = (2**attempt) + random.random() * 0.25
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise XDocsError(
                    code="ETIMEOUT",
                    message="Timeout rendering URL with Playwright.",
                    details={"url": url, "timeout_s": timeout_s, "error": str(e)},
                ) from e
            except self._PlaywrightError as e:
                if attempt < retries:
                    backoff = (2**attempt) + random.random() * 0.25
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise XDocsError(
                    code="ENET",
                    message="Playwright error rendering URL.",
                    details={"url": url, "error": str(e)},
                ) from e
            except Exception as e:  # pragma: no cover
                if attempt < retries:
                    backoff = (2**attempt) + random.random() * 0.25
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise XDocsError(
                    code="EPLAYWRIGHT",
                    message="Unexpected Playwright render failure.",
                    details={"url": url, "error": f"{type(e).__name__}: {e}"},
                ) from e
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass


def _selected_headers_from_dict(headers: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in ("etag", "last-modified", "cache-control", "content-length"):
        v = headers.get(k)
        if v is not None:
            out[k] = str(v)
    return out
