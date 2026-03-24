"""Tests for KnownSources dataclass, registry parsing, and validation."""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

from xdocs.known_sources import (
    SourceCheckResult,
    _is_html_response,
    _is_xml_response,
    validate_known_sources,
)
from xdocs.registry import KnownSources, Registry, Exchange, ExchangeSection, load_registry


class TestKnownSources(unittest.TestCase):
    """Unit tests for the KnownSources dataclass."""

    def test_all_urls_returns_non_none_fields(self) -> None:
        ks = KnownSources(llms_txt="https://example.com/llms.txt", github_org="https://github.com/ex")
        urls = ks.all_urls()
        self.assertEqual(urls, {
            "llms_txt": "https://example.com/llms.txt",
            "github_org": "https://github.com/ex",
        })

    def test_all_urls_empty_when_all_none(self) -> None:
        ks = KnownSources()
        self.assertEqual(ks.all_urls(), {})

    def test_null_fields_excluded_from_all_urls(self) -> None:
        ks = KnownSources(llms_txt=None, github_org="https://github.com/org")
        urls = ks.all_urls()
        self.assertNotIn("llms_txt", urls)
        self.assertIn("github_org", urls)

    def test_confirmed_absent_default_empty(self) -> None:
        ks = KnownSources()
        self.assertEqual(ks.confirmed_absent, [])

    def test_confirmed_absent_populated(self) -> None:
        ks = KnownSources(confirmed_absent=["llms_txt", "rss_feed"])
        self.assertEqual(ks.confirmed_absent, ["llms_txt", "rss_feed"])

    def test_last_verified_field(self) -> None:
        ks = KnownSources(last_verified="2026-03-24")
        self.assertEqual(ks.last_verified, "2026-03-24")


class TestLoadRegistryKnownSources(unittest.TestCase):
    """Test that load_registry() parses known_sources correctly."""

    def _make_yaml(self, known_sources_block: str = "") -> str:
        return f"""
exchanges:
  - exchange_id: testex
    display_name: Test Exchange
    allowed_domains:
      - docs.testex.com
    {known_sources_block}
    sections:
      - section_id: api
        base_urls: ["https://api.testex.com"]
        seed_urls: ["https://docs.testex.com/api"]
"""

    def test_backward_compat_no_known_sources(self) -> None:
        """Registry without known_sources should parse with empty defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(self._make_yaml())
            f.flush()
            reg = load_registry(Path(f.name))
        ex = reg.get_exchange("testex")
        self.assertEqual(ex.known_sources.all_urls(), {})
        self.assertEqual(ex.known_sources.confirmed_absent, [])
        self.assertIsNone(ex.known_sources.last_verified)

    def test_known_sources_parsed(self) -> None:
        yaml_block = """known_sources:
      llms_txt: https://docs.testex.com/llms.txt
      github_org: https://github.com/testex
      confirmed_absent:
        - rss_feed
        - fix_docs
      last_verified: "2026-03-24"
    """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(self._make_yaml(yaml_block))
            f.flush()
            reg = load_registry(Path(f.name))
        ex = reg.get_exchange("testex")
        self.assertEqual(ex.known_sources.llms_txt, "https://docs.testex.com/llms.txt")
        self.assertEqual(ex.known_sources.github_org, "https://github.com/testex")
        self.assertIsNone(ex.known_sources.status_page)
        self.assertEqual(ex.known_sources.confirmed_absent, ["rss_feed", "fix_docs"])
        self.assertEqual(ex.known_sources.last_verified, "2026-03-24")

    def test_null_values_parsed_as_none(self) -> None:
        """Explicit null in YAML should become None in dataclass."""
        yaml_block = """known_sources:
      llms_txt: null
      github_org: https://github.com/testex
    """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(self._make_yaml(yaml_block))
            f.flush()
            reg = load_registry(Path(f.name))
        ex = reg.get_exchange("testex")
        self.assertIsNone(ex.known_sources.llms_txt)
        self.assertNotIn("llms_txt", ex.known_sources.all_urls())


class TestHtmlDetection(unittest.TestCase):
    """Test SPA shell / HTML detection helpers."""

    def test_doctype_html(self) -> None:
        self.assertTrue(_is_html_response("<!DOCTYPE html><html>", None))

    def test_html_tag(self) -> None:
        self.assertTrue(_is_html_response("<html lang='en'>", None))

    def test_bom_prefix_html(self) -> None:
        self.assertTrue(_is_html_response("\ufeff<!doctype html>", None))

    def test_whitespace_prefix_html(self) -> None:
        self.assertTrue(_is_html_response("  \n<!doctype html>", None))

    def test_content_type_html(self) -> None:
        self.assertTrue(_is_html_response("random body", "text/html; charset=utf-8"))

    def test_plain_text_not_html(self) -> None:
        self.assertFalse(_is_html_response("# llms.txt\n- [Page](/page)", None))

    def test_json_not_html(self) -> None:
        self.assertFalse(_is_html_response('{"openapi": "3.0"}', "application/json"))


class TestXmlDetection(unittest.TestCase):
    """Test XML detection for RSS/Atom feeds."""

    def test_xml_declaration(self) -> None:
        self.assertTrue(_is_xml_response("<?xml version='1.0'?>", None))

    def test_rss_tag(self) -> None:
        self.assertTrue(_is_xml_response("<rss version='2.0'>", None))

    def test_atom_feed_tag(self) -> None:
        self.assertTrue(_is_xml_response("<feed xmlns='http://www.w3.org/2005/Atom'>", None))

    def test_xml_content_type(self) -> None:
        self.assertTrue(_is_xml_response("body", "application/rss+xml"))

    def test_html_not_xml(self) -> None:
        self.assertFalse(_is_xml_response("<!doctype html><html>", "text/html"))


class TestValidateKnownSources(unittest.TestCase):
    """Test validate_known_sources() with mocked HTTP."""

    def _mock_exchange(self, ks: KnownSources) -> Registry:
        ex = Exchange(
            exchange_id="testex", display_name="Test", allowed_domains=["docs.testex.com"],
            sections=[], known_sources=ks,
        )
        return Registry(exchanges=[ex])

    def _mock_response(self, status: int = 200, text: str = "ok", url: str = "", ct: str = "text/plain") -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.text = text
        resp.url = url
        resp.headers = {"content-type": ct}
        return resp

    @patch("xdocs.known_sources.create_session")
    def test_llms_txt_plain_text_ok(self, mock_cs: MagicMock) -> None:
        session = MagicMock()
        session.get.return_value = self._mock_response(
            text="# llms.txt\n- [API](/api)", url="https://docs.testex.com/llms.txt",
        )
        mock_cs.return_value = session
        reg = self._mock_exchange(KnownSources(llms_txt="https://docs.testex.com/llms.txt"))
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertTrue(r["ok"])
        self.assertEqual(r["passed"], 1)
        self.assertEqual(r["exchanges"][0]["results"][0]["reason"], "ok")

    @patch("xdocs.known_sources.create_session")
    def test_llms_txt_spa_shell_detected(self, mock_cs: MagicMock) -> None:
        """The exact dYdX failure: SPA returns 200 + HTML for llms.txt route."""
        session = MagicMock()
        session.get.return_value = self._mock_response(
            text='<!doctype html><html lang="en"><head></head><body><div id="app"></div></body></html>',
            url="https://docs.testex.com/llms.txt",
            ct="text/html; charset=utf-8",
        )
        mock_cs.return_value = session
        reg = self._mock_exchange(KnownSources(llms_txt="https://docs.testex.com/llms.txt"))
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertFalse(r["ok"])
        self.assertEqual(r["failed"], 1)
        self.assertEqual(r["exchanges"][0]["results"][0]["reason"], "spa_shell")

    @patch("xdocs.known_sources.create_session")
    def test_llms_txt_bom_html_detected(self, mock_cs: MagicMock) -> None:
        """BOM + HTML should still be caught as SPA shell."""
        session = MagicMock()
        session.get.return_value = self._mock_response(
            text="\ufeff<!DOCTYPE html><html>",
            url="https://docs.testex.com/llms.txt",
        )
        mock_cs.return_value = session
        reg = self._mock_exchange(KnownSources(llms_full_txt="https://docs.testex.com/llms.txt"))
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertFalse(r["ok"])
        self.assertEqual(r["exchanges"][0]["results"][0]["reason"], "spa_shell")

    @patch("xdocs.known_sources.create_session")
    def test_http_404(self, mock_cs: MagicMock) -> None:
        session = MagicMock()
        session.get.return_value = self._mock_response(status=404, url="https://github.com/noexist")
        mock_cs.return_value = session
        reg = self._mock_exchange(KnownSources(github_org="https://github.com/noexist"))
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertFalse(r["ok"])
        self.assertEqual(r["exchanges"][0]["results"][0]["reason"], "http_404")

    @patch("xdocs.known_sources.create_session")
    def test_redirect_detected(self, mock_cs: MagicMock) -> None:
        session = MagicMock()
        session.get.return_value = self._mock_response(
            text="content", url="https://new-docs.testex.com/",
        )
        mock_cs.return_value = session
        reg = self._mock_exchange(KnownSources(changelog="https://old-docs.testex.com/changelog"))
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertTrue(r["ok"])
        result = r["exchanges"][0]["results"][0]
        self.assertEqual(result["reason"], "redirect")
        self.assertEqual(result["final_url"], "https://new-docs.testex.com/")

    @patch("xdocs.known_sources.create_session")
    def test_network_error(self, mock_cs: MagicMock) -> None:
        session = MagicMock()
        session.get.side_effect = ConnectionError("DNS resolution failed")
        mock_cs.return_value = session
        reg = self._mock_exchange(KnownSources(status_page="https://status.testex.com"))
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertFalse(r["ok"])
        self.assertEqual(r["exchanges"][0]["results"][0]["reason"], "network_error")

    @patch("xdocs.known_sources.create_session")
    def test_rss_xml_ok(self, mock_cs: MagicMock) -> None:
        session = MagicMock()
        session.get.return_value = self._mock_response(
            text='<?xml version="1.0"?><rss><channel></channel></rss>',
            url="https://docs.testex.com/feed.xml",
            ct="application/rss+xml",
        )
        mock_cs.return_value = session
        reg = self._mock_exchange(KnownSources(rss_feed="https://docs.testex.com/feed.xml"))
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertTrue(r["ok"])

    @patch("xdocs.known_sources.create_session")
    def test_rss_html_not_xml(self, mock_cs: MagicMock) -> None:
        session = MagicMock()
        session.get.return_value = self._mock_response(
            text="<!doctype html><html><body>Not RSS</body></html>",
            url="https://docs.testex.com/feed.xml",
            ct="text/html",
        )
        mock_cs.return_value = session
        reg = self._mock_exchange(KnownSources(rss_feed="https://docs.testex.com/feed.xml"))
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertFalse(r["ok"])
        self.assertEqual(r["exchanges"][0]["results"][0]["reason"], "not_xml")

    @patch("xdocs.known_sources.create_session")
    def test_empty_known_sources_skipped(self, mock_cs: MagicMock) -> None:
        reg = self._mock_exchange(KnownSources())
        r = validate_known_sources(registry=reg, exchange_id="testex")
        self.assertTrue(r["ok"])
        self.assertEqual(r["total"], 0)


if __name__ == "__main__":
    unittest.main()
