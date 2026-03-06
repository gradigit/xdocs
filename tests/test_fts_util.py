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


if __name__ == "__main__":
    unittest.main()
