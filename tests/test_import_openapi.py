from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cex_api_docs.coverage import endpoint_coverage
from cex_api_docs.openapi_import import import_openapi
from cex_api_docs.endpoints import search_endpoints
from cex_api_docs.store import init_store
from tests.http_server import serve_directory


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestImportOpenApi(unittest.TestCase):
    def test_import_openapi_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir(parents=True, exist_ok=True)

            (site / "openapi.yaml").write_text(
                "\n".join(
                    [
                        "openapi: 3.0.0",
                        "info:",
                        "  title: Test API",
                        "  version: 1.0.0",
                        "servers:",
                        "  - url: https://api.test.example",
                        "paths:",
                        "  /api/v1/time:",
                        "    get:",
                        "      summary: Get server time",
                        "      responses:",
                        "        '200':",
                        "          description: OK",
                        "  /api/v1/ping:",
                        "    get:",
                        "      summary: Ping",
                        "      responses:",
                        "        '200':",
                        "          description: OK",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_directory(site) as base_url:
                spec_url = f"{base_url}/openapi.yaml"
                r = import_openapi(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange="binance",
                    section="spot",
                    url=spec_url,
                    base_url=None,
                    api_version=None,
                    timeout_s=5.0,
                    max_bytes=5_000_000,
                    max_redirects=3,
                    retries=0,
                    continue_on_error=False,
                )

            self.assertEqual(r["counts"]["ok"], 2)
            self.assertEqual(r["counts"]["errors"], 0)

            matches = search_endpoints(docs_dir=str(docs_dir), query="/api/v1/time", exchange="binance", section="spot", limit=10)
            self.assertTrue(any(m["path"] == "/api/v1/time" for m in matches))

            cov = endpoint_coverage(docs_dir=str(docs_dir), exchange="binance", section="spot", limit_samples=2)
            self.assertEqual(cov["totals"]["endpoints"], 2)


if __name__ == "__main__":
    unittest.main()

