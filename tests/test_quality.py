from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cex_api_docs.db import open_db
from cex_api_docs.quality import quality_check
from cex_api_docs.store import init_store

REPO_ROOT = Path(__file__).resolve().parents[1]


def _insert_page(conn, *, canonical_url: str, word_count: int, raw_path: str) -> None:
    conn.execute(
        """
INSERT INTO pages (canonical_url, url, final_url, domain, path_hash, title, word_count, raw_path, content_hash)
VALUES (?, ?, ?, 'example.com', 'h', 'T', ?, ?, 'ch');
""",
        (canonical_url, canonical_url, canonical_url, word_count, raw_path),
    )
    conn.commit()


class TestQualityCheck(unittest.TestCase):
    def test_quality_check_detects_empty_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docs_dir = tmp_path / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            # Create a tiny raw file.
            raw_dir = docs_dir / "raw" / "example.com"
            raw_dir.mkdir(parents=True, exist_ok=True)
            tiny_raw = raw_dir / "tiny.bin"
            tiny_raw.write_bytes(b"<html></html>")

            # Create a normal-sized raw file.
            normal_raw = raw_dir / "normal.bin"
            normal_raw.write_bytes(b"x" * 2000)

            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page(conn, canonical_url="https://example.com/empty", word_count=0, raw_path=str(tiny_raw.relative_to(docs_dir)))
                _insert_page(conn, canonical_url="https://example.com/thin", word_count=30, raw_path=str(normal_raw.relative_to(docs_dir)))
                _insert_page(conn, canonical_url="https://example.com/ok", word_count=500, raw_path=str(normal_raw.relative_to(docs_dir)))
            finally:
                conn.close()

            result = quality_check(docs_dir=str(docs_dir))
            self.assertEqual(result["counts"]["total"], 3)
            self.assertEqual(result["counts"]["empty"], 1)
            self.assertEqual(result["counts"]["thin"], 1)
            self.assertEqual(result["counts"]["ok"], 1)
            self.assertEqual(len(result["issues"]), 2)

            types = {i["type"] for i in result["issues"]}
            self.assertIn("empty", {t.split("+")[0] for t in types})
            self.assertIn("thin", types)

    def test_quality_check_passes_normal_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docs_dir = tmp_path / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            raw_dir = docs_dir / "raw" / "example.com"
            raw_dir.mkdir(parents=True, exist_ok=True)
            normal_raw = raw_dir / "normal.bin"
            normal_raw.write_bytes(b"x" * 5000)

            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page(conn, canonical_url="https://example.com/page1", word_count=200, raw_path=str(normal_raw.relative_to(docs_dir)))
                _insert_page(conn, canonical_url="https://example.com/page2", word_count=1500, raw_path=str(normal_raw.relative_to(docs_dir)))
            finally:
                conn.close()

            result = quality_check(docs_dir=str(docs_dir))
            self.assertEqual(result["counts"]["total"], 2)
            self.assertEqual(result["counts"]["ok"], 2)
            self.assertEqual(result["counts"]["empty"], 0)
            self.assertEqual(result["counts"]["thin"], 0)
            self.assertEqual(result["counts"]["tiny_html"], 0)
            self.assertEqual(len(result["issues"]), 0)


if __name__ == "__main__":
    unittest.main()
