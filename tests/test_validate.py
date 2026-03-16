"""Tests for golden QA validation (src/xdocs/validate.py)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xdocs.validate import (
    ValidationResult,
    _domain,
    _match_counts,
    _norm,
    _prefix_match,
    validate_retrieval,
)


class TestHelpers(unittest.TestCase):
    def test_norm_strips_trailing_slash_and_fragment(self) -> None:
        self.assertEqual(_norm("https://a.com/path/"), "https://a.com/path")
        self.assertEqual(_norm("https://a.com/p#sec"), "https://a.com/p")
        self.assertEqual(_norm("https://a.com/p/#s"), "https://a.com/p")

    def test_prefix_match_either_direction(self) -> None:
        self.assertTrue(_prefix_match(
            "https://a.com/docs/rest-api",
            "https://a.com/docs/rest-api/account-endpoints",
        ))
        self.assertTrue(_prefix_match(
            "https://a.com/docs/rest-api/account-endpoints",
            "https://a.com/docs/rest-api",
        ))
        self.assertFalse(_prefix_match(
            "https://a.com/docs/rest-api",
            "https://b.com/docs/rest-api",
        ))

    def test_domain_extraction(self) -> None:
        self.assertEqual(_domain("https://docs.kraken.com/api/x"), "docs.kraken.com")
        self.assertEqual(_domain("https://a.com:8080/path"), "a.com")
        self.assertEqual(_domain("not-a-url"), "")

    def test_match_counts_exact(self) -> None:
        exact, prefix, domain = _match_counts(
            ["https://a.com/x"], ["https://a.com/x"]
        )
        self.assertEqual(exact, 1)
        self.assertEqual(prefix, 1)
        self.assertEqual(domain, 1)

    def test_match_counts_prefix_only(self) -> None:
        exact, prefix, domain = _match_counts(
            ["https://a.com/docs/rest-api"],
            ["https://a.com/docs/rest-api/account"],
        )
        self.assertEqual(exact, 0)
        self.assertEqual(prefix, 1)
        self.assertEqual(domain, 1)

    def test_match_counts_domain_only(self) -> None:
        exact, prefix, domain = _match_counts(
            ["https://a.com/page1"],
            ["https://a.com/page2"],
        )
        self.assertEqual(exact, 0)
        self.assertEqual(prefix, 0)
        self.assertEqual(domain, 1)

    def test_match_counts_percent_encoding(self) -> None:
        """Percent-encoded and decoded URLs should match exactly."""
        exact, prefix, domain = _match_counts(
            ["https://a.com/docs/%EC%9D%B8%EC%A6%9D"],
            ["https://a.com/docs/인증"],
        )
        self.assertEqual(exact, 1)

    def test_match_counts_no_match(self) -> None:
        exact, prefix, domain = _match_counts(
            ["https://a.com/x"],
            ["https://b.com/y"],
        )
        self.assertEqual(exact, 0)
        self.assertEqual(prefix, 0)
        self.assertEqual(domain, 0)


class TestValidate(unittest.TestCase):
    def test_empty_qa_file(self) -> None:
        """An empty QA file should return zero metrics."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("")
            qa_path = f.name

        result = validate_retrieval(docs_dir="/tmp/fake", qa_path=qa_path, limit=5)
        self.assertIsInstance(result, ValidationResult)
        self.assertEqual(result.total_queries, 0)
        self.assertEqual(result.hit_rate, 0.0)
        self.assertEqual(result.prefix_hit_rate, 0.0)
        self.assertEqual(result.domain_hit_rate, 0.0)

    def test_validation_with_mock_search(self) -> None:
        """Validation should compute correct metrics with mocked semantic search."""
        qa_pairs = [
            {"query": "check balance", "expected_urls": ["https://example.com/account"], "expected_exchange": None},
            {"query": "place order", "expected_urls": ["https://example.com/order"], "expected_exchange": None},
            {"query": "missing query", "expected_urls": ["https://example.com/nowhere"], "expected_exchange": None},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for pair in qa_pairs:
                f.write(json.dumps(pair) + "\n")
            qa_path = f.name

        def mock_search(*, docs_dir, query, exchange, limit, query_type, **kwargs):
            if "balance" in query:
                return [{"url": "https://example.com/account", "title": "Account", "page_id": 1, "exchange": "test", "word_count": 50, "score": 0.9}]
            if "order" in query:
                return [{"url": "https://example.com/order", "title": "Order", "page_id": 2, "exchange": "test", "word_count": 60, "score": 0.8}]
            return []

        with patch("xdocs.semantic.semantic_search", side_effect=mock_search):
            result = validate_retrieval(docs_dir="/tmp/fake", qa_path=qa_path, limit=5)

        self.assertEqual(result.total_queries, 3)
        self.assertAlmostEqual(result.hit_rate, 2 / 3)
        self.assertAlmostEqual(result.mean_recall, 2 / 3)
        self.assertAlmostEqual(result.prefix_hit_rate, 2 / 3)
        self.assertAlmostEqual(result.domain_hit_rate, 2 / 3)
        self.assertEqual(result.k, 5)
        # Per-query checks.
        self.assertTrue(result.per_query[0].hit)
        self.assertTrue(result.per_query[0].prefix_hit)
        self.assertTrue(result.per_query[0].domain_hit)
        self.assertTrue(result.per_query[1].hit)
        self.assertFalse(result.per_query[2].hit)
        self.assertFalse(result.per_query[2].domain_hit)

    def test_prefix_hit_without_exact(self) -> None:
        """A sibling-page retrieval should be a prefix hit but not an exact hit."""
        qa_pairs = [
            {
                "query": "position info",
                "expected_urls": ["https://docs.ex.com/v5/position"],
                "expected_exchange": None,
            },
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for pair in qa_pairs:
                f.write(json.dumps(pair) + "\n")
            qa_path = f.name

        def mock_search(**kwargs):
            return [{"url": "https://docs.ex.com/v5/position/leverage"}]

        with patch("xdocs.semantic.semantic_search", side_effect=mock_search):
            result = validate_retrieval(docs_dir="/tmp/fake", qa_path=qa_path, limit=5)

        qr = result.per_query[0]
        self.assertFalse(qr.hit)
        self.assertTrue(qr.prefix_hit)
        self.assertTrue(qr.domain_hit)
        self.assertEqual(result.hit_rate, 0.0)
        self.assertEqual(result.prefix_hit_rate, 1.0)
        self.assertEqual(result.domain_hit_rate, 1.0)

    def test_domain_hit_without_prefix(self) -> None:
        """Right domain, wrong path should be domain hit only."""
        qa_pairs = [
            {
                "query": "some query",
                "expected_urls": ["https://docs.ex.com/page1"],
                "expected_exchange": None,
            },
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for pair in qa_pairs:
                f.write(json.dumps(pair) + "\n")
            qa_path = f.name

        def mock_search(**kwargs):
            return [{"url": "https://docs.ex.com/totally-different"}]

        with patch("xdocs.semantic.semantic_search", side_effect=mock_search):
            result = validate_retrieval(docs_dir="/tmp/fake", qa_path=qa_path, limit=5)

        qr = result.per_query[0]
        self.assertFalse(qr.hit)
        self.assertFalse(qr.prefix_hit)
        self.assertTrue(qr.domain_hit)

    def test_validation_forwards_rerank_flag(self) -> None:
        """validate_retrieval should pass rerank flag to semantic_search."""
        qa_pairs = [
            {"query": "check balance", "expected_urls": ["https://example.com/account"], "expected_exchange": None},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for pair in qa_pairs:
                f.write(json.dumps(pair) + "\n")
            qa_path = f.name

        seen_kwargs = {}

        def mock_search(**kwargs):
            seen_kwargs.update(kwargs)
            return [{"url": "https://example.com/account"}]

        with patch("xdocs.semantic.semantic_search", side_effect=mock_search):
            validate_retrieval(docs_dir="/tmp/fake", qa_path=qa_path, limit=5, rerank=False)

        self.assertIn("rerank", seen_kwargs)
        self.assertIs(seen_kwargs["rerank"], False)


if __name__ == "__main__":
    unittest.main()
