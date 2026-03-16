from __future__ import annotations

import random
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .errors import XDocsError
from .httpfetch import FetchResult, _host_allowed, _is_http_url
from .urlutil import url_host as _host


def _run(
    args: list[str],
    *,
    timeout: float,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run agent-browser subprocess, capturing output."""
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise XDocsError(
            code="ETIMEOUT",
            message="agent-browser command timed out.",
            details={"args": args, "timeout": timeout},
        ) from e
    except FileNotFoundError as e:
        raise XDocsError(
            code="ENOAGENTBROWSER",
            message="agent-browser CLI not found on PATH.",
            details={"error": str(e)},
        ) from e


@dataclass(slots=True)
class AgentBrowserFetcher:
    """
    JS-rendering fetcher using the agent-browser CLI.

    Same interface as PlaywrightFetcher: open(), fetch(), close().
    Uses subprocess calls per command (open, wait, get url, get html).
    """

    allowed_domains: set[str]

    _bin: str | None = field(init=False, default=None, repr=False)
    _open: bool = field(init=False, default=False, repr=False)

    def open(self) -> "AgentBrowserFetcher":
        bin_path = shutil.which("agent-browser")
        if bin_path is None:
            raise XDocsError(
                code="ENOAGENTBROWSER",
                message="agent-browser CLI not found on PATH.",
            )
        self._bin = bin_path
        # Start a session by navigating to about:blank.
        _run([self._bin, "open", "about:blank"], timeout=30)
        self._open = True
        return self

    def close(self) -> None:
        if self._open and self._bin:
            try:
                _run([self._bin, "close"], timeout=15, check=False)
            except Exception:
                pass
        self._open = False

    def __enter__(self) -> "AgentBrowserFetcher":
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
        scroll_full_page: bool = False,
        expand_accordions: bool = False,
    ) -> FetchResult:
        if not _is_http_url(url):
            raise XDocsError(
                code="EBADURL",
                message="Only http/https URLs are supported.",
                details={"url": url},
            )
        if not self._open or not self._bin:
            raise XDocsError(
                code="ENOAGENTBROWSER",
                message="AgentBrowserFetcher not initialized. Call open() first.",
            )

        attempt = 0
        subprocess_timeout = timeout_s + 15
        while True:
            try:
                return self._fetch_once(
                    url=url,
                    timeout_s=timeout_s,
                    max_bytes=max_bytes,
                    subprocess_timeout=subprocess_timeout,
                    wait_for_text_min=wait_for_text_min,
                    wait_for_text_s=wait_for_text_s,
                    scroll_full_page=scroll_full_page,
                    expand_accordions=expand_accordions,
                )
            except XDocsError:
                raise
            except Exception as e:
                if attempt < retries:
                    backoff = (2 ** attempt) + random.random() * 0.25
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise XDocsError(
                    code="ENET",
                    message="agent-browser render failure.",
                    details={"url": url, "error": f"{type(e).__name__}: {e}"},
                ) from e

    def _scroll_full_page(self, subprocess_timeout: float) -> None:
        """Scroll page by window.innerHeight increments to trigger lazy-loaded content.

        Checks document.documentElement.scrollHeight stability for 3 consecutive
        iterations before stopping.
        """
        assert self._bin is not None
        stable_count = 0
        last_height = -1
        max_iterations = 50  # Safety limit

        for _ in range(max_iterations):
            # Scroll down by one viewport height
            _run(
                [self._bin, "eval", "window.scrollBy(0, window.innerHeight)"],
                timeout=10,
                check=False,
            )
            time.sleep(0.3)

            # Check scroll height
            height_result = _run(
                [self._bin, "eval", "document.documentElement.scrollHeight.toString()"],
                timeout=10,
                check=False,
            )
            if height_result.returncode != 0:
                break
            try:
                current_height = int(height_result.stdout.strip())
            except ValueError:
                break

            if current_height == last_height:
                stable_count += 1
                if stable_count >= 3:
                    break
            else:
                stable_count = 0
                last_height = current_height

        # Scroll back to top
        _run(
            [self._bin, "eval", "window.scrollTo(0, 0)"],
            timeout=10,
            check=False,
        )

    def _expand_accordions(self, subprocess_timeout: float) -> None:
        """Expand collapsed accordion/details elements.

        Clicks all [aria-expanded="false"] elements and opens <details> elements.
        """
        assert self._bin is not None

        # Click all elements with aria-expanded="false"
        _run(
            [self._bin, "eval", """
                (function() {
                    var els = document.querySelectorAll('[aria-expanded="false"]');
                    for (var i = 0; i < els.length; i++) {
                        try { els[i].click(); } catch(e) {}
                    }
                    return els.length.toString();
                })()
            """.strip()],
            timeout=subprocess_timeout,
            check=False,
        )

        # Open all <details> elements
        _run(
            [self._bin, "eval", """
                (function() {
                    var details = document.querySelectorAll('details:not([open])');
                    for (var i = 0; i < details.length; i++) {
                        try { details[i].setAttribute('open', ''); } catch(e) {}
                    }
                    return details.length.toString();
                })()
            """.strip()],
            timeout=subprocess_timeout,
            check=False,
        )

        # Brief pause for content to render
        time.sleep(0.3)

    def _fetch_once(
        self,
        *,
        url: str,
        timeout_s: float,
        max_bytes: int,
        subprocess_timeout: float,
        wait_for_text_min: int,
        wait_for_text_s: float,
        scroll_full_page: bool = False,
        expand_accordions: bool = False,
    ) -> FetchResult:
        assert self._bin is not None

        # 1. Navigate to URL (pass allowed domains so agent-browser can scope).
        allowed_csv = ",".join(sorted(self.allowed_domains)) if self.allowed_domains else ""
        open_args = [self._bin, "open", url]
        if allowed_csv:
            open_args.extend(["--allowed-domains", allowed_csv])
        result = _run(open_args, timeout=subprocess_timeout)
        if result.returncode != 0:
            raise XDocsError(
                code="ENET",
                message="agent-browser open failed.",
                details={"url": url, "stderr": result.stderr.strip()[:500]},
            )

        # 2. Wait for page to render.
        wait_ms = int(timeout_s * 1000)
        result = _run(
            [self._bin, "wait", "--load", "networkidle"],
            timeout=subprocess_timeout,
        )
        # networkidle may fail on some pages; try domcontentloaded as fallback.
        if result.returncode != 0:
            _run(
                [self._bin, "wait", "--load", "domcontentloaded"],
                timeout=subprocess_timeout,
                check=False,
            )

        # 2a. Expand accordions — Pass 1 (before scroll): expand collapsed elements.
        if expand_accordions:
            self._expand_accordions(subprocess_timeout)

        # 3. Best-effort readiness: wait for visible text to appear.
        deadline = time.monotonic() + float(wait_for_text_s)
        while time.monotonic() < deadline:
            eval_result = _run(
                [self._bin, "eval", "(document.body ? (document.body.innerText || '').length : 0).toString()"],
                timeout=10,
                check=False,
            )
            if eval_result.returncode == 0:
                try:
                    n = int(eval_result.stdout.strip())
                    if n >= wait_for_text_min:
                        break
                except ValueError:
                    pass
            time.sleep(0.5)

        # 3a. Scroll full page to trigger lazy-loaded content.
        if scroll_full_page:
            self._scroll_full_page(subprocess_timeout)

        # 3b. Expand accordions — Pass 2 (after scroll): expand dynamically loaded accordions.
        if expand_accordions:
            self._expand_accordions(subprocess_timeout)

        # 4. Get final URL (detect redirects).
        url_result = _run([self._bin, "get", "url"], timeout=10)
        final_url = url_result.stdout.strip() or url

        # 5. Validate final URL host.
        fh = _host(final_url)
        if fh and not _host_allowed(fh, self.allowed_domains):
            raise XDocsError(
                code="EDOMAIN",
                message="Final URL host is outside allowed domain scope.",
                details={
                    "url": url,
                    "final_url": final_url,
                    "final_host": fh,
                    "allowed_domains": sorted(self.allowed_domains),
                },
            )

        # 6. Get rendered HTML (full document for proper markdown conversion).
        # Use eval to get document.documentElement.outerHTML which includes <html><head>...</head><body>...</body></html>.
        # Falls back to `get html body` (body-only) if eval fails.
        html_result = _run(
            [self._bin, "eval", "document.documentElement.outerHTML"],
            timeout=subprocess_timeout,
            check=False,
        )
        if html_result.returncode != 0 or not html_result.stdout.strip():
            html_result = _run([self._bin, "get", "html", "body"], timeout=subprocess_timeout)
            if html_result.returncode != 0:
                raise XDocsError(
                    code="ENET",
                    message="agent-browser get html failed.",
                    details={"url": url, "stderr": html_result.stderr.strip()[:500]},
                )

        body = html_result.stdout.encode("utf-8", errors="replace")

        # 7. Enforce max_bytes.
        if len(body) > max_bytes:
            raise XDocsError(
                code="ETOOBIG",
                message="Rendered HTML exceeded max_bytes limit.",
                details={"url": url, "max_bytes": max_bytes, "received_bytes": len(body)},
            )

        # Build redirect chain from URL comparison.
        redirect_chain: list[str] = []
        if final_url and final_url != url:
            redirect_chain = [url]

        return FetchResult(
            url=url,
            final_url=final_url,
            redirect_chain=redirect_chain,
            http_status=200,
            content_type="text/html; charset=utf-8",
            headers={},
            body=body,
        )
