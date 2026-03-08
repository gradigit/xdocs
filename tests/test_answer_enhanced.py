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


class TestDetectBinanceSection(unittest.TestCase):
    """Test _detect_binance_section keyword-to-section mapping."""

    def test_spot(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("binance spot trading api"), "spot")

    def test_futures_usdm(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("usd-m futures rate limit"), "futures_usdm")

    def test_futures_coinm(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("coin-m delivery endpoint"), "futures_coinm")

    def test_portfolio_margin(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("portfolio margin account info"), "portfolio_margin")

    def test_websocket(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("ws stream connection"), "websocket")

    def test_no_match(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertIsNone(_detect_binance_section("what is the api key format"))

    def test_generic_futures(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("futures order endpoint"), "futures_usdm")

    def test_options(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("european options pricing"), "options")

    def test_wallet(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("wallet deposit address"), "wallet")

    def test_copy_trading(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("copy trading lead trader"), "copy_trading")


class TestDetectSectionKeywords(unittest.TestCase):
    """Test _detect_section_keywords for generic multi-section exchanges."""

    def _make_exchange(self, section_ids: list[str]):
        """Create a minimal exchange-like object with sections."""
        from types import SimpleNamespace
        sections = [SimpleNamespace(section_id=sid) for sid in section_ids]
        return SimpleNamespace(sections=sections)

    def test_exact_section_match(self) -> None:
        from cex_api_docs.answer import _detect_section_keywords
        ex = self._make_exchange(["spot", "futures", "websocket"])
        self.assertEqual(_detect_section_keywords("spot order book depth", ex), "spot")

    def test_underscore_to_space_match(self) -> None:
        from cex_api_docs.answer import _detect_section_keywords
        ex = self._make_exchange(["rest", "copy_trading", "options"])
        self.assertEqual(_detect_section_keywords("how does copy trading work", ex), "copy_trading")

    def test_single_section_returns_none(self) -> None:
        from cex_api_docs.answer import _detect_section_keywords
        ex = self._make_exchange(["rest"])
        self.assertIsNone(_detect_section_keywords("rest endpoint info", ex))

    def test_no_match(self) -> None:
        from cex_api_docs.answer import _detect_section_keywords
        ex = self._make_exchange(["spot", "futures"])
        self.assertIsNone(_detect_section_keywords("api key permissions", ex))


class TestSanitizeExchangeFilter(unittest.TestCase):
    """Test _sanitize_exchange_filter prevents injection."""

    def test_valid_name(self) -> None:
        from cex_api_docs.semantic import _sanitize_exchange_filter
        self.assertEqual(_sanitize_exchange_filter("binance"), "binance")

    def test_valid_with_underscores(self) -> None:
        from cex_api_docs.semantic import _sanitize_exchange_filter
        self.assertEqual(_sanitize_exchange_filter("crypto_com"), "crypto_com")

    def test_valid_with_digits(self) -> None:
        from cex_api_docs.semantic import _sanitize_exchange_filter
        self.assertEqual(_sanitize_exchange_filter("gate_io2"), "gate_io2")

    def test_rejects_sql_injection(self) -> None:
        from cex_api_docs.semantic import _sanitize_exchange_filter
        with self.assertRaises(ValueError):
            _sanitize_exchange_filter("binance' OR 1=1 --")

    def test_rejects_special_chars(self) -> None:
        from cex_api_docs.semantic import _sanitize_exchange_filter
        with self.assertRaises(ValueError):
            _sanitize_exchange_filter("bin;DROP TABLE")

    def test_rejects_uppercase(self) -> None:
        from cex_api_docs.semantic import _sanitize_exchange_filter
        with self.assertRaises(ValueError):
            _sanitize_exchange_filter("Binance")

    def test_rejects_empty(self) -> None:
        from cex_api_docs.semantic import _sanitize_exchange_filter
        with self.assertRaises(ValueError):
            _sanitize_exchange_filter("")


class TestSpecUrlSuppression(unittest.TestCase):
    """Test that _is_spec_url correctly identifies spec URLs."""

    def test_openapi_url(self) -> None:
        from cex_api_docs.resolve_docs_urls import _is_spec_url
        self.assertTrue(_is_spec_url("https://example.com/openapi/v3/spec.json"))

    def test_swagger_url(self) -> None:
        from cex_api_docs.resolve_docs_urls import _is_spec_url
        self.assertTrue(_is_spec_url("https://example.com/swagger.json"))

    def test_normal_doc_url(self) -> None:
        from cex_api_docs.resolve_docs_urls import _is_spec_url
        self.assertFalse(_is_spec_url("https://docs.example.com/api/v5/order"))

    def test_postman_url(self) -> None:
        from cex_api_docs.resolve_docs_urls import _is_spec_url
        self.assertTrue(_is_spec_url("https://www.postman.com/collections/12345"))


class TestSchemaVersion6Migration(unittest.TestCase):
    """Test v5→v6 migration (changelog FTS porter stemming)."""

    def test_fresh_db_gets_version_6(self) -> None:
        import sqlite3
        from cex_api_docs.db import init_db
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            result = init_db(db_path, REPO_ROOT / "schema" / "schema.sql")
            self.assertEqual(result.schema_user_version, 6)

    def test_v5_migrates_to_v6(self) -> None:
        import sqlite3
        from cex_api_docs.db import apply_schema, open_db, _get_user_version
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            conn = open_db(db_path)
            try:
                # Set up a v5 DB with the old-style changelog FTS.
                schema_path = REPO_ROOT / "schema" / "schema.sql"
                conn.executescript(schema_path.read_text(encoding="utf-8"))
                # Simulate v5: drop new FTS table, recreate without porter.
                conn.execute("DROP TABLE IF EXISTS changelog_entries_fts;")
                conn.execute("""
CREATE VIRTUAL TABLE changelog_entries_fts USING fts5(
  exchange_id, section_id, entry_date, entry_text,
  content=changelog_entries, content_rowid=id
);
""")
                conn.execute("PRAGMA user_version = 5;")
                conn.commit()

                # Now apply schema — should migrate 5→6.
                version = apply_schema(conn, schema_path, expected_user_version=6)
                self.assertEqual(version, 6)

                # Verify FTS table was recreated (by inserting a test row).
                conn.execute("""
INSERT INTO changelog_entries (exchange_id, section_id, source_url, entry_text, content_hash, extracted_at)
VALUES ('test', 'rest', 'https://example.com', 'API changed', 'abc123', '2026-01-01');
""")
                conn.commit()
                # Rebuild FTS content.
                conn.execute("INSERT INTO changelog_entries_fts(changelog_entries_fts) VALUES('rebuild');")
                # Porter stemming should match "changing" to "changed".
                rows = conn.execute(
                    "SELECT * FROM changelog_entries_fts WHERE changelog_entries_fts MATCH 'changing';"
                ).fetchall()
                self.assertEqual(len(rows), 1)
            finally:
                conn.close()


class TestNavRegionDetection(unittest.TestCase):
    """Test that excerpt extraction skips navigation/TOC regions."""

    def test_is_nav_region_bullet_list(self):
        from cex_api_docs.answer import _is_nav_region

        nav_md = "\n".join([
            "NAV",
            "* [API Overview](https://example.com/api)",
            "* [Authentication](https://example.com/auth)",
            "* Rate Limits",
            "  * Trading-related APIs",
            "  * Sub-account rate limit",
            "* Market Maker Program",
            "* [WebSocket](https://example.com/ws)",
            "* [REST API](https://example.com/rest)",
            "* [Change Log](https://example.com/log)",
        ])
        self.assertTrue(_is_nav_region(nav_md, 50))

    def test_is_nav_region_content(self):
        from cex_api_docs.answer import _is_nav_region

        content_md = "\n".join([
            "## Rate Limits",
            "",
            "Our REST and WebSocket APIs use rate limits to protect against abuse.",
            "When a request is rejected due to rate limits, error code 50011 is returned.",
            "The rate limit is different for each endpoint.",
            "",
            "| Endpoint | Rate Limit | Weight |",
            "| --- | --- | --- |",
            "| GET /api/v5/account/balance | 10 req/s | 1 |",
        ])
        self.assertFalse(_is_nav_region(content_md, 50))

    def test_make_excerpt_skips_nav(self):
        import re
        from cex_api_docs.answer import _make_excerpt

        # Build a large enough nav section so it's clearly separated from content
        nav_lines = [f"* [{f'Section {i}'}](https://example.com/s{i})" for i in range(40)]
        nav_lines.insert(5, "* Rate Limits")
        nav_lines.insert(6, "  * Trading rate limits")
        nav_lines.insert(7, "  * Sub-account rate limit")
        nav = "\n".join(nav_lines)
        # Add filler paragraphs between nav and content (simulating real pages)
        filler = "\n\n" + ("Lorem ipsum dolor sit amet. " * 20 + "\n\n") * 3
        content = "\n".join([
            "## Rate Limits",
            "",
            "Our REST and WebSocket APIs use rate limits to protect against abuse.",
            "When a request is rejected the system returns error code 50011.",
        ])
        md = nav + filler + content
        needle = re.compile(r"rate\s+limit", re.IGNORECASE)
        excerpt, start, end = _make_excerpt(md, needle_re=needle)
        # Excerpt should come from the content section, not the nav
        self.assertIn("REST and WebSocket APIs", excerpt)


if __name__ == "__main__":
    unittest.main()
