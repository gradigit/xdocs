"""Tests for reranker module (src/cex_api_docs/reranker.py).

These tests mock the Jina v3 backend to avoid downloading models.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock


class TestReranker(unittest.TestCase):
    def _make_mock_jina(self, n_results=None):
        """Create a mock Jina v3 model that returns results in order."""
        mock_model = MagicMock()

        def mock_rerank(query, docs, top_n=5):
            # Score by word overlap with query
            q_words = set(query.lower().split())
            scored = []
            for i, doc in enumerate(docs):
                d_words = set(doc.lower().split())
                score = len(q_words & d_words) / max(len(q_words), 1)
                scored.append((i, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [
                {"index": idx, "relevance_score": score}
                for idx, score in scored[:top_n]
            ]

        mock_model.rerank = mock_rerank
        return mock_model

    @patch("cex_api_docs.reranker._load_jina_v3")
    def test_rerank_changes_order(self, mock_load) -> None:
        """Reranking should reorder results by relevance."""
        from cex_api_docs.reranker import rerank

        mock_load.return_value = self._make_mock_jina()

        results = [
            {"text": "The weather is sunny today", "url": "a.com", "score": 0.9},
            {"text": "Check your account balance and holdings", "url": "b.com", "score": 0.8},
            {"text": "Account balance API endpoint for wallet", "url": "c.com", "score": 0.7},
        ]
        reranked = rerank("account balance", results, top_n=3)
        self.assertEqual(len(reranked), 3)
        self.assertIn("rerank_score", reranked[0])
        urls = [r["url"] for r in reranked]
        weather_idx = urls.index("a.com")
        self.assertGreater(weather_idx, 0)

    def test_empty_input(self) -> None:
        """Empty results list should return empty."""
        from cex_api_docs.reranker import rerank
        self.assertEqual(rerank("query", []), [])

    @patch("cex_api_docs.reranker._load_jina_v3")
    def test_top_n_truncation(self, mock_load) -> None:
        """top_n should limit the number of returned results."""
        from cex_api_docs.reranker import rerank

        mock_load.return_value = self._make_mock_jina()

        results = [
            {"text": f"Document {i} about testing", "url": f"url{i}.com", "score": 0.5}
            for i in range(10)
        ]
        reranked = rerank("testing", results, top_n=3)
        self.assertEqual(len(reranked), 3)

    @patch("cex_api_docs.reranker._load_jina_v3")
    def test_jina_v3_returns_rerank_score(self, mock_load) -> None:
        """Jina v3 should return results with rerank_score."""
        from cex_api_docs.reranker import rerank

        mock_model = MagicMock()
        mock_model.rerank.return_value = [
            {"index": 0, "relevance_score": 0.9},
        ]
        mock_load.return_value = mock_model

        results = [{"text": "relevant doc", "url": "a.com"}]
        reranked = rerank("query", results, top_n=1)
        self.assertEqual(len(reranked), 1)
        self.assertAlmostEqual(reranked[0]["rerank_score"], 0.9)

    @patch("cex_api_docs.reranker._is_mlx_available", return_value=False)
    @patch("cex_api_docs.reranker._load_jina_v3")
    def test_auto_uses_jina_v3_on_linux(self, mock_load_jina, mock_mlx) -> None:
        """On Linux (no MLX), auto should use jina-v3 PyTorch."""
        from cex_api_docs.reranker import rerank

        mock_model = MagicMock()
        mock_model.rerank.return_value = [
            {"index": 0, "relevance_score": 0.95},
        ]
        mock_load_jina.return_value = mock_model

        result = rerank("test query", [{"text": "test doc"}], top_n=1)
        self.assertEqual(len(result), 1)
        mock_load_jina.assert_called_once()

    @patch("cex_api_docs.reranker._is_mlx_available", return_value=True)
    @patch("cex_api_docs.reranker._load_jina_v3_mlx")
    def test_auto_uses_mlx_on_macos(self, mock_load_mlx, mock_mlx) -> None:
        """On macOS with MLX, auto should try MLX variant first."""
        from cex_api_docs.reranker import rerank

        mock_model = MagicMock()
        mock_model.rerank.return_value = [
            {"index": 0, "relevance_score": 0.95},
        ]
        mock_load_mlx.return_value = mock_model

        result = rerank("test query", [{"text": "test doc"}], top_n=1)
        self.assertEqual(len(result), 1)
        mock_load_mlx.assert_called_once()


if __name__ == "__main__":
    unittest.main()
