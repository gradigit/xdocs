from __future__ import annotations

import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

# TODO: migrate to inventory+fetch_inventory pipeline (crawl is deprecated)
from xdocs.crawler import crawl_store
from xdocs.pages import diff_pages, search_pages
from xdocs.store import init_store
from tests.http_server import serve_directory, serve_handler


REPO_ROOT = Path(__file__).resolve().parents[1]


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

    def test_redirect_to_disallowed_host_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            class DisallowedHandler(BaseHTTPRequestHandler):
                hits = 0

                def log_message(self, _format: str, *_args) -> None:  # pragma: no cover
                    return

                def do_GET(self) -> None:  # type: ignore[override]
                    type(self).hits += 1
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<html><body>disallowed</body></html>\n")

            with serve_handler(DisallowedHandler) as disallowed_base:
                disallowed_url = f"{disallowed_base}/target"

                class AllowedHandler(BaseHTTPRequestHandler):
                    def log_message(self, _format: str, *_args) -> None:  # pragma: no cover
                        return

                    def do_GET(self) -> None:  # type: ignore[override]
                        self.send_response(302)
                        self.send_header("Location", disallowed_url)
                        self.end_headers()

                with serve_handler(AllowedHandler) as allowed_base:
                    port = urlsplit(allowed_base).port
                    assert port is not None
                    seed = f"http://localhost:{port}/start"
                    r = crawl_store(
                        docs_dir=str(docs_dir),
                        schema_version="v1",
                        lock_timeout_s=1.0,
                        seeds=[seed],
                        allowed_domains=["localhost"],
                        max_depth=0,
                        max_pages=10,
                        delay_s=0.0,
                        timeout_s=5.0,
                        ignore_robots=True,
                        render_mode="http",
                    )

            self.assertEqual(r["counts"]["stored"], 0)
            self.assertGreaterEqual(r["counts"]["errors"], 1)
            self.assertEqual(DisallowedHandler.hits, 0)


if __name__ == "__main__":
    unittest.main()
