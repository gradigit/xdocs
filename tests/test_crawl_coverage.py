from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cex_api_docs.crawl_coverage import (
    CoverageAuditResult,
    SectionCoverage,
    _get_stale_urls,
    _get_store_urls_for_domains,
    audit_crawl_coverage,
    backfill_gaps,
)
from cex_api_docs.crawl_targets import DiscoveredUrl, DiscoveryResult
from cex_api_docs.registry import (
    Exchange,
    ExchangeSection,
    Registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXCHANGE_ID = "testex"
SECTION_ID = "rest"
ALLOWED_DOMAINS = ["docs.testex.com"]
DOCS_DIR = "/tmp/test-cex-docs"
REGISTRY_PATH = Path("/tmp/test-registry/exchanges.yaml")


def _make_registry():
    return Registry(exchanges=[
        Exchange(
            exchange_id=EXCHANGE_ID,
            display_name="Test Exchange",
            allowed_domains=ALLOWED_DOMAINS,
            sections=[
                ExchangeSection(
                    section_id=SECTION_ID,
                    base_urls=["https://api.testex.com"],
                    seed_urls=["https://docs.testex.com/api/"],
                ),
            ],
        ),
    ])


def _make_discovery_result(urls_list, method_counts=None, warnings=None):
    discovered = [
        DiscoveredUrl(url=u, sources=frozenset({"sitemap"}), first_seen_via="sitemap")
        for u in urls_list
    ]
    return DiscoveryResult(
        exchange_id=EXCHANGE_ID,
        section_id=SECTION_ID,
        urls=discovered,
        method_counts=method_counts or {"sitemap": len(urls_list), "link_follow": 0},
        intersection_count=0,
        single_source_count=len(urls_list),
        rejected_urls=[],
        method_errors={},
        warnings=warnings or [],
    )


def _init_test_db(db_path: Path, pages=None, inventories=None, entries=None):
    """Create a minimal test DB with pages and inventory tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY,
            canonical_url TEXT NOT NULL UNIQUE,
            domain TEXT NOT NULL,
            crawled_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventories (
            id INTEGER PRIMARY KEY,
            exchange_id TEXT NOT NULL,
            section_id TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            sources_json TEXT NOT NULL DEFAULT '{}',
            url_count INTEGER NOT NULL DEFAULT 0,
            inventory_hash TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_entries (
            id INTEGER PRIMARY KEY,
            inventory_id INTEGER NOT NULL REFERENCES inventories(id),
            canonical_url TEXT NOT NULL,
            status TEXT NOT NULL,
            UNIQUE (inventory_id, canonical_url)
        )
    """)

    for p in (pages or []):
        conn.execute(
            "INSERT INTO pages (canonical_url, domain, crawled_at) VALUES (?, ?, ?)",
            (p["url"], p["domain"], p.get("crawled_at")),
        )

    for inv in (inventories or []):
        conn.execute(
            "INSERT INTO inventories (id, exchange_id, section_id, generated_at, url_count) VALUES (?, ?, ?, ?, ?)",
            (inv["id"], inv["exchange_id"], inv["section_id"], inv["generated_at"], inv.get("url_count", 0)),
        )

    for e in (entries or []):
        conn.execute(
            "INSERT INTO inventory_entries (inventory_id, canonical_url, status) VALUES (?, ?, ?)",
            (e["inventory_id"], e["url"], e["status"]),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# _get_store_urls_for_domains
# ---------------------------------------------------------------------------


class TestGetStoreUrlsForDomains:
    def test_returns_matching_urls(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(db_path, pages=[
            {"url": "https://docs.testex.com/api/spot", "domain": "docs.testex.com"},
            {"url": "https://other.com/page", "domain": "other.com"},
        ])

        urls = _get_store_urls_for_domains(db_path, ["docs.testex.com"])
        assert "https://docs.testex.com/api/spot" in urls
        assert "https://other.com/page" not in urls

    def test_empty_domains(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(db_path, pages=[
            {"url": "https://docs.testex.com/api/spot", "domain": "docs.testex.com"},
        ])

        urls = _get_store_urls_for_domains(db_path, [])
        assert len(urls) == 0


# ---------------------------------------------------------------------------
# _get_stale_urls
# ---------------------------------------------------------------------------


class TestGetStaleUrls:
    def test_detects_stale_pages(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(db_path, pages=[
            {"url": "https://docs.testex.com/old", "domain": "docs.testex.com", "crawled_at": "2020-01-01T00:00:00Z"},
            {"url": "https://docs.testex.com/recent", "domain": "docs.testex.com", "crawled_at": "2099-01-01T00:00:00Z"},
        ])

        stale = _get_stale_urls(db_path, ["docs.testex.com"], stale_days=90)
        assert "https://docs.testex.com/old" in stale
        assert "https://docs.testex.com/recent" not in stale

    def test_ignores_never_crawled(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(db_path, pages=[
            {"url": "https://docs.testex.com/new", "domain": "docs.testex.com", "crawled_at": None},
        ])

        stale = _get_stale_urls(db_path, ["docs.testex.com"])
        assert len(stale) == 0


# ---------------------------------------------------------------------------
# audit_crawl_coverage
# ---------------------------------------------------------------------------


class TestAuditCrawlCoverage:
    @patch("cex_api_docs.crawl_coverage._get_stale_urls")
    @patch("cex_api_docs.crawl_coverage._get_store_urls_for_domains")
    @patch("cex_api_docs.crawl_coverage.discover_crawl_targets")
    @patch("cex_api_docs.crawl_coverage.require_store_db")
    @patch("cex_api_docs.crawl_coverage.load_registry")
    def test_full_coverage(self, mock_reg, mock_db, mock_disc, mock_store, mock_stale):
        mock_reg.return_value = _make_registry()
        mock_db.return_value = Path("/tmp/db/docs.db")

        discovered = ["https://docs.testex.com/api/spot", "https://docs.testex.com/api/margin"]
        mock_disc.return_value = _make_discovery_result(discovered)
        mock_store.return_value = set(discovered)
        mock_stale.return_value = []

        result = audit_crawl_coverage(
            docs_dir=DOCS_DIR,
            registry_path=REGISTRY_PATH,
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
        )

        assert len(result.sections) == 1
        assert result.sections[0].coverage_pct == 100.0
        assert result.total_missing == 0
        assert result.total_stale == 0

    @patch("cex_api_docs.crawl_coverage._get_stale_urls")
    @patch("cex_api_docs.crawl_coverage._get_store_urls_for_domains")
    @patch("cex_api_docs.crawl_coverage.discover_crawl_targets")
    @patch("cex_api_docs.crawl_coverage.require_store_db")
    @patch("cex_api_docs.crawl_coverage.load_registry")
    def test_partial_coverage(self, mock_reg, mock_db, mock_disc, mock_store, mock_stale):
        mock_reg.return_value = _make_registry()
        mock_db.return_value = Path("/tmp/db/docs.db")

        discovered = ["https://docs.testex.com/api/spot", "https://docs.testex.com/api/margin", "https://docs.testex.com/api/futures"]
        mock_disc.return_value = _make_discovery_result(discovered)
        # Only 1 of 3 in store.
        mock_store.return_value = {"https://docs.testex.com/api/spot"}
        mock_stale.return_value = []

        result = audit_crawl_coverage(
            docs_dir=DOCS_DIR,
            registry_path=REGISTRY_PATH,
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
        )

        assert result.sections[0].coverage_pct == pytest.approx(33.33, abs=0.01)
        assert result.total_missing == 2
        assert len(result.sections[0].missing_urls) == 2

    @patch("cex_api_docs.crawl_coverage._get_stale_urls")
    @patch("cex_api_docs.crawl_coverage._get_store_urls_for_domains")
    @patch("cex_api_docs.crawl_coverage.discover_crawl_targets")
    @patch("cex_api_docs.crawl_coverage.require_store_db")
    @patch("cex_api_docs.crawl_coverage.load_registry")
    def test_stale_pages_detected(self, mock_reg, mock_db, mock_disc, mock_store, mock_stale):
        mock_reg.return_value = _make_registry()
        mock_db.return_value = Path("/tmp/db/docs.db")

        discovered = ["https://docs.testex.com/api/spot"]
        mock_disc.return_value = _make_discovery_result(discovered)
        mock_store.return_value = set(discovered)
        mock_stale.return_value = ["https://docs.testex.com/api/spot"]

        result = audit_crawl_coverage(
            docs_dir=DOCS_DIR,
            registry_path=REGISTRY_PATH,
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
        )

        assert result.total_stale == 1
        assert any("stale" in w for w in result.sections[0].warnings)

    @patch("cex_api_docs.crawl_coverage._get_stale_urls")
    @patch("cex_api_docs.crawl_coverage._get_store_urls_for_domains")
    @patch("cex_api_docs.crawl_coverage.discover_crawl_targets")
    @patch("cex_api_docs.crawl_coverage.require_store_db")
    @patch("cex_api_docs.crawl_coverage.load_registry")
    def test_zero_discovered(self, mock_reg, mock_db, mock_disc, mock_store, mock_stale):
        mock_reg.return_value = _make_registry()
        mock_db.return_value = Path("/tmp/db/docs.db")
        mock_disc.return_value = _make_discovery_result([])
        mock_store.return_value = set()
        mock_stale.return_value = []

        result = audit_crawl_coverage(
            docs_dir=DOCS_DIR,
            registry_path=REGISTRY_PATH,
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
        )

        # 0 discovered => 100% coverage (nothing to miss).
        assert result.sections[0].coverage_pct == 100.0

    @patch("cex_api_docs.crawl_coverage._get_stale_urls")
    @patch("cex_api_docs.crawl_coverage._get_store_urls_for_domains")
    @patch("cex_api_docs.crawl_coverage.discover_crawl_targets")
    @patch("cex_api_docs.crawl_coverage.require_store_db")
    @patch("cex_api_docs.crawl_coverage.load_registry")
    def test_overall_coverage(self, mock_reg, mock_db, mock_disc, mock_store, mock_stale):
        # Registry with 2 sections.
        registry = Registry(exchanges=[
            Exchange(
                exchange_id=EXCHANGE_ID,
                display_name="Test Exchange",
                allowed_domains=ALLOWED_DOMAINS,
                sections=[
                    ExchangeSection(
                        section_id="rest",
                        base_urls=[],
                        seed_urls=["https://docs.testex.com/api/"],
                    ),
                    ExchangeSection(
                        section_id="ws",
                        base_urls=[],
                        seed_urls=["https://docs.testex.com/ws/"],
                    ),
                ],
            ),
        ])
        mock_reg.return_value = registry
        mock_db.return_value = Path("/tmp/db/docs.db")

        # First section: 2 discovered, 2 stored.
        # Second section: 2 discovered, 1 stored.
        call_count = [0]

        def disc_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_discovery_result(["https://docs.testex.com/api/a", "https://docs.testex.com/api/b"])
            return _make_discovery_result(["https://docs.testex.com/ws/a", "https://docs.testex.com/ws/b"])

        store_call = [0]

        def store_side_effect(db, domains):
            store_call[0] += 1
            if store_call[0] == 1:
                return {"https://docs.testex.com/api/a", "https://docs.testex.com/api/b"}
            return {"https://docs.testex.com/ws/a"}

        mock_disc.side_effect = disc_side_effect
        mock_store.side_effect = store_side_effect
        mock_stale.return_value = []

        result = audit_crawl_coverage(
            docs_dir=DOCS_DIR,
            registry_path=REGISTRY_PATH,
            exchange_id=EXCHANGE_ID,
        )

        assert len(result.sections) == 2
        # Overall: 3 stored / 4 discovered = 75%.
        assert result.overall_coverage_pct == 75.0


# ---------------------------------------------------------------------------
# backfill_gaps
# ---------------------------------------------------------------------------


class TestBackfillGaps:
    def test_dry_run(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(
            db_path,
            inventories=[
                {"id": 1, "exchange_id": EXCHANGE_ID, "section_id": SECTION_ID, "generated_at": "2025-01-01T00:00:00Z"},
            ],
            entries=[
                {"inventory_id": 1, "url": "https://docs.testex.com/api/existing", "status": "fetched"},
            ],
        )

        result = backfill_gaps(
            docs_dir=str(tmp_path),
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            missing_urls=[
                "https://docs.testex.com/api/new1",
                "https://docs.testex.com/api/new2",
                "https://docs.testex.com/api/existing",  # Already exists.
            ],
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["inserted"] == 2
        assert result["already_existed"] == 1

        # Verify nothing was actually inserted.
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM inventory_entries").fetchone()[0]
        conn.close()
        assert count == 1  # Only the original.

    def test_write_mode(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(
            db_path,
            inventories=[
                {"id": 1, "exchange_id": EXCHANGE_ID, "section_id": SECTION_ID, "generated_at": "2025-01-01T00:00:00Z", "url_count": 1},
            ],
            entries=[
                {"inventory_id": 1, "url": "https://docs.testex.com/api/existing", "status": "fetched"},
            ],
        )

        result = backfill_gaps(
            docs_dir=str(tmp_path),
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            missing_urls=[
                "https://docs.testex.com/api/new1",
                "https://docs.testex.com/api/new2",
            ],
            dry_run=False,
        )

        assert result["dry_run"] is False
        assert result["inserted"] == 2
        assert result["already_existed"] == 0

        # Verify entries were inserted.
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT canonical_url, status FROM inventory_entries WHERE inventory_id = 1 ORDER BY canonical_url"
        ).fetchall()
        conn.close()

        assert len(rows) == 3
        urls = [r["canonical_url"] for r in rows]
        assert "https://docs.testex.com/api/new1" in urls
        assert "https://docs.testex.com/api/new2" in urls

        # New entries should have status 'pending'.
        new_entries = [r for r in rows if r["canonical_url"].endswith("new1") or r["canonical_url"].endswith("new2")]
        assert all(r["status"] == "pending" for r in new_entries)

    def test_no_inventory(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(db_path)

        result = backfill_gaps(
            docs_dir=str(tmp_path),
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            missing_urls=["https://docs.testex.com/api/new"],
            dry_run=True,
        )

        assert result["inserted"] == 0
        assert "error" in result

    def test_updates_url_count(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(
            db_path,
            inventories=[
                {"id": 1, "exchange_id": EXCHANGE_ID, "section_id": SECTION_ID, "generated_at": "2025-01-01T00:00:00Z", "url_count": 1},
            ],
            entries=[
                {"inventory_id": 1, "url": "https://docs.testex.com/api/existing", "status": "fetched"},
            ],
        )

        backfill_gaps(
            docs_dir=str(tmp_path),
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            missing_urls=["https://docs.testex.com/api/new1"],
            dry_run=False,
        )

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT url_count FROM inventories WHERE id = 1").fetchone()
        conn.close()
        assert row[0] == 2  # 1 existing + 1 new.

    def test_empty_missing_urls(self, tmp_path):
        db_path = tmp_path / "db" / "docs.db"
        _init_test_db(
            db_path,
            inventories=[
                {"id": 1, "exchange_id": EXCHANGE_ID, "section_id": SECTION_ID, "generated_at": "2025-01-01T00:00:00Z"},
            ],
        )

        result = backfill_gaps(
            docs_dir=str(tmp_path),
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            missing_urls=[],
            dry_run=False,
        )

        assert result["inserted"] == 0
        assert result["already_existed"] == 0
