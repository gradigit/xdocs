"""Tests for resolve_docs_urls module."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from xdocs.resolve_docs_urls import (
    _is_spec_url,
    _path_segments,
    link_endpoints_bulk,
    resolve_docs_url,
)
from xdocs.store import init_store

REPO_ROOT = Path(__file__).resolve().parents[1]


def _setup_store(tmp: str) -> tuple[Path, sqlite3.Connection]:
    """Create a temporary store and return (docs_dir, conn)."""
    docs_dir = Path(tmp) / "cex-docs"
    schema_path = REPO_ROOT / "schema" / "schema.sql"
    init_store(docs_dir=str(docs_dir), schema_sql_path=schema_path, lock_timeout_s=1.0)
    db_path = docs_dir / "db" / "docs.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return docs_dir, conn


def _add_page(conn: sqlite3.Connection, docs_dir: Path, url: str, title: str, markdown: str) -> None:
    """Insert a page and its FTS entry."""
    from urllib.parse import urlsplit
    import hashlib

    host = urlsplit(url).hostname or ""
    path_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    content_hash = hashlib.sha256(markdown.encode()).hexdigest()[:16]

    # Write markdown file.
    md_dir = docs_dir / "pages" / path_hash
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / "page.md"
    md_path.write_text(markdown, encoding="utf-8")

    conn.execute(
        """INSERT INTO pages (canonical_url, url, final_url, domain, path_hash,
           title, http_status, content_hash, markdown_path, word_count)
           VALUES (?, ?, ?, ?, ?, ?, 200, ?, ?, ?);""",
        (url, url, url, host, path_hash, title, content_hash, str(md_path), len(markdown.split())),
    )
    page_id = conn.execute("SELECT last_insert_rowid();").fetchone()[0]
    conn.execute(
        "INSERT INTO pages_fts (rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);",
        (page_id, url, title, markdown),
    )
    conn.commit()


def _add_endpoint(conn: sqlite3.Connection, endpoint_id: str, exchange: str, section: str,
                  method: str, path: str, spec_url: str) -> None:
    """Insert an endpoint with a spec source."""
    import json
    from datetime import datetime, timezone

    record = {
        "method": method,
        "path": path,
        "exchange": exchange,
        "section": section,
        "sources": [{"url": spec_url, "field_name": "description"}],
    }
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO endpoints (endpoint_id, exchange, section, protocol, method, path, json, updated_at)
           VALUES (?, ?, ?, 'rest', ?, ?, ?, ?);""",
        (endpoint_id, exchange, section, method, path, json.dumps(record), now),
    )
    # FTS entry.
    conn.execute(
        "INSERT INTO endpoints_fts (endpoint_id, exchange, section, method, path, search_text) VALUES (?, ?, ?, ?, ?, ?);",
        (endpoint_id, exchange, section, method, path, f"{method} {path}"),
    )
    conn.commit()


class TestIsSpecUrl(unittest.TestCase):
    def test_github_raw(self) -> None:
        self.assertTrue(_is_spec_url("https://raw.githubusercontent.com/binance/binance-api-swagger/master/spot_api.yaml"))

    def test_swagger_in_url(self) -> None:
        self.assertTrue(_is_spec_url("https://api.example.com/swagger/v2/spec"))

    def test_yaml_extension(self) -> None:
        self.assertTrue(_is_spec_url("https://example.com/api/openapi.yaml"))

    def test_yml_extension(self) -> None:
        self.assertTrue(_is_spec_url("https://example.com/api.yml"))

    def test_postman_url(self) -> None:
        self.assertTrue(_is_spec_url("https://www.postman.com/collections/abc123"))

    def test_official_docs_page(self) -> None:
        self.assertFalse(_is_spec_url("https://developers.binance.com/docs/wallet/asset/user-universal-transfer"))

    def test_normal_page(self) -> None:
        self.assertFalse(_is_spec_url("https://docs.okx.com/rest-api/"))


class TestPathSegments(unittest.TestCase):
    def test_basic(self) -> None:
        self.assertEqual(_path_segments("/sapi/v1/convert/getQuote"), ["sapi", "convert", "getQuote"])

    def test_skips_versions(self) -> None:
        self.assertEqual(_path_segments("/api/v5/account/balance"), ["account", "balance"])

    def test_short_segments(self) -> None:
        # Single-char segments are skipped.
        self.assertEqual(_path_segments("/v1/a/b/transfer"), ["transfer"])


class TestResolveDocsUrl(unittest.TestCase):
    def test_resolves_matching_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                _add_page(conn, docs_dir,
                          "https://developers.binance.com/docs/wallet/asset/user-universal-transfer",
                          "Universal Transfer",
                          "## Universal Transfer\n\nPOST /sapi/v1/asset/transfer\n\nTransfer between wallets.")
                result = resolve_docs_url(
                    conn, path="/sapi/v1/asset/transfer",
                    exchange="binance", allowed_domains=["developers.binance.com"],
                )
                self.assertEqual(result, "https://developers.binance.com/docs/wallet/asset/user-universal-transfer")
            finally:
                conn.close()

    def test_returns_none_when_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                _add_page(conn, docs_dir,
                          "https://developers.binance.com/docs/wallet/overview",
                          "Wallet Overview",
                          "This is the wallet overview page with no endpoint paths.")
                result = resolve_docs_url(
                    conn, path="/sapi/v1/nonexistent/endpoint",
                    exchange="binance", allowed_domains=["developers.binance.com"],
                )
                self.assertIsNone(result)
            finally:
                conn.close()

    def test_skips_spec_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                # Add a spec page that contains the path.
                _add_page(conn, docs_dir,
                          "https://raw.githubusercontent.com/binance/binance-api-swagger/master/spot_api.yaml",
                          "Spot API Swagger",
                          "/sapi/v1/asset/transfer description: Transfer funds")
                # Add an official docs page that also contains the path.
                _add_page(conn, docs_dir,
                          "https://developers.binance.com/docs/wallet/asset/transfer",
                          "Transfer",
                          "## Transfer\n\nPOST /sapi/v1/asset/transfer\n\nTransfer funds.")
                result = resolve_docs_url(
                    conn, path="/sapi/v1/asset/transfer",
                    exchange="binance", allowed_domains=["developers.binance.com", "raw.githubusercontent.com"],
                )
                # Should pick the official docs page, not the spec.
                self.assertEqual(result, "https://developers.binance.com/docs/wallet/asset/transfer")
            finally:
                conn.close()

    def test_empty_path_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                result = resolve_docs_url(
                    conn, path="", exchange="binance", allowed_domains=["developers.binance.com"],
                )
                self.assertIsNone(result)
            finally:
                conn.close()

    def test_strips_postman_url_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                _add_page(conn, docs_dir,
                          "https://developers.binance.com/docs/convert/trade",
                          "Convert Trade",
                          "## Convert\n\nPOST /sapi/v1/convert/getQuote\n\nGet a quote.")
                result = resolve_docs_url(
                    conn, path="{{url}}/sapi/v1/convert/getQuote",
                    exchange="binance", allowed_domains=["developers.binance.com"],
                )
                self.assertEqual(result, "https://developers.binance.com/docs/convert/trade")
            finally:
                conn.close()


class TestLinkEndpointsBulk(unittest.TestCase):
    def test_links_endpoints_to_docs_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                _add_page(conn, docs_dir,
                          "https://developers.binance.com/docs/wallet/asset/transfer",
                          "Transfer",
                          "## Transfer\n\nPOST /sapi/v1/asset/transfer\n\nTransfer between wallets.")
                _add_endpoint(conn, "ep1", "binance", "spot", "POST", "/sapi/v1/asset/transfer",
                              "https://raw.githubusercontent.com/binance/binance-api-swagger/master/spot_api.yaml")

                result = link_endpoints_bulk(
                    conn, exchange="binance", allowed_domains=["developers.binance.com"],
                )
                self.assertEqual(result["resolved"], 1)
                self.assertEqual(result["skipped"], 0)

                # Verify the docs_url was set.
                row = conn.execute("SELECT docs_url FROM endpoints WHERE endpoint_id = 'ep1';").fetchone()
                self.assertEqual(row["docs_url"], "https://developers.binance.com/docs/wallet/asset/transfer")
            finally:
                conn.close()

    def test_skips_already_linked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                _add_page(conn, docs_dir,
                          "https://developers.binance.com/docs/wallet/asset/transfer",
                          "Transfer",
                          "## Transfer\n\nPOST /sapi/v1/asset/transfer\n\nTransfer between wallets.")
                _add_endpoint(conn, "ep1", "binance", "spot", "POST", "/sapi/v1/asset/transfer",
                              "https://raw.githubusercontent.com/binance/binance-api-swagger/master/spot_api.yaml")
                # Pre-set docs_url.
                conn.execute("UPDATE endpoints SET docs_url = 'https://already.set/' WHERE endpoint_id = 'ep1';")
                conn.commit()

                result = link_endpoints_bulk(
                    conn, exchange="binance", allowed_domains=["developers.binance.com"],
                )
                # Should find 0 since docs_url IS NOT NULL.
                self.assertEqual(result["total"], 0)
            finally:
                conn.close()

    def test_section_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                _add_page(conn, docs_dir,
                          "https://developers.binance.com/docs/wallet/asset/transfer",
                          "Transfer",
                          "## Transfer\n\nPOST /sapi/v1/asset/transfer\n\nTransfer between wallets.")
                _add_endpoint(conn, "ep1", "binance", "spot", "POST", "/sapi/v1/asset/transfer",
                              "https://spec.example.com/spec.yaml")
                _add_endpoint(conn, "ep2", "binance", "futures_usdm", "GET", "/fapi/v1/balance",
                              "https://spec.example.com/spec.yaml")

                result = link_endpoints_bulk(
                    conn, exchange="binance", section="spot",
                    allowed_domains=["developers.binance.com"],
                )
                # Only ep1 should be processed (section=spot).
                self.assertEqual(result["total"], 1)
            finally:
                conn.close()


class TestFaqDemotion(unittest.TestCase):
    """BUG-2: FAQ pages should be demoted in docs_url resolution scoring."""

    def test_faq_url_demoted(self) -> None:
        from xdocs.resolve_docs_urls import _FAQ_INDICATORS

        faq_urls = [
            "https://example.com/docs/faqs/order-faq",
            "https://example.com/docs/FAQ/common-issues",
            "https://example.com/docs/troubleshoot/auth",
        ]
        for url in faq_urls:
            url_lower = url.lower()
            is_faq = any(ind in url_lower for ind in _FAQ_INDICATORS)
            self.assertTrue(is_faq, f"Expected {url} to be detected as FAQ")

    def test_non_faq_url_not_demoted(self) -> None:
        from xdocs.resolve_docs_urls import _FAQ_INDICATORS

        normal_urls = [
            "https://example.com/docs/rest-api/new-order",
            "https://example.com/docs/trading/place-order",
        ]
        for url in normal_urls:
            url_lower = url.lower()
            is_faq = any(ind in url_lower for ind in _FAQ_INDICATORS)
            self.assertFalse(is_faq, f"Expected {url} to NOT be FAQ")

    def test_faq_scores_lower_than_endpoint_page(self) -> None:
        """A FAQ page should score lower than the actual endpoint page."""
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir, conn = _setup_store(tmp)
            try:
                endpoint_md = "# New Order\n\nPOST /api/v3/order\n\nPlace a new order.\n\nParameters:\n- symbol\n- side"
                faq_md = "# FAQ: Order Amendment\n\n/api/v3/order\n\nQ: How do I amend an order?\nA: Use PUT /api/v3/order/amend."

                _add_page(conn, docs_dir,
                          url="https://developers.example.com/docs/rest-api/new-order",
                          title="New Order", markdown=endpoint_md)
                _add_page(conn, docs_dir,
                          url="https://developers.example.com/docs/faqs/order-amend",
                          title="FAQ: Order Amendment", markdown=faq_md)

                result = resolve_docs_url(
                    conn, path="/api/v3/order", exchange="binance",
                    allowed_domains=["developers.example.com"],
                )
                # Should pick the endpoint page, not the FAQ.
                self.assertIsNotNone(result)
                self.assertIn("new-order", result)
                self.assertNotIn("faq", result)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
