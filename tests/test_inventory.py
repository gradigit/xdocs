from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler

from cex_api_docs.inventory import create_inventory
from cex_api_docs.inventory_fetch import fetch_inventory
from cex_api_docs.store import init_store

from .http_server import serve_directory, serve_handler


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestInventory(unittest.TestCase):
    def test_inventory_and_fetch_inventory_with_local_sitemap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Serve a fake doc site.
            site = tmp_path / "site"
            (site / "docs").mkdir(parents=True, exist_ok=True)
            (site / "other").mkdir(parents=True, exist_ok=True)

            (site / "robots.txt").write_text(
                "User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n",
                encoding="utf-8",
            )
            (site / "sitemap.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{BASE}/docs/a.html</loc></url>
  <url><loc>{BASE}/docs/b.html</loc></url>
  <url><loc>{BASE}/other/out.html</loc></url>
</urlset>
""",
                encoding="utf-8",
            )

            (site / "docs" / "a.html").write_text("<html><head><title>A</title></head><body><h1>A</h1>Hello A</body></html>\n", encoding="utf-8")
            (site / "docs" / "b.html").write_text("<html><head><title>B</title></head><body><h1>B</h1>Hello B</body></html>\n", encoding="utf-8")
            (site / "docs" / "intro.html").write_text("<html><head><title>Intro</title></head><body><h1>Intro</h1>Hello</body></html>\n", encoding="utf-8")
            (site / "other" / "out.html").write_text("<html><body>OUT</body></html>\n", encoding="utf-8")

            with serve_directory(site) as base:
                # Fill in BASE in robots + sitemap now that we have a port.
                (site / "robots.txt").write_text(
                    (site / "robots.txt").read_text(encoding="utf-8").replace("{BASE}", base),
                    encoding="utf-8",
                )
                (site / "sitemap.xml").write_text(
                    (site / "sitemap.xml").read_text(encoding="utf-8").replace("{BASE}", base),
                    encoding="utf-8",
                )

                # Init a fresh local store.
                docs_dir = tmp_path / "cex-docs"
                init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

                seed = f"{base}/docs/intro.html"
                inv = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=[seed],
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )

                # Inventory should include docs/a, docs/b, and the seed intro. It should exclude /other/out.
                self.assertEqual(inv.url_count, 3)

                # Ensure inventory persisted.
                conn = sqlite3.connect(docs_dir / "db" / "docs.db")
                conn.row_factory = sqlite3.Row
                try:
                    n = conn.execute("SELECT COUNT(*) AS n FROM inventory_entries WHERE inventory_id = ?;", (int(inv.inventory_id),)).fetchone()
                    assert n is not None
                    self.assertEqual(int(n["n"]), 3)
                finally:
                    conn.close()

                fr = fetch_inventory(
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
                )
                self.assertEqual(fr["counts"]["errors"], 0)
                self.assertEqual(fr["counts"]["stored"], 3)

                conn2 = sqlite3.connect(docs_dir / "db" / "docs.db")
                conn2.row_factory = sqlite3.Row
                try:
                    fetched = conn2.execute(
                        "SELECT COUNT(*) AS n FROM inventory_entries WHERE inventory_id = ? AND status = 'fetched';",
                        (int(inv.inventory_id),),
                    ).fetchone()
                    assert fetched is not None
                    self.assertEqual(int(fetched["n"]), 3)
                finally:
                    conn2.close()


    def test_force_refetch_redownloads_fetched_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            site = tmp_path / "site"
            (site / "docs").mkdir(parents=True, exist_ok=True)
            (site / "docs" / "a.html").write_text(
                "<html><head><title>A</title></head><body><h1>A</h1>Hello A content here</body></html>\n",
                encoding="utf-8",
            )
            (site / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

            with serve_directory(site) as base:
                docs_dir = tmp_path / "cex-docs"
                init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

                seed = f"{base}/docs/a.html"
                inv = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=[seed],
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )
                self.assertEqual(inv.url_count, 1)

                # First fetch.
                fr1 = fetch_inventory(
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
                )
                self.assertEqual(fr1["counts"]["stored"], 1)
                self.assertEqual(fr1["counts"]["new_pages"], 1)

                # Modify the content on disk.
                (site / "docs" / "a.html").write_text(
                    "<html><head><title>A</title></head><body><h1>A</h1>Updated content here now</body></html>\n",
                    encoding="utf-8",
                )

                # Force-refetch: should re-download and detect the update.
                fr2 = fetch_inventory(
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
                    force_refetch=True,
                )
                self.assertEqual(fr2["counts"]["stored"], 1)
                self.assertEqual(fr2["counts"]["updated_pages"], 1)
                self.assertEqual(fr2["counts"]["new_pages"], 0)

    def test_force_refetch_and_resume_mutual_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            site = tmp_path / "site"
            site.mkdir(parents=True, exist_ok=True)
            (site / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
            (site / "a.html").write_text("<html><body>A</body></html>\n", encoding="utf-8")

            with serve_directory(site) as base:
                docs_dir = tmp_path / "cex-docs"
                init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

                inv = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=[f"{base}/a.html"],
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )

                from cex_api_docs.errors import CexApiDocsError

                with self.assertRaises(CexApiDocsError) as ctx:
                    fetch_inventory(
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
                        render_mode="http",
                        resume=True,
                        force_refetch=True,
                    )
                self.assertEqual(ctx.exception.code, "EBADARG")

    def test_scope_dedupe_respects_priority_and_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            site = tmp_path / "site"
            site.mkdir(parents=True, exist_ok=True)
            (site / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
            (site / "a.html").write_text("<html><body><h1>A</h1>alpha</body></html>\n", encoding="utf-8")
            (site / "b.html").write_text("<html><body><h1>B</h1>beta</body></html>\n", encoding="utf-8")

            with serve_directory(site) as base:
                docs_dir = tmp_path / "cex-docs"
                init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

                seed_urls = [f"{base}/a.html", f"{base}/b.html"]
                inv_a = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs_a",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=seed_urls,
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )
                inv_b = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs_b",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=seed_urls,
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )

                # First owner claims URLs.
                fr_a = fetch_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs_a",
                    inventory_id=int(inv_a.inventory_id),
                    allowed_domains=["127.0.0.1"],
                    delay_s=0.0,
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                    render_mode="http",
                    scope_dedupe=True,
                    scope_group="testex",
                    scope_priority=10,
                )
                self.assertEqual(fr_a["counts"]["stored"], 2)
                self.assertEqual(fr_a["counts"]["dedupe_skipped"], 0)

                # Lower-priority section should be dedupe-skipped.
                fr_b = fetch_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs_b",
                    inventory_id=int(inv_b.inventory_id),
                    allowed_domains=["127.0.0.1"],
                    delay_s=0.0,
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                    render_mode="http",
                    scope_dedupe=True,
                    scope_group="testex",
                    scope_priority=20,
                )
                self.assertEqual(fr_b["counts"]["stored"], 0)
                self.assertEqual(fr_b["counts"]["dedupe_skipped"], 2)

                # Higher-priority section can claim ownership.
                inv_c = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs_c",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=seed_urls,
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )
                fr_c = fetch_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs_c",
                    inventory_id=int(inv_c.inventory_id),
                    allowed_domains=["127.0.0.1"],
                    delay_s=0.0,
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                    render_mode="http",
                    scope_dedupe=True,
                    scope_group="testex",
                    scope_priority=5,
                )
                self.assertEqual(fr_c["counts"]["stored"], 2)
                self.assertEqual(fr_c["counts"]["dedupe_skipped"], 0)

                conn = sqlite3.connect(docs_dir / "db" / "docs.db")
                conn.row_factory = sqlite3.Row
                try:
                    rows = conn.execute(
                        """
SELECT canonical_url, owner_section_id, owner_priority
FROM inventory_scope_ownership
WHERE scope_group = 'testex'
ORDER BY canonical_url;
"""
                    ).fetchall()
                    self.assertEqual(len(rows), 2)
                    self.assertTrue(all(str(r["owner_section_id"]) == "docs_c" for r in rows))
                    self.assertTrue(all(int(r["owner_priority"]) == 5 for r in rows))
                finally:
                    conn.close()

    def test_conditional_revalidation_304_uses_cached_validators(self) -> None:
        etag = '"v1"'
        last_mod = "Wed, 21 Oct 2015 07:28:00 GMT"
        body = b"<html><head><title>A</title></head><body><h1>A</h1>hello world</body></html>"

        class ConditionalHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/robots.txt":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"User-agent: *\nAllow: /\n")
                    return

                if self.path == "/docs/a.html":
                    inm = self.headers.get("If-None-Match")
                    if inm == etag:
                        self.send_response(304)
                        self.send_header("ETag", etag)
                        self.send_header("Last-Modified", last_mod)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("ETag", etag)
                    self.send_header("Last-Modified", last_mod)
                    self.end_headers()
                    self.wfile.write(body)
                    return

                self.send_response(404)
                self.end_headers()

            def log_message(self, _format: str, *_args) -> None:  # noqa: D401
                return

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docs_dir = tmp_path / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_handler(ConditionalHandler) as base:
                inv = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=[f"{base}/docs/a.html"],
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )

                first = fetch_inventory(
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
                    conditional=True,
                )
                self.assertEqual(first["counts"]["stored"], 1)
                self.assertEqual(first["counts"]["revalidated_unchanged"], 0)

                second = fetch_inventory(
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
                    conditional=True,
                )
                self.assertEqual(second["counts"]["stored"], 0)
                self.assertEqual(second["counts"]["fetched"], 1)
                self.assertEqual(second["counts"]["revalidated_unchanged"], 1)

                conn = sqlite3.connect(docs_dir / "db" / "docs.db")
                conn.row_factory = sqlite3.Row
                try:
                    row = conn.execute(
                        "SELECT last_http_status, last_etag, last_last_modified FROM inventory_entries WHERE inventory_id = ? LIMIT 1;",
                        (int(inv.inventory_id),),
                    ).fetchone()
                    assert row is not None
                    self.assertEqual(int(row["last_http_status"]), 304)
                    self.assertEqual(str(row["last_etag"]), etag)
                    self.assertEqual(str(row["last_last_modified"]), last_mod)

                    pv = conn.execute("SELECT COUNT(*) AS n FROM page_versions;").fetchone()
                    assert pv is not None
                    self.assertEqual(int(pv["n"]), 1)
                finally:
                    conn.close()

    def test_conditional_304_reclaims_scope_ownership_when_missing(self) -> None:
        etag = '"v1"'
        body = b"<html><head><title>A</title></head><body><h1>A</h1>hello world</body></html>"

        class ConditionalHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/robots.txt":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"User-agent: *\nAllow: /\n")
                    return

                if self.path == "/docs/a.html":
                    inm = self.headers.get("If-None-Match")
                    if inm == etag:
                        self.send_response(304)
                        self.send_header("ETag", etag)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("ETag", etag)
                    self.end_headers()
                    self.wfile.write(body)
                    return

                self.send_response(404)
                self.end_headers()

            def log_message(self, _format: str, *_args) -> None:  # noqa: D401
                return

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docs_dir = tmp_path / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            with serve_handler(ConditionalHandler) as base:
                inv = create_inventory(
                    docs_dir=str(docs_dir),
                    lock_timeout_s=1.0,
                    exchange_id="testex",
                    section_id="docs",
                    allowed_domains=["127.0.0.1"],
                    seed_urls=[f"{base}/docs/a.html"],
                    timeout_s=5.0,
                    max_bytes=2_000_000,
                    max_redirects=3,
                    retries=0,
                    ignore_robots=False,
                )

                first = fetch_inventory(
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
                    conditional=True,
                    scope_dedupe=True,
                    scope_group="testex",
                    scope_priority=10,
                )
                self.assertEqual(first["counts"]["stored"], 1)

                conn = sqlite3.connect(docs_dir / "db" / "docs.db")
                conn.row_factory = sqlite3.Row
                try:
                    deleted = conn.execute(
                        "DELETE FROM inventory_scope_ownership WHERE scope_group = ?;",
                        ("testex",),
                    )
                    self.assertEqual(int(deleted.rowcount), 1)
                    conn.commit()
                finally:
                    conn.close()

                second = fetch_inventory(
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
                    conditional=True,
                    scope_dedupe=True,
                    scope_group="testex",
                    scope_priority=10,
                )
                self.assertEqual(second["counts"]["stored"], 0)
                self.assertEqual(second["counts"]["revalidated_unchanged"], 1)

                conn2 = sqlite3.connect(docs_dir / "db" / "docs.db")
                conn2.row_factory = sqlite3.Row
                try:
                    owner = conn2.execute(
                        """
SELECT owner_exchange_id, owner_section_id, owner_priority
FROM inventory_scope_ownership
WHERE scope_group = ? AND canonical_url = ?;
""",
                        ("testex", f"{base}/docs/a.html"),
                    ).fetchone()
                    assert owner is not None
                    self.assertEqual(str(owner["owner_exchange_id"]), "testex")
                    self.assertEqual(str(owner["owner_section_id"]), "docs")
                    self.assertEqual(int(owner["owner_priority"]), 10)
                finally:
                    conn2.close()


if __name__ == "__main__":
    unittest.main()
