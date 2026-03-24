from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from xdocs.db import open_db
from xdocs.quality import classify_source_type, detect_content_flags, quality_check
from xdocs.store import init_store

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


class TestClassifySourceType(unittest.TestCase):
    def test_official_docs(self) -> None:
        self.assertEqual(classify_source_type("https://developers.binance.com/docs/spot"), "official_docs")

    def test_spec_url(self) -> None:
        self.assertEqual(classify_source_type("https://docs.gemini.com/rest.yaml"), "spec")

    def test_github_repo(self) -> None:
        self.assertEqual(classify_source_type("https://github.com/BingX-API/api-ai-skills/blob/main/SKILL.md"), "github_repo")

    def test_ccxt_ref(self) -> None:
        self.assertEqual(classify_source_type("https://docs.ccxt.com/exchanges/binance.md"), "ccxt_ref")
        self.assertEqual(classify_source_type("https://docs.ccxt.com/Manual.md"), "ccxt_ref")

    def test_readme_reference(self) -> None:
        self.assertEqual(classify_source_type("https://bluefin-exchange.readme.io/reference/getaccountdetails"), "official_docs")


class TestDetectContentFlags(unittest.TestCase):
    def test_empty_page(self) -> None:
        flags = detect_content_flags(markdown="", word_count=0)
        self.assertIn("empty", flags)

    def test_thin_page(self) -> None:
        flags = detect_content_flags(markdown="Some thin content", word_count=10)
        self.assertIn("thin", flags)

    def test_nav_chrome(self) -> None:
        nav_md = "\n".join([
            "* [Home](/)",
            "* [API Reference](/api)",
            "* [Guides](/guides)",
            "* [WebSocket](/ws)",
            "* [REST API](/rest)",
            "* [Rate Limits](/limits)",
            "* [Authentication](/auth)",
        ])
        flags = detect_content_flags(markdown=nav_md, word_count=14)
        self.assertIn("nav_chrome", flags)

    def test_spa_shell(self) -> None:
        html = '<html><body><div id="app"></div><script>window.__NEXT_DATA__ = {};</script></body></html>'
        flags = detect_content_flags(markdown="", html=html, word_count=0)
        self.assertIn("spa_shell", flags)

    def test_normal_page(self) -> None:
        prose = "This is a normal documentation page with plenty of content. " * 20
        flags = detect_content_flags(markdown=prose, word_count=200)
        self.assertEqual(flags, [])


if __name__ == "__main__":
    unittest.main()
