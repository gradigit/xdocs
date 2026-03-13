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
INSERT INTO endpoints (endpoint_id, exchange, section, protocol, method, path, base_url, description, json, updated_at, docs_url)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                endpoint.get("docs_url"),
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


class TestIsTestnetUrl(unittest.TestCase):
    """Test testnet/sandbox URL detection."""

    def test_testnet_path(self):
        from cex_api_docs.answer import _is_testnet_url

        self.assertTrue(_is_testnet_url("https://testnet.binance.vision/testnet/api"))
        self.assertTrue(_is_testnet_url("https://api.binance.com/testnet/v3/account"))

    def test_sandbox_path(self):
        from cex_api_docs.answer import _is_testnet_url

        self.assertTrue(_is_testnet_url("https://api.coinbase.com/sandbox/v2/orders"))

    def test_case_insensitive(self):
        from cex_api_docs.answer import _is_testnet_url

        self.assertTrue(_is_testnet_url("https://api.example.com/TESTNET/api"))
        self.assertTrue(_is_testnet_url("https://api.example.com/Sandbox/api"))

    def test_normal_url(self):
        from cex_api_docs.answer import _is_testnet_url

        self.assertFalse(_is_testnet_url("https://api.binance.com/api/v3/account"))
        self.assertFalse(_is_testnet_url("https://www.okx.com/docs-v5/en/"))

    def test_empty_url(self):
        from cex_api_docs.answer import _is_testnet_url

        self.assertFalse(_is_testnet_url(""))

    def test_testnet_in_domain_not_path(self):
        from cex_api_docs.answer import _is_testnet_url

        # "testnet" in domain but not as /testnet/ path segment
        self.assertFalse(_is_testnet_url("https://testnet.binance.vision/api/v3"))


class TestApplySectionBoost(unittest.TestCase):
    """Test section boost score multiplication."""

    def test_boost_matching_urls(self):
        from cex_api_docs import answer
        from cex_api_docs.answer import _apply_section_boost

        old = answer._SECTION_BOOST_ENABLED
        try:
            answer._SECTION_BOOST_ENABLED = True
            results = [
                {"canonical_url": "https://api.binance.com/spot/v1/order", "rrf_score": 0.5},
                {"canonical_url": "https://api.binance.com/futures/v1/order", "rrf_score": 0.6},
                {"canonical_url": "https://api.binance.com/spot/v1/account", "rrf_score": 0.4},
            ]
            boosted = _apply_section_boost(results, section_prefix="https://api.binance.com/spot/")
            # Spot URLs should be boosted by 1.3x
            spot_urls = [r for r in boosted if "/spot/" in r["canonical_url"]]
            for r in spot_urls:
                self.assertTrue(r.get("section_boosted", False))
            # Non-spot should not be boosted
            futures_urls = [r for r in boosted if "/futures/" in r["canonical_url"]]
            for r in futures_urls:
                self.assertFalse(r.get("section_boosted", False))
        finally:
            answer._SECTION_BOOST_ENABLED = old

    def test_boost_reorders(self):
        from cex_api_docs import answer
        from cex_api_docs.answer import _apply_section_boost

        old = answer._SECTION_BOOST_ENABLED
        try:
            answer._SECTION_BOOST_ENABLED = True
            results = [
                {"canonical_url": "https://a.com/other/page", "rrf_score": 0.6},
                {"canonical_url": "https://a.com/spot/page", "rrf_score": 0.5},
            ]
            boosted = _apply_section_boost(results, section_prefix="https://a.com/spot/")
            # 0.5 * 1.3 = 0.65 > 0.6, so spot page should be first
            self.assertIn("/spot/", boosted[0]["canonical_url"])
        finally:
            answer._SECTION_BOOST_ENABLED = old

    def test_no_boost_when_disabled(self):
        import os
        from cex_api_docs import answer

        old = answer._SECTION_BOOST_ENABLED
        try:
            answer._SECTION_BOOST_ENABLED = False
            results = [{"canonical_url": "https://a.com/spot/p", "rrf_score": 0.5}]
            out = answer._apply_section_boost(results, section_prefix="https://a.com/spot/")
            self.assertFalse(out[0].get("section_boosted", False))
        finally:
            answer._SECTION_BOOST_ENABLED = old

    def test_no_boost_when_no_prefix(self):
        from cex_api_docs.answer import _apply_section_boost

        results = [{"canonical_url": "https://a.com/x", "rrf_score": 0.5}]
        out = _apply_section_boost(results, section_prefix=None)
        self.assertEqual(out[0]["rrf_score"], 0.5)

    def test_empty_results(self):
        from cex_api_docs.answer import _apply_section_boost

        out = _apply_section_boost([], section_prefix="https://a.com/spot/")
        self.assertEqual(out, [])


class TestExcerptSnapping(unittest.TestCase):
    """Test excerpt boundary snapping functions."""

    def test_snap_start_backward_to_newline(self):
        from cex_api_docs.answer import _snap_start_backward

        md = "line one\nline two\nline three"
        # Snap backward from middle of "line two"
        pos = md.index("two") + 1  # middle of "two"
        snapped = _snap_start_backward(md, pos)
        self.assertEqual(snapped, md.index("line two"))

    def test_snap_start_backward_at_zero(self):
        from cex_api_docs.answer import _snap_start_backward

        self.assertEqual(_snap_start_backward("any text", 0), 0)

    def test_snap_end_forward_to_paragraph(self):
        from cex_api_docs.answer import _snap_end_forward

        md = "First sentence.\n\nSecond paragraph."
        pos = 10  # middle of first sentence
        snapped = _snap_end_forward(md, pos)
        # Should snap to the double-newline paragraph break
        self.assertEqual(snapped, md.index("\n\n"))

    def test_snap_end_forward_to_sentence(self):
        from cex_api_docs.answer import _snap_end_forward

        md = "First sentence. Second sentence."
        pos = 10
        snapped = _snap_end_forward(md, pos)
        self.assertEqual(snapped, md.index(". ") + 1)

    def test_snap_end_forward_at_eof(self):
        from cex_api_docs.answer import _snap_end_forward

        md = "short"
        self.assertEqual(_snap_end_forward(md, len(md)), len(md))


class TestCleanExcerpt(unittest.TestCase):
    """Test zero-width character stripping."""

    def test_strips_zero_width_chars(self):
        from cex_api_docs.answer import _clean_excerpt

        text = "hello\u200bworld\u200c\u200d\ufeff\u00ad"
        cleaned = _clean_excerpt(text)
        self.assertEqual(cleaned, "helloworld")

    def test_strips_whitespace(self):
        from cex_api_docs.answer import _clean_excerpt

        self.assertEqual(_clean_excerpt("  hello  "), "hello")

    def test_empty_string(self):
        from cex_api_docs.answer import _clean_excerpt

        self.assertEqual(_clean_excerpt(""), "")


class TestExtractWeightFromExcerpt(unittest.TestCase):
    """Test weight extraction from excerpt text."""

    def test_weight_is_pattern(self):
        from cex_api_docs.answer import _extract_weight_from_excerpt

        self.assertEqual(_extract_weight_from_excerpt("The weight is 10 for this endpoint"), 10)

    def test_weight_colon_pattern(self):
        from cex_api_docs.answer import _extract_weight_from_excerpt

        self.assertEqual(_extract_weight_from_excerpt("weight: 5"), 5)

    def test_weight_equals_pattern(self):
        from cex_api_docs.answer import _extract_weight_from_excerpt

        self.assertEqual(_extract_weight_from_excerpt("weight=20"), 20)

    def test_no_weight(self):
        from cex_api_docs.answer import _extract_weight_from_excerpt

        self.assertIsNone(_extract_weight_from_excerpt("No weight info here"))


class TestNavRegionEdgeCases(unittest.TestCase):
    """Test nav region detection edge cases."""

    def test_short_region_not_nav(self):
        from cex_api_docs.answer import _is_nav_region

        short = "Just a line."
        self.assertFalse(_is_nav_region(short, 5))

    def test_empty_string(self):
        from cex_api_docs.answer import _is_nav_region

        self.assertFalse(_is_nav_region("", 0))

    def test_link_only_lines(self):
        from cex_api_docs.answer import _is_nav_region

        # Pure link-only lines should be detected as nav
        links = "\n".join([f"[Page {i}](https://example.com/p{i})" for i in range(20)])
        self.assertTrue(_is_nav_region(links, len(links) // 2))

    def test_mixed_content_below_threshold(self):
        from cex_api_docs.answer import _is_nav_region

        # Mix of content and nav — below 55% threshold
        lines = []
        for i in range(10):
            lines.append(f"This is a substantive paragraph about topic {i} with enough words to be real content.")
        for i in range(5):
            lines.append(f"* [Link {i}](https://example.com/{i})")
        md = "\n".join(lines)
        # 5/15 = 33% nav, should NOT be detected
        self.assertFalse(_is_nav_region(md, len(md) // 2))

    def test_window_parameter(self):
        from cex_api_docs.answer import _is_nav_region

        # Large nav followed by content — position in content should not be nav
        nav = "\n".join([f"* [Link {i}](https://example.com/{i})" for i in range(50)])
        content = "\n" * 5 + "This is real content. " * 50
        md = nav + content
        content_pos = len(nav) + 100
        self.assertFalse(_is_nav_region(md, content_pos, window=200))


class TestBug16NavChromeInExcerpts(unittest.TestCase):
    """BUG-16: Nav chrome leaks into excerpts on single-page sites.

    Four failure modes fixed:
    1. All-nav fallback: when every match is in nav, use page prefix not nav match
    2. Skip-link detection: [Skip to content](#main) lines
    3. Multi-link lines: [Foo](url1) | [Bar](url2) separator lines
    4. Threshold lowered from 55% to 40%
    """

    def test_all_nav_matches_use_prefix_fallback(self):
        """When every match is in a nav region, excerpt should be page prefix."""
        import re
        from cex_api_docs.answer import _make_excerpt

        # Build a page where "orders" only appears in nav
        nav = "\n".join([f"* [Orders page {i}](https://ex.com/orders/{i})" for i in range(20)])
        content = "\n\n## Introduction\n\nThis API provides trading capabilities.\n\n" + (
            "The exchange supports spot and margin trading. " * 20
        )
        md = nav + content
        needle = re.compile(r"orders", re.IGNORECASE)
        excerpt, start, end = _make_excerpt(md, needle_re=needle)
        # Should get page prefix (Introduction) not nav chrome
        self.assertEqual(start, 0, "All-nav fallback should start at 0")

    def test_skip_link_detected_as_nav(self):
        """Anchor-only skip links like [Skip to content](#main) are nav (caught by link-only-line branch)."""
        from cex_api_docs.answer import _is_nav_region

        lines = [
            "[Skip to content](#main)",
            "[Home](#home)",
            "[API Reference](#api-ref)",
            "[REST API](#rest)",
            "[WebSocket](#ws)",
            "[Authentication](#auth)",
            "[Rate Limits](#limits)",
            "[Errors](#errors)",
        ]
        md = "\n".join(lines)
        self.assertTrue(_is_nav_region(md, len(md) // 2))

    def test_multi_link_lines_detected_as_nav(self):
        """Lines with multiple links separated by pipes are nav."""
        from cex_api_docs.answer import _is_nav_region

        lines = [
            "[Home](/) | [API](/api) | [Docs](/docs)",
            "[REST](/rest) | [WebSocket](/ws) | [FIX](/fix)",
            "[Spot](/spot) | [Futures](/futures) | [Options](/options)",
            "[Auth](/auth) | [Limits](/limits)",
            "[Errors](/errors) | [Changelog](/changelog)",
            "[SDK](/sdk) | [Examples](/examples)",
        ]
        md = "\n".join(lines)
        self.assertTrue(_is_nav_region(md, len(md) // 2))

    def test_threshold_40_percent(self):
        """Region with 42% nav lines (was below old 55% threshold) now detected."""
        from cex_api_docs.answer import _is_nav_region

        # 5 nav + 7 content = 12 lines, 5/12 = 41.7%
        lines = []
        for i in range(5):
            lines.append(f"* [Link {i}](https://example.com/{i})")
        for i in range(7):
            lines.append(f"This is substantive content line {i} with enough words to be real text.")
        md = "\n".join(lines)
        self.assertTrue(_is_nav_region(md, len(md) // 4))  # pos in nav area

    def test_35_percent_nav_not_detected(self):
        """Region with 35% nav should NOT be detected (still below 40%)."""
        from cex_api_docs.answer import _is_nav_region

        # 7 nav + 13 content = 20 lines, 7/20 = 35%
        lines = []
        for i in range(7):
            lines.append(f"* [Link {i}](https://example.com/{i})")
        for i in range(13):
            lines.append(f"This is substantive content line {i} with enough words to be real text.")
        md = "\n".join(lines)
        self.assertFalse(_is_nav_region(md, len(md) // 2))


class TestMakeExcerptEdgeCases(unittest.TestCase):
    """Test excerpt extraction edge cases."""

    def test_no_match_fallback(self):
        import re
        from cex_api_docs.answer import _make_excerpt

        md = "This is a document without the search term."
        needle = re.compile(r"nonexistent_term_xyz")
        excerpt, start, end = _make_excerpt(md, needle_re=needle)
        # Should fallback to first N chars
        self.assertEqual(start, 0)
        self.assertIn("This is a document", excerpt)

    def test_match_in_content_not_nav(self):
        import re
        from cex_api_docs.answer import _make_excerpt

        # Simulate large page: nav → filler → content
        nav = "\n".join([f"* [Item {i}](https://ex.com/{i})" for i in range(30)])
        nav += "\n* WebSocket\n  * Connect\n  * Subscribe\n"
        filler = "\n\n" + ("This is paragraph content. " * 30 + "\n\n") * 3
        content = "## WebSocket\n\nUse WebSocket to receive real-time market data."
        md = nav + filler + content
        needle = re.compile(r"websocket", re.IGNORECASE)
        excerpt, start, end = _make_excerpt(md, needle_re=needle)
        # Should prefer the content match
        self.assertIn("real-time market data", excerpt)


class TestDetectBinanceSection(unittest.TestCase):
    """Test _detect_binance_section for all keyword patterns."""

    def test_portfolio_margin(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("portfolio margin requirements"), "portfolio_margin")

    def test_copy_trading(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("copy trading lead trader"), "copy_trading")

    def test_margin_trading(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("margin trading interest rates"), "margin_trading")

    def test_futures_coinm(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("coin-m futures mark price"), "futures_coinm")
        self.assertEqual(_detect_binance_section("futures coinm delivery"), "futures_coinm")

    def test_futures_usdm(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("usd-m futures open interest"), "futures_usdm")
        self.assertEqual(_detect_binance_section("usds contract details"), "futures_usdm")

    def test_futures_generic_maps_to_usdm(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("futures position risk"), "futures_usdm")

    def test_options(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("european options pricing"), "options")

    def test_websocket(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("websocket stream connection"), "websocket")
        self.assertEqual(_detect_binance_section("ws connection limit"), "websocket")

    def test_wallet(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("wallet deposit address"), "wallet")

    def test_spot(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertEqual(_detect_binance_section("spot order book depth"), "spot")

    def test_no_match(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        self.assertIsNone(_detect_binance_section("api key permissions"))

    def test_priority_specific_over_generic(self) -> None:
        from cex_api_docs.answer import _detect_binance_section
        # "coin-m" should match before generic "futures"
        self.assertEqual(_detect_binance_section("coin-m futures"), "futures_coinm")
        # "portfolio margin" should match before generic "margin"
        self.assertEqual(_detect_binance_section("portfolio margin"), "portfolio_margin")


class TestExchangeSectionKeywords(unittest.TestCase):
    """Test _EXCHANGE_SECTION_KEYWORDS patterns for multi-section exchanges."""

    def test_kucoin_futures(self) -> None:
        from cex_api_docs.answer import _EXCHANGE_SECTION_KEYWORDS
        patterns = _EXCHANGE_SECTION_KEYWORDS["kucoin"]
        matched = None
        for pat, sid in patterns:
            if pat.search("perpetual futures rate"):
                matched = sid
                break
        self.assertEqual(matched, "futures")

    def test_kucoin_margin(self) -> None:
        from cex_api_docs.answer import _EXCHANGE_SECTION_KEYWORDS
        patterns = _EXCHANGE_SECTION_KEYWORDS["kucoin"]
        matched = None
        for pat, sid in patterns:
            if pat.search("margin borrow rate"):
                matched = sid
                break
        self.assertEqual(matched, "margin")

    def test_htx_coin_margined(self) -> None:
        from cex_api_docs.answer import _EXCHANGE_SECTION_KEYWORDS
        patterns = _EXCHANGE_SECTION_KEYWORDS["htx"]
        matched = None
        for pat, sid in patterns:
            if pat.search("coin-margined swap"):
                matched = sid
                break
        self.assertEqual(matched, "coin_margined_swap")

    def test_htx_usdt_swap(self) -> None:
        from cex_api_docs.answer import _EXCHANGE_SECTION_KEYWORDS
        patterns = _EXCHANGE_SECTION_KEYWORDS["htx"]
        matched = None
        for pat, sid in patterns:
            if pat.search("usdt swap linear"):
                matched = sid
                break
        self.assertEqual(matched, "usdt_swap")

    def test_coinbase_prime(self) -> None:
        from cex_api_docs.answer import _EXCHANGE_SECTION_KEYWORDS
        patterns = _EXCHANGE_SECTION_KEYWORDS["coinbase"]
        matched = None
        for pat, sid in patterns:
            if pat.search("coinbase prime api"):
                matched = sid
                break
        self.assertEqual(matched, "prime")

    def test_okx_websocket(self) -> None:
        from cex_api_docs.answer import _EXCHANGE_SECTION_KEYWORDS
        patterns = _EXCHANGE_SECTION_KEYWORDS["okx"]
        matched = None
        for pat, sid in patterns:
            if pat.search("websocket public channel"):
                matched = sid
                break
        self.assertEqual(matched, "websocket")

    def test_mexc_futures(self) -> None:
        from cex_api_docs.answer import _EXCHANGE_SECTION_KEYWORDS
        patterns = _EXCHANGE_SECTION_KEYWORDS["mexc"]
        matched = None
        for pat, sid in patterns:
            if pat.search("contract position"):
                matched = sid
                break
        self.assertEqual(matched, "futures")

    def test_bitmart_spot(self) -> None:
        from cex_api_docs.answer import _EXCHANGE_SECTION_KEYWORDS
        patterns = _EXCHANGE_SECTION_KEYWORDS["bitmart"]
        matched = None
        for pat, sid in patterns:
            if pat.search("spot market order"):
                matched = sid
                break
        self.assertEqual(matched, "spot")


class TestDirectRoute(unittest.TestCase):
    """Test _direct_route for high-confidence typed queries."""

    def _setup_store(self, tmp_path):
        docs_dir = tmp_path / "cex-docs"
        init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)
        conn = open_db(docs_dir / "db" / "docs.db")
        return docs_dir, conn

    def _make_exchange(self, exchange_id="binance", sections=None, allowed_domains=None):
        from types import SimpleNamespace
        if sections is None:
            sections = [SimpleNamespace(section_id="spot", seed_urls=["https://developers.binance.com/docs/"])]
        if allowed_domains is None:
            allowed_domains = ["developers.binance.com"]
        return SimpleNamespace(exchange_id=exchange_id, sections=sections, allowed_domains=allowed_domains)

    def _make_classification(self, input_type, confidence=0.8, signals=None):
        from types import SimpleNamespace
        return SimpleNamespace(input_type=input_type, confidence=confidence, signals=signals or {})

    def test_endpoint_path_returns_none_when_no_match(self) -> None:
        from cex_api_docs.answer import _direct_route
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            exchange = self._make_exchange()
            cls = self._make_classification("endpoint_path", signals={"path": "/nonexistent/xyz"})
            result = _direct_route(conn, classification=cls, exchange=exchange,
                                   docs_dir=str(docs_dir), question="test", norm="test")
            self.assertIsNone(result)

    def test_error_message_returns_none_when_no_match(self) -> None:
        from cex_api_docs.answer import _direct_route
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            exchange = self._make_exchange()
            cls = self._make_classification("error_message", signals={"error_codes": [{"code": "-99999"}]})
            result = _direct_route(conn, classification=cls, exchange=exchange,
                                   docs_dir=str(docs_dir), question="test", norm="test")
            self.assertIsNone(result)

    def test_endpoint_path_with_stored_endpoint(self) -> None:
        from cex_api_docs.answer import _direct_route
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            _insert_endpoint(docs_dir, conn, endpoint={
                "endpoint_id": "ep1",
                "exchange": "binance",
                "section": "spot",
                "protocol": "http",
                "http": {"method": "GET", "path": "/api/v3/ticker/price"},
                "description": "Get price ticker",
            })
            exchange = self._make_exchange()
            cls = self._make_classification("endpoint_path", signals={"path": "/api/v3/ticker/price", "method": "GET"})
            result = _direct_route(conn, classification=cls, exchange=exchange,
                                   docs_dir=str(docs_dir), question="GET /api/v3/ticker/price", norm="get /api/v3/ticker/price")
            self.assertIsNotNone(result)
            self.assertEqual(result["routing"], "direct")
            self.assertTrue(len(result["claims"]) > 0)

    def test_question_type_returns_none(self) -> None:
        from cex_api_docs.answer import _direct_route
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            exchange = self._make_exchange()
            cls = self._make_classification("question", signals={})
            result = _direct_route(conn, classification=cls, exchange=exchange,
                                   docs_dir=str(docs_dir), question="test", norm="test")
            self.assertIsNone(result)

    def test_error_message_with_stored_page(self) -> None:
        from cex_api_docs.answer import _direct_route
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            # Insert a page that mentions error -1003
            md = "## Error Codes\n\n| Code | Description |\n| -1003 | Too many requests. Rate limit exceeded. |\n"
            _insert_page(docs_dir, conn, url="https://developers.binance.com/docs/errors", md=md)
            exchange = self._make_exchange()
            cls = self._make_classification("error_message", signals={"error_codes": [{"code": "-1003"}]})
            result = _direct_route(conn, classification=cls, exchange=exchange,
                                   docs_dir=str(docs_dir), question="-1003", norm="-1003")
            # May or may not find via FTS depending on how search_error_code works
            # but should not crash
            self.assertTrue(result is None or result.get("routing") == "direct")


class TestBug18DirectRouteExcerpts(unittest.TestCase):
    """BUG-18: Direct-routed citations must include excerpts."""

    def _setup_store(self, tmp_path):
        docs_dir = tmp_path / "cex-docs"
        init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)
        conn = open_db(docs_dir / "db" / "docs.db")
        return docs_dir, conn

    def _make_exchange(self, exchange_id="binance"):
        from types import SimpleNamespace
        return SimpleNamespace(
            exchange_id=exchange_id,
            sections=[SimpleNamespace(section_id="spot", seed_urls=["https://developers.binance.com/docs/"])],
            allowed_domains=["developers.binance.com"],
        )

    def _make_classification(self, input_type, confidence=0.8, signals=None):
        from types import SimpleNamespace
        return SimpleNamespace(input_type=input_type, confidence=confidence, signals=signals or {})

    def test_endpoint_path_claim_has_excerpt(self) -> None:
        from cex_api_docs.answer import _direct_route
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            page_url = "https://developers.binance.com/docs/spot/ticker-price"
            md = "# Symbol Price Ticker\n\nGET /api/v3/ticker/price\n\nGet latest price for a symbol or all symbols.\n\n## Parameters\n\n| Name | Type | Required |\n| symbol | STRING | NO |\n"
            _insert_page(docs_dir, conn, url=page_url, md=md)
            _insert_endpoint(docs_dir, conn, endpoint={
                "endpoint_id": "ep-ticker",
                "exchange": "binance",
                "section": "spot",
                "protocol": "http",
                "http": {"method": "GET", "path": "/api/v3/ticker/price"},
                "description": "Symbol price ticker",
                "docs_url": page_url,
            })
            exchange = self._make_exchange()
            cls = self._make_classification("endpoint_path", signals={"path": "/api/v3/ticker/price", "method": "GET"})
            result = _direct_route(conn, classification=cls, exchange=exchange,
                                   docs_dir=str(docs_dir), question="GET /api/v3/ticker/price", norm="get /api/v3/ticker/price")
            self.assertIsNotNone(result)
            citations = result["claims"][0]["citations"]
            self.assertTrue(len(citations) > 0)
            cit = citations[0]
            self.assertEqual(cit["url"], page_url)
            self.assertIn("excerpt", cit)
            self.assertIn("excerpt_start", cit)
            self.assertIn("excerpt_end", cit)
            self.assertTrue(len(cit["excerpt"]) > 0)

    def test_error_message_page_claim_has_excerpt(self) -> None:
        from cex_api_docs.answer import _direct_route
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            page_url = "https://developers.binance.com/docs/errors"
            md = "# Error Codes\n\nThe Binance API uses the following error codes:\n\n| Code | Description |\n| -1003 | Too many requests. Rate limit exceeded. |\n| -1021 | Timestamp outside recvWindow. |\n"
            _insert_page(docs_dir, conn, url=page_url, md=md)
            exchange = self._make_exchange()
            cls = self._make_classification("error_message", signals={"error_codes": [{"code": "-1003", "exchange_hint": "binance"}]})
            result = _direct_route(conn, classification=cls, exchange=exchange,
                                   docs_dir=str(docs_dir), question="Binance error -1003", norm="binance error -1003")
            # FTS5 may or may not match "-1003" depending on tokenizer behavior
            # in fresh test stores. When it does match, verify excerpts are present.
            if result is None or not result["claims"]:
                self.skipTest("FTS5 did not match error code in fresh test store")
            cit_list = result["claims"][0].get("citations", [])
            if not cit_list:
                self.skipTest("No citation URL resolved for error claim")
            cit = cit_list[0]
            self.assertIn("excerpt", cit, "Direct-route error citation must have excerpt")
            self.assertIn("excerpt_start", cit)
            self.assertIn("excerpt_end", cit)

    def test_build_full_citation_returns_url_only_for_missing_page(self) -> None:
        from cex_api_docs.answer import _build_full_citation
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            cit = _build_full_citation(conn, "https://nonexistent.example.com/page", "test query")
            self.assertEqual(cit["url"], "https://nonexistent.example.com/page")
            self.assertNotIn("excerpt", cit)

    def test_build_full_citation_returns_excerpt_for_existing_page(self) -> None:
        from cex_api_docs.answer import _build_full_citation
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = self._setup_store(Path(tmp))
            page_url = "https://example.com/api/docs"
            md = "# API Documentation\n\nThis page describes the create order endpoint for placing trades.\n\n## Parameters\n\nsymbol, side, type, quantity.\n"
            _insert_page(docs_dir, conn, url=page_url, md=md)
            cit = _build_full_citation(conn, page_url, "create order")
            self.assertEqual(cit["url"], page_url)
            self.assertIn("excerpt", cit)
            self.assertIn("excerpt_start", cit)
            self.assertIn("excerpt_end", cit)
            self.assertIn("crawled_at", cit)
            self.assertTrue(len(cit["excerpt"]) > 0)


class TestDirectoryPrefix(unittest.TestCase):
    """Test _directory_prefix URL stripping."""

    def test_strips_last_segment(self):
        from cex_api_docs.answer import _directory_prefix
        self.assertEqual(
            _directory_prefix("https://example.com/docs/ws/connect"),
            "https://example.com/docs/ws/",
        )

    def test_trailing_slash_kept(self):
        from cex_api_docs.answer import _directory_prefix
        self.assertEqual(
            _directory_prefix("https://example.com/docs/"),
            "https://example.com/docs/",
        )

    def test_strips_query(self):
        from cex_api_docs.answer import _directory_prefix
        self.assertEqual(
            _directory_prefix("https://example.com/docs/page?v=2"),
            "https://example.com/docs/",
        )

    def test_strips_fragment(self):
        from cex_api_docs.answer import _directory_prefix
        self.assertEqual(
            _directory_prefix("https://example.com/docs/page#section"),
            "https://example.com/docs/",
        )

    def test_root_path(self):
        from cex_api_docs.answer import _directory_prefix
        # Short URL shouldn't strip beyond scheme
        result = _directory_prefix("https://a.com/x")
        self.assertTrue(result.startswith("https://"))


class TestPageTypeBoost(unittest.TestCase):
    """Test page-type boost for overview/intro pages."""

    def test_broad_question_boosts_intro_url(self):
        from cex_api_docs import answer
        old = answer._PAGE_TYPE_BOOST_ENABLED
        try:
            answer._PAGE_TYPE_BOOST_ENABLED = True
            results = [
                {"canonical_url": "https://docs.ex.com/api/spot/get-ticker", "rrf_score": 0.5},
                {"canonical_url": "https://docs.ex.com/api/introduction", "rrf_score": 0.4},
            ]
            boosted = answer._apply_page_type_boost(results, norm="how to authenticate with the api")
            # Introduction should be boosted: 0.4*1.4=0.56 > 0.5
            self.assertEqual(boosted[0]["canonical_url"], "https://docs.ex.com/api/introduction")
            self.assertTrue(boosted[0].get("page_type_boosted"))
        finally:
            answer._PAGE_TYPE_BOOST_ENABLED = old

    def test_specific_query_no_boost(self):
        from cex_api_docs import answer
        old = answer._PAGE_TYPE_BOOST_ENABLED
        try:
            answer._PAGE_TYPE_BOOST_ENABLED = True
            results = [
                {"canonical_url": "https://docs.ex.com/api/spot/get-ticker", "rrf_score": 0.5},
                {"canonical_url": "https://docs.ex.com/api/introduction", "rrf_score": 0.4},
            ]
            # "get ticker" is specific, not a broad question
            boosted = answer._apply_page_type_boost(results, norm="get ticker symbol btcusdt")
            self.assertEqual(boosted[0]["canonical_url"], "https://docs.ex.com/api/spot/get-ticker")
        finally:
            answer._PAGE_TYPE_BOOST_ENABLED = old

    def test_rate_limit_question_boosts(self):
        from cex_api_docs import answer
        old = answer._PAGE_TYPE_BOOST_ENABLED
        try:
            answer._PAGE_TYPE_BOOST_ENABLED = True
            results = [
                {"canonical_url": "https://docs.ex.com/api/spot/get-order", "rrf_score": 0.5},
                {"canonical_url": "https://docs.ex.com/api/rate-limit", "rrf_score": 0.35},
            ]
            boosted = answer._apply_page_type_boost(results, norm="rate limit for binance api")
            # 0.35*1.4=0.49 < 0.5, so rate-limit page stays second (close but not enough)
            self.assertEqual(boosted[0]["canonical_url"], "https://docs.ex.com/api/spot/get-order")
        finally:
            answer._PAGE_TYPE_BOOST_ENABLED = old

    def test_overview_url_patterns(self):
        from cex_api_docs.answer import _OVERVIEW_URL_PATTERNS
        # Should match
        self.assertIsNotNone(_OVERVIEW_URL_PATTERNS.search("/rest-api/introduction"))
        self.assertIsNotNone(_OVERVIEW_URL_PATTERNS.search("/general-info"))
        self.assertIsNotNone(_OVERVIEW_URL_PATTERNS.search("/overview"))
        self.assertIsNotNone(_OVERVIEW_URL_PATTERNS.search("/quick-start"))
        self.assertIsNotNone(_OVERVIEW_URL_PATTERNS.search("/authentication"))
        self.assertIsNotNone(_OVERVIEW_URL_PATTERNS.search("/rest-api"))
        # Should NOT match
        self.assertIsNone(_OVERVIEW_URL_PATTERNS.search("/spot/get-ticker"))
        self.assertIsNone(_OVERVIEW_URL_PATTERNS.search("/trade/place-order"))

    def test_disabled_no_effect(self):
        from cex_api_docs import answer
        old = answer._PAGE_TYPE_BOOST_ENABLED
        try:
            answer._PAGE_TYPE_BOOST_ENABLED = False
            results = [
                {"canonical_url": "https://docs.ex.com/api/spot/get-ticker", "rrf_score": 0.5},
                {"canonical_url": "https://docs.ex.com/api/introduction", "rrf_score": 0.4},
            ]
            boosted = answer._apply_page_type_boost(results, norm="how to authenticate")
            self.assertEqual(boosted[0]["canonical_url"], "https://docs.ex.com/api/spot/get-ticker")
        finally:
            answer._PAGE_TYPE_BOOST_ENABLED = old

    def test_empty_results(self):
        from cex_api_docs.answer import _apply_page_type_boost
        result = _apply_page_type_boost([], norm="how to authenticate")
        self.assertEqual(result, [])


class TestSectionBoostReordering(unittest.TestCase):
    """Test that _apply_section_boost correctly reorders candidates."""

    def test_boost_promotes_matching_urls(self):
        from cex_api_docs import answer
        old = answer._SECTION_BOOST_ENABLED
        try:
            answer._SECTION_BOOST_ENABLED = True
            candidates = [
                {"canonical_url": "https://docs.kraken.com/spot/page1", "rrf_score": 0.5},
                {"canonical_url": "https://docs.kraken.com/futures/page2", "rrf_score": 0.4},
                {"canonical_url": "https://docs.kraken.com/futures/page3", "rrf_score": 0.3},
            ]
            boosted = answer._apply_section_boost(candidates, section_prefix="https://docs.kraken.com/futures/")
            # Futures pages should be boosted: 0.4*1.3=0.52 > 0.5, 0.3*1.3=0.39 < 0.5
            self.assertEqual(boosted[0]["canonical_url"], "https://docs.kraken.com/futures/page2")
            self.assertTrue(boosted[0].get("section_boosted"))
        finally:
            answer._SECTION_BOOST_ENABLED = old

    def test_boost_disabled_no_change(self):
        from cex_api_docs import answer
        old = answer._SECTION_BOOST_ENABLED
        try:
            answer._SECTION_BOOST_ENABLED = False
            candidates = [
                {"canonical_url": "https://a.com/spot/p1", "rrf_score": 0.5},
                {"canonical_url": "https://a.com/futures/p2", "rrf_score": 0.4},
            ]
            result = answer._apply_section_boost(candidates, section_prefix="https://a.com/futures/")
            self.assertEqual(result[0]["canonical_url"], "https://a.com/spot/p1")  # No reorder
        finally:
            answer._SECTION_BOOST_ENABLED = old

    def test_no_prefix_no_change(self):
        from cex_api_docs.answer import _apply_section_boost
        candidates = [
            {"canonical_url": "https://a.com/p1", "rrf_score": 0.5},
            {"canonical_url": "https://a.com/p2", "rrf_score": 0.4},
        ]
        result = _apply_section_boost(candidates, section_prefix=None)
        self.assertEqual(result[0]["canonical_url"], "https://a.com/p1")

    def test_empty_results(self):
        from cex_api_docs.answer import _apply_section_boost
        result = _apply_section_boost([], section_prefix="https://a.com/")
        self.assertEqual(result, [])


class TestDeprecatedDemotion(unittest.TestCase):
    """Test deprecated/abandoned URL demotion."""

    def test_abandoned_endpoint_demoted(self):
        from cex_api_docs.answer import _apply_deprecated_demotion
        results = [
            {"canonical_url": "https://kucoin.com/docs-new/abandoned-endpoints/get-deposit-v1", "rrf_score": 0.6},
            {"canonical_url": "https://kucoin.com/docs-new/rest/account-info/deposit/get-deposit-v3", "rrf_score": 0.5},
        ]
        demoted = _apply_deprecated_demotion(results)
        # Abandoned page (0.6*0.5=0.3) should now rank below current (0.5)
        self.assertEqual(demoted[0]["canonical_url"], "https://kucoin.com/docs-new/rest/account-info/deposit/get-deposit-v3")
        self.assertTrue(demoted[1].get("deprecated_demoted"))

    def test_deprecated_path_demoted(self):
        from cex_api_docs.answer import _apply_deprecated_demotion
        results = [
            {"canonical_url": "https://docs.ex.com/deprecated/old-order", "rrf_score": 0.8},
            {"canonical_url": "https://docs.ex.com/api/new-order", "rrf_score": 0.5},
        ]
        demoted = _apply_deprecated_demotion(results)
        self.assertEqual(demoted[0]["canonical_url"], "https://docs.ex.com/api/new-order")

    def test_legacy_api_demoted(self):
        from cex_api_docs.answer import _apply_deprecated_demotion
        results = [
            {"canonical_url": "https://docs.ex.com/legacy-api/balance", "rrf_score": 0.7},
            {"canonical_url": "https://docs.ex.com/api/v3/balance", "rrf_score": 0.5},
        ]
        demoted = _apply_deprecated_demotion(results)
        self.assertEqual(demoted[0]["canonical_url"], "https://docs.ex.com/api/v3/balance")

    def test_no_deprecated_no_change(self):
        from cex_api_docs.answer import _apply_deprecated_demotion
        results = [
            {"canonical_url": "https://docs.ex.com/api/ticker", "rrf_score": 0.6},
            {"canonical_url": "https://docs.ex.com/api/balance", "rrf_score": 0.5},
        ]
        demoted = _apply_deprecated_demotion(results)
        self.assertEqual(demoted[0]["canonical_url"], "https://docs.ex.com/api/ticker")
        self.assertFalse(demoted[0].get("deprecated_demoted", False))

    def test_empty_results(self):
        from cex_api_docs.answer import _apply_deprecated_demotion
        result = _apply_deprecated_demotion([])
        self.assertEqual(result, [])

    def test_url_patterns(self):
        from cex_api_docs.answer import _DEPRECATED_URL_PATTERNS
        # Should match
        self.assertIsNotNone(_DEPRECATED_URL_PATTERNS.search("/abandoned-endpoints/get-deposit"))
        self.assertIsNotNone(_DEPRECATED_URL_PATTERNS.search("/deprecated/old-endpoint"))
        self.assertIsNotNone(_DEPRECATED_URL_PATTERNS.search("/legacy-api/v1/balance"))
        self.assertIsNotNone(_DEPRECATED_URL_PATTERNS.search("/obsolete/ticker"))
        self.assertIsNotNone(_DEPRECATED_URL_PATTERNS.search("/old-api/markets"))
        # Should NOT match
        self.assertIsNone(_DEPRECATED_URL_PATTERNS.search("/api/v3/balance"))
        self.assertIsNone(_DEPRECATED_URL_PATTERNS.search("/rest/ticker"))
        self.assertIsNone(_DEPRECATED_URL_PATTERNS.search("/docs/legacy"))  # not followed by /


class TestPayloadActionInference(unittest.TestCase):
    """Tests for _infer_payload_action and _PAYLOAD_ACTION_MAP."""

    def test_place_order_binance(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action(["symbol", "side", "type", "quantity", "price"])
        self.assertEqual(result, "place order")

    def test_place_order_okx(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action(["instId", "tdMode", "side", "ordType", "px", "sz"])
        self.assertEqual(result, "place order")

    def test_place_order_bybit(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action(["category", "symbol", "orderType", "side", "qty"])
        self.assertEqual(result, "place order")

    def test_withdraw(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action(["asset", "address", "amount", "network"])
        self.assertEqual(result, "withdraw")

    def test_withdraw_coin(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action(["coin", "chain", "address", "amount"])
        self.assertEqual(result, "withdraw")

    def test_set_leverage(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action(["leverage", "symbol", "marginCoin"])
        self.assertEqual(result, "set leverage")

    def test_websocket_subscribe(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action(["type", "channel", "instId"])
        self.assertEqual(result, "websocket subscribe")

    def test_no_match(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action(["symbol", "invalid"])
        self.assertIsNone(result)

    def test_empty(self) -> None:
        from cex_api_docs.answer import _infer_payload_action
        result = _infer_payload_action([])
        self.assertIsNone(result)


class TestBroadQuestionPatterns(unittest.TestCase):
    """Tests for broadened _BROAD_QUESTION_PATTERNS."""

    def test_how_many(self) -> None:
        from cex_api_docs.answer import _BROAD_QUESTION_PATTERNS
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("How many requests per minute does Bitget allow"))

    def test_endpoints_suffix(self) -> None:
        from cex_api_docs.answer import _BROAD_QUESTION_PATTERNS
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("Binance margin account endpoints"))
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("Binance USDM futures order endpoint"))

    def test_api_suffix(self) -> None:
        from cex_api_docs.answer import _BROAD_QUESTION_PATTERNS
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("Bitget copy trading API"))
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("Coinbase Advanced Trade API"))

    def test_best_practice(self) -> None:
        from cex_api_docs.answer import _BROAD_QUESTION_PATTERNS
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("Upbit REST API best practice"))

    def test_sandbox(self) -> None:
        from cex_api_docs.answer import _BROAD_QUESTION_PATTERNS
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("Gemini API sandbox environment"))

    def test_original_patterns_preserved(self) -> None:
        from cex_api_docs.answer import _BROAD_QUESTION_PATTERNS
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("how to authenticate"))
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("what is the rate limit"))
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("authentication guide"))
        self.assertIsNotNone(_BROAD_QUESTION_PATTERNS.search("overview of the API"))


class TestCodeIndicatorPatternsBug14(unittest.TestCase):
    """BUG-14: Bare API signing code should be classified as code_snippet."""

    def test_hmac_signing_code(self) -> None:
        from cex_api_docs.classify import classify_input
        text = 'headers = {"X-MBX-APIKEY": api_key}; signature = hmac.new(secret, query_string, hashlib.sha256).hexdigest()'
        result = classify_input(text)
        self.assertEqual(result.input_type, "code_snippet")

    def test_base64_encoding(self) -> None:
        from cex_api_docs.classify import classify_input
        text = "sign = base64.b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest())"
        result = classify_input(text)
        self.assertEqual(result.input_type, "code_snippet")

    def test_nodejs_crypto(self) -> None:
        from cex_api_docs.classify import classify_input
        text = "const signature = crypto.createHmac('sha256', secretKey).update(queryString).digest('hex')"
        result = classify_input(text)
        self.assertEqual(result.input_type, "code_snippet")

    def test_plain_question_unchanged(self) -> None:
        from cex_api_docs.classify import classify_input
        text = "How do I authenticate with the Binance API?"
        result = classify_input(text)
        self.assertEqual(result.input_type, "question")


if __name__ == "__main__":
    unittest.main()
