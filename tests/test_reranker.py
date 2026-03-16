"""Tests for reranker module (src/cex_api_docs/reranker.py).

These tests mock the backends to avoid downloading models.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock


class TestReranker(unittest.TestCase):
    def _mock_cross_encoder_predict(self, pairs):
        """Mock CrossEncoder.predict — score by word overlap."""
        scores = []
        for query, doc in pairs:
            q_words = set(query.lower().split())
            d_words = set(doc.lower().split())
            scores.append(len(q_words & d_words) / max(len(q_words), 1))
        return scores

    def _make_mock_ce(self):
        mock_ce = MagicMock()
        mock_ce.predict = self._mock_cross_encoder_predict
        return mock_ce

    @patch("cex_api_docs.reranker._load_cross_encoder")
    def test_rerank_changes_order(self, mock_load) -> None:
        """Reranking should reorder results by relevance."""
        from cex_api_docs.reranker import rerank

        mock_load.return_value = self._make_mock_ce()

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

    @patch("cex_api_docs.reranker._load_cross_encoder")
    def test_empty_input(self, mock_load) -> None:
        """Empty results list should return empty."""
        from cex_api_docs.reranker import rerank

        mock_load.return_value = self._make_mock_ce()
        self.assertEqual(rerank("query", []), [])

    @patch("cex_api_docs.reranker._load_cross_encoder")
    def test_top_n_truncation(self, mock_load) -> None:
        """top_n should limit the number of returned results."""
        from cex_api_docs.reranker import rerank

        mock_load.return_value = self._make_mock_ce()

        results = [
            {"text": f"Document {i} about testing", "url": f"url{i}.com", "score": 0.5}
            for i in range(10)
        ]
        reranked = rerank("testing", results, top_n=3)
        self.assertEqual(len(reranked), 3)

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("flashrank") is not None,
        "flashrank not installed",
    )
    @patch("cex_api_docs.reranker._BACKEND", "flashrank")
    @patch("cex_api_docs.reranker._load_flashrank")
    def test_flashrank_backend(self, mock_load) -> None:
        """FlashRank backend should work when selected."""
        from cex_api_docs.reranker import rerank

        mock_ranker = MagicMock()

        def mock_rerank(request):
            return [{"id": p["id"], "text": p["text"], "score": 0.5} for p in request.passages]

        mock_ranker.rerank = mock_rerank
        mock_load.return_value = mock_ranker

        results = [{"text": "test doc", "url": "a.com"}]
        reranked = rerank("test", results, top_n=1)
        self.assertEqual(len(reranked), 1)
        self.assertIn("rerank_score", reranked[0])

    def test_invalid_backend_raises(self) -> None:
        """Invalid backend name should raise ValueError."""
        import cex_api_docs.reranker as mod
        original = mod._BACKEND
        try:
            mod._BACKEND = "nonexistent"
            with self.assertRaises(ValueError):
                mod.rerank("query", [{"text": "doc"}])
        finally:
            mod._BACKEND = original

    @patch("cex_api_docs.reranker._BACKEND", "jina-v3")
    @patch("cex_api_docs.reranker._load_jina_v3")
    def test_jina_v3_backend(self, mock_load) -> None:
        """Jina v3 backend should call model.rerank() and return results."""
        from cex_api_docs.reranker import rerank

        mock_model = MagicMock()
        mock_model.rerank.return_value = [
            {"document": "relevant doc", "relevance_score": 0.9, "index": 0, "embedding": None},
        ]
        mock_load.return_value = mock_model

        results = [{"text": "relevant doc", "url": "a.com"}]
        reranked = rerank("query", results, top_n=1)
        self.assertEqual(len(reranked), 1)
        self.assertIn("rerank_score", reranked[0])
        self.assertAlmostEqual(reranked[0]["rerank_score"], 0.9)

    @patch("cex_api_docs.reranker._BACKEND", "qwen3")
    @patch("cex_api_docs.reranker._load_qwen3_seq_cls")
    def test_qwen3_backend(self, mock_load) -> None:
        """Qwen3 seq-cls backend should format prompts and return results."""
        from cex_api_docs.reranker import rerank

        mock_load.return_value = self._make_mock_ce()

        results = [
            {"text": "relevant API documentation about balance", "url": "a.com"},
            {"text": "unrelated weather forecast", "url": "b.com"},
        ]
        reranked = rerank("API balance", results, top_n=2)
        self.assertEqual(len(reranked), 2)
        self.assertIn("rerank_score", reranked[0])

    @patch("cex_api_docs.reranker._BACKEND", "qwen3")
    @patch("cex_api_docs.reranker._load_qwen3_seq_cls")
    def test_qwen3_prompt_formatting(self, mock_load) -> None:
        """Qwen3 should use special prompt template with im_start markers."""
        from cex_api_docs.reranker import rerank, _format_qwen3_query, _format_qwen3_doc

        mock_ce = self._make_mock_ce()
        mock_load.return_value = mock_ce

        # Verify prompt format
        q = _format_qwen3_query("test query")
        self.assertIn("<|im_start|>system", q)
        self.assertIn("<Query>: test query", q)

        d = _format_qwen3_doc("test doc")
        self.assertIn("<Document>: test doc", d)
        self.assertIn("<think>", d)

    @patch("cex_api_docs.reranker._is_mlx_available", return_value=False)
    @patch("cex_api_docs.reranker._load_jina_v3")
    def test_auto_uses_jina_v3_on_linux(self, mock_load_jina, mock_mlx) -> None:
        """On Linux (no MLX), auto should try jina-v3 first (+15.6% MRR, p=0.0014)."""
        import cex_api_docs.reranker as mod
        original = mod._BACKEND

        # Mock Jina v3 model's .rerank() method
        mock_model = unittest.mock.MagicMock()
        mock_model.rerank.return_value = [
            {"index": 0, "relevance_score": 0.95},
        ]
        mock_load_jina.return_value = mock_model

        try:
            mod._BACKEND = "auto"
            result = mod.rerank("test query", [{"text": "test doc"}], top_n=1)
            self.assertEqual(len(result), 1)
            mock_load_jina.assert_called_once()
        finally:
            mod._BACKEND = original


if __name__ == "__main__":
    unittest.main()
