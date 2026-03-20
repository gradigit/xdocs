"""Tests for changelog extraction and classification (M36)."""
from __future__ import annotations

import re
import unittest


class TestProseDateParsing(unittest.TestCase):
    """M36.1: Prose date formats must be parseable."""

    def test_parse_month_day_year(self) -> None:
        from xdocs.changelog import _parse_prose_date
        self.assertEqual(_parse_prose_date("December 23rd, 2025"), "2025-12-23")
        self.assertEqual(_parse_prose_date("January 15, 2026"), "2026-01-15")
        self.assertEqual(_parse_prose_date("March 12, 2024"), "2024-03-12")

    def test_parse_month_year(self) -> None:
        from xdocs.changelog import _parse_prose_date
        # Month-only → first of month
        result = _parse_prose_date("February 2026")
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("2026-02"))

    def test_iso_date_passthrough(self) -> None:
        from xdocs.changelog import _parse_prose_date
        self.assertEqual(_parse_prose_date("2025-12-23"), "2025-12-23")

    def test_no_date_returns_none(self) -> None:
        from xdocs.changelog import _parse_prose_date
        self.assertIsNone(_parse_prose_date("no date here"))
        self.assertIsNone(_parse_prose_date(""))

    def test_orderly_format(self) -> None:
        """Orderly uses 'December 23rd, 2025 - Major Update'."""
        from xdocs.changelog import _parse_prose_date
        result = _parse_prose_date("December 23rd, 2025 - Major Update")
        self.assertEqual(result, "2025-12-23")


class TestSplitByDateHeadings(unittest.TestCase):
    """M36.1: Splitting should handle both ISO and prose date headings."""

    def test_iso_headings(self) -> None:
        from xdocs.changelog import _split_by_date_headings
        md = "### 2026-01-15\nNew endpoint added.\n\n### 2026-01-10\nBug fix."
        chunks = _split_by_date_headings(md)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0][0], "2026-01-15")
        self.assertEqual(chunks[1][0], "2026-01-10")

    def test_prose_headings(self) -> None:
        from xdocs.changelog import _split_by_date_headings
        md = "## December 23, 2025\nMajor update.\n\n## November 1, 2025\nMinor fix."
        chunks = _split_by_date_headings(md)
        # Should find at least 2 chunks with parsed dates
        dated = [c for c in chunks if c[0] is not None]
        self.assertGreaterEqual(len(dated), 2)

    def test_zero_width_space_headings(self) -> None:
        """Orderly uses '##\\u200b' (zero-width space after ##)."""
        from xdocs.changelog import _split_by_date_headings
        md = "## \u200b\nDecember 23rd, 2025 - Major Update\n\nNew feature.\n\n## \u200b\nNovember 1st, 2025\n\nBug fix."
        chunks = _split_by_date_headings(md)
        dated = [c for c in chunks if c[0] is not None]
        self.assertGreaterEqual(len(dated), 1, "Should extract at least one dated chunk from ZWS headings")


class TestChangelogClassify(unittest.TestCase):
    """M36.2: Changelog entry classification by impact type."""

    def test_endpoint_removed(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("The GET /api/v1/old-endpoint has been removed.")
        self.assertIn("endpoint_removed", [c["impact_type"] for c in result])

    def test_endpoint_deprecated(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("POST /api/v3/order is now deprecated. Use POST /api/v4/order instead.")
        self.assertIn("endpoint_deprecated", [c["impact_type"] for c in result])

    def test_endpoint_added(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Added a new endpoint GET /api/v5/market/history for historical data.")
        self.assertIn("endpoint_added", [c["impact_type"] for c in result])

    def test_rate_limit_change(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Rate limit for market data endpoints increased from 10 to 20 requests per second.")
        self.assertIn("rate_limit_change", [c["impact_type"] for c in result])

    def test_breaking_change(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Breaking change: the response format for /api/v2/trades has changed.")
        self.assertIn("breaking_change", [c["impact_type"] for c in result])

    def test_field_added(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Added a new field `avgPrice` to the order response.")
        self.assertIn("field_added", [c["impact_type"] for c in result])

    def test_informational_default(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Updated documentation for clarity.")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["impact_type"], "informational")

    def test_multiple_classifications(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Added new endpoint POST /v2/order. Deprecated the old POST /v1/order.")
        types = [c["impact_type"] for c in result]
        self.assertIn("endpoint_added", types)
        self.assertIn("endpoint_deprecated", types)


class TestEndpointPathExtraction(unittest.TestCase):
    """M36.2: Extract API paths from changelog entry text."""

    def test_extract_get_path(self) -> None:
        from xdocs.changelog_classify import extract_endpoint_paths
        paths = extract_endpoint_paths("Added GET /api/v5/market/ticker endpoint.")
        self.assertEqual(paths, [("GET", "/api/v5/market/ticker")])

    def test_extract_multiple_paths(self) -> None:
        from xdocs.changelog_classify import extract_endpoint_paths
        paths = extract_endpoint_paths("POST /api/v3/order deprecated. Use POST /api/v4/order.")
        self.assertEqual(len(paths), 2)

    def test_no_paths(self) -> None:
        from xdocs.changelog_classify import extract_endpoint_paths
        paths = extract_endpoint_paths("General documentation update.")
        self.assertEqual(paths, [])

    def test_path_without_method(self) -> None:
        from xdocs.changelog_classify import extract_endpoint_paths
        paths = extract_endpoint_paths("The /sapi/v1/margin/order endpoint was updated.")
        self.assertGreaterEqual(len(paths), 1)


class TestSeverityMapping(unittest.TestCase):
    """M36.2: Severity levels correctly assigned."""

    def test_err_severity(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Endpoint /api/v1/old removed.")
        for c in result:
            if c["impact_type"] == "endpoint_removed":
                self.assertEqual(c["severity"], "err")

    def test_warn_severity(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Rate limit changed for spot endpoints.")
        for c in result:
            if c["impact_type"] == "rate_limit_change":
                self.assertEqual(c["severity"], "warn")

    def test_info_severity(self) -> None:
        from xdocs.changelog_classify import classify_entry
        result = classify_entry("Added new endpoint GET /api/v5/data.")
        for c in result:
            if c["impact_type"] == "endpoint_added":
                self.assertEqual(c["severity"], "info")


if __name__ == "__main__":
    unittest.main()
