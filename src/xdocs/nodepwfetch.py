from __future__ import annotations

import json
import os
import random
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import XDocsError
from .httpfetch import FetchResult, _host_allowed, _is_http_url
from .urlutil import url_host as _host

# Known install location for the Node.js playwright module.
_NODE_PW_MODULE = Path("/opt/homebrew/lib/node_modules/@playwright/cli/node_modules/playwright")

# Inline Node.js script that reads JSON-line requests from stdin
# and writes JSON-line responses to stdout.
# Uses the globally-installed playwright module.
_NODE_SCRIPT = r"""
const pw = require(process.env.PW_MODULE || 'playwright');
const readline = require('readline');

(async () => {
  const browser = await pw.chromium.launch({ headless: true });
  const context = await browser.newContext();

  const rl = readline.createInterface({ input: process.stdin });

  for await (const line of rl) {
    let req;
    try {
      req = JSON.parse(line.trim());
    } catch {
      process.stdout.write(JSON.stringify({ error: 'invalid JSON' }) + '\n');
      continue;
    }

    if (req.cmd === 'quit') {
      break;
    }

    const { url, timeout_ms, allowed_domains, wait_for_text_min, wait_for_text_s } = req;
    const page = await context.newPage();
    const timeoutMs = timeout_ms || 30000;
    const textMin = wait_for_text_min || 100;
    const textWaitS = wait_for_text_s || 15;

    try {
      page.setDefaultNavigationTimeout(timeoutMs);
      page.setDefaultTimeout(timeoutMs);

      // Block navigation to disallowed domains.
      const allowSet = new Set((allowed_domains || []).map(d => d.toLowerCase()));
      await page.route('**/*', (route, request) => {
        try {
          const reqUrl = new URL(request.url());
          const host = reqUrl.hostname.toLowerCase();
          if (request.isNavigationRequest() && allowSet.size > 0) {
            let ok = false;
            for (const d of allowSet) {
              if (host === d || host.endsWith('.' + d)) { ok = true; break; }
            }
            if (!ok) { route.abort(); return; }
          }
          route.continue();
        } catch { try { route.abort(); } catch {} }
      });

      const resp = await page.goto(url, { waitUntil: 'commit' });
      const status = resp ? resp.status() : 0;
      const headers = resp ? resp.headers() : {};
      const contentType = headers['content-type'] || 'text/html; charset=utf-8';

      // Wait for visible text.
      const deadline = Date.now() + textWaitS * 1000;
      while (Date.now() < deadline) {
        try {
          const n = await page.evaluate(() => document.body ? (document.body.innerText || '').length : 0);
          if (n >= textMin) break;
        } catch { break; }
        await new Promise(r => setTimeout(r, 250));
      }

      const html = await page.content();
      const finalUrl = page.url();

      // Selected cache headers.
      const selHeaders = {};
      for (const k of ['etag', 'last-modified', 'cache-control', 'content-length']) {
        if (headers[k]) selHeaders[k] = headers[k];
      }

      process.stdout.write(JSON.stringify({
        url, final_url: finalUrl, status, content_type: contentType,
        headers: selHeaders, html,
      }) + '\n');
    } catch (e) {
      process.stdout.write(JSON.stringify({
        url, error: e.message || String(e),
      }) + '\n');
    } finally {
      await page.close().catch(() => {});
    }
  }

  await context.close().catch(() => {});
  await browser.close().catch(() => {});
  process.exit(0);
})();
"""


def _find_node_pw_module() -> Path:
    """Locate the Node.js playwright module directory."""
    # 1. Environment override.
    env = os.environ.get("CEX_NODE_PW_MODULE")
    if env:
        p = Path(env)
        if (p / "index.js").exists():
            return p

    # 2. Known Homebrew path.
    if (_NODE_PW_MODULE / "index.js").exists():
        return _NODE_PW_MODULE

    # 3. Try npm root -g.
    try:
        result = subprocess.run(
            ["npm", "root", "-g"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            root = Path(result.stdout.strip())
            for candidate in [
                root / "playwright",
                root / "@playwright" / "cli" / "node_modules" / "playwright",
            ]:
                if (candidate / "index.js").exists():
                    return candidate
    except Exception:
        pass

    raise XDocsError(
        code="ENOPLAYWRIGHT",
        message="Node.js playwright module not found. Install: npm install -g @playwright/cli",
    )


def _check_chromium_binary(pw_module: Path) -> None:
    """Verify that a Chromium browser binary is installed for playwright."""
    # playwright stores browsers under ~/.cache/ms-playwright/ or similar.
    # The simplest check is to run a quick Node.js snippet.
    check_script = f"""
const pw = require('{pw_module}');
(async () => {{
  try {{
    const b = await pw.chromium.launch({{ headless: true }});
    await b.close();
    process.exit(0);
  }} catch (e) {{
    process.stderr.write(e.message);
    process.exit(1);
  }}
}})();
"""
    try:
        result = subprocess.run(
            ["node", "-e", check_script],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PW_MODULE": str(pw_module)},
        )
        if result.returncode != 0:
            raise XDocsError(
                code="ENOPLAYWRIGHT",
                message="Playwright Chromium browser not installed. Run: npx playwright install chromium",
                details={"stderr": result.stderr.strip()[:500]},
            )
    except subprocess.TimeoutExpired as e:
        raise XDocsError(
            code="ETIMEOUT",
            message="Chromium browser check timed out.",
        ) from e
    except FileNotFoundError as e:
        raise XDocsError(
            code="ENOPLAYWRIGHT",
            message="Node.js not found on PATH.",
            details={"error": str(e)},
        ) from e


@dataclass(slots=True)
class NodePlaywrightFetcher:
    """
    JS-rendering fetcher using the Node.js playwright module via a long-running subprocess.

    Same interface as PlaywrightFetcher: open(), fetch(), close().
    Keeps a single browser process alive for session reuse.
    """

    allowed_domains: set[str]

    _pw_module: Path | None = field(init=False, default=None, repr=False)
    _proc: subprocess.Popen[str] | None = field(init=False, default=None, repr=False)

    def open(self) -> "NodePlaywrightFetcher":
        pw_module = _find_node_pw_module()
        _check_chromium_binary(pw_module)
        self._pw_module = pw_module

        self._proc = subprocess.Popen(
            ["node", "-e", _NODE_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PW_MODULE": str(pw_module)},
        )
        return self

    def close(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                assert self._proc.stdin is not None
                self._proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=15)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None

    def __enter__(self) -> "NodePlaywrightFetcher":
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
            raise XDocsError(
                code="EBADURL",
                message="Only http/https URLs are supported.",
                details={"url": url},
            )
        if self._proc is None or self._proc.poll() is not None:
            raise XDocsError(
                code="ENOPLAYWRIGHT",
                message="NodePlaywrightFetcher not initialized. Call open() first.",
            )

        attempt = 0
        while True:
            try:
                return self._fetch_once(
                    url=url,
                    timeout_s=timeout_s,
                    max_bytes=max_bytes,
                    wait_for_text_min=wait_for_text_min,
                    wait_for_text_s=wait_for_text_s,
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
                    message="Node.js playwright render failure.",
                    details={"url": url, "error": f"{type(e).__name__}: {e}"},
                ) from e

    def _fetch_once(
        self,
        *,
        url: str,
        timeout_s: float,
        max_bytes: int,
        wait_for_text_min: int,
        wait_for_text_s: float,
    ) -> FetchResult:
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        req = {
            "url": url,
            "timeout_ms": int(timeout_s * 1000),
            "allowed_domains": sorted(self.allowed_domains),
            "wait_for_text_min": wait_for_text_min,
            "wait_for_text_s": wait_for_text_s,
        }
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()

        # Read response line with timeout.
        # We use a simple blocking read since the Node process responds per-request.
        line = self._proc.stdout.readline()
        if not line:
            raise XDocsError(
                code="ENET",
                message="Node.js playwright subprocess closed unexpectedly.",
                details={"url": url},
            )

        resp = json.loads(line.strip())

        if "error" in resp:
            raise XDocsError(
                code="ENET",
                message="Node.js playwright page error.",
                details={"url": url, "node_error": resp["error"]},
            )

        final_url = resp.get("final_url", url)
        status = int(resp.get("status", 200))
        content_type = resp.get("content_type", "text/html; charset=utf-8")
        headers = resp.get("headers", {})
        html = resp.get("html", "")

        # Validate final URL host.
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

        body = html.encode("utf-8", errors="replace")
        if len(body) > max_bytes:
            raise XDocsError(
                code="ETOOBIG",
                message="Rendered HTML exceeded max_bytes limit.",
                details={"url": url, "max_bytes": max_bytes, "received_bytes": len(body)},
            )

        # Build redirect chain.
        redirect_chain: list[str] = []
        if final_url and final_url != url:
            redirect_chain = [url]

        return FetchResult(
            url=url,
            final_url=final_url,
            redirect_chain=redirect_chain,
            http_status=status,
            content_type=content_type,
            headers=headers,
            body=body,
        )
