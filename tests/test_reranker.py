"""Tests for reranker module (src/cex_api_docs/reranker.py).

These tests mock the FlashRank Ranker to avoid downloading the model.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock


class TestReranker(unittest.TestCase):
    def _make_mock_ranker(self):
        """Create a mock FlashRank Ranker that returns results sorted by simple heuristic."""
        mock = MagicMock()

        def mock_rerank(request):
            query = request.query
            passages = request.passages
            query_words = set(query.lower().split())
            scored = []
            for p in passages:
                doc_words = set(p["text"].lower().split())
                score = len(query_words & doc_words) / max(len(query_words), 1)
                scored.append({"id": p["id"], "text": p["text"], "score": score})
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored

        mock.rerank = mock_rerank
        return mock

    @patch("cex_api_docs.reranker._require_ranker")
    def test_rerank_changes_order(self, mock_require) -> None:
        """Reranking should reorder results by relevance."""
        from cex_api_docs.reranker import rerank

        mock_require.return_value = self._make_mock_ranker()

        results = [
            {"text": "The weather is sunny today", "url": "a.com", "score": 0.9},
            {"text": "Check your account balance and holdings", "url": "b.com", "score": 0.8},
            {"text": "Account balance API endpoint for wallet", "url": "c.com", "score": 0.7},
        ]
        reranked = rerank("account balance", results, top_n=3)
        self.assertEqual(len(reranked), 3)
        # The weather result should not be first after reranking.
        self.assertIn("rerank_score", reranked[0])
        # Results about "account balance" should rank higher.
        urls = [r["url"] for r in reranked]
        weather_idx = urls.index("a.com")
        self.assertGreater(weather_idx, 0)

    @patch("cex_api_docs.reranker._require_ranker")
    def test_empty_input(self, mock_require) -> None:
        """Empty results list should return empty."""
        from cex_api_docs.reranker import rerank

        mock_require.return_value = self._make_mock_ranker()
        self.assertEqual(rerank("query", []), [])

    @patch("cex_api_docs.reranker._require_ranker")
    def test_top_n_truncation(self, mock_require) -> None:
        """top_n should limit the number of returned results."""
        from cex_api_docs.reranker import rerank

        mock_require.return_value = self._make_mock_ranker()

        results = [
            {"text": f"Document {i} about testing", "url": f"url{i}.com", "score": 0.5}
            for i in range(10)
        ]
        reranked = rerank("testing", results, top_n=3)
        self.assertEqual(len(reranked), 3)


if __name__ == "__main__":
    unittest.main()
