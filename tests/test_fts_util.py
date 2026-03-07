"""Tests for fts_util module."""

from __future__ import annotations

import unittest

from cex_api_docs.fts_util import (
    sanitize_fts_query,
    build_fts_query,
    extract_search_terms,
    endpoint_search_text,
    normalize_bm25_score,
)


class TestSanitizeFtsQuery(unittest.TestCase):
    def test_plain_terms(self) -> None:
        self.assertEqual(sanitize_fts_query("hello world"), "hello world")

    def test_hyphenated_term(self) -> None:
        result = sanitize_fts_query("account-overview")
        self.assertEqual(result, '"account-overview"')

    def test_colon_term(self) -> None:
        result = sanitize_fts_query("title:hello")
        self.assertEqual(result, '"title:hello"')

    def test_already_quoted(self) -> None:
        result = sanitize_fts_query('"already-quoted"')
        self.assertEqual(result, '"already-quoted"')

    def test_mixed_terms(self) -> None:
        result = sanitize_fts_query("hello account-overview world")
        self.assertEqual(result, 'hello "account-overview" world')

    def test_internal_double_quotes_escaped(self) -> None:
        result = sanitize_fts_query('test"value')
        self.assertIn('""', result)

    def test_question_mark_quoted(self) -> None:
        result = sanitize_fts_query("details?symbol=BTC")
        self.assertTrue(result.startswith('"'))
        self.assertTrue(result.endswith('"'))

    def test_url_query_params_quoted(self) -> None:
        result = sanitize_fts_query("rate limit details?symbol=BTCUSDT")
        self.assertIn('"details?symbol=BTCUSDT"', result)


class TestBuildFtsQuery(unittest.TestCase):
    def test_single_term(self) -> None:
        self.assertEqual(build_fts_query(["hello"]), "hello")

    def test_two_terms_or(self) -> None:
        result = build_fts_query(["rate", "limit"])
        self.assertEqual(result, "rate OR limit")

    def test_three_plus_terms_and(self) -> None:
        result = build_fts_query(["rate", "limit", "weight"])
        self.assertEqual(result, "rate AND limit AND weight")

    def test_filters_fts_keywords(self) -> None:
        result = build_fts_query(["hello", "OR", "world"])
        self.assertEqual(result, "hello OR world")

    def test_empty_input(self) -> None:
        self.assertEqual(build_fts_query([]), "")

    def test_max_terms(self) -> None:
        terms = [f"t{i}" for i in range(20)]
        result = build_fts_query(terms, max_terms=3)
        self.assertEqual(result, "t0 AND t1 AND t2")


class TestExtractSearchTerms(unittest.TestCase):
    def test_basic(self) -> None:
        terms = extract_search_terms("What is the rate limit?")
        self.assertIn("rate", terms)
        self.assertIn("limit", terms)
        self.assertNotIn("what", terms)
        self.assertNotIn("the", terms)

    def test_extra_stopwords(self) -> None:
        terms = extract_search_terms("binance rate limit", extra_stopwords={"binance"})
        self.assertNotIn("binance", terms)
        self.assertIn("rate", terms)

    def test_short_words_filtered(self) -> None:
        terms = extract_search_terms("is it ok to go")
        # All words <= 2 chars should be filtered
        for t in terms:
            self.assertGreater(len(t), 2)


class TestEndpointSearchText(unittest.TestCase):
    def test_values_only(self) -> None:
        record = {
            "description": "Get account info",
            "rate_limit": {"note": "weight 10"},
            "error_codes": [{"code": "-1002", "message": "Unauthorized"}],
            "required_permissions": ["READ"],
        }
        text = endpoint_search_text(record)
        self.assertIn("Get account info", text)
        self.assertIn("weight 10", text)
        self.assertIn("-1002", text)
        self.assertIn("Unauthorized", text)
        self.assertIn("READ", text)
        # Should NOT contain JSON key names.
        self.assertNotIn("error_codes", text)
        self.assertNotIn("rate_limit", text)
        self.assertNotIn("field_status", text)

    def test_empty_record(self) -> None:
        self.assertEqual(endpoint_search_text({}), "")


class TestNormalizeBm25Score(unittest.TestCase):
    def test_zero(self) -> None:
        self.assertAlmostEqual(normalize_bm25_score(0.0), 0.0)

    def test_negative_score(self) -> None:
        # BM25 scores are negative in FTS5.
        score = normalize_bm25_score(-5.0)
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_large_negative(self) -> None:
        score = normalize_bm25_score(-100.0)
        self.assertGreater(score, 0.98)
        self.assertLess(score, 1.0)

    def test_monotonic(self) -> None:
        # More negative = better match = higher normalized score.
        s1 = normalize_bm25_score(-1.0)
        s2 = normalize_bm25_score(-5.0)
        s3 = normalize_bm25_score(-10.0)
        self.assertLess(s1, s2)
        self.assertLess(s2, s3)


class TestRrfFuse(unittest.TestCase):
    """Test Reciprocal Rank Fusion."""

    def test_single_list(self) -> None:
        from cex_api_docs.fts_util import rrf_fuse
        items = [{"canonical_url": "a"}, {"canonical_url": "b"}]
        result = rrf_fuse(items)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["canonical_url"], "a")
        self.assertGreater(result[0]["rrf_score"], result[1]["rrf_score"])

    def test_two_lists_overlap(self) -> None:
        from cex_api_docs.fts_util import rrf_fuse
        list1 = [{"canonical_url": "a"}, {"canonical_url": "b"}]
        list2 = [{"canonical_url": "b"}, {"canonical_url": "c"}]
        result = rrf_fuse(list1, list2)
        # "b" appears in both lists so should have highest RRF score.
        self.assertEqual(result[0]["canonical_url"], "b")
        self.assertEqual(len(result), 3)

    def test_disjoint_lists(self) -> None:
        from cex_api_docs.fts_util import rrf_fuse
        list1 = [{"canonical_url": "a"}]
        list2 = [{"canonical_url": "b"}]
        result = rrf_fuse(list1, list2)
        self.assertEqual(len(result), 2)
        # Same rank in different lists — equal scores.
        self.assertAlmostEqual(result[0]["rrf_score"], result[1]["rrf_score"])

    def test_empty_lists(self) -> None:
        from cex_api_docs.fts_util import rrf_fuse
        result = rrf_fuse([], [])
        self.assertEqual(result, [])

    def test_k_parameter(self) -> None:
        from cex_api_docs.fts_util import rrf_fuse
        items = [{"canonical_url": "a"}]
        r60 = rrf_fuse(items, k=60)
        r10 = rrf_fuse(items, k=10)
        # Lower k gives higher score (1/(k+1)).
        self.assertGreater(r10[0]["rrf_score"], r60[0]["rrf_score"])


class TestPositionAwareBlend(unittest.TestCase):
    """Test position-aware reranker blending."""

    def test_no_rerank_scores(self) -> None:
        from cex_api_docs.fts_util import position_aware_blend
        items = [{"rrf_score": 0.5}, {"rrf_score": 0.3}]
        result = position_aware_blend(items)
        # Max-normalized: 0.5/0.5 = 1.0, 0.3/0.5 = 0.6
        self.assertAlmostEqual(result[0]["blended_score"], 1.0)
        self.assertAlmostEqual(result[1]["blended_score"], 0.6)

    def test_with_rerank_scores(self) -> None:
        from cex_api_docs.fts_util import position_aware_blend
        items = [
            {"rrf_score": 0.5, "rerank_score": 2.0},
            {"rrf_score": 0.3, "rerank_score": -1.0},
        ]
        result = position_aware_blend(items)
        # First item: 75% * 0.5 + 25% * sigmoid(2.0).
        self.assertGreater(result[0]["blended_score"], result[1]["blended_score"])

    def test_reranker_can_reorder(self) -> None:
        from cex_api_docs.fts_util import position_aware_blend
        # Second item has much higher reranker score.
        items = [
            {"rrf_score": 0.5, "rerank_score": -5.0},
            {"rrf_score": 0.3, "rerank_score": 10.0},
        ]
        result = position_aware_blend(items)
        # Reranker score for item 2 is very high, should be reordered to top.
        self.assertEqual(len(result), 2)


class TestShouldSkipVectorSearch(unittest.TestCase):
    """Test strong-signal BM25 shortcut."""

    def test_strong_signal(self) -> None:
        from cex_api_docs.fts_util import should_skip_vector_search
        results = [{"bm25_score": 0.9}, {"bm25_score": 0.2}]
        self.assertTrue(should_skip_vector_search(results))

    def test_weak_signal(self) -> None:
        from cex_api_docs.fts_util import should_skip_vector_search
        results = [{"bm25_score": 0.4}, {"bm25_score": 0.3}]
        self.assertFalse(should_skip_vector_search(results))

    def test_close_scores(self) -> None:
        from cex_api_docs.fts_util import should_skip_vector_search
        results = [{"bm25_score": 0.8}, {"bm25_score": 0.7}]
        self.assertFalse(should_skip_vector_search(results))

    def test_single_result(self) -> None:
        from cex_api_docs.fts_util import should_skip_vector_search
        results = [{"bm25_score": 0.8}]
        self.assertTrue(should_skip_vector_search(results))

    def test_empty_results(self) -> None:
        from cex_api_docs.fts_util import should_skip_vector_search
        self.assertFalse(should_skip_vector_search([]))


class TestSigmoid(unittest.TestCase):
    """Test sigmoid normalization."""

    def test_zero(self) -> None:
        from cex_api_docs.fts_util import sigmoid
        self.assertAlmostEqual(sigmoid(0.0), 0.5)

    def test_large_positive(self) -> None:
        from cex_api_docs.fts_util import sigmoid
        self.assertGreater(sigmoid(10.0), 0.99)

    def test_large_negative(self) -> None:
        from cex_api_docs.fts_util import sigmoid
        self.assertLess(sigmoid(-10.0), 0.01)

    def test_monotonic(self) -> None:
        from cex_api_docs.fts_util import sigmoid
        self.assertLess(sigmoid(-1.0), sigmoid(0.0))
        self.assertLess(sigmoid(0.0), sigmoid(1.0))


if __name__ == "__main__":
    unittest.main()
