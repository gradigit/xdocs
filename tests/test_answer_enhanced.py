from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from cex_api_docs.answer import answer_question
from cex_api_docs.db import open_db
from cex_api_docs.hashing import sha256_hex_bytes, sha256_hex_text
from cex_api_docs.store import init_store
from cex_api_docs.timeutil import now_iso_utc

REPO_ROOT = Path(__file__).resolve().parents[1]


def _insert_page(docs_dir: Path, conn, *, url: str, md: str) -> None:
    domain = (urlsplit(url).hostname or "").lower()
    path_hash = sha256_hex_text(url)
    content_hash = sha256_hex_text(md)
    raw_hash = sha256_hex_bytes(b"")
    crawled_at = now_iso_utc()

    for subdir in ("raw", "pages", "meta"):
        d = docs_dir / subdir / domain
        d.mkdir(parents=True, exist_ok=True)

    raw_path = docs_dir / "raw" / domain / f"{path_hash}.bin"
    md_path = docs_dir / "pages" / domain / f"{path_hash}.md"
    meta_path = docs_dir / "meta" / domain / f"{path_hash}.json"
    raw_path.write_bytes(b"")
    md_path.write_text(md, encoding="utf-8")
    meta_path.write_text("{}", encoding="utf-8")

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


def _insert_endpoint(docs_dir: Path, conn, *, endpoint: dict) -> None:
    http = endpoint.get("http", {})
    updated_at = now_iso_utc()
    with conn:
        cur = conn.execute(
            """
INSERT INTO endpoints (endpoint_id, exchange, section, protocol, method, path, base_url, description, json, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
            (
                endpoint["endpoint_id"],
                endpoint["exchange"],
                endpoint["section"],
                endpoint.get("protocol", "http"),
                http.get("method"),
                http.get("path"),
                http.get("base_url"),
                endpoint.get("description"),
                json.dumps(endpoint, sort_keys=True, ensure_ascii=False),
                updated_at,
            ),
        )
        rowid = int(cur.lastrowid)
        search_text = json.dumps({
            "description": endpoint.get("description"),
            "rate_limit": endpoint.get("rate_limit"),
            "error_codes": endpoint.get("error_codes"),
            "field_status": endpoint.get("field_status"),
        }, sort_keys=True, ensure_ascii=False)
        conn.execute(
            """
INSERT INTO endpoints_fts (rowid, endpoint_id, exchange, section, method, path, search_text)
VALUES (?, ?, ?, ?, ?, ?, ?);
""",
            (rowid, endpoint["endpoint_id"], endpoint["exchange"], endpoint["section"],
             http.get("method", ""), http.get("path", ""), search_text),
        )


class TestAnswerIncludesEndpointData(unittest.TestCase):
    def test_answer_includes_endpoint_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                # Insert an endpoint about trading fees.
                _insert_endpoint(docs_dir, conn, endpoint={
                    "endpoint_id": "test-fees-1",
                    "exchange": "okx",
                    "section": "rest",
                    "protocol": "http",
                    "http": {"method": "GET", "path": "/api/v5/account/trade-fee", "base_url": "https://www.okx.com"},
                    "description": "Get trading fee rates for different instrument types",
                    "field_status": {"rate_limit": "documented", "description": "documented"},
                    "rate_limit": {"requests_per_second": 5},
                })

                # Insert a page with trading fee content.
                _insert_page(docs_dir, conn,
                    url="https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-fee-rates",
                    md="# Get Fee Rates\n\nGet trading fee rates. Rate limit: 5 requests per 2 seconds.\n\nGET /api/v5/account/trade-fee\n")

                conn.commit()
            finally:
                conn.close()

            result = answer_question(docs_dir=str(docs_dir), question="What are the OKX trading fees?")
            self.assertEqual(result["status"], "ok")
            # Should have claims including endpoint data.
            endpoint_claims = [c for c in result["claims"] if c.get("kind") == "ENDPOINT"]
            self.assertGreaterEqual(len(endpoint_claims), 1)
            self.assertIn("trade-fee", endpoint_claims[0]["text"])


class TestAnswerRateLimitInferred(unittest.TestCase):
    def test_answer_rate_limit_inferred(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                # Insert endpoint with unknown rate limit.
                _insert_endpoint(docs_dir, conn, endpoint={
                    "endpoint_id": "test-order-1",
                    "exchange": "okx",
                    "section": "rest",
                    "protocol": "http",
                    "http": {"method": "POST", "path": "/api/v5/trade/order", "base_url": "https://www.okx.com"},
                    "description": "Place an order",
                    "field_status": {"rate_limit": "unknown", "description": "documented"},
                })

                # Insert page that mentions the rate limit near the endpoint path.
                _insert_page(docs_dir, conn,
                    url="https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-place-order",
                    md="# Place Order\n\nPOST /api/v5/trade/order\n\nRate limit: weight is 60 requests per 2s\n\nPlace a new order.\n")

                conn.commit()
            finally:
                conn.close()

            result = answer_question(docs_dir=str(docs_dir), question="What is the rate limit for OKX place order?")
            self.assertEqual(result["status"], "ok")
            # Should have some claims.
            self.assertGreater(len(result["claims"]), 0)


if __name__ == "__main__":
    unittest.main()
