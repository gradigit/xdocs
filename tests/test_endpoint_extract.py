"""Tests for endpoint_extract: regex patterns, normalization, citations, records."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from xdocs.endpoint_extract import (
    EndpointCandidate,
    _build_citation,
    _build_endpoint_record,
    _build_line_offsets,
    _clean_heading_for_description,
    _normalize_path,
    _normalize_path_for_dedup,
    extract_params_near,
    scan_endpoints_from_page,
)
from xdocs.endpoints import HARD_MAX_EXCERPT_CHARS, REQUIRED_HTTP_FIELD_STATUS_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scan(md: str, **kwargs) -> list[EndpointCandidate]:
    defaults = {
        "md": md,
        "page_url": "https://docs.example.com/api",
        "crawled_at": "2026-03-27T00:00:00Z",
        "content_hash": "abc123",
        "path_hash": "def456",
        "exchange": "testex",
        "section": "api",
        "base_url": "https://api.example.com",
    }
    defaults.update(kwargs)
    return scan_endpoints_from_page(**defaults)


# ---------------------------------------------------------------------------
# Pattern tests
# ---------------------------------------------------------------------------

class TestPattern1InlineMethodPath(unittest.TestCase):
    def test_basic(self) -> None:
        md = "## Place Order\n\nPOST `/v2/spot/order`\n\nSome description."
        cands = _scan(md)
        self.assertTrue(any(c.method == "POST" and c.norm_path == "/v2/spot/order" for c in cands))

    def test_no_backticks(self) -> None:
        md = "## Get Balance\n\nGET /v1/user/assets\n"
        cands = _scan(md)
        self.assertTrue(any(c.method == "GET" and c.norm_path == "/v1/user/assets" for c in cands))


class TestPattern2CodeBlock(unittest.TestCase):
    def test_code_block_method_path(self) -> None:
        md = "## Query products\n\n> Request\n\n```text\nGET /public/products\n```\n\nReturns list."
        cands = _scan(md)
        paths = [(c.method, c.norm_path, c.pattern) for c in cands]
        self.assertTrue(any(m == "GET" and p == "/public/products" and pat == "P2" for m, p, pat in paths))


class TestPattern3HeadingWithMethod(unittest.TestCase):
    def test_heading_http_method_with_code_block(self) -> None:
        md = (
            "## Place order (HTTP PUT, _prefered_)\n\n"
            "```text\n"
            "PUT /orders/create?clOrdID=xxx\n"
            "```\n"
        )
        cands = _scan(md)
        self.assertTrue(
            any(c.method == "PUT" and "/orders/create" in c.norm_path and c.pattern == "P3" for c in cands),
            f"Expected P3 match, got: {[(c.method, c.norm_path, c.pattern) for c in cands]}",
        )

    def test_p3_method_from_heading_path_from_block(self) -> None:
        md = (
            "## Cancel order (HTTP DELETE)\n\n"
            "```\n"
            "/orders/cancel\n"
            "```\n"
        )
        cands = _scan(md)
        self.assertTrue(
            any(c.method == "DELETE" and c.norm_path == "/orders/cancel" for c in cands),
            f"Expected DELETE /orders/cancel, got: {[(c.method, c.norm_path) for c in cands]}",
        )


class TestPattern4HeadingIsMethodPath(unittest.TestCase):
    def test_heading_method_path(self) -> None:
        md = "# GET /options-history\n\nReturns option settlement history."
        cands = _scan(md)
        self.assertTrue(any(c.method == "GET" and c.norm_path == "/options-history" and c.pattern == "P4" for c in cands))


class TestPattern5BacktickWrapped(unittest.TestCase):
    def test_backtick_wrapped(self) -> None:
        md = "## Get System Status\n\n` GET /v1/public/system_info `\n\nReturns status."
        cands = _scan(md)
        self.assertTrue(
            any(c.method == "GET" and c.norm_path == "/v1/public/system_info" and c.pattern == "P5" for c in cands),
            f"Expected P5 match, got: {[(c.method, c.norm_path, c.pattern) for c in cands]}",
        )


class TestMultilineRegex(unittest.TestCase):
    def test_patterns_find_matches_on_later_lines(self) -> None:
        md = "# Introduction\n\nSome preamble text.\n\n## Create Order\n\nPOST `/api/v1/order`\n\n## Get Balance\n\nGET `/api/v1/balance`\n"
        cands = _scan(md)
        methods_paths = {(c.method, c.norm_path) for c in cands}
        self.assertIn(("POST", "/api/v1/order"), methods_paths)
        self.assertIn(("GET", "/api/v1/balance"), methods_paths)


class TestPatternPriority(unittest.TestCase):
    def test_dedup_first_wins(self) -> None:
        md = "# GET /api/test\n\nGET `/api/test`\n"
        cands = _scan(md)
        matches = [c for c in cands if c.norm_path == "/api/test"]
        self.assertEqual(len(matches), 1, "Should dedup to one match")
        self.assertEqual(matches[0].pattern, "P4", "P4 should win (runs first)")


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------

class TestNormalizePath(unittest.TestCase):
    def test_query_params_stripped(self) -> None:
        self.assertEqual(_normalize_path("/path?key=val&other=1"), "/path")

    def test_angle_bracket_params(self) -> None:
        self.assertEqual(_normalize_path("/orders/<orderId>/trades"), "/orders/{orderId}/trades")

    def test_colon_params(self) -> None:
        self.assertEqual(_normalize_path("/v1/order/:oid/trades"), "/v1/order/{oid}/trades")

    def test_brace_params_preserved(self) -> None:
        self.assertEqual(_normalize_path("/orders/{order_id}"), "/orders/{order_id}")

    def test_zero_width_chars(self) -> None:
        self.assertEqual(_normalize_path("/path\u200b/test\ufeff"), "/path/test")

    def test_trailing_punctuation(self) -> None:
        self.assertEqual(_normalize_path("/path)"), "/path")
        self.assertEqual(_normalize_path("/path]"), "/path")
        self.assertEqual(_normalize_path("/path,"), "/path")
        self.assertEqual(_normalize_path("/path."), "/path")

    def test_trailing_slash(self) -> None:
        self.assertEqual(_normalize_path("/api/v1/"), "/api/v1")

    def test_root_path(self) -> None:
        self.assertEqual(_normalize_path("/"), "/")


class TestNormalizePathForDedup(unittest.TestCase):
    def test_collapses_param_names(self) -> None:
        self.assertEqual(_normalize_path_for_dedup("/orders/{order_id}"), "/orders/{}")

    def test_strips_postman_prefix(self) -> None:
        self.assertEqual(_normalize_path_for_dedup("{{url}}/api/v1/order"), "/api/v1/order")


# ---------------------------------------------------------------------------
# Citation tests
# ---------------------------------------------------------------------------

class TestBuildCitation(unittest.TestCase):
    def test_excerpt_matches_source(self) -> None:
        md = "x" * 100 + "GET /api/test" + "y" * 600
        cit = _build_citation(
            page_url="https://example.com",
            crawled_at="2026-01-01",
            content_hash="abc",
            path_hash="def",
            md=md,
            char_start=100,
            field_name="http.method",
        )
        self.assertEqual(md[cit["excerpt_start"]:cit["excerpt_end"]], cit["excerpt"])

    def test_excerpt_within_hard_max(self) -> None:
        md = "a" * 1000
        cit = _build_citation(
            page_url="u", crawled_at="t", content_hash="c",
            path_hash="p", md=md, char_start=0, field_name="f",
        )
        self.assertLessEqual(len(cit["excerpt"]), HARD_MAX_EXCERPT_CHARS)

    def test_near_end_of_file(self) -> None:
        md = "hello world"
        cit = _build_citation(
            page_url="u", crawled_at="t", content_hash="c",
            path_hash="p", md=md, char_start=6, field_name="f",
        )
        self.assertEqual(cit["excerpt"], "world")
        self.assertEqual(cit["excerpt_start"], 6)
        self.assertEqual(cit["excerpt_end"], 11)


# ---------------------------------------------------------------------------
# Line offset tests
# ---------------------------------------------------------------------------

class TestBuildLineOffsets(unittest.TestCase):
    def test_basic(self) -> None:
        md = "line1\nline2\nline3"
        offsets = _build_line_offsets(md)
        self.assertEqual(offsets[1], 0)   # line 1 starts at char 0
        self.assertEqual(offsets[2], 6)   # line 2 starts at char 6
        self.assertEqual(offsets[3], 12)  # line 3 starts at char 12


# ---------------------------------------------------------------------------
# Record construction tests
# ---------------------------------------------------------------------------

class TestBuildEndpointRecord(unittest.TestCase):
    def _make_record(self) -> dict:
        md = "## Get Balance\n\nGET /v1/balance\n"
        cand = EndpointCandidate(
            method="GET", raw_path="/v1/balance", norm_path="/v1/balance",
            char_start=18, char_end=32, pattern="P1",
            heading_text="Get Balance", page_url="https://docs.ex.com/api",
            line_number=3,
        )
        return _build_endpoint_record(
            candidate=cand, md=md, crawled_at="2026-01-01T00:00:00Z",
            content_hash="abc", path_hash="def",
            exchange="testex", section="api",
            base_url="https://api.ex.com", api_version=None,
        )

    def test_field_status_keys(self) -> None:
        rec = self._make_record()
        for k in REQUIRED_HTTP_FIELD_STATUS_KEYS:
            self.assertIn(k, rec["field_status"])

    def test_method_path_documented(self) -> None:
        rec = self._make_record()
        self.assertEqual(rec["field_status"]["http.method"], "documented")
        self.assertEqual(rec["field_status"]["http.path"], "documented")

    def test_base_url_unknown(self) -> None:
        rec = self._make_record()
        self.assertEqual(rec["field_status"]["http.base_url"], "unknown")

    def test_sources_match_documented_fields(self) -> None:
        rec = self._make_record()
        documented = {k for k, v in rec["field_status"].items() if v == "documented"}
        source_fields = {s["field_name"] for s in rec["sources"]}
        for f in documented:
            self.assertIn(f, source_fields, f"Documented field {f} missing citation")

    def test_extraction_fields(self) -> None:
        rec = self._make_record()
        self.assertEqual(rec["extraction"]["model"], "extract-markdown")
        self.assertEqual(rec["extraction"]["temperature"], 0)
        self.assertEqual(rec["extraction"]["prompt_hash"], "n/a")
        self.assertIn("input_content_hash", rec["extraction"])

    def test_endpoint_id_present(self) -> None:
        rec = self._make_record()
        self.assertTrue(rec["endpoint_id"])

    def test_description_from_heading(self) -> None:
        rec = self._make_record()
        self.assertEqual(rec["description"], "Get Balance")


class TestCleanHeadingForDescription(unittest.TestCase):
    def test_strips_http_method(self) -> None:
        self.assertEqual(_clean_heading_for_description("Place order (HTTP PUT, _prefered_)", "PUT", "/orders"), "Place order")

    def test_strips_path(self) -> None:
        self.assertEqual(_clean_heading_for_description("GET /options-history", "GET", "/options-history"), None)

    def test_empty_heading(self) -> None:
        self.assertIsNone(_clean_heading_for_description("", "GET", "/test"))


# ---------------------------------------------------------------------------
# Full page extraction tests
# ---------------------------------------------------------------------------

class TestPhemexSyntheticMonolith(unittest.TestCase):
    def test_extracts_multiple_endpoints(self) -> None:
        md = (
            "# COIN-M Perpetual API\n\n"
            "## Query product information\n\n"
            "> Request\n\n```text\nGET /public/products\n```\n\n"
            "## Query server time\n\n"
            "> Request\n\n```text\nGET /public/time\n```\n\n"
            "## Place order (HTTP PUT, _prefered_)\n\n"
            "> Request format\n\n```text\n"
            "PUT /orders/create?clOrdID=xxx&symbol=yyy\n```\n\n"
            "## Cancel order\n\n"
            "> Request format\n\n```text\n"
            "DELETE /orders/cancel?symbol=xxx&orderID=yyy\n```\n\n"
            "## Query account info\n\n"
            "> Request\n\n```text\nGET /accounts/accountPositions\n```\n\n"
        )
        cands = _scan(md)
        paths = {c.norm_path for c in cands}
        self.assertIn("/public/products", paths)
        self.assertIn("/public/time", paths)
        self.assertIn("/orders/create", paths)
        self.assertIn("/orders/cancel", paths)
        self.assertIn("/accounts/accountPositions", paths)
        self.assertGreaterEqual(len(cands), 5)


class TestDedupSamePage(unittest.TestCase):
    def test_duplicate_method_path_deduped(self) -> None:
        md = (
            "## Create Order\n\nPOST `/api/v1/order`\n\n"
            "## Also Create Order\n\nPOST `/api/v1/order`\n"
        )
        cands = _scan(md)
        matches = [c for c in cands if c.norm_path == "/api/v1/order"]
        self.assertEqual(len(matches), 1, "Duplicate should be deduped")


# ---------------------------------------------------------------------------
# Parameter table extraction tests
# ---------------------------------------------------------------------------

class TestExtractParamsNearPipeTable(unittest.TestCase):
    """Pipe-delimited parameter tables (cryptocom, bybit, apex, etc.)."""

    def test_basic_cryptocom_format(self) -> None:
        md = (
            "## public/get-announcements\n\n"
            "POST `/v1/public/get-announcements`\n\n"
            "### Request Params\n\n"
            "Name | Type | Required | Description\n"
            "---|---|---|---\n"
            "category | string | N | filter by category\n"
            "product_type | string | N | filter by product type\n\n"
            "### Response Attributes\n"
        )
        params = extract_params_near(md, md.index("POST"), method="POST")
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0]["name"], "category")
        self.assertEqual(params[0]["type"], "string")
        self.assertEqual(params[0]["required"], False)
        self.assertEqual(params[0]["description"], "filter by category")
        self.assertEqual(params[0]["in"], "body")

    def test_bybit_3col_format(self) -> None:
        md = (
            "## Get Orderbook\n\n"
            "GET `/v5/market/orderbook`\n\n"
            "### Request Parameters\n\n"
            "| Parameter | Type | Comments |\n"
            "|---|---|---|\n"
            "| category | string | Product type |\n"
            "| symbol | string | Symbol name |\n"
            "| limit | integer | Limit size |\n"
        )
        params = extract_params_near(md, md.index("GET"), method="GET")
        self.assertEqual(len(params), 3)
        self.assertEqual(params[0]["name"], "category")
        self.assertEqual(params[0]["in"], "query")  # GET → query
        self.assertEqual(params[2]["name"], "limit")

    def test_nested_params_dash_prefix(self) -> None:
        md = (
            "## Place Order\n\n"
            "POST `/v1/private/create-order`\n\n"
            "### Request Params\n\n"
            "Name | Type | Required | Description\n"
            "---|---|---|---\n"
            "instrument_name | string | Y | e.g. BTC_USDT\n"
            "side | string | Y | BUY or SELL\n"
            "order_info | object | Y | Order details\n"
            "- price | string | N | Limit price\n"
            "- quantity | string | Y | Order amount\n"
            "time_in_force | string | N | GTC or IOC\n"
        )
        params = extract_params_near(md, md.index("POST"), method="POST")
        self.assertEqual(len(params), 6)
        # Check nested params
        price = next(p for p in params if p["name"] == "price")
        self.assertEqual(price["parent"], "order_info")
        qty = next(p for p in params if p["name"] == "quantity")
        self.assertEqual(qty["parent"], "order_info")
        # Non-nested after nested
        tif = next(p for p in params if p["name"] == "time_in_force")
        self.assertNotIn("parent", tif)

    def test_apex_5col_format(self) -> None:
        md = (
            "## Create Order\n\n"
            "POST `/api/v3/order`\n\n"
            "### Request Parameters\n\n"
            "| Parameter | Position | Type | Type | Comment |\n"
            "|---|---|---|---|---|\n"
            "| symbol | body | string | true | Trading pair |\n"
            "| side | body | string | true | BUY/SELL |\n"
        )
        params = extract_params_near(md, md.index("POST"), method="POST")
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0]["name"], "symbol")

    def test_no_table_returns_empty(self) -> None:
        md = "## Get Time\n\nGET `/public/time`\n\nReturns server time.\n"
        params = extract_params_near(md, md.index("GET"), method="GET")
        self.assertEqual(params, [])

    def test_non_param_table_skipped(self) -> None:
        """A table without name/type columns should be skipped."""
        md = (
            "## Order Types\n\n"
            "POST `/orders`\n\n"
            "### Common Fields\n\n"
            "Order Type | Description\n"
            "---|---\n"
            "Limit | Limit order\n"
            "Market | Market order\n"
        )
        params = extract_params_near(md, md.index("POST"), method="POST")
        self.assertEqual(params, [])

    def test_required_normalization(self) -> None:
        md = (
            "POST `/api/test`\n\n"
            "### Request Body\n\n"
            "Name | Type | Required | Description\n"
            "---|---|---|---\n"
            "a | string | Y | field a\n"
            "b | string | true | field b\n"
            "c | string | optional | field c\n"
            "d | string | N | field d\n"
            "e | string | conditional | field e\n"
        )
        params = extract_params_near(md, 0, method="POST")
        self.assertIs(params[0]["required"], True)   # Y
        self.assertIs(params[1]["required"], True)   # true
        self.assertIs(params[2]["required"], False)   # optional
        self.assertIs(params[3]["required"], False)   # N
        self.assertEqual(params[4]["required"], "conditional")  # pass-through

    def test_outer_pipes_optional(self) -> None:
        """Tables with leading/trailing pipes should work."""
        md = (
            "POST `/test`\n\n"
            "### Request Parameters\n\n"
            "| Name | Type | Required |\n"
            "| --- | --- | --- |\n"
            "| symbol | string | Y |\n"
        )
        params = extract_params_near(md, 0, method="POST")
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "symbol")

    def test_stops_at_next_heading(self) -> None:
        md = (
            "POST `/test`\n\n"
            "### Request Params\n\n"
            "Name | Type | Required | Description\n"
            "---|---|---|---\n"
            "symbol | string | Y | pair\n\n"
            "### Response Attributes\n\n"
            "Name | Type | Description\n"
            "---|---|---\n"
            "id | string | order id\n"
        )
        params = extract_params_near(md, 0, method="POST")
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "symbol")


class TestExtractParamsNearTabTable(unittest.TestCase):
    """Tab-delimited parameter tables (Coinone, Aster)."""

    def test_coinone_korean_headers(self) -> None:
        # Simulate Coinone's literal \n format after unescaping.
        md = (
            "POST https://api.coinone.co.kr/v2.1/order/cancel\n\n"
            "Request Body\n"
            "필드\t유형\t필수\t설명\n"
            "access_token\tString\ttrue\t사용자의 액세스 토큰\n"
            "nonce\tString\ttrue\tUUID nonce\n"
            "order_id\tString\ttrue\t주문 식별 ID\n"
        )
        params = extract_params_near(md, 0, method="POST")
        self.assertEqual(len(params), 3)
        self.assertEqual(params[0]["name"], "access_token")
        self.assertEqual(params[0]["type"], "String")
        self.assertIs(params[0]["required"], True)
        self.assertEqual(params[0]["description"], "사용자의 액세스 토큰")

    def test_coinone_literal_backslash_n(self) -> None:
        """Coinone stores content with literal \\n and \\t — extract_params_near should handle it."""
        # Simulate stored format: literal two-char sequences (backslash+n, backslash+t).
        # In the .md file: `\n` is two chars, `\t` is two chars. Very few real newlines.
        md = (
            '"주문 취소\\nPOST https://api.coinone.co.kr/v2.1/order/cancel"'
            "\n\n"  # only real newlines are between JSON strings
            '"Request Body\\n필드\\t유형\\t필수\\t설명\\n'
            'access_token\\tString\\ttrue\\t토큰\\n'
            'nonce\\tString\\ttrue\\tUUID"'
        )
        params = extract_params_near(md, 0, method="POST")
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0]["name"], "access_token")

    def test_coinone_english_headers(self) -> None:
        md = (
            "GET /v2/account/balance\n\n"
            "Request Body\n"
            "Key\tType\tDescription\n"
            "access_token\tString\t토큰\n"
            "nonce\tString\tUUID\n"
        )
        params = extract_params_near(md, 0, method="GET")
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0]["in"], "query")

    def test_tab_nested_params(self) -> None:
        md = (
            "POST /api/order\n\n"
            "Request Parameters\n"
            "필드\t타입\t설명\n"
            "range_price_units\tArray[Object]\t가격 단위 정보\n"
            "- range_min\tinteger\t최소 가격\n"
            "- price_unit\tdouble\t호가 단위\n"
            "side\tString\t매수/매도\n"
        )
        params = extract_params_near(md, 0, method="POST")
        self.assertEqual(len(params), 4)
        self.assertEqual(params[1]["name"], "range_min")
        self.assertEqual(params[1]["parent"], "range_price_units")
        self.assertNotIn("parent", params[3])


class TestExtractParamsEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_backward_search_finds_table(self) -> None:
        """When the endpoint definition comes AFTER the param table."""
        md = (
            "### Request Parameters\n\n"
            "Name | Type | Required\n"
            "---|---|---\n"
            "symbol | string | Y\n\n"
            "POST `/api/order`\n"
        )
        # Point char_pos at the POST line (after the table).
        pos = md.index("POST")
        params = extract_params_near(md, pos, method="POST")
        self.assertEqual(len(params), 1)

    def test_delete_method_uses_query(self) -> None:
        md = (
            "DELETE `/api/order`\n\n"
            "### Request Parameters\n\n"
            "Name | Type | Required\n"
            "---|---|---\n"
            "order_id | string | Y\n"
        )
        params = extract_params_near(md, 0, method="DELETE")
        self.assertEqual(params[0]["in"], "query")

    def test_missing_required_column(self) -> None:
        """Tables without a required column should still parse."""
        md = (
            "POST `/test`\n\n"
            "### Parameters\n\n"
            "Field | Type | Description\n"
            "---|---|---\n"
            "symbol | string | Trading pair\n"
        )
        params = extract_params_near(md, 0, method="POST")
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "symbol")
        self.assertNotIn("required", params[0])

    def test_backtick_stripped_from_name(self) -> None:
        md = (
            "POST `/test`\n\n"
            "### Request Params\n\n"
            "Name | Type | Required\n"
            "---|---|---\n"
            "`symbol` | string | Y\n"
        )
        params = extract_params_near(md, 0, method="POST")
        self.assertEqual(params[0]["name"], "symbol")


if __name__ == "__main__":
    unittest.main()
