from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from xdocs.errors import XDocsError
from xdocs.lock import acquire_write_lock
from xdocs.store import ensure_store_schema, init_store, migrate_store_schema


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestInit(unittest.TestCase):
    def test_init_idempotent_and_schema_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            schema_path = REPO_ROOT / "schema" / "schema.sql"

            r1 = init_store(docs_dir=str(docs_dir), schema_sql_path=schema_path, lock_timeout_s=1.0)
            self.assertEqual(r1["db"]["schema_user_version"], 6)
            self.assertTrue(Path(r1["db"]["path"]).exists())

            # Idempotent second run.
            r2 = init_store(docs_dir=str(docs_dir), schema_sql_path=schema_path, lock_timeout_s=1.0)
            self.assertEqual(r2["db"]["schema_user_version"], 6)

            conn = sqlite3.connect(docs_dir / "db" / "docs.db")
            try:
                names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master;").fetchall()}
            finally:
                conn.close()

            for required in (
                "pages",
                "pages_fts",
                "endpoints",
                "endpoints_fts",
                "review_queue",
                "inventories",
                "inventory_entries",
                "inventory_scope_ownership",
            ):
                self.assertIn(required, names)

    def test_lockfile_blocks_other_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            lock_path = docs_dir / "db" / ".write.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)

            holder_code = """
import sys, time
from pathlib import Path
from xdocs.lock import acquire_write_lock

lock_path = Path(sys.argv[1])
with acquire_write_lock(lock_path, timeout_s=0.0):
    time.sleep(2.0)
"""

            env = dict(**os.environ)
            # Ensure child can import from src/ when running without installation.
            env["PYTHONPATH"] = str(REPO_ROOT / "src") + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

            p = subprocess.Popen(
                [sys.executable, "-c", holder_code, str(lock_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            try:
                time.sleep(0.3)
                with self.assertRaises(XDocsError) as ctx:
                    with acquire_write_lock(lock_path, timeout_s=0.2):
                        pass
                self.assertEqual(ctx.exception.code, "ELOCKED")
            finally:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()

    def test_ensure_store_schema_migrates_v1_inventory_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            db_dir = docs_dir / "db"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "docs.db"

            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
CREATE TABLE inventories (
  id INTEGER PRIMARY KEY,
  exchange_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  sources_json TEXT NOT NULL,
  url_count INTEGER NOT NULL,
  inventory_hash TEXT NOT NULL
);

CREATE TABLE inventory_entries (
  id INTEGER PRIMARY KEY,
  inventory_id INTEGER NOT NULL REFERENCES inventories(id),
  canonical_url TEXT NOT NULL,
  status TEXT NOT NULL,
  last_fetched_at TEXT,
  last_http_status INTEGER,
  last_content_hash TEXT,
  last_final_url TEXT,
  last_page_canonical_url TEXT,
  error_json TEXT,
  UNIQUE (inventory_id, canonical_url)
);
"""
                )
                conn.execute("PRAGMA user_version = 1;")
                conn.commit()
            finally:
                conn.close()

            mig = ensure_store_schema(docs_dir=str(docs_dir), lock_timeout_s=1.0)
            self.assertTrue(mig["upgraded"])
            self.assertEqual(mig["schema_user_version_before"], 1)
            self.assertEqual(mig["schema_user_version_after"], 6)

            conn2 = sqlite3.connect(db_path)
            try:
                col_rows = conn2.execute("PRAGMA table_info(inventory_entries);").fetchall()
                cols = {str(r[1]) for r in col_rows}
                self.assertIn("last_etag", cols)
                self.assertIn("last_last_modified", cols)
                self.assertIn("last_cache_control", cols)

                names = {row[0] for row in conn2.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
                self.assertIn("inventory_scope_ownership", names)

                # Check endpoints.docs_url column exists (v2→v3 migration).
                ep_cols = {str(r[1]) for r in conn2.execute("PRAGMA table_info(endpoints);").fetchall()}
                self.assertIn("docs_url", ep_cols)

                # Check changelog_entries table exists (v3→v4 migration).
                self.assertIn("changelog_entries", names)

                uv = conn2.execute("PRAGMA user_version;").fetchone()
                assert uv is not None
                self.assertEqual(int(uv[0]), 6)
            finally:
                conn2.close()

    def test_migrate_store_schema_dry_run_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            db_dir = docs_dir / "db"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "docs.db"

            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
CREATE TABLE inventories (
  id INTEGER PRIMARY KEY,
  exchange_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  sources_json TEXT NOT NULL,
  url_count INTEGER NOT NULL,
  inventory_hash TEXT NOT NULL
);
CREATE TABLE inventory_entries (
  id INTEGER PRIMARY KEY,
  inventory_id INTEGER NOT NULL REFERENCES inventories(id),
  canonical_url TEXT NOT NULL,
  status TEXT NOT NULL,
  last_fetched_at TEXT,
  last_http_status INTEGER,
  last_content_hash TEXT,
  last_final_url TEXT,
  last_page_canonical_url TEXT,
  error_json TEXT,
  UNIQUE (inventory_id, canonical_url)
);
"""
                )
                conn.execute("PRAGMA user_version = 1;")
                conn.commit()
            finally:
                conn.close()

            dry = migrate_store_schema(docs_dir=str(docs_dir), lock_timeout_s=1.0, dry_run=True)
            self.assertTrue(dry["upgrade_required"])
            self.assertEqual(int(dry["schema_user_version"]), 1)

            applied = migrate_store_schema(docs_dir=str(docs_dir), lock_timeout_s=1.0, dry_run=False)
            self.assertTrue(applied["upgraded"])
            self.assertEqual(int(applied["schema_user_version_after"]), 6)

            dry2 = migrate_store_schema(docs_dir=str(docs_dir), lock_timeout_s=1.0, dry_run=True)
            self.assertFalse(dry2["upgrade_required"])
            self.assertEqual(int(dry2["schema_user_version"]), 6)


class TestVerifyImportSource(unittest.TestCase):
    """Test the import source guard in xdocs.__init__."""

    def test_passes_for_current_repo(self) -> None:
        from xdocs import verify_import_source

        result = verify_import_source(REPO_ROOT)
        self.assertTrue(result.exists())
        self.assertEqual(result.name, "xdocs")

    def test_passes_with_auto_detection(self) -> None:
        from xdocs import verify_import_source

        # When called from within the repo, auto-detection should work
        result = verify_import_source()
        self.assertTrue(result.exists())

    def test_fails_for_wrong_repo(self) -> None:
        from xdocs import verify_import_source

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError) as ctx:
                verify_import_source(tmp)
            self.assertIn("Wrong source tree imported", str(ctx.exception))
            self.assertIn("uv pip install", str(ctx.exception))


class TestSearchPagesSanitization(unittest.TestCase):
    """Test that search_pages() sanitizes FTS5-hostile characters."""

    def test_hyphenated_query_no_crash(self) -> None:
        """Hyphens in queries (e.g. X-MBX-APIKEY) must not crash FTS5."""
        from xdocs.pages import search_pages

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            schema_path = REPO_ROOT / "schema" / "schema.sql"
            init_store(docs_dir=str(docs_dir), schema_sql_path=schema_path, lock_timeout_s=1.0)

            # Should not raise -- hyphen is sanitized to a quoted term.
            results = search_pages(docs_dir=str(docs_dir), query="X-MBX-APIKEY", limit=5)
            self.assertIsInstance(results, list)

    def test_colon_query_no_crash(self) -> None:
        """Colons in queries (e.g. column:prefix) must not crash FTS5."""
        from xdocs.pages import search_pages

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            schema_path = REPO_ROOT / "schema" / "schema.sql"
            init_store(docs_dir=str(docs_dir), schema_sql_path=schema_path, lock_timeout_s=1.0)

            results = search_pages(docs_dir=str(docs_dir), query="title:hello", limit=5)
            self.assertIsInstance(results, list)

    def test_special_chars_query_no_crash(self) -> None:
        """Mixed special characters must not crash FTS5."""
        from xdocs.pages import search_pages

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            schema_path = REPO_ROOT / "schema" / "schema.sql"
            init_store(docs_dir=str(docs_dir), schema_sql_path=schema_path, lock_timeout_s=1.0)

            results = search_pages(
                docs_dir=str(docs_dir),
                query="rate-limit /api/v1/order?symbol=BTC",
                limit=5,
            )
            self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
