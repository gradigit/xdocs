from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from xdocs.coverage import endpoint_coverage
from xdocs.endpoints import search_endpoints
from xdocs.postman_import import import_postman
from xdocs.store import init_store
from tests.http_server import serve_directory


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestImportPostman(unittest.TestCase):
    def test_import_postman_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir(parents=True, exist_ok=True)

            coll = {
                "info": {"name": "Test Collection", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
                "item": [
                    {
                        "name": "Ping",
                        "request": {
                            "method": "GET",
                            "url": {"raw": "https://api.test.example/api/v1/ping"},
                        },
                    }
                ],
            }

            (site / "collection.json").write_text(json.dumps(coll, ensure_ascii=False), encoding="utf-8")

            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_directory(site) as base_url:
                coll_url = f"{base_url}/collection.json"
                r = import_postman(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange="binance",
                    section="spot",
                    url=coll_url,
                    base_url="https://api.test.example",
                    api_version=None,
                    timeout_s=5.0,
                    max_bytes=5_000_000,
                    max_redirects=3,
                    retries=0,
                    continue_on_error=False,
                )

            self.assertEqual(r["counts"]["ok"], 1)
            self.assertEqual(r["counts"]["errors"], 0)

            matches = search_endpoints(docs_dir=str(docs_dir), query="/api/v1/ping", exchange="binance", section="spot", limit=10)
            self.assertTrue(any(m["path"] == "/api/v1/ping" for m in matches))

            cov = endpoint_coverage(docs_dir=str(docs_dir), exchange="binance", section="spot", limit_samples=2)
            self.assertEqual(cov["totals"]["endpoints"], 1)


if __name__ == "__main__":
    unittest.main()

