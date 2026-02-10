from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

# TODO: migrate to inventory+fetch_inventory pipeline (crawl is deprecated)
from cex_api_docs.crawler import crawl_store
from cex_api_docs.endpoints import compute_endpoint_id, review_list, review_resolve, save_endpoint, search_endpoints
from cex_api_docs.pages import get_page
from cex_api_docs.store import init_store
from cex_api_docs.db import open_db
from tests.http_server import serve_directory


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestEndpoints(unittest.TestCase):
    def test_save_endpoint_search_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "site"
            fixture.mkdir(parents=True, exist_ok=True)

            (fixture / "index.html").write_text(
                "<html><head><title>Index</title></head><body><a href=\"/page2.html\">Page2</a><a href=\"/page3.html\">Page3</a></body></html>\n",
                encoding="utf-8",
            )
            (fixture / "page2.html").write_text(
                "<html><head><title>Page2</title></head><body><p>Rate limit weight is 10 per second.</p></body></html>\n",
                encoding="utf-8",
            )
            (fixture / "page3.html").write_text(
                "<html><head><title>Page3</title></head><body><p>Rate limit weight is 20 per second.</p></body></html>\n",
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
                # Only mark fields as "documented" when we also provide mechanically-verifiable citations.
                "field_status": {
                    "http.method": "unknown",
                    "http.path": "unknown",
                    "http.base_url": "unknown",
                    "description": "unknown",
                    "request_schema": "unknown",
                    "response_schema": "unknown",
                    "required_permissions": "unknown",
                    "rate_limit": "documented",
                    "error_codes": "unknown",
                },
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

            # Saving the same endpoint again should not leave stale endpoint_sources mappings.
            page3_url = f"{base_url}/page3.html"
            page3 = get_page(docs_dir=str(docs_dir), url=page3_url)
            md3 = page3["markdown"]
            meta3 = page3["meta"]
            needle3 = "Rate limit weight is 20 per second."
            start3 = md3.index(needle3)
            end3 = start3 + len(needle3)
            excerpt3 = md3[start3:end3]

            record_update = dict(record)
            record_update["sources"] = [
                {
                    "url": page3_url,
                    "crawled_at": meta3["crawled_at"],
                    "content_hash": meta3["content_hash"],
                    "path_hash": meta3["path_hash"],
                    "excerpt": excerpt3,
                    "excerpt_start": start3,
                    "excerpt_end": end3,
                    "field_name": "rate_limit",
                }
            ]
            record_update["endpoint_id"] = compute_endpoint_id(record_update)

            endpoint_path_update = Path(tmp) / "endpoint-update.json"
            endpoint_path_update.write_text(
                json.dumps(record_update, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            save_endpoint(
                docs_dir=str(docs_dir),
                lock_timeout_s=1.0,
                endpoint_json_path=endpoint_path_update,
                schema_path=REPO_ROOT / "schemas" / "endpoint.schema.json",
            )

            conn = open_db(Path(docs_dir) / "db" / "docs.db")
            try:
                rows = conn.execute(
                    "SELECT page_canonical_url FROM endpoint_sources WHERE endpoint_id = ? AND field_name = 'rate_limit';",
                    (record["endpoint_id"],),
                ).fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["page_canonical_url"], page3_url)
            finally:
                conn.close()

            # Save another endpoint missing per-field citation to trigger review queue.
            record2 = dict(record)
            record2["http"] = {"method": "GET", "path": "/api/v3/ping", "base_url": "https://api.binance.com", "api_version": None}
            record2["endpoint_id"] = compute_endpoint_id(record2)
            # This endpoint has a rate_limit value but no per-field citation mapping.
            # We intentionally mark it unknown to trigger a review item rather than
            # claiming it's documented.
            record2["field_status"] = dict(record["field_status"])
            record2["field_status"]["rate_limit"] = "unknown"
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
