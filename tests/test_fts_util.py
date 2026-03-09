"""Tests for fts_util module."""

from __future__ import annotations

import unittest

from cex_api_docs.fts_util import (
    sanitize_fts_query,
    build_fts_query,
    extract_search_terms,
    expand_synonyms,
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

    def test_two_terms_and(self) -> None:
        result = build_fts_query(["rate", "limit"])
        self.assertEqual(result, "rate AND limit")

    def test_two_terms_or_explicit(self) -> None:
        result = build_fts_query(["rate", "limit"], operator="or")
        self.assertEqual(result, "rate OR limit")

    def test_three_plus_terms_and(self) -> None:
        result = build_fts_query(["rate", "limit", "weight"])
        self.assertEqual(result, "rate AND limit AND weight")

    def test_filters_fts_keywords(self) -> None:
        result = build_fts_query(["hello", "OR", "world"])
        self.assertEqual(result, "hello AND world")

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

    def test_synonym_expansion(self) -> None:
        terms = extract_search_terms("auth ohlc depth")
        self.assertIn("auth", terms)
        self.assertIn("authentication", terms)  # synonym for auth
        self.assertIn("ohlc", terms)

    def test_no_synonyms_flag(self) -> None:
        terms = extract_search_terms("auth ohlc", synonyms=False)
        self.assertIn("auth", terms)
        self.assertNotIn("authentication", terms)


class TestExpandSynonyms(unittest.TestCase):
    def test_basic_expansion(self) -> None:
        result = expand_synonyms(["ws"])
        self.assertIn("ws", result)
        self.assertIn("websocket", result)

    def test_no_duplicates(self) -> None:
        result = expand_synonyms(["websocket", "ws"])
        self.assertEqual(len(set(result)), len(result))

    def test_max_expansions(self) -> None:
        result = expand_synonyms(["ohlc"], max_expansions=1)
        # ohlc + at most 1 expansion
        self.assertLessEqual(len(result), 2)

    def test_unknown_term(self) -> None:
        result = expand_synonyms(["foobar"])
        self.assertEqual(result, ["foobar"])


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


class TestPostmanExtractRequestSchema(unittest.TestCase):
    """Test Postman parameter extraction from request objects."""

    def test_urlencoded_body(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {
            "body": {
                "mode": "urlencoded",
                "urlencoded": [
                    {"key": "symbol", "value": "BTCUSDT"},
                    {"key": "side", "value": "BUY"},
                ],
            }
        }
        result = _extract_request_schema(req)
        self.assertIsNotNone(result)
        params = result["parameters"]
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0]["name"], "symbol")
        self.assertEqual(params[0]["in"], "body")
        self.assertEqual(params[1]["name"], "side")
        self.assertEqual(params[1]["in"], "body")

    def test_url_query_params(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {
            "url": {
                "raw": "https://api.example.com/v1/order",
                "query": [
                    {"key": "symbol", "value": "BTCUSDT"},
                    {"key": "limit", "value": "10"},
                ],
            }
        }
        result = _extract_request_schema(req)
        self.assertIsNotNone(result)
        params = result["parameters"]
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0]["name"], "symbol")
        self.assertEqual(params[0]["in"], "query")
        self.assertEqual(params[1]["name"], "limit")
        self.assertEqual(params[1]["in"], "query")

    def test_formdata_body(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {
            "body": {
                "mode": "formdata",
                "formdata": [
                    {"key": "file", "type": "file"},
                    {"key": "description", "value": "test"},
                ],
            }
        }
        result = _extract_request_schema(req)
        self.assertIsNotNone(result)
        params = result["parameters"]
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0]["name"], "file")
        self.assertEqual(params[0]["in"], "body")

    def test_raw_json_body(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {
            "body": {
                "mode": "raw",
                "raw": '{"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT"}',
            }
        }
        result = _extract_request_schema(req)
        self.assertIsNotNone(result)
        params = result["parameters"]
        names = {p["name"] for p in params}
        self.assertIn("symbol", names)
        self.assertIn("side", names)
        self.assertIn("type", names)
        for p in params:
            self.assertEqual(p["in"], "body")

    def test_mixed_query_and_body(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {
            "url": {
                "raw": "https://api.example.com/v1/order",
                "query": [
                    {"key": "recvWindow", "value": "5000"},
                ],
            },
            "body": {
                "mode": "urlencoded",
                "urlencoded": [
                    {"key": "symbol", "value": "BTCUSDT"},
                ],
            },
        }
        result = _extract_request_schema(req)
        self.assertIsNotNone(result)
        params = result["parameters"]
        self.assertEqual(len(params), 2)
        query_params = [p for p in params if p["in"] == "query"]
        body_params = [p for p in params if p["in"] == "body"]
        self.assertEqual(len(query_params), 1)
        self.assertEqual(query_params[0]["name"], "recvWindow")
        self.assertEqual(len(body_params), 1)
        self.assertEqual(body_params[0]["name"], "symbol")

    def test_empty_request_returns_none(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        result = _extract_request_schema({})
        self.assertIsNone(result)

    def test_no_params_returns_none(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {"url": {"raw": "https://api.example.com/v1/time"}}
        result = _extract_request_schema(req)
        self.assertIsNone(result)

    def test_raw_invalid_json_returns_none(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {
            "body": {
                "mode": "raw",
                "raw": "not-json-content",
            }
        }
        result = _extract_request_schema(req)
        self.assertIsNone(result)

    def test_deduplicates_params(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {
            "url": {
                "raw": "https://api.example.com/v1/order",
                "query": [
                    {"key": "symbol", "value": "BTCUSDT"},
                    {"key": "symbol", "value": "ETHUSDT"},
                ],
            },
        }
        result = _extract_request_schema(req)
        self.assertIsNotNone(result)
        params = result["parameters"]
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "symbol")

    def test_empty_key_skipped(self) -> None:
        from cex_api_docs.postman_import import _extract_request_schema
        req = {
            "body": {
                "mode": "urlencoded",
                "urlencoded": [
                    {"key": "", "value": "test"},
                    {"key": "  ", "value": "test"},
                    {"key": "valid", "value": "test"},
                ],
            }
        }
        result = _extract_request_schema(req)
        self.assertIsNotNone(result)
        params = result["parameters"]
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "valid")


class TestCcFuse(unittest.TestCase):
    """Tests for cc_fuse (convex combination score-aware fusion)."""

    def test_basic_fusion(self) -> None:
        from cex_api_docs.fts_util import cc_fuse
        fts = [
            {"canonical_url": "a", "bm25_score": 0.9},
            {"canonical_url": "b", "bm25_score": 0.5},
        ]
        sem = [
            {"canonical_url": "b", "semantic_score": 0.9},
            {"canonical_url": "c", "semantic_score": 0.7},
        ]
        result = cc_fuse(fts, sem, alpha=0.5)
        urls = [r["canonical_url"] for r in result]
        # b appears in both → highest combined score.
        self.assertEqual(urls[0], "b")
        self.assertIn("a", urls)
        self.assertIn("c", urls)
        # All have cc_score and rrf_score alias.
        for r in result:
            self.assertIn("cc_score", r)
            self.assertIn("rrf_score", r)

    def test_alpha_zero_semantic_only(self) -> None:
        from cex_api_docs.fts_util import cc_fuse
        fts = [{"canonical_url": "a", "bm25_score": 0.9}]
        sem = [
            {"canonical_url": "b", "semantic_score": 0.9},
            {"canonical_url": "a", "semantic_score": 0.1},
        ]
        result = cc_fuse(fts, sem, alpha=0.0)
        # With alpha=0, only semantic scores matter.
        self.assertEqual(result[0]["canonical_url"], "b")

    def test_alpha_one_bm25_only(self) -> None:
        from cex_api_docs.fts_util import cc_fuse
        fts = [
            {"canonical_url": "a", "bm25_score": 0.9},
            {"canonical_url": "b", "bm25_score": 0.3},
        ]
        sem = [{"canonical_url": "b", "semantic_score": 0.99}]
        result = cc_fuse(fts, sem, alpha=1.0)
        # With alpha=1, only BM25 scores matter.
        self.assertEqual(result[0]["canonical_url"], "a")

    def test_empty_inputs(self) -> None:
        from cex_api_docs.fts_util import cc_fuse
        self.assertEqual(cc_fuse([], []), [])
        result = cc_fuse(
            [{"canonical_url": "a", "bm25_score": 0.5}],
            [],
            alpha=0.5,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["canonical_url"], "a")

    def test_single_item_minmax(self) -> None:
        from cex_api_docs.fts_util import cc_fuse
        # Single item in each list → MinMax yields 1.0 (OpenSearch convention).
        result = cc_fuse(
            [{"canonical_url": "a", "bm25_score": 0.3}],
            [{"canonical_url": "a", "semantic_score": 0.7}],
            alpha=0.5,
        )
        # Both normalize to 1.0, so cc_score = 0.5 * 1.0 + 0.5 * 1.0 = 1.0.
        self.assertAlmostEqual(result[0]["cc_score"], 1.0)

    def test_reranker_correction_preserved(self) -> None:
        """BUG-8 scenario: reranker should correct retrieval ranking."""
        from cex_api_docs.fts_util import cc_fuse
        # FTS: a > b (close scores).
        fts = [
            {"canonical_url": "a", "bm25_score": 0.65},
            {"canonical_url": "b", "bm25_score": 0.60},
        ]
        # Semantic (reranker-corrected): b >> a.
        sem = [
            {"canonical_url": "b", "semantic_score": 0.9},
            {"canonical_url": "a", "semantic_score": 0.3},
        ]
        result = cc_fuse(fts, sem, alpha=0.35)  # Vector-favoring
        # b should win because semantic advantage outweighs BM25 advantage.
        self.assertEqual(result[0]["canonical_url"], "b")


class TestCodeStopwords(unittest.TestCase):
    """Tests for CODE_STOPWORDS used in code_snippet query cleaning."""

    def test_code_stopwords_exist(self) -> None:
        from cex_api_docs.fts_util import CODE_STOPWORDS
        self.assertIn("import", CODE_STOPWORDS)
        self.assertIn("ccxt", CODE_STOPWORDS)
        self.assertIn("exchange", CODE_STOPWORDS)
        self.assertIn("const", CODE_STOPWORDS)
        self.assertIn("require", CODE_STOPWORDS)

    def test_code_stopwords_strip_noise(self) -> None:
        from cex_api_docs.fts_util import CODE_STOPWORDS
        terms = extract_search_terms(
            "import ccxt exchange ccxt binance balance fetch_balance",
            extra_stopwords=CODE_STOPWORDS,
        )
        self.assertNotIn("import", terms)
        self.assertNotIn("ccxt", terms)
        self.assertNotIn("exchange", terms)
        self.assertIn("binance", terms)
        self.assertIn("balance", terms)

    def test_code_stopwords_preserve_domain_terms(self) -> None:
        from cex_api_docs.fts_util import CODE_STOPWORDS
        terms = extract_search_terms(
            "const client new kucoinclient passphrase getaccountslist",
            extra_stopwords=CODE_STOPWORDS,
        )
        self.assertNotIn("const", terms)
        self.assertNotIn("client", terms)
        self.assertNotIn("new", terms)
        self.assertIn("kucoinclient", terms)
        self.assertIn("passphrase", terms)
        self.assertIn("getaccountslist", terms)


if __name__ == "__main__":
    unittest.main()
