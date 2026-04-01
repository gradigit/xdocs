"""Regression tests for M23 endpoint extraction + BUG-15 fix.

These tests guard against specific failure modes discovered during
M23 development and the BUG-15 fix. Each test documents WHY it exists
so future changes can assess whether the guard is still relevant.
"""
from __future__ import annotations

import re
import unittest

from xdocs.classify import classify_input
from xdocs.endpoint_extract import (
    EndpointCandidate,
    _build_citation,
    _build_endpoint_record,
    _normalize_path,
    _normalize_path_for_dedup,
    scan_endpoints_from_page,
)
from xdocs.endpoints import HARD_MAX_EXCERPT_CHARS, REQUIRED_HTTP_FIELD_STATUS_KEYS


def _scan(md: str, **kw) -> list[EndpointCandidate]:
    defaults = dict(
        md=md, page_url="https://docs.example.com/api",
        crawled_at="2026-01-01T00:00:00Z", content_hash="abc",
        path_hash="def", exchange="testex", section="api",
        base_url="https://api.example.com",
    )
    defaults.update(kw)
    return scan_endpoints_from_page(**defaults)


# ===================================================================
# BUG-15 regression: numeric literals in code must not be error_message
# ===================================================================

class TestBug15Regression(unittest.TestCase):
    """Guard: prices/quantities in SDK calls must classify as code_snippet,
    not error_message. Root cause was generic \\d{5,6} pattern matching 30000."""

    def test_create_order_with_price(self):
        r = classify_input('exchange.create_order("BTC/USDT", "limit", "buy", 0.001, 30000)')
        self.assertEqual(r.input_type, "code_snippet")

    def test_submit_order_bybit(self):
        r = classify_input('RestClientV5.submitOrder(symbol="BTCUSDT", price=30000, qty=0.001)')
        self.assertEqual(r.input_type, "code_snippet")

    def test_fetch_balance_with_timestamp(self):
        r = classify_input('exchange.fetch_balance(params={"timestamp": 1700490703})')
        self.assertEqual(r.input_type, "code_snippet")

    def test_real_error_codes_unaffected(self):
        """Exchange-specific error codes must still classify as error_message."""
        for code, expected_type in [
            ("-1002", "error_message"),      # Binance
            ("50004", "error_message"),       # OKX
            ("110001", "error_message"),      # Bybit
            ("HTTP 429 Too Many Requests", "error_message"),
        ]:
            r = classify_input(code)
            self.assertEqual(r.input_type, expected_type,
                             f"{code!r} should be {expected_type}, got {r.input_type}")

    def test_generic_number_without_code_context(self):
        """A bare 5-digit number without code signals should still be error_message."""
        r = classify_input("Error: 30001")
        self.assertEqual(r.input_type, "error_message")

    def test_code_with_exchange_specific_error_still_error(self):
        """If code contains an exchange-specific error code, error_message should win."""
        r = classify_input('response = {"code": -1002, "msg": "unauthorized"}')
        # -1002 is Binance-specific, should trigger error_message despite code context
        self.assertEqual(r.input_type, "error_message")


# ===================================================================
# M23 extraction: regex pattern correctness
# ===================================================================

class TestExtractionPatternRobustness(unittest.TestCase):
    """Guard: regex patterns must handle real-world markdown edge cases
    found during M23 validation on 6 exchanges."""

    def test_phemex_code_block_with_query_params(self):
        """Phemex endpoints have query params in code blocks — must be stripped."""
        md = "## Place order\n\n```text\nPUT /orders/create?clOrdID=xxx&symbol=yyy\n```\n"
        cands = _scan(md)
        paths = {c.norm_path for c in cands}
        self.assertIn("/orders/create", paths)
        # Query params must NOT be in the normalized path
        self.assertFalse(any("clOrdID" in c.norm_path for c in cands))

    def test_woo_backtick_with_spaces(self):
        """WOO uses ` METHOD /path ` with leading/trailing spaces inside backticks."""
        md = "## Get Status\n\n` GET /v1/public/system_info `\n\nReturns info.\n"
        cands = _scan(md)
        self.assertTrue(any(c.norm_path == "/v1/public/system_info" and c.pattern == "P5" for c in cands))

    def test_woo_colon_path_params(self):
        """WOO uses :param style path params — must normalize to {param}."""
        md = "## Get Trade\n\n` GET /v1/client/trade/:tid `\n"
        cands = _scan(md)
        self.assertTrue(any(c.norm_path == "/v1/client/trade/{tid}" for c in cands))

    def test_coinex_zero_width_space_in_path(self):
        """CoinEx has U+200B zero-width spaces in some content."""
        md = "## HTTP request\u200b\n\nGET /account/info\u200b\n"
        cands = _scan(md)
        self.assertTrue(any(c.norm_path == "/account/info" for c in cands))

    def test_aevo_heading_is_method_path(self):
        """Aevo per-endpoint pages use heading as method+path."""
        md = "# GET /account\n\nReturns account details.\n"
        cands = _scan(md)
        self.assertTrue(any(c.method == "GET" and c.norm_path == "/account" and c.pattern == "P4" for c in cands))

    def test_apex_trailing_punctuation(self):
        """Apex endpoints sometimes have trailing markdown punctuation."""
        md = "## Create Order\n\n` POST /v3/generate-nonce) `\n"
        cands = _scan(md)
        # Trailing ) must be stripped by _normalize_path
        self.assertTrue(any(c.norm_path == "/v3/generate-nonce" for c in cands))

    def test_multiline_document_finds_all(self):
        """Patterns must work across a multi-line document, not just first line.
        Root cause: adversarial review found missing re.MULTILINE flag."""
        md = "# Intro\n\nSome preamble.\n\n" + "filler text. " * 50 + "\n\n"
        md += "## Order\n\nPOST `/api/order`\n\n"
        md += "filler. " * 50 + "\n\n"
        md += "## Balance\n\nGET `/api/balance`\n"
        cands = _scan(md)
        paths = {c.norm_path for c in cands}
        self.assertIn("/api/order", paths)
        self.assertIn("/api/balance", paths)

    def test_p3_heading_method_pairs_with_code_block(self):
        """P3: heading has method in parens, path comes from next code block.
        This was a plan gap found in adversarial review round 3."""
        md = "## Cancel All (HTTP DELETE)\n\n```\n/orders/all\n```\n"
        cands = _scan(md)
        self.assertTrue(
            any(c.method == "DELETE" and c.norm_path == "/orders/all" for c in cands),
            f"Expected DELETE /orders/all, got {[(c.method, c.norm_path) for c in cands]}",
        )


# ===================================================================
# M23 extraction: record construction correctness
# ===================================================================

class TestRecordConstructionSafety(unittest.TestCase):
    """Guard: extracted records must pass save_endpoints_bulk validation.
    Adversarial review found 2 critical bugs here."""

    def _make_record(self, method="GET", path="/api/test", heading="Test Endpoint"):
        md = f"## {heading}\n\n{method} `{path}`\n"
        cand = EndpointCandidate(
            method=method, raw_path=path, norm_path=_normalize_path(path),
            char_start=len(f"## {heading}\n\n"), char_end=len(f"## {heading}\n\n{method} `{path}`"),
            pattern="P1", heading_text=heading,
            page_url="https://docs.ex.com/api", line_number=3,
        )
        return _build_endpoint_record(
            candidate=cand, md=md, crawled_at="2026-01-01T00:00:00Z",
            content_hash="abc123", path_hash="def456",
            exchange="testex", section="api",
            base_url="https://api.ex.com", api_version=None,
        )

    def test_base_url_must_be_unknown(self):
        """Critical fix from adversarial review round 2:
        base_url field_status must be 'unknown', not 'documented'.
        Setting it to 'documented' causes EBADCITE rejection because
        no citation from the page proves the base_url."""
        rec = self._make_record()
        self.assertEqual(rec["field_status"]["http.base_url"], "unknown")

    def test_documented_fields_have_citations(self):
        """Every 'documented' field must have a matching source citation.
        _save_endpoint_record checks this and raises EBADCITE if missing."""
        rec = self._make_record()
        documented = {k for k, v in rec["field_status"].items() if v == "documented"}
        source_fields = {s["field_name"] for s in rec["sources"]}
        for f in documented:
            self.assertIn(f, source_fields, f"Documented field {f!r} has no citation")

    def test_citation_excerpt_matches_source(self):
        """Citation excerpt must match the markdown at the specified offsets.
        This is verified byte-for-byte by _verify_citation_against_store."""
        md = "## Test\n\nGET `/api/test`\n"
        cand = EndpointCandidate(
            method="GET", raw_path="/api/test", norm_path="/api/test",
            char_start=10, char_end=25, pattern="P1",
            heading_text="Test", page_url="https://ex.com",
            line_number=3,
        )
        rec = _build_endpoint_record(
            candidate=cand, md=md, crawled_at="t", content_hash="c",
            path_hash="p", exchange="x", section="s",
            base_url="https://api.ex.com", api_version=None,
        )
        for src in rec["sources"]:
            excerpt = src["excerpt"]
            start = src["excerpt_start"]
            end = src["excerpt_end"]
            self.assertEqual(md[start:end], excerpt,
                             f"Citation for {src['field_name']} doesn't match source markdown")

    def test_extraction_metadata_complete(self):
        """Schema requires 4 extraction fields: model, temperature, prompt_hash, input_content_hash."""
        rec = self._make_record()
        ext = rec["extraction"]
        for field in ("model", "temperature", "prompt_hash", "input_content_hash"):
            self.assertIn(field, ext, f"Missing extraction field: {field}")
        self.assertEqual(ext["model"], "extract-markdown")
        self.assertEqual(ext["temperature"], 0)

    def test_all_field_status_keys_present(self):
        """All REQUIRED_HTTP_FIELD_STATUS_KEYS must be in field_status."""
        rec = self._make_record()
        for k in REQUIRED_HTTP_FIELD_STATUS_KEYS:
            self.assertIn(k, rec["field_status"], f"Missing field_status key: {k}")

    def test_endpoint_id_deterministic(self):
        """Same input must produce same endpoint_id."""
        rec1 = self._make_record()
        rec2 = self._make_record()
        self.assertEqual(rec1["endpoint_id"], rec2["endpoint_id"])

    def test_description_preserves_normal_words(self):
        """'Get Balance' heading should keep 'Get' (normal word, not HTTP method).
        Bug found during M23: case-insensitive method stripping removed 'Get'."""
        rec = self._make_record(heading="Get Balance")
        self.assertEqual(rec["description"], "Get Balance")

    def test_description_strips_uppercase_method(self):
        """Uppercase HTTP methods in headings should be stripped."""
        rec = self._make_record(heading="GET /api/test")
        # The method and path are stripped, description should be empty/None
        self.assertTrue(rec["description"] is None or rec["description"] == "")


# ===================================================================
# M23 extraction: dedup correctness
# ===================================================================

class TestDedupCorrectness(unittest.TestCase):
    """Guard: dedup must handle Postman {{url}} prefixes, different
    path parameter styles, and zero-width characters."""

    def test_postman_prefix_stripped(self):
        self.assertEqual(_normalize_path_for_dedup("{{url}}/api/v1/order"), "/api/v1/order")
        self.assertEqual(_normalize_path_for_dedup("{{host}}/api/v1/order"), "/api/v1/order")
        self.assertEqual(_normalize_path_for_dedup("{{baseUrl}}/api/v1/order"), "/api/v1/order")

    def test_param_styles_collapse_for_dedup(self):
        """Different param styles must collapse to {} for comparison."""
        self.assertEqual(_normalize_path_for_dedup("/order/{id}"), "/order/{}")
        self.assertEqual(_normalize_path_for_dedup("/order/:id"), "/order/{}")
        self.assertEqual(_normalize_path_for_dedup("/order/<id>"), "/order/{}")

    def test_same_endpoint_different_param_style_deduped(self):
        """Same endpoint with :param and {param} should dedup to one."""
        md = (
            "## Get Order v1\n\nGET `/order/:id`\n\n"
            "## Get Order v2\n\nGET `/order/{id}`\n"
        )
        cands = _scan(md)
        order_cands = [c for c in cands if "order" in c.norm_path]
        self.assertEqual(len(order_cands), 1, "Same path with different param style should dedup")


# ===================================================================
# Classification: non-regression for other types
# ===================================================================

class TestClassificationNonRegression(unittest.TestCase):
    """Guard: BUG-15 fix must not break other classification paths."""

    def test_endpoint_path_with_method(self):
        r = classify_input("POST /api/v3/order")
        self.assertEqual(r.input_type, "endpoint_path")

    def test_endpoint_path_without_method(self):
        r = classify_input("/api/v3/ticker/price")
        self.assertEqual(r.input_type, "endpoint_path")

    def test_question_still_detected(self):
        r = classify_input("What is the rate limit for Binance spot API?")
        self.assertEqual(r.input_type, "question")

    def test_json_payload_still_detected(self):
        r = classify_input('{"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT"}')
        self.assertEqual(r.input_type, "request_payload")

    def test_error_phrase_still_detected(self):
        r = classify_input("rate limit exceeded, please try again later")
        self.assertEqual(r.input_type, "error_message")

    def test_ccxt_import_is_code(self):
        r = classify_input("import ccxt\nexchange = ccxt.okx()")
        self.assertEqual(r.input_type, "code_snippet")

    def test_curl_is_code(self):
        r = classify_input("curl -X GET https://api.binance.com/api/v3/ticker/price")
        self.assertEqual(r.input_type, "code_snippet")


# ===================================================================
# BUG-8 regression: blend weights are query-type-aware
# ===================================================================

class TestBug8BlendWeights(unittest.TestCase):
    """Guard: code_snippet and request_payload queries should use
    reranker-heavy blend weights (BUG-8)."""

    def test_code_snippet_narrows_gap_between_items(self):
        from xdocs.fts_util import position_aware_blend
        # "a" has better rrf, "b" has better rerank.
        # With reranker-heavy weights, the gap between them should shrink
        # (reranker signal for "b" carries more weight).
        items = [
            {"url": "a", "rrf_score": 0.50, "rerank_score": 0.1},
            {"url": "b", "rrf_score": 0.45, "rerank_score": 0.9},
        ]
        default = position_aware_blend(items, query_type_hint="question")
        code = position_aware_blend(items, query_type_hint="code_snippet")
        a_def = next(r["blended_score"] for r in default if r["url"] == "a")
        b_def = next(r["blended_score"] for r in default if r["url"] == "b")
        a_code = next(r["blended_score"] for r in code if r["url"] == "a")
        b_code = next(r["blended_score"] for r in code if r["url"] == "b")
        gap_default = a_def - b_def
        gap_code = a_code - b_code
        self.assertLess(gap_code, gap_default,
                       "code_snippet should narrow the gap (reranker gets more weight)")

    def test_default_weights_unchanged_for_question(self):
        from xdocs.fts_util import position_aware_blend
        items = [
            {"url": "a", "rrf_score": 1.0, "rerank_score": 0.5},
            {"url": "b", "rrf_score": 0.5, "rerank_score": 0.8},
        ]
        result = position_aware_blend(items, query_type_hint="question")
        # With default weights (75/25 at rank 1), high-rrf item "a" should still win
        self.assertEqual(result[0]["url"], "a")

    def test_request_payload_narrows_gap_between_items(self):
        from xdocs.fts_util import position_aware_blend
        items = [
            {"url": "a", "rrf_score": 0.50, "rerank_score": 0.1},
            {"url": "b", "rrf_score": 0.45, "rerank_score": 0.9},
        ]
        default = position_aware_blend(items, query_type_hint="question")
        payload = position_aware_blend(items, query_type_hint="request_payload")
        a_def = next(r["blended_score"] for r in default if r["url"] == "a")
        b_def = next(r["blended_score"] for r in default if r["url"] == "b")
        a_pay = next(r["blended_score"] for r in payload if r["url"] == "a")
        b_pay = next(r["blended_score"] for r in payload if r["url"] == "b")
        gap_default = a_def - b_def
        gap_payload = a_pay - b_pay
        self.assertLess(gap_payload, gap_default,
                       "request_payload should narrow the gap (reranker gets more weight)")


# ===================================================================
# BUG-17 regression: path-only queries find endpoints
# ===================================================================

class TestBug17PathOnlyQueries(unittest.TestCase):
    """Guard: bare endpoint paths without exchange name should return
    results by looking up the path in the endpoint DB."""

    def test_okx_unique_path(self):
        """OKX has a unique /api/v5/ prefix — should auto-detect."""
        from xdocs.classify import classify_input
        r = classify_input("GET /api/v5/account/balance")
        self.assertEqual(r.input_type, "endpoint_path")
        self.assertIn("path", r.signals)

    def test_classification_detects_bare_path(self):
        """Bare paths without method should still classify as endpoint_path."""
        from xdocs.classify import classify_input
        r = classify_input("/api/v3/ticker/price")
        self.assertEqual(r.input_type, "endpoint_path")


if __name__ == "__main__":
    unittest.main()
