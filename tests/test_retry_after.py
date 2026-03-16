from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from xdocs.inventory import create_inventory
from xdocs.inventory_fetch import _parse_retry_after_seconds, fetch_inventory
from xdocs.store import init_store

from .http_server import serve_handler


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestRetryAfter(unittest.TestCase):
    def test_parse_retry_after_seconds_integer(self) -> None:
        self.assertEqual(_parse_retry_after_seconds("5"), 5.0)
        self.assertEqual(_parse_retry_after_seconds("0"), 0.0)

    def test_parse_retry_after_seconds_http_date(self) -> None:
        now = datetime.now(timezone.utc)
        future = now + timedelta(seconds=4)
        header = format_datetime(future)
        parsed = _parse_retry_after_seconds(header, now_epoch_s=now.timestamp())
        assert parsed is not None
        self.assertGreaterEqual(parsed, 3.0)
        self.assertLessEqual(parsed, 5.0)

    def test_fetch_inventory_applies_retry_after_delay(self) -> None:
        request_times: dict[str, list[float]] = {"a": [], "b": []}

        class RetryAfterHandler(BaseHTTPRequestHandler):
            _a_hits = 0

            def do_GET(self):  # noqa: N802
                if self.path == "/robots.txt":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"User-agent: *\nAllow: /\n")
                    return

                if self.path == "/docs/a.html":
                    request_times["a"].append(time.monotonic())
                    RetryAfterHandler._a_hits += 1
                    if RetryAfterHandler._a_hits == 1:
                        self.send_response(429)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Retry-After", "1")
                        self.end_headers()
                        self.wfile.write(b"<html><body>busy</body></html>")
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h1>A</h1>ok</body></html>")
                    return

                if self.path == "/docs/b.html":
                    request_times["b"].append(time.monotonic())
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h1>B</h1>ok</body></html>")
                    return

                self.send_response(404)
                self.end_headers()

            def log_message(self, _format: str, *_args) -> None:  # noqa: D401
                return

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docs_dir = tmp_path / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_handler(RetryAfterHandler) as base:
                inv = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=[f"{base}/docs/a.html", f"{base}/docs/b.html"],
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )

                # Reset hit counter — create_inventory's auto link-follow
                # fallback may have fetched the seeds (consuming the first 429).
                RetryAfterHandler._a_hits = 0
                request_times["a"].clear()
                request_times["b"].clear()

                result = fetch_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    inventory_id=int(inv.inventory_id),
                    allowed_domains=["127.0.0.1"],
                    delay_s=0.0,
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                    render_mode="http",
                    adaptive_delay=True,
                    max_domain_delay_s=2.0,
                )

                self.assertEqual(result["counts"]["retry_after_applied"], 1)
                self.assertGreaterEqual(len(request_times["a"]), 1)
                self.assertGreaterEqual(len(request_times["b"]), 1)
                self.assertGreaterEqual(request_times["b"][0] - request_times["a"][0], 0.9)

                snapshot = result.get("domain_delay_snapshot") or {}
                host_state = snapshot.get("127.0.0.1") or {}
                self.assertEqual(int(host_state.get("retry_after_applied") or 0), 1)
                self.assertGreaterEqual(float(host_state.get("current_delay_s") or 0.0), 0.0)

    def test_fetch_inventory_applies_retry_after_delay_with_concurrency(self) -> None:
        arrivals: list[float] = []
        first_hit = {"seen": False}

        class RetryAfterConcurrentHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/robots.txt":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"User-agent: *\nAllow: /\n")
                    return

                if self.path in {"/docs/a.html", "/docs/b.html"}:
                    arrivals.append(time.monotonic())
                    if not first_hit["seen"]:
                        first_hit["seen"] = True
                        self.send_response(429)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Retry-After", "1")
                        self.end_headers()
                        self.wfile.write(b"<html><body>busy</body></html>")
                        return

                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h1>ok</h1></body></html>")
                    return

                self.send_response(404)
                self.end_headers()

            def log_message(self, _format: str, *_args) -> None:  # noqa: D401
                return

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docs_dir = tmp_path / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_handler(RetryAfterConcurrentHandler) as base:
                inv = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=[f"{base}/docs/a.html", f"{base}/docs/b.html"],
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )

                # Reset hit flag — create_inventory's auto link-follow
                # fallback may have fetched the seeds (consuming the first 429).
                first_hit["seen"] = False
                arrivals.clear()

                result = fetch_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    inventory_id=int(inv.inventory_id),
                    allowed_domains=["127.0.0.1"],
                    delay_s=0.0,
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                    render_mode="http",
                    concurrency=2,
                    adaptive_delay=True,
                    max_domain_delay_s=2.0,
                )

                self.assertEqual(result["counts"]["retry_after_applied"], 1)
                self.assertEqual(len(arrivals), 2)
                self.assertGreaterEqual(arrivals[1] - arrivals[0], 0.9)


if __name__ == "__main__":
    unittest.main()
