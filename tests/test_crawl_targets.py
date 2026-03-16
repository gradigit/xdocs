from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xdocs.crawl_targets import (
    DiscoveredUrl,
    DiscoveryResult,
    _discover_link_follow,
    _discover_wayback,
    _host_allowed,
    _sanitize_and_filter,
    _self_check,
    discover_crawl_targets,
)
from xdocs.nav_extract import NavExtractionResult, NavNode
from xdocs.registry import (
    DocSource,
    Exchange,
    ExchangeSection,
    InventoryPolicy,
    Registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXCHANGE_ID = "testex"
SECTION_ID = "rest"
ALLOWED_DOMAINS = {"docs.testex.com"}
SEED_URL = "https://docs.testex.com/api/"
REGISTRY_PATH = Path("/tmp/test-registry/exchanges.yaml")


def _make_registry(seed_urls=None, doc_sources=None):
    return Registry(exchanges=[
        Exchange(
            exchange_id=EXCHANGE_ID,
            display_name="Test Exchange",
            allowed_domains=list(ALLOWED_DOMAINS),
            sections=[
                ExchangeSection(
                    section_id=SECTION_ID,
                    base_urls=["https://api.testex.com"],
                    seed_urls=seed_urls or [SEED_URL],
                    doc_sources=doc_sources or [],
                ),
            ],
        ),
    ])


# ---------------------------------------------------------------------------
# _host_allowed
# ---------------------------------------------------------------------------


class TestHostAllowed:
    def test_exact(self):
        assert _host_allowed("docs.testex.com", {"docs.testex.com"}) is True

    def test_subdomain(self):
        assert _host_allowed("sub.docs.testex.com", {"docs.testex.com"}) is True

    def test_no_match(self):
        assert _host_allowed("other.com", {"docs.testex.com"}) is False


# ---------------------------------------------------------------------------
# _sanitize_and_filter
# ---------------------------------------------------------------------------


class TestSanitizeAndFilter:
    def test_accepts_valid_urls(self):
        urls = ["https://docs.testex.com/api/spot", "https://docs.testex.com/api/margin"]
        accepted, rejected = _sanitize_and_filter(
            urls,
            allowed_domains=ALLOWED_DOMAINS,
            scope_prefixes=["https://docs.testex.com/api/"],
        )
        assert len(accepted) == 2
        assert len(rejected) == 0

    def test_rejects_out_of_scope(self):
        urls = ["https://docs.testex.com/blog/post"]
        accepted, rejected = _sanitize_and_filter(
            urls,
            allowed_domains=ALLOWED_DOMAINS,
            scope_prefixes=["https://docs.testex.com/api/"],
        )
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert rejected[0]["reason"] == "out_of_scope"

    def test_rejects_wrong_domain(self):
        urls = ["https://other.com/api/docs"]
        accepted, rejected = _sanitize_and_filter(
            urls,
            allowed_domains=ALLOWED_DOMAINS,
            scope_prefixes=[],
        )
        assert len(accepted) == 0
        assert rejected[0]["reason"] == "domain_not_allowed"

    def test_deduplicates(self):
        urls = [
            "https://docs.testex.com/api/spot",
            "https://docs.testex.com/api/spot",
        ]
        accepted, _ = _sanitize_and_filter(
            urls,
            allowed_domains=ALLOWED_DOMAINS,
            scope_prefixes=[],
        )
        assert len(accepted) == 1

    def test_rejects_bad_urls(self):
        urls = ["javascript:void(0)", "", "mailto:test@test.com"]
        accepted, rejected = _sanitize_and_filter(
            urls,
            allowed_domains=ALLOWED_DOMAINS,
            scope_prefixes=[],
        )
        assert len(accepted) == 0
        assert len(rejected) == 3


# ---------------------------------------------------------------------------
# _self_check
# ---------------------------------------------------------------------------


class TestSelfCheck:
    def test_all_methods_failed(self):
        warnings = _self_check(
            method_counts={"sitemap": 0, "link_follow": 0},
            total_urls=0,
            intersection_count=0,
            single_source_count=0,
            store_url_count=50,
        )
        assert any("all_methods_failed" in w for w in warnings)

    def test_no_warning_when_methods_find_urls(self):
        warnings = _self_check(
            method_counts={"sitemap": 100, "link_follow": 80},
            total_urls=120,
            intersection_count=60,
            single_source_count=60,
            store_url_count=100,
        )
        assert not any("all_methods_failed" in w for w in warnings)

    def test_method_divergence(self):
        warnings = _self_check(
            method_counts={"sitemap": 5, "link_follow": 500},
            total_urls=500,
            intersection_count=5,
            single_source_count=495,
            store_url_count=0,
        )
        assert any("method_divergence" in w for w in warnings)

    def test_low_cross_validation(self):
        warnings = _self_check(
            method_counts={"sitemap": 10, "link_follow": 15},
            total_urls=20,
            intersection_count=5,
            single_source_count=15,
            store_url_count=0,
        )
        assert any("low_cross_validation" in w for w in warnings)

    def test_no_low_cross_validation_when_enough_urls(self):
        warnings = _self_check(
            method_counts={"sitemap": 100, "link_follow": 100},
            total_urls=100,
            intersection_count=10,
            single_source_count=90,
            store_url_count=0,
        )
        # total_urls >= 50, so no warning.
        assert not any("low_cross_validation" in w for w in warnings)


# ---------------------------------------------------------------------------
# _discover_link_follow
# ---------------------------------------------------------------------------


class TestDiscoverLinkFollow:
    def test_extracts_links_from_seed(self):
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html><body>
          <a href="/api/spot">Spot</a>
          <a href="/api/margin">Margin</a>
          <a href="https://other.com/page">External</a>
        </body></html>
        """
        session.get.return_value = mock_resp

        urls, errors = _discover_link_follow(
            session,
            seed_urls=[SEED_URL],
            allowed_domains=ALLOWED_DOMAINS,
            scope_prefixes=["https://docs.testex.com/api/"],
            timeout_s=10.0,
        )

        assert len(errors) == 0
        assert any("spot" in u for u in urls)
        assert any("margin" in u for u in urls)
        # External link should be filtered.
        assert not any("other.com" in u for u in urls)

    def test_handles_http_error(self):
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        session.get.return_value = mock_resp

        urls, errors = _discover_link_follow(
            session,
            seed_urls=[SEED_URL],
            allowed_domains=ALLOWED_DOMAINS,
            scope_prefixes=[],
            timeout_s=10.0,
        )

        assert len(urls) == 0
        assert len(errors) == 1

    def test_handles_network_error(self):
        session = MagicMock()
        session.get.side_effect = ConnectionError("timeout")

        urls, errors = _discover_link_follow(
            session,
            seed_urls=[SEED_URL],
            allowed_domains=ALLOWED_DOMAINS,
            scope_prefixes=[],
            timeout_s=10.0,
        )

        assert len(urls) == 0
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# _discover_wayback (mocked)
# ---------------------------------------------------------------------------


class TestDiscoverWayback:
    @patch("xdocs.crawl_targets.time.sleep")  # Skip real delays.
    def test_parses_cdx_response(self, mock_sleep):
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            ["original"],
            ["https://docs.testex.com/api/spot"],
            ["https://docs.testex.com/api/margin"],
            ["https://other.com/unrelated"],
        ]
        session.get.return_value = mock_resp

        urls, errors = _discover_wayback(
            session,
            allowed_domains=["docs.testex.com"],
            scope_prefixes=["https://docs.testex.com/api/"],
            timeout_s=10.0,
        )

        assert len(errors) == 0
        assert any("spot" in u for u in urls)
        assert any("margin" in u for u in urls)
        assert not any("other.com" in u for u in urls)

    @patch("xdocs.crawl_targets.time.sleep")
    def test_handles_404(self, mock_sleep):
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        session.get.return_value = mock_resp

        urls, errors = _discover_wayback(
            session,
            allowed_domains=["docs.testex.com"],
            scope_prefixes=[],
            timeout_s=10.0,
        )

        assert len(urls) == 0
        assert len(errors) == 0  # 404 is normal empty.

    @patch("xdocs.crawl_targets.time.sleep")
    def test_handles_503_retries(self, mock_sleep):
        session = MagicMock()

        # Return 503 four times (exceeds max retries of 3).
        mock_resp_503 = MagicMock()
        mock_resp_503.status_code = 503
        session.get.return_value = mock_resp_503

        urls, errors = _discover_wayback(
            session,
            allowed_domains=["docs.testex.com"],
            scope_prefixes=[],
            timeout_s=10.0,
        )

        assert len(urls) == 0
        assert len(errors) == 1
        assert "503" in errors[0]["error"]

    @patch("xdocs.crawl_targets.time.sleep")
    def test_handles_json_decode_error(self, mock_sleep):
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad json")
        session.get.return_value = mock_resp

        urls, errors = _discover_wayback(
            session,
            allowed_domains=["docs.testex.com"],
            scope_prefixes=[],
            timeout_s=10.0,
        )

        assert len(urls) == 0
        assert len(errors) == 1
        assert "JSON" in errors[0]["error"]


# ---------------------------------------------------------------------------
# discover_crawl_targets (integration)
# ---------------------------------------------------------------------------


class TestDiscoverCrawlTargets:
    @patch("xdocs.crawl_targets._discover_link_follow")
    @patch("xdocs.crawl_targets._discover_sitemap")
    @patch("xdocs.crawl_targets.load_registry")
    def test_union_with_provenance(self, mock_reg, mock_sm, mock_lf):
        mock_reg.return_value = _make_registry()

        sm_urls = ["https://docs.testex.com/api/spot", "https://docs.testex.com/api/margin"]
        lf_urls = ["https://docs.testex.com/api/margin", "https://docs.testex.com/api/futures"]

        mock_sm.return_value = (sm_urls, [])
        mock_lf.return_value = (lf_urls, [])

        result = discover_crawl_targets(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
        )

        assert result.exchange_id == EXCHANGE_ID
        assert len(result.urls) == 3  # spot, margin, futures

        # margin should be found by both methods.
        margin = [u for u in result.urls if "margin" in u.url]
        assert len(margin) == 1
        assert "sitemap" in margin[0].sources
        assert "link_follow" in margin[0].sources

        # spot only in sitemap.
        spot = [u for u in result.urls if "spot" in u.url]
        assert len(spot) == 1
        assert spot[0].sources == frozenset({"sitemap"})
        assert spot[0].first_seen_via == "sitemap"

        # futures only in link_follow.
        futures = [u for u in result.urls if "futures" in u.url]
        assert len(futures) == 1
        assert futures[0].sources == frozenset({"link_follow"})

        assert result.intersection_count == 1
        assert result.single_source_count == 2
        assert result.method_counts["sitemap"] == 2
        assert result.method_counts["link_follow"] == 2

    @patch("xdocs.crawl_targets._discover_nav")
    @patch("xdocs.crawl_targets._discover_link_follow")
    @patch("xdocs.crawl_targets._discover_sitemap")
    @patch("xdocs.crawl_targets.load_registry")
    def test_nav_enabled(self, mock_reg, mock_sm, mock_lf, mock_nav):
        mock_reg.return_value = _make_registry()
        mock_sm.return_value = (["https://docs.testex.com/api/spot"], [])
        mock_lf.return_value = ([], [])
        mock_nav.return_value = (["https://docs.testex.com/api/nav-page"], [])

        result = discover_crawl_targets(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            enable_nav=True,
        )

        assert "nav_extraction" in result.method_counts
        nav_urls = [u for u in result.urls if "nav-page" in u.url]
        assert len(nav_urls) == 1
        assert "nav_extraction" in nav_urls[0].sources

    @patch("xdocs.crawl_targets._discover_wayback")
    @patch("xdocs.crawl_targets._discover_link_follow")
    @patch("xdocs.crawl_targets._discover_sitemap")
    @patch("xdocs.crawl_targets.load_registry")
    def test_wayback_enabled(self, mock_reg, mock_sm, mock_lf, mock_wb):
        mock_reg.return_value = _make_registry()
        mock_sm.return_value = ([], [])
        mock_lf.return_value = ([], [])
        mock_wb.return_value = (["https://docs.testex.com/api/archived"], [])

        result = discover_crawl_targets(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
            enable_wayback=True,
        )

        assert "wayback" in result.method_counts
        wb_urls = [u for u in result.urls if "archived" in u.url]
        assert len(wb_urls) == 1

    @patch("xdocs.crawl_targets._discover_link_follow")
    @patch("xdocs.crawl_targets._discover_sitemap")
    @patch("xdocs.crawl_targets.load_registry")
    def test_errors_collected(self, mock_reg, mock_sm, mock_lf):
        mock_reg.return_value = _make_registry()
        mock_sm.return_value = ([], [{"url": "sitemap.xml", "error": "404"}])
        mock_lf.return_value = ([], [{"url": SEED_URL, "error": "timeout"}])

        result = discover_crawl_targets(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
        )

        assert len(result.method_errors["sitemap"]) == 1
        assert len(result.method_errors["link_follow"]) == 1

    @patch("xdocs.crawl_targets._discover_link_follow")
    @patch("xdocs.crawl_targets._discover_sitemap")
    @patch("xdocs.crawl_targets.load_registry")
    def test_self_check_warnings(self, mock_reg, mock_sm, mock_lf):
        mock_reg.return_value = _make_registry()
        mock_sm.return_value = ([], [])
        mock_lf.return_value = ([], [])

        # No URLs found by any method, but we don't provide docs_dir
        # so store_url_count will be 0, no all_methods_failed warning.
        result = discover_crawl_targets(
            exchange_id=EXCHANGE_ID,
            section_id=SECTION_ID,
            registry_path=REGISTRY_PATH,
        )

        assert len(result.urls) == 0
        # No warnings because store_url_count is also 0.
        assert not any("all_methods_failed" in w for w in result.warnings)
