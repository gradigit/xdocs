from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from cex_api_docs.inventory import create_inventory
from cex_api_docs.inventory_fetch import fetch_inventory
from cex_api_docs.store import init_store

from .http_server import serve_directory


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


if __name__ == "__main__":
    unittest.main()
