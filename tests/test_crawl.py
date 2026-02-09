from __future__ import annotations

import contextlib
import os
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cex_api_docs.crawler import crawl_store
from cex_api_docs.pages import diff_pages, search_pages
from cex_api_docs.store import init_store


REPO_ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def serve_directory(path: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args) -> None:
            return

    class FastThreadingHTTPServer(ThreadingHTTPServer):
        # Avoid reverse-DNS lookup in socket.getfqdn(host) on macOS,
        # which can block tests for ~30s on misconfigured networks.
        def server_bind(self) -> None:  # type: ignore[override]
            self.socket.bind(self.server_address)
            self.server_address = self.socket.getsockname()
            host, port = self.server_address[:2]
            self.server_name = host
            self.server_port = port

    cwd = os.getcwd()
    os.chdir(path)
    try:
        httpd = FastThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        host, port = httpd.server_address
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield f"http://{host}:{port}"
        finally:
            httpd.shutdown()
            httpd.server_close()
            t.join(timeout=2)
    finally:
        os.chdir(cwd)


class TestCrawl(unittest.TestCase):
    def test_fixture_crawl_and_search_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "site"
            fixture.mkdir(parents=True, exist_ok=True)

            (fixture / "index.html").write_text(
                """
<!doctype html>
<html>
  <head><title>Index</title></head>
  <body>
    <h1>Hello Docs</h1>
    <a href="/page2.html">Page2</a>
  </body>
</html>
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (fixture / "page2.html").write_text(
                """
<!doctype html>
<html>
  <head><title>Page2</title></head>
  <body>
    <p>Rate limit weight is 10 per second.</p>
    <a href="/index.html">Back</a>
  </body>
</html>
""".strip()
                + "\n",
                encoding="utf-8",
            )

            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_directory(fixture) as base_url:
                seed = f"{base_url}/index.html"
                r = crawl_store(
                    docs_dir=str(docs_dir),
                    schema_version="v1",
                    lock_timeout_s=1.0,
                    seeds=[seed],
                    allowed_domains=["127.0.0.1"],
                    max_depth=2,
                    max_pages=10,
                    delay_s=0.0,
                    timeout_s=5.0,
                    ignore_robots=False,
                    render_mode="http",
                )

            self.assertEqual(r["counts"]["errors"], 0)
            self.assertGreaterEqual(r["counts"]["stored"], 2)

            matches = search_pages(docs_dir=str(docs_dir), query="rate limit", limit=10)
            self.assertGreaterEqual(len(matches), 1)

            d = diff_pages(docs_dir=str(docs_dir), crawl_run_id=r["crawl_run_id"], limit=10)
            self.assertGreaterEqual(d["counts"]["new"], 2)


if __name__ == "__main__":
    unittest.main()
