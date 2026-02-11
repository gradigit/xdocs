from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cex_api_docs.db import open_db
from cex_api_docs.store import init_store

REPO_ROOT = Path(__file__).resolve().parents[1]


def _insert_page_with_md(
    conn, *, docs_dir: Path, canonical_url: str, domain: str, title: str, word_count: int, markdown: str
) -> None:
    """Insert a page row and write its markdown file."""
    import hashlib

    path_hash = hashlib.sha256(canonical_url.encode()).hexdigest()
    md_rel = f"{docs_dir.name}/pages/{domain}/{path_hash}.md"
    md_path = docs_dir.parent / md_rel
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")

    raw_rel = f"{docs_dir.name}/raw/{domain}/{path_hash}.bin"
    raw_path = docs_dir.parent / raw_rel
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"<html>" + markdown.encode() + b"</html>")

    conn.execute(
        """
INSERT INTO pages (canonical_url, url, final_url, domain, path_hash, title, word_count,
                   raw_path, markdown_path, content_hash)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
        (canonical_url, canonical_url, canonical_url, domain, path_hash, title, word_count,
         raw_rel, md_rel, hashlib.sha256(markdown.encode()).hexdigest()),
    )
    conn.commit()


class TestSemantic(unittest.TestCase):
    def test_build_index_and_search(self) -> None:
        try:
            from cex_api_docs.semantic import build_index, semantic_search
        except ImportError:
            self.skipTest("lancedb not installed (optional dependency)")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docs_dir = tmp_path / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page_with_md(
                    conn,
                    docs_dir=docs_dir,
                    canonical_url="https://example.com/spot/account",
                    domain="example.com",
                    title="Account Balance",
                    word_count=50,
                    markdown="# Account Balance\n\nUse GET /api/v3/account to check your wallet balance and asset holdings.",
                )
                _insert_page_with_md(
                    conn,
                    docs_dir=docs_dir,
                    canonical_url="https://example.com/spot/order",
                    domain="example.com",
                    title="Place Order",
                    word_count=60,
                    markdown="# Place Order\n\nUse POST /api/v3/order to submit a new buy or sell trade on the exchange.",
                )
                _insert_page_with_md(
                    conn,
                    docs_dir=docs_dir,
                    canonical_url="https://example.com/spot/ticker",
                    domain="example.com",
                    title="Market Ticker",
                    word_count=40,
                    markdown="# Market Ticker\n\nGet current price and 24h volume for a trading pair via GET /api/v3/ticker.",
                )
            finally:
                conn.close()

            # Build index.
            result = build_index(docs_dir=str(docs_dir))
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["pages_embedded"], 3)

            # Vector search.
            results = semantic_search(docs_dir=str(docs_dir), query="check wallet balance", limit=3, query_type="vector")
            self.assertGreater(len(results), 0)
            # The top result should be the account balance page (semantic match).
            self.assertEqual(results[0]["url"], "https://example.com/spot/account")

            # Hybrid search.
            results2 = semantic_search(docs_dir=str(docs_dir), query="place a trade", limit=3, query_type="hybrid")
            self.assertGreater(len(results2), 0)


if __name__ == "__main__":
    unittest.main()
