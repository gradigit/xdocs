from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from xdocs.db import open_db
from xdocs.hashing import sha256_hex_bytes, sha256_hex_text
from xdocs.lookup import lookup_endpoint_by_path, search_error_code
from xdocs.markdown import normalize_markdown
from xdocs.store import init_store
from xdocs.timeutil import now_iso_utc

REPO_ROOT = Path(__file__).resolve().parents[1]


def _setup_store_with_endpoints(docs_dir: Path) -> None:
    """Set up a store with test endpoint records and pages."""
    init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

    conn = open_db(docs_dir / "db" / "docs.db")
    updated_at = now_iso_utc()

    # Insert test endpoints.
    endpoints = [
        {
            "endpoint_id": "test-ep-1",
            "exchange": "binance",
            "section": "spot",
            "protocol": "http",
            "http": {"method": "POST", "path": "/sapi/v1/convert/getQuote", "base_url": "https://api.binance.com"},
            "description": "Get a quote for Convert trade",
            "field_status": {"rate_limit": "unknown", "error_codes": "documented"},
            "error_codes": [{"code": "-1002", "message": "Unauthorized"}],
        },
        {
            "endpoint_id": "test-ep-2",
            "exchange": "binance",
            "section": "spot",
            "protocol": "http",
            "http": {"method": "GET", "path": "/api/v3/order", "base_url": "https://api.binance.com"},
            "description": "Query order status",
            "field_status": {"rate_limit": "documented"},
            "rate_limit": {"weight": 4},
        },
        {
            "endpoint_id": "test-ep-3",
            "exchange": "binance",
            "section": "spot",
            "protocol": "http",
            "http": {"method": "DELETE", "path": "/api/v3/order", "base_url": "https://api.binance.com"},
            "description": "Cancel an active order",
            "field_status": {"rate_limit": "documented"},
            "rate_limit": {"weight": 1},
        },
        {
            "endpoint_id": "test-ep-4",
            "exchange": "binance",
            "section": "spot",
            "protocol": "http",
            "http": {"method": "POST", "path": "{{url}}/api/v3/order", "base_url": "https://api.binance.com"},
            "description": "Place order (Postman import)",
            "field_status": {"rate_limit": "unknown"},
        },
    ]

    try:
        with conn:
            for ep in endpoints:
                http = ep.get("http", {})
                cur = conn.execute(
                    """
INSERT INTO endpoints (endpoint_id, exchange, section, protocol, method, path, base_url, description, json, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                    (
                        ep["endpoint_id"],
                        ep["exchange"],
                        ep["section"],
                        ep["protocol"],
                        http.get("method"),
                        http.get("path"),
                        http.get("base_url"),
                        ep.get("description"),
                        json.dumps(ep, sort_keys=True, ensure_ascii=False),
                        updated_at,
                    ),
                )
                rowid = int(cur.lastrowid)
                search_text = json.dumps({
                    "description": ep.get("description"),
                    "error_codes": ep.get("error_codes"),
                    "rate_limit": ep.get("rate_limit"),
                    "field_status": ep.get("field_status"),
                }, sort_keys=True, ensure_ascii=False)
                conn.execute(
                    """
INSERT INTO endpoints_fts (rowid, endpoint_id, exchange, section, method, path, search_text)
VALUES (?, ?, ?, ?, ?, ?, ?);
""",
                    (rowid, ep["endpoint_id"], ep["exchange"], ep["section"],
                     http.get("method", ""), http.get("path", ""), search_text),
                )

        # Insert a test page with error code content.
        _insert_test_page(docs_dir, conn,
            url="https://developers.binance.com/docs/spot/general/error-codes",
            md="# Error Codes\n\n-1002 UNAUTHORIZED\n\nYou are not authorized. Enable Convert API permission.\n\n-1003 TOO_MANY_REQUESTS\n")

        conn.commit()
    finally:
        conn.close()


def _insert_test_page(docs_dir: Path, conn, *, url: str, md: str) -> None:
    domain = (urlsplit(url).hostname or "").lower()
    path_hash = sha256_hex_text(url)
    content_hash = sha256_hex_text(md)
    raw_hash = sha256_hex_bytes(b"")

    md_path = docs_dir / "pages" / domain / f"{path_hash}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")

    raw_path = docs_dir / "raw" / domain / f"{path_hash}.bin"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"")

    meta_path = docs_dir / "meta" / domain / f"{path_hash}.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text("{}", encoding="utf-8")

    crawled_at = now_iso_utc()
    with conn:
        cur = conn.execute(
            """
INSERT INTO pages (
  canonical_url, url, final_url, domain, path_hash, title,
  http_status, content_type, render_mode, raw_hash, content_hash,
  crawled_at, raw_path, markdown_path, meta_path, word_count,
  extractor_name, extractor_version, extractor_config_json, extractor_config_hash,
  last_crawl_run_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
            (url, url, url, domain, path_hash, None, 200, "text/html", "http",
             raw_hash, content_hash, crawled_at, str(raw_path), str(md_path), str(meta_path),
             len(md.split()), "html2text", "test", "{}", "test", None),
        )
        page_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO pages_fts (rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);",
            (page_id, url, "", md),
        )


class TestLookupEndpointByPath(unittest.TestCase):
    def test_lookup_by_exact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            results = lookup_endpoint_by_path(
                docs_dir=str(docs_dir),
                path="/sapi/v1/convert/getQuote",
                method="POST",
                exchange="binance",
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["endpoint_id"], "test-ep-1")

    def test_lookup_by_path_without_method(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            results = lookup_endpoint_by_path(
                docs_dir=str(docs_dir),
                path="/api/v3/order",
            )
            # Should return GET, DELETE, and Postman {{url}} variant.
            self.assertGreaterEqual(len(results), 2)
            methods = {r.get("http", {}).get("method") for r in results}
            self.assertIn("GET", methods)
            self.assertIn("DELETE", methods)

    def test_lookup_strips_postman_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            results = lookup_endpoint_by_path(
                docs_dir=str(docs_dir),
                path="/api/v3/order",
                method="POST",
            )
            # Should find the Postman-imported endpoint with {{url}} prefix.
            postman_results = [r for r in results if "{{url}}" in r.get("http", {}).get("path", "")]
            self.assertEqual(len(postman_results), 1)
            self.assertEqual(postman_results[0]["endpoint_id"], "test-ep-4")


class TestSearchErrorCode(unittest.TestCase):
    def test_search_error_code_in_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            results = search_error_code(
                docs_dir=str(docs_dir),
                error_code="-1002",
                exchange="binance",
            )
            endpoint_results = [r for r in results if r["source_type"] == "endpoint"]
            self.assertGreaterEqual(len(endpoint_results), 1)

    def test_search_error_code_in_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            results = search_error_code(
                docs_dir=str(docs_dir),
                error_code="1003",
            )
            page_results = [r for r in results if r["source_type"] == "page"]
            self.assertGreaterEqual(len(page_results), 1)


class TestGetEndpoint(unittest.TestCase):
    def test_get_endpoint_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            from xdocs.endpoints import get_endpoint
            result = get_endpoint(docs_dir=str(docs_dir), endpoint_id="test-ep-1")
            self.assertEqual(result["endpoint_id"], "test-ep-1")
            self.assertEqual(result["http"]["path"], "/sapi/v1/convert/getQuote")

    def test_get_endpoint_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            from xdocs.endpoints import get_endpoint
            from xdocs.errors import XDocsError
            with self.assertRaises(XDocsError) as ctx:
                get_endpoint(docs_dir=str(docs_dir), endpoint_id="nonexistent")
            self.assertEqual(ctx.exception.code, "ENOTFOUND")


if __name__ == "__main__":
    unittest.main()
