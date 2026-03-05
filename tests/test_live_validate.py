from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cex_api_docs.live_validate import (
    LiveValidationResult,
    _get_store_urls,
    validate_live_site,
)
from cex_api_docs.nav_extract import NavExtractionResult, NavNode
from cex_api_docs.registry import Exchange, ExchangeSection, InventoryPolicy, Registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXCHANGE_ID = "binance"
SECTION_ID = "spot"
ALLOWED_DOMAINS = ["developers.binance.com"]
SEED_URL = "https://developers.binance.com/docs/binance-spot-api-docs/"
DOCS_DIR = "/tmp/test-cex-docs"
REGISTRY_PATH = Path("/tmp/test-registry/exchanges.yaml")


def _make_registry():
    return Registry(exchanges=[
        Exchange(
            exchange_id=EXCHANGE_ID,
            display_name="Binance",
            allowed_domains=ALLOWED_DOMAINS,
            sections=[
                ExchangeSection(
                    section_id=SECTION_ID,
                    base_urls=["https://api.binance.com"],
                    seed_urls=[SEED_URL],
                ),
            ],
        ),
    ])


def _make_nav_result(urls=None, errors=None, method="http_fallback"):
    return NavExtractionResult(
        seed_url=SEED_URL,
        urls=urls or [],
        nav_nodes=[NavNode(url=u, text="", depth=0) for u in (urls or [])],
        errors=errors or [],
        method=method,
    )


# ---------------------------------------------------------------------------
# _get_store_urls
# ---------------------------------------------------------------------------


class TestGetStoreUrls:
    def test_queries_by_domain(self, tmp_path):
        """Test that _get_store_urls queries by domain correctly."""
        import sqlite3

        db_path = tmp_path / "db" / "docs.db"
        db_path.parent.mkdir(parents=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY,
                canonical_url TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO pages (canonical_url, domain) VALUES (?, ?)",
                      ("https://developers.binance.com/docs/spot", "developers.binance.com"))
        conn.execute("INSERT INTO pages (canonical_url, domain) VALUES (?, ?)",
                      ("https://api.binance.com/docs/other", "api.binance.com"))
        conn.execute("INSERT INTO pages (canonical_url, domain) VALUES (?, ?)",
                      ("https://docs.okx.com/page", "docs.okx.com"))
        conn.commit()
        conn.close()

        urls = _get_store_urls(db_path, ["developers.binance.com"])
        assert "https://developers.binance.com/docs/spot" in urls
        assert "https://docs.okx.com/page" not in urls

    def test_subdomain_matching(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "db" / "docs.db"
        db_path.parent.mkdir(parents=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY,
                canonical_url TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO pages (canonical_url, domain) VALUES (?, ?)",
                      ("https://sub.binance.com/page", "sub.binance.com"))
        conn.commit()
        conn.close()

        urls = _get_store_urls(db_path, ["binance.com"])
        assert "https://sub.binance.com/page" in urls

    def test_deduplicates(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "db" / "docs.db"
        db_path.parent.mkdir(parents=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY,
                canonical_url TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO pages (canonical_url, domain) VALUES (?, ?)",
                      ("https://sub.example.com/page", "sub.example.com"))
        conn.commit()
        conn.close()

        # Query with both parent and subdomain — should not duplicate.
        urls = _get_store_urls(db_path, ["example.com", "sub.example.com"])
        assert urls.count("https://sub.example.com/page") == 1


# ---------------------------------------------------------------------------
# validate_live_site
# ---------------------------------------------------------------------------


class TestValidateLiveSite:
    @patch("cex_api_docs.live_validate.extract_nav_urls")
    @patch("cex_api_docs.live_validate._get_store_urls")
    @patch("cex_api_docs.live_validate.require_store_db")
    @patch("cex_api_docs.live_validate.load_registry")
    def test_basic_coverage(self, mock_load_reg, mock_require_db, mock_get_store, mock_nav):
        mock_load_reg.return_value = _make_registry()
        mock_require_db.return_value = Path("/tmp/db/docs.db")

        live = [
            "https://developers.binance.com/docs/spot",
            "https://developers.binance.com/docs/margin",
            "https://developers.binance.com/docs/futures",
        ]
        store = [
            "https://developers.binance.com/docs/spot",
            "https://developers.binance.com/docs/margin",
            "https://developers.binance.com/docs/wallet",
        ]

        mock_nav.return_value = _make_nav_result(urls=live)
        mock_get_store.return_value = store

        result = validate_live_site(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            docs_dir=DOCS_DIR,
            timeout_s=10.0,
        )

        assert result.exchange_id == EXCHANGE_ID
        assert result.section_id == SECTION_ID
        assert len(result.overlap) == 2
        assert "https://developers.binance.com/docs/futures" in result.missing_from_store
        assert "https://developers.binance.com/docs/wallet" in result.missing_from_live
        assert result.coverage_pct == pytest.approx(66.67, abs=0.01)

    @patch("cex_api_docs.live_validate.extract_nav_urls")
    @patch("cex_api_docs.live_validate._get_store_urls")
    @patch("cex_api_docs.live_validate.require_store_db")
    @patch("cex_api_docs.live_validate.load_registry")
    def test_full_coverage(self, mock_load_reg, mock_require_db, mock_get_store, mock_nav):
        mock_load_reg.return_value = _make_registry()
        mock_require_db.return_value = Path("/tmp/db/docs.db")

        urls = [
            "https://developers.binance.com/docs/spot",
            "https://developers.binance.com/docs/margin",
        ]
        mock_nav.return_value = _make_nav_result(urls=urls)
        mock_get_store.return_value = urls

        result = validate_live_site(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            docs_dir=DOCS_DIR,
        )

        assert result.coverage_pct == 100.0
        assert len(result.missing_from_store) == 0
        assert len(result.missing_from_live) == 0

    @patch("cex_api_docs.live_validate.extract_nav_urls")
    @patch("cex_api_docs.live_validate._get_store_urls")
    @patch("cex_api_docs.live_validate.require_store_db")
    @patch("cex_api_docs.live_validate.load_registry")
    def test_empty_nav_with_store_pages(self, mock_load_reg, mock_require_db, mock_get_store, mock_nav):
        mock_load_reg.return_value = _make_registry()
        mock_require_db.return_value = Path("/tmp/db/docs.db")
        mock_nav.return_value = _make_nav_result(urls=[])
        mock_get_store.return_value = ["https://developers.binance.com/docs/spot"]

        result = validate_live_site(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            docs_dir=DOCS_DIR,
        )

        assert result.coverage_pct == 0.0
        warning_types = [w["type"] for w in result.warnings]
        assert "nav_extraction_empty" in warning_types

    @patch("cex_api_docs.live_validate.load_registry")
    def test_no_seed_urls(self, mock_load_reg):
        # Registry with no seed URLs.
        mock_load_reg.return_value = Registry(exchanges=[
            Exchange(
                exchange_id=EXCHANGE_ID,
                display_name="Binance",
                allowed_domains=ALLOWED_DOMAINS,
                sections=[
                    ExchangeSection(
                        section_id=SECTION_ID,
                        base_urls=[],
                        seed_urls=[],
                    ),
                ],
            ),
        ])

        result = validate_live_site(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            docs_dir=DOCS_DIR,
        )

        assert result.coverage_pct == 0.0
        assert len(result.live_urls) == 0
        warning_types = [w["type"] for w in result.warnings]
        assert "no_seeds" in warning_types

    @patch("cex_api_docs.live_validate.extract_nav_urls")
    @patch("cex_api_docs.live_validate._get_store_urls")
    @patch("cex_api_docs.live_validate.require_store_db")
    @patch("cex_api_docs.live_validate.load_registry")
    def test_nav_errors_propagated(self, mock_load_reg, mock_require_db, mock_get_store, mock_nav):
        mock_load_reg.return_value = _make_registry()
        mock_require_db.return_value = Path("/tmp/db/docs.db")
        mock_nav.return_value = _make_nav_result(
            urls=["https://developers.binance.com/docs/spot"],
            errors=[{"stage": "http_fetch", "error": "timeout"}],
        )
        mock_get_store.return_value = []

        result = validate_live_site(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            docs_dir=DOCS_DIR,
        )

        assert len(result.errors) == 1
        assert result.errors[0]["stage"] == "http_fetch"

    @patch("cex_api_docs.live_validate.extract_nav_urls")
    @patch("cex_api_docs.live_validate._get_store_urls")
    @patch("cex_api_docs.live_validate.require_store_db")
    @patch("cex_api_docs.live_validate.load_registry")
    def test_missing_from_store_warning(self, mock_load_reg, mock_require_db, mock_get_store, mock_nav):
        mock_load_reg.return_value = _make_registry()
        mock_require_db.return_value = Path("/tmp/db/docs.db")
        mock_nav.return_value = _make_nav_result(
            urls=["https://developers.binance.com/docs/new-page"],
        )
        mock_get_store.return_value = []

        result = validate_live_site(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            docs_dir=DOCS_DIR,
        )

        assert len(result.missing_from_store) == 1
        warning_types = [w["type"] for w in result.warnings]
        assert "missing_from_store" in warning_types

    @patch("cex_api_docs.live_validate.extract_nav_urls")
    @patch("cex_api_docs.live_validate._get_store_urls")
    @patch("cex_api_docs.live_validate.require_store_db")
    @patch("cex_api_docs.live_validate.load_registry")
    def test_nav_method_reported(self, mock_load_reg, mock_require_db, mock_get_store, mock_nav):
        mock_load_reg.return_value = _make_registry()
        mock_require_db.return_value = Path("/tmp/db/docs.db")
        mock_nav.return_value = _make_nav_result(
            urls=["https://developers.binance.com/docs/spot"],
            method="agent_browser",
        )
        mock_get_store.return_value = []

        result = validate_live_site(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            docs_dir=DOCS_DIR,
        )

        assert result.nav_method == "agent_browser"
