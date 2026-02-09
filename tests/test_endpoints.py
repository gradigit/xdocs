from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cex_api_docs.crawler import crawl_store
from cex_api_docs.endpoints import compute_endpoint_id, review_list, review_resolve, save_endpoint, search_endpoints
from cex_api_docs.pages import get_page
from cex_api_docs.store import init_store


REPO_ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def serve_directory(path: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args) -> None:
            return

    class FastThreadingHTTPServer(ThreadingHTTPServer):
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


class TestEndpoints(unittest.TestCase):
    def test_save_endpoint_search_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "site"
            fixture.mkdir(parents=True, exist_ok=True)

            (fixture / "index.html").write_text(
                "<html><head><title>Index</title></head><body><a href=\"/page2.html\">Page2</a></body></html>\n",
                encoding="utf-8",
            )
            (fixture / "page2.html").write_text(
                "<html><head><title>Page2</title></head><body><p>Rate limit weight is 10 per second.</p></body></html>\n",
                encoding="utf-8",
            )

            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_directory(fixture) as base_url:
                crawl_store(
                    docs_dir=str(docs_dir),
                    schema_version="v1",
                    lock_timeout_s=1.0,
                    seeds=[f"{base_url}/index.html"],
                    allowed_domains=["127.0.0.1"],
                    max_depth=2,
                    max_pages=10,
                    delay_s=0.0,
                    timeout_s=5.0,
                    ignore_robots=False,
                    render_mode="http",
                )

                page2_url = f"{base_url}/page2.html"

            page = get_page(docs_dir=str(docs_dir), url=page2_url)
            md = page["markdown"]
            meta = page["meta"]
            self.assertIsInstance(md, str)
            self.assertIsInstance(meta, dict)

            needle = "Rate limit weight is 10 per second."
            start = md.index(needle)
            end = start + len(needle)
            excerpt = md[start:end]

            record: dict = {
                "exchange": "binance",
                "section": "spot",
                "protocol": "http",
                "http": {"method": "GET", "path": "/api/v3/time", "base_url": "https://api.binance.com", "api_version": None},
                "description": "Test endpoint",
                "rate_limit": {"note": needle},
                "sources": [
                    {
                        "url": page2_url,
                        "crawled_at": meta["crawled_at"],
                        "content_hash": meta["content_hash"],
                        "path_hash": meta["path_hash"],
                        "excerpt": excerpt,
                        "excerpt_start": start,
                        "excerpt_end": end,
                        "field_name": "rate_limit",
                    }
                ],
                "extraction": {"model": "test", "temperature": 0, "prompt_hash": "x", "input_content_hash": meta["content_hash"]},
            }
            record["endpoint_id"] = compute_endpoint_id(record)

            endpoint_path = Path(tmp) / "endpoint.json"
            endpoint_path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            r = save_endpoint(
                docs_dir=str(docs_dir),
                lock_timeout_s=1.0,
                endpoint_json_path=endpoint_path,
                schema_path=REPO_ROOT / "schemas" / "endpoint.schema.json",
            )
            self.assertEqual(r["endpoint_id"], record["endpoint_id"])

            matches = search_endpoints(docs_dir=str(docs_dir), query="weight", exchange="binance", section="spot", limit=10)
            self.assertTrue(any(m["endpoint_id"] == record["endpoint_id"] for m in matches))

            # Save another endpoint missing per-field citation to trigger review queue.
            record2 = dict(record)
            record2["http"] = {"method": "GET", "path": "/api/v3/ping", "base_url": "https://api.binance.com", "api_version": None}
            record2["endpoint_id"] = compute_endpoint_id(record2)
            record2["sources"] = [
                {
                    "url": page2_url,
                    "crawled_at": meta["crawled_at"],
                    "content_hash": meta["content_hash"],
                    "path_hash": meta["path_hash"],
                    "excerpt": excerpt,
                    "excerpt_start": start,
                    "excerpt_end": end,
                    "field_name": None,
                }
            ]

            endpoint_path2 = Path(tmp) / "endpoint2.json"
            endpoint_path2.write_text(json.dumps(record2, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            save_endpoint(
                docs_dir=str(docs_dir),
                lock_timeout_s=1.0,
                endpoint_json_path=endpoint_path2,
                schema_path=REPO_ROOT / "schemas" / "endpoint.schema.json",
            )

            open_items = review_list(docs_dir=str(docs_dir), status="open", limit=50)
            self.assertTrue(any(i["endpoint_id"] == record2["endpoint_id"] and i["field_name"] == "rate_limit" for i in open_items))

            # Resolve first matching review item.
            rid = next(i["id"] for i in open_items if i["endpoint_id"] == record2["endpoint_id"] and i["field_name"] == "rate_limit")
            review_resolve(docs_dir=str(docs_dir), lock_timeout_s=1.0, review_id=rid, resolution="ok")

            resolved_items = review_list(docs_dir=str(docs_dir), status="resolved", limit=50)
            self.assertTrue(any(i["id"] == rid for i in resolved_items))


if __name__ == "__main__":
    unittest.main()

