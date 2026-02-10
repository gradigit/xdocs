from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from cex_api_docs.stale_citations import detect_stale_citations
from cex_api_docs.store import init_store


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestStaleCitations(unittest.TestCase):
    def test_detect_stale_citations_no_filters_does_not_break_left_join_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            db_path = docs_dir / "db" / "docs.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                # Minimal page row (required NOT NULL cols).
                conn.execute(
                    """
INSERT INTO pages (canonical_url, url, final_url, domain, path_hash, content_hash)
VALUES (?, ?, ?, ?, ?, ?);
""",
                    (
                        "https://example.test/page1",
                        "https://example.test/page1",
                        "https://example.test/page1",
                        "example.test",
                        "p1",
                        "hash_current",
                    ),
                )
                conn.execute(
                    """
INSERT INTO pages (canonical_url, url, final_url, domain, path_hash, content_hash)
VALUES (?, ?, ?, ?, ?, ?);
""",
                    (
                        "https://example.test/page3",
                        "https://example.test/page3",
                        "https://example.test/page3",
                        "example.test",
                        "p3",
                        "hash_new",
                    ),
                )

                # Endpoints + sources.
                conn.execute(
                    """
INSERT INTO endpoints (endpoint_id, exchange, section, protocol, json, updated_at)
VALUES (?, ?, ?, ?, ?, ?);
""",
                    ("e1", "ex", "sec", "http", "{}", "2026-02-10T00:00:00Z"),
                )

                # One valid citation (page exists, hash matches).
                conn.execute(
                    """
INSERT INTO endpoint_sources (endpoint_id, field_name, page_canonical_url, page_content_hash, created_at)
VALUES (?, ?, ?, ?, ?);
""",
                    ("e1", "rate_limit", "https://example.test/page1", "hash_current", "2026-02-10T00:00:00Z"),
                )

                # One missing source (page row does not exist).
                conn.execute(
                    """
INSERT INTO endpoint_sources (endpoint_id, field_name, page_canonical_url, page_content_hash, created_at)
VALUES (?, ?, ?, ?, ?);
""",
                    ("e1", "permissions", "https://example.test/page2", "hash_missing", "2026-02-10T00:00:00Z"),
                )

                # One stale source (page exists, but current hash differs).
                conn.execute(
                    """
INSERT INTO endpoint_sources (endpoint_id, field_name, page_canonical_url, page_content_hash, created_at)
VALUES (?, ?, ?, ?, ?);
""",
                    ("e1", "errors", "https://example.test/page3", "hash_old", "2026-02-10T00:00:00Z"),
                )

                conn.commit()
            finally:
                conn.close()

            r = detect_stale_citations(docs_dir=str(docs_dir), lock_timeout_s=1.0, exchange=None, section=None, dry_run=True, limit=None)
            counts = r["counts"]

            # Regression: without filters, missing_source should not explode to all sources.
            self.assertEqual(int(counts["missing_source"]), 1)
            self.assertEqual(int(counts["stale_citation"]), 1)
            self.assertEqual(int(counts["total_findings"]), 2)


if __name__ == "__main__":
    unittest.main()

