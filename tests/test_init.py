from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from cex_api_docs.errors import CexApiDocsError
from cex_api_docs.lock import acquire_write_lock
from cex_api_docs.store import init_store


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestInit(unittest.TestCase):
    def test_init_idempotent_and_schema_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            schema_path = REPO_ROOT / "schema" / "schema.sql"

            r1 = init_store(docs_dir=str(docs_dir), schema_sql_path=schema_path, lock_timeout_s=1.0)
            self.assertEqual(r1["db"]["schema_user_version"], 1)
            self.assertTrue(Path(r1["db"]["path"]).exists())

            # Idempotent second run.
            r2 = init_store(docs_dir=str(docs_dir), schema_sql_path=schema_path, lock_timeout_s=1.0)
            self.assertEqual(r2["db"]["schema_user_version"], 1)

            conn = sqlite3.connect(docs_dir / "db" / "docs.db")
            try:
                names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master;").fetchall()}
            finally:
                conn.close()

            for required in ("pages", "pages_fts", "endpoints", "endpoints_fts", "review_queue"):
                self.assertIn(required, names)

    def test_lockfile_blocks_other_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            lock_path = docs_dir / "db" / ".write.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)

            holder_code = """
import sys, time
from pathlib import Path
from cex_api_docs.lock import acquire_write_lock

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
                with self.assertRaises(CexApiDocsError) as ctx:
                    with acquire_write_lock(lock_path, timeout_s=0.2):
                        pass
                self.assertEqual(ctx.exception.code, "ELOCKED")
            finally:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()


if __name__ == "__main__":
    unittest.main()
