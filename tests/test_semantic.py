from __future__ import annotations

import tempfile
import unittest
import importlib.util
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
    def test_rerank_policy_normalization(self) -> None:
        from cex_api_docs.semantic import _normalize_rerank_policy

        self.assertEqual(_normalize_rerank_policy(True), "always")
        self.assertEqual(_normalize_rerank_policy(False), "never")
        self.assertEqual(_normalize_rerank_policy("auto"), "auto")
        self.assertEqual(_normalize_rerank_policy("always"), "always")
        self.assertEqual(_normalize_rerank_policy("never"), "never")
        with self.assertRaises(ValueError):
            _normalize_rerank_policy("sometimes")

    def test_auto_rerank_heuristic(self) -> None:
        from cex_api_docs.semantic import _should_auto_rerank

        ambiguous = [
            {"score": 0.1000},
            {"score": 0.1002},
            {"score": 0.1004},
            {"score": 0.1006},
            {"score": 0.1008},
            {"score": 0.1010},
            {"score": 0.1012},
            {"score": 0.1014},
            {"score": 0.1016},
            {"score": 0.1018},
            {"score": 0.1020},
            {"score": 0.1022},
        ]
        should, reason = _should_auto_rerank(ambiguous, limit=5)
        self.assertTrue(should)
        self.assertEqual(reason, "ambiguous_top_scores")

        confident = [
            {"score": 0.40},
            {"score": 0.15},
            {"score": 0.08},
            {"score": 0.04},
            {"score": 0.02},
            {"score": 0.01},
            {"score": 0.005},
            {"score": 0.003},
            {"score": 0.002},
            {"score": 0.001},
            {"score": 0.0005},
            {"score": 0.0001},
        ]
        should2, reason2 = _should_auto_rerank(confident, limit=5)
        self.assertFalse(should2)
        self.assertEqual(reason2, "confident_ranking")

    def test_build_index_and_search(self) -> None:
        try:
            from cex_api_docs.semantic import build_index, semantic_search
        except ImportError:
            self.skipTest("lancedb not installed (optional dependency)")
        if importlib.util.find_spec("lancedb") is None:
            self.skipTest("lancedb not installed (optional dependency)")
        if importlib.util.find_spec("mistune") is None:
            self.skipTest("mistune not installed (optional dependency)")
        # Check for Jina MLX backend (needs mlx + huggingface_hub + tokenizers)
        has_jina_mlx = (
            importlib.util.find_spec("mlx") is not None
            and importlib.util.find_spec("huggingface_hub") is not None
            and importlib.util.find_spec("tokenizers") is not None
        )
        has_st = importlib.util.find_spec("sentence_transformers") is not None
        if not has_jina_mlx and not has_st:
            self.skipTest("No embedding backend installed (optional dependency)")

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
            # New chunking-based fields.
            self.assertIn("pages_processed", result)
            self.assertIn("chunks_embedded", result)
            self.assertEqual(result["pages_processed"], 3)
            self.assertGreaterEqual(result["chunks_embedded"], result["pages_processed"])
            # Model info.
            self.assertIn("jina-embeddings-v5", result["model"])
            self.assertGreater(result["ndims"], 0)

            # Vector search (rerank=never to isolate retrieval quality from reranker).
            results = semantic_search(docs_dir=str(docs_dir), query="check wallet balance", limit=3, query_type="vector", rerank="never")
            self.assertGreater(len(results), 0)
            # The top result should be the account balance page (semantic match).
            self.assertEqual(results[0]["url"], "https://example.com/spot/account")
            # Chunk fields should be present.
            self.assertIn("chunk_index", results[0])
            self.assertIn("heading", results[0])

            # Hybrid search.
            results2 = semantic_search(docs_dir=str(docs_dir), query="place a trade", limit=3, query_type="hybrid")
            self.assertGreater(len(results2), 0)

            # De-duplication: results should have unique page_ids.
            page_ids = [r["page_id"] for r in results]
            self.assertEqual(len(page_ids), len(set(page_ids)))

    def test_incremental_build_index(self) -> None:
        """Build index, add a page, rebuild incrementally, verify new page is searchable."""
        try:
            from cex_api_docs.semantic import build_index, semantic_search
        except ImportError:
            self.skipTest("lancedb not installed (optional dependency)")
        if importlib.util.find_spec("lancedb") is None:
            self.skipTest("lancedb not installed (optional dependency)")
        if importlib.util.find_spec("mistune") is None:
            self.skipTest("mistune not installed (optional dependency)")
        # Check for Jina MLX backend (needs mlx + huggingface_hub + tokenizers)
        has_jina_mlx = (
            importlib.util.find_spec("mlx") is not None
            and importlib.util.find_spec("huggingface_hub") is not None
            and importlib.util.find_spec("tokenizers") is not None
        )
        has_st = importlib.util.find_spec("sentence_transformers") is not None
        if not has_jina_mlx and not has_st:
            self.skipTest("No embedding backend installed (optional dependency)")

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
            finally:
                conn.close()

            # Full build with 2 pages.
            result1 = build_index(docs_dir=str(docs_dir))
            self.assertEqual(result1["status"], "ok")
            self.assertEqual(result1["pages_processed"], 2)
            initial_chunks = result1["chunks_embedded"]

            # Add a third page.
            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page_with_md(
                    conn,
                    docs_dir=docs_dir,
                    canonical_url="https://example.com/spot/withdraw",
                    domain="example.com",
                    title="Withdraw Funds",
                    word_count=45,
                    markdown="# Withdraw Funds\n\nUse POST /api/v3/withdraw to transfer crypto from exchange to external wallet.",
                )
            finally:
                conn.close()

            # Incremental build — should only process the new page.
            result2 = build_index(docs_dir=str(docs_dir), incremental=True)
            self.assertEqual(result2["status"], "ok")
            self.assertEqual(result2.get("mode"), "incremental")
            self.assertEqual(result2["pages_processed"], 1)
            self.assertEqual(result2["pages_deleted"], 0)
            self.assertEqual(result2["chunks_deleted"], 0)
            self.assertGreater(result2["total_rows"], initial_chunks)

            # New page should be searchable.
            results = semantic_search(docs_dir=str(docs_dir), query="withdraw crypto to wallet", limit=3, query_type="vector")
            self.assertGreater(len(results), 0)
            urls = [r["url"] for r in results]
            self.assertIn("https://example.com/spot/withdraw", urls)

            # Old pages should still be searchable (rerank=never to isolate retrieval).
            results2 = semantic_search(docs_dir=str(docs_dir), query="check wallet balance", limit=3, query_type="vector", rerank="never")
            self.assertGreater(len(results2), 0)
            self.assertEqual(results2[0]["url"], "https://example.com/spot/account")

            # Incremental with no changes — should be up_to_date.
            result3 = build_index(docs_dir=str(docs_dir), incremental=True)
            self.assertEqual(result3["status"], "up_to_date")
            self.assertEqual(result3["pages_processed"], 0)


if __name__ == "__main__":
    unittest.main()
