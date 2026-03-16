"""Tests for link_check module."""

from __future__ import annotations

import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests.http_server import serve_handler


# ---------------------------------------------------------------------------
# Test HTTP handler
# ---------------------------------------------------------------------------

class LinkCheckHandler(BaseHTTPRequestHandler):
    """Minimal handler for link-check tests."""

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_HEAD(self):
        path = self.path
        if path == "/ok":
            self.send_response(200)
            self.end_headers()
        elif path == "/not-found":
            self.send_response(404)
            self.end_headers()
        elif path == "/head-not-allowed":
            self.send_response(405)
            self.end_headers()
        elif path == "/redirect":
            self.send_response(301)
            # Build absolute redirect URL from Host header.
            host = self.headers.get("Host", "localhost")
            self.send_header("Location", f"http://{host}/ok")
            self.end_headers()
        elif path == "/slow":
            import time
            time.sleep(5)
            self.send_response(200)
            self.end_headers()
        elif path == "/server-error":
            self.send_response(500)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        path = self.path
        if path == "/head-not-allowed":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        elif path == "/ok":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()


# ---------------------------------------------------------------------------
# Fixture: minimal store with pages table
# ---------------------------------------------------------------------------

@pytest.fixture
def store_with_urls(tmp_path: Path):
    """Create a minimal SQLite store with a pages table."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "docs.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY,
            canonical_url TEXT,
            domain TEXT,
            title TEXT,
            word_count INTEGER DEFAULT 0,
            markdown_path TEXT,
            content_hash TEXT
        )
    """)
    # Set user_version so require_store_db doesn't fail.
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()
    return tmp_path


def _insert_page(store_path: Path, url: str, domain: str = "localhost") -> None:
    db_path = store_path / "db" / "docs.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO pages (canonical_url, domain) VALUES (?, ?)",
        (url, domain),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCheckStoredLinks:
    def test_head_200_ok(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        with serve_handler(LinkCheckHandler) as base_url:
            _insert_page(store_with_urls, f"{base_url}/ok")
            report = check_stored_links(
                docs_dir=str(store_with_urls),
                timeout_s=5.0,
                concurrency=1,
                delay_s=0.0,
            )
        assert report.checked == 1
        assert report.ok == 1
        assert report.client_error == 0
        assert report.network_error == 0
        assert len(report.results) == 0  # No non-ok results

    def test_head_404_error(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        with serve_handler(LinkCheckHandler) as base_url:
            _insert_page(store_with_urls, f"{base_url}/not-found")
            report = check_stored_links(
                docs_dir=str(store_with_urls),
                timeout_s=5.0,
                concurrency=1,
                delay_s=0.0,
            )
        assert report.checked == 1
        assert report.ok == 0
        assert report.client_error == 1
        assert len(report.results) == 1
        assert report.results[0].http_status == 404

    def test_head_405_get_fallback(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        with serve_handler(LinkCheckHandler) as base_url:
            _insert_page(store_with_urls, f"{base_url}/head-not-allowed")
            report = check_stored_links(
                docs_dir=str(store_with_urls),
                timeout_s=5.0,
                concurrency=1,
                delay_s=0.0,
            )
        assert report.checked == 1
        assert report.ok == 1
        assert report.client_error == 0

    def test_server_error(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        with serve_handler(LinkCheckHandler) as base_url:
            _insert_page(store_with_urls, f"{base_url}/server-error")
            report = check_stored_links(
                docs_dir=str(store_with_urls),
                timeout_s=5.0,
                concurrency=1,
                delay_s=0.0,
            )
        assert report.checked == 1
        assert report.server_error == 1

    def test_timeout_network_error(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        with serve_handler(LinkCheckHandler) as base_url:
            _insert_page(store_with_urls, f"{base_url}/slow")
            report = check_stored_links(
                docs_dir=str(store_with_urls),
                timeout_s=0.5,  # Very short to trigger timeout
                concurrency=1,
                delay_s=0.0,
            )
        assert report.checked == 1
        assert report.network_error == 1

    def test_exchange_filter(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        with serve_handler(LinkCheckHandler) as base_url:
            _insert_page(store_with_urls, f"{base_url}/ok", domain="docs.binance.com")
            _insert_page(store_with_urls, f"{base_url}/ok", domain="docs.okx.com")
            report = check_stored_links(
                docs_dir=str(store_with_urls),
                exchange="binance",
                timeout_s=5.0,
                concurrency=1,
                delay_s=0.0,
            )
        assert report.checked == 1  # Only binance

    def test_sample_limit(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        with serve_handler(LinkCheckHandler) as base_url:
            for i in range(10):
                _insert_page(store_with_urls, f"{base_url}/ok?p={i}")
            report = check_stored_links(
                docs_dir=str(store_with_urls),
                sample=3,
                timeout_s=5.0,
                concurrency=1,
                delay_s=0.0,
            )
        assert report.checked == 3

    def test_redirect_detected(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        with serve_handler(LinkCheckHandler) as base_url:
            _insert_page(store_with_urls, f"{base_url}/redirect")
            report = check_stored_links(
                docs_dir=str(store_with_urls),
                timeout_s=5.0,
                concurrency=1,
                delay_s=0.0,
            )
        assert report.checked == 1
        assert report.redirect == 1
        assert len(report.results) == 1
        assert report.results[0].redirect_url is not None

    def test_non_http_scheme_skipped(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        _insert_page(store_with_urls, "ftp://example.com/file")
        report = check_stored_links(
            docs_dir=str(store_with_urls),
            timeout_s=5.0,
            concurrency=1,
            delay_s=0.0,
        )
        assert report.checked == 1
        assert report.network_error == 1
        assert "non-HTTP scheme" in report.results[0].error

    def test_empty_store(self, store_with_urls: Path):
        from xdocs.link_check import check_stored_links

        report = check_stored_links(
            docs_dir=str(store_with_urls),
            timeout_s=5.0,
            concurrency=1,
            delay_s=0.0,
        )
        assert report.checked == 0
        assert report.ok == 0
