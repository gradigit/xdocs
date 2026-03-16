from __future__ import annotations

import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from xdocs.sitemap_validate import (
    SitemapCrossValidation,
    SitemapHealth,
    cross_validate_sitemap,
)
from xdocs.sitemaps import SitemapEntry, parse_sitemap_bytes
from xdocs.sitemap_validate import _check_sitemap, _count_stale

import requests

from .http_server import serve_handler


class TestCrossValidateSitemap:
    def test_basic_overlap(self) -> None:
        result = cross_validate_sitemap(
            sitemap_urls=["https://a.com/1", "https://a.com/2", "https://a.com/3"],
            store_urls=["https://a.com/2", "https://a.com/3", "https://a.com/4"],
        )
        assert result.in_both == ["https://a.com/2", "https://a.com/3"]
        assert result.in_sitemap_only == ["https://a.com/1"]
        assert result.in_store_only == ["https://a.com/4"]

    def test_empty_sitemap(self) -> None:
        result = cross_validate_sitemap(
            sitemap_urls=[],
            store_urls=["https://a.com/1"],
        )
        assert result.in_both == []
        assert result.in_sitemap_only == []
        assert result.in_store_only == ["https://a.com/1"]
        assert result.sitemap_url == ""

    def test_empty_store(self) -> None:
        result = cross_validate_sitemap(
            sitemap_urls=["https://a.com/1"],
            store_urls=[],
        )
        assert result.in_both == []
        assert result.in_sitemap_only == ["https://a.com/1"]
        assert result.in_store_only == []

    def test_identical_sets(self) -> None:
        urls = ["https://a.com/1", "https://a.com/2"]
        result = cross_validate_sitemap(sitemap_urls=urls, store_urls=urls)
        assert result.in_both == sorted(urls)
        assert result.in_sitemap_only == []
        assert result.in_store_only == []


class TestCountStale:
    def test_no_lastmod(self) -> None:
        entries = [SitemapEntry(loc="https://a.com/1")]
        assert _count_stale(entries) == 0

    def test_recent_entry(self) -> None:
        entries = [SitemapEntry(loc="https://a.com/1", lastmod="2026-01-01")]
        assert _count_stale(entries) == 0

    def test_stale_entry(self) -> None:
        entries = [SitemapEntry(loc="https://a.com/1", lastmod="2020-01-01")]
        assert _count_stale(entries) == 1

    def test_stale_with_datetime(self) -> None:
        entries = [SitemapEntry(loc="https://a.com/1", lastmod="2020-01-01T00:00:00Z")]
        assert _count_stale(entries) == 1

    def test_mixed(self) -> None:
        entries = [
            SitemapEntry(loc="https://a.com/1", lastmod="2020-01-01"),
            SitemapEntry(loc="https://a.com/2", lastmod="2026-02-01"),
            SitemapEntry(loc="https://a.com/3"),
        ]
        assert _count_stale(entries) == 1


class TestCheckSitemap:
    def test_healthy_sitemap(self) -> None:
        sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://a.com/1</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>https://a.com/2</loc></url>
</urlset>"""

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.end_headers()
                self.wfile.write(sitemap_xml)

            def log_message(self, _format, *_args):
                return

        session = requests.Session()
        with serve_handler(Handler) as base:
            h = _check_sitemap(session, url=f"{base}/sitemap.xml", timeout_s=5.0)
            assert h.reachable is True
            assert h.http_status == 200
            assert h.entry_count == 2
            assert h.has_lastmod is True
            assert h.error is None

    def test_404_sitemap(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(404)
                self.end_headers()

            def log_message(self, _format, *_args):
                return

        session = requests.Session()
        with serve_handler(Handler) as base:
            h = _check_sitemap(session, url=f"{base}/sitemap.xml", timeout_s=5.0)
            assert h.reachable is True
            assert h.http_status == 404
            assert h.entry_count == 0
            assert h.error == "HTTP 404"

    def test_invalid_xml(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.end_headers()
                self.wfile.write(b"not valid xml at all <<<<")

            def log_message(self, _format, *_args):
                return

        session = requests.Session()
        with serve_handler(Handler) as base:
            h = _check_sitemap(session, url=f"{base}/sitemap.xml", timeout_s=5.0)
            assert h.reachable is True
            assert h.http_status == 200
            assert h.entry_count == 0
            assert h.error is not None


class TestSitemapParseResultEntries:
    """Verify that the enhanced SitemapParseResult includes entries with metadata."""

    def test_entries_with_metadata(self) -> None:
        data = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://a.com/1</loc>
    <lastmod>2026-01-15</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://a.com/2</loc>
  </url>
</urlset>"""
        result = parse_sitemap_bytes(data=data, url="https://a.com/sitemap.xml")
        assert result.kind == "urlset"
        assert result.locs == ["https://a.com/1", "https://a.com/2"]
        assert len(result.entries) == 2

        e0 = result.entries[0]
        assert e0.loc == "https://a.com/1"
        assert e0.lastmod == "2026-01-15"
        assert e0.changefreq == "weekly"
        assert e0.priority == "0.8"

        e1 = result.entries[1]
        assert e1.loc == "https://a.com/2"
        assert e1.lastmod is None
        assert e1.changefreq is None
        assert e1.priority is None

    def test_sitemap_index_entries(self) -> None:
        data = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>https://a.com/sitemap1.xml</loc>
    <lastmod>2026-02-01</lastmod>
  </sitemap>
</sitemapindex>"""
        result = parse_sitemap_bytes(data=data, url="https://a.com/sitemap_index.xml")
        assert result.kind == "sitemap_index"
        assert result.locs == ["https://a.com/sitemap1.xml"]
        assert len(result.entries) == 1
        assert result.entries[0].lastmod == "2026-02-01"

    def test_backward_compat_locs(self) -> None:
        """Existing callers using .locs should still get the same flat list."""
        data = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://a.com/page1</loc></url>
  <url><loc>https://a.com/page2</loc></url>
</urlset>"""
        result = parse_sitemap_bytes(data=data, url="https://a.com/sitemap.xml")
        assert result.locs == ["https://a.com/page1", "https://a.com/page2"]
