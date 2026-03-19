from __future__ import annotations

import unittest

from xdocs.classify import InputClassification, classify_input


class TestClassifyErrorMessages(unittest.TestCase):
    def test_binance_error_code(self) -> None:
        result = classify_input('Error -1002: You are not authorized to execute this request.')
        self.assertEqual(result.input_type, "error_message")
        self.assertGreater(result.confidence, 0.5)
        self.assertIn("error_codes", result.signals)
        codes = result.signals["error_codes"]
        self.assertTrue(any(c["code"] == "-1002" for c in codes))
        self.assertTrue(any(c["exchange_hint"] == "binance" for c in codes))

    def test_okx_error_code(self) -> None:
        result = classify_input("50004 endpoint request timeout")
        self.assertEqual(result.input_type, "error_message")
        codes = result.signals.get("error_codes", [])
        self.assertTrue(any(c["code"] == "50004" for c in codes))
        self.assertTrue(any(c["exchange_hint"] == "okx" for c in codes))

    def test_plain_text_error(self) -> None:
        result = classify_input("not authorized to access this endpoint")
        self.assertEqual(result.input_type, "error_message")

    def test_mixed_error_with_path(self) -> None:
        result = classify_input("-1002 when calling /sapi/v1/convert/getQuote")
        self.assertEqual(result.input_type, "error_message")
        self.assertIn("path", result.signals)
        self.assertEqual(result.signals["path"], "/sapi/v1/convert/getQuote")


class TestClassifyEndpointPaths(unittest.TestCase):
    def test_path_with_method(self) -> None:
        result = classify_input("POST /sapi/v1/convert/getQuote")
        self.assertEqual(result.input_type, "endpoint_path")
        self.assertGreater(result.confidence, 0.5)
        self.assertEqual(result.signals["method"], "POST")
        self.assertEqual(result.signals["path"], "/sapi/v1/convert/getQuote")

    def test_path_without_method(self) -> None:
        result = classify_input("/api/v3/order")
        self.assertEqual(result.input_type, "endpoint_path")
        self.assertIsNone(result.signals.get("method"))

    def test_path_with_exchange_hint(self) -> None:
        result = classify_input("GET /api/v5/trade/order on OKX")
        self.assertEqual(result.input_type, "endpoint_path")
        self.assertEqual(result.signals.get("exchange_hint"), "okx")


class TestClassifyPayloads(unittest.TestCase):
    def test_json_payload(self) -> None:
        result = classify_input('{"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT"}')
        self.assertEqual(result.input_type, "request_payload")
        self.assertEqual(result.signals.get("payload_format"), "json")

    def test_url_encoded_payload(self) -> None:
        result = classify_input("symbol=BTCUSDT&side=BUY&type=LIMIT")
        self.assertEqual(result.input_type, "request_payload")


class TestClassifyCodeSnippets(unittest.TestCase):
    def test_python_ccxt(self) -> None:
        result = classify_input("import ccxt\nexchange = ccxt.binance()")
        self.assertEqual(result.input_type, "code_snippet")

    def test_curl(self) -> None:
        result = classify_input("curl -X POST https://api.binance.com/sapi/v1/convert/getQuote")
        self.assertEqual(result.input_type, "code_snippet")

    def test_javascript(self) -> None:
        result = classify_input("const client = new BinanceConnector(apiKey, apiSecret);")
        self.assertEqual(result.input_type, "code_snippet")


class TestClassifyQuestions(unittest.TestCase):
    def test_rate_limit_question(self) -> None:
        result = classify_input("What are the rate limits for Binance spot trading?")
        self.assertEqual(result.input_type, "question")
        self.assertEqual(result.signals.get("exchange_hint"), "binance")

    def test_general_question(self) -> None:
        result = classify_input("How do I authenticate with the OKX API?")
        self.assertEqual(result.input_type, "question")
        self.assertEqual(result.signals.get("exchange_hint"), "okx")

    def test_exchange_hint_kraken(self) -> None:
        result = classify_input("How do I place an order on Kraken?")
        self.assertEqual(result.input_type, "question")
        self.assertEqual(result.signals.get("exchange_hint"), "kraken")

    def test_exchange_hint_coinbase(self) -> None:
        result = classify_input("What are Coinbase API rate limits?")
        self.assertEqual(result.input_type, "question")
        self.assertEqual(result.signals.get("exchange_hint"), "coinbase")

    def test_exchange_hint_bitmex(self) -> None:
        result = classify_input("How to get positions on BitMEX?")
        self.assertEqual(result.input_type, "question")
        self.assertEqual(result.signals.get("exchange_hint"), "bitmex")

    def test_exchange_hint_bitmart(self) -> None:
        result = classify_input("What permissions does BitMart API key need?")
        self.assertEqual(result.input_type, "question")
        self.assertEqual(result.signals.get("exchange_hint"), "bitmart")

    def test_exchange_hint_whitebit(self) -> None:
        result = classify_input("WhiteBIT withdrawal endpoint")
        self.assertIn(result.signals.get("exchange_hint", "").lower(), ("whitebit",))

    def test_exchange_hint_aster(self) -> None:
        result = classify_input("How to use Aster DEX API?")
        self.assertEqual(result.input_type, "question")
        self.assertEqual(result.signals.get("exchange_hint"), "aster")

    def test_exchange_hint_apex(self) -> None:
        result = classify_input("ApeX exchange trading API")
        self.assertIn("apex", result.signals.get("exchange_hint", "").lower())


class TestClassifyJsonPayloadNotError(unittest.TestCase):
    """JSON payloads with numeric values must not trigger error_message."""

    def test_json_with_large_numeric_values(self) -> None:
        result = classify_input('{"price":"30000","quantity":"50000"}')
        self.assertEqual(result.input_type, "request_payload")
        self.assertNotIn("error_codes", result.signals)

    def test_json_order_payload(self) -> None:
        result = classify_input('{"symbol":"BTCUSDT","side":"BUY","type":"LIMIT","price":"30000","quantity":"0.5"}')
        self.assertEqual(result.input_type, "request_payload")
        self.assertEqual(result.signals.get("payload_format"), "json")

    def test_error_code_still_detected_in_plain_text(self) -> None:
        """Regression guard: error codes in non-JSON text must still be detected."""
        result = classify_input("Error 50111: permission denied")
        self.assertEqual(result.input_type, "error_message")
        self.assertIn("error_codes", result.signals)

    def test_binance_negative_error_still_works(self) -> None:
        """Regression guard: Binance -1002 style errors."""
        result = classify_input("-1002 unauthorized")
        self.assertEqual(result.input_type, "error_message")


class TestBug15GenericErrorCodeFloor(unittest.TestCase):
    """BUG-15: Generic-only numeric codes should not get the 0.7 hard floor.

    Bare 5-6 digit numbers (e.g. timestamps, order IDs) were being over-scored
    because the generic pattern ``\\d{5,6}`` triggered the same floor as
    exchange-specific patterns like Binance's ``-\\d{4}``.
    """

    def test_generic_only_code_no_floor(self) -> None:
        """A bare 5-digit number without exchange context scores below 0.7."""
        result = classify_input("order 12345 is pending")
        # Should NOT be classified as error_message with high confidence.
        # The generic match gives +0.4, but no 0.7 floor.
        if result.input_type == "error_message":
            self.assertLess(result.confidence, 0.7)

    def test_generic_six_digit_no_floor(self) -> None:
        """A bare 6-digit number like a timestamp should not get error floor."""
        result = classify_input("created at 170045")
        if "error_codes" in result.signals:
            codes = result.signals["error_codes"]
            has_specific = any(c["exchange_hint"] not in ("generic", "http") for c in codes)
            self.assertFalse(has_specific, "Should only have generic match")
        # Should not be high-confidence error_message
        if result.input_type == "error_message":
            self.assertLess(result.confidence, 0.7)

    def test_exchange_specific_still_gets_floor(self) -> None:
        """Binance -1002 should still get the 0.7 floor."""
        result = classify_input("-1002")
        self.assertEqual(result.input_type, "error_message")
        self.assertGreaterEqual(result.confidence, 0.7)

    def test_okx_specific_still_gets_floor(self) -> None:
        """OKX 50004 should still get the 0.7 floor."""
        result = classify_input("50004")
        self.assertEqual(result.input_type, "error_message")
        self.assertGreaterEqual(result.confidence, 0.7)

    def test_mixed_generic_and_specific_gets_floor(self) -> None:
        """If both generic and exchange-specific patterns match, floor applies."""
        result = classify_input("error -1002 with trace 99999")
        self.assertEqual(result.input_type, "error_message")
        self.assertGreaterEqual(result.confidence, 0.7)

    def test_http_only_no_floor(self) -> None:
        """HTTP status codes alone should not get the exchange-specific floor."""
        result = classify_input("HTTP 503 service unavailable")
        # HTTP match gives +0.4, error phrase gives +0.3, but no 0.7 floor
        # from exchange-specific patterns. Total could exceed 0.7 naturally
        # from phrase + HTTP match, which is fine — we test that the floor
        # mechanism itself doesn't fire for http-only.
        if "error_codes" in result.signals:
            codes = result.signals["error_codes"]
            has_specific = any(c["exchange_hint"] not in ("generic", "http") for c in codes)
            self.assertFalse(has_specific)


class TestBug14CryptoCodePatterns(unittest.TestCase):
    """BUG-14: Bare API usage code (hmac, hashlib, dict assignment) must be
    classified as code_snippet, not question."""

    def test_hmac_signing_code(self) -> None:
        code = 'signature = hmac.new(secret, query_string, hashlib.sha256).hexdigest()'
        result = classify_input(code)
        self.assertEqual(result.input_type, "code_snippet")

    def test_dict_assignment_with_string_keys(self) -> None:
        code = 'payload = {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT"}'
        result = classify_input(code)
        self.assertEqual(result.input_type, "code_snippet")

    def test_encode_call(self) -> None:
        code = 'msg = query_string.encode("utf-8")'
        result = classify_input(code)
        self.assertEqual(result.input_type, "code_snippet")

    def test_base64_encoding(self) -> None:
        code = 'sig = base64.b64encode(hmac_obj.digest())'
        result = classify_input(code)
        self.assertEqual(result.input_type, "code_snippet")

    def test_nodejs_crypto(self) -> None:
        code = 'const sig = crypto.createHmac("sha256", secret).update(msg).digest("hex");'
        result = classify_input(code)
        self.assertEqual(result.input_type, "code_snippet")

    def test_question_not_affected(self) -> None:
        """Regression guard: plain questions must stay as question."""
        result = classify_input("What rate limits does Binance have?")
        self.assertEqual(result.input_type, "question")


class TestOpt2ApiPathExtraction(unittest.TestCase):
    """OPT-2: Extract API path from URLs in code snippets."""

    def test_bybit_url_in_requests_get(self) -> None:
        code = "import requests\nresponse = requests.get('https://api.bybit.com/v5/market/tickers', params={'category': 'spot'})"
        result = classify_input(code)
        self.assertEqual(result.input_type, "code_snippet")
        self.assertEqual(result.signals.get("api_path"), "/v5/market/tickers")

    def test_binance_url_in_curl(self) -> None:
        code = "curl -X GET 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'"
        result = classify_input(code)
        self.assertEqual(result.input_type, "code_snippet")
        self.assertEqual(result.signals.get("api_path"), "/api/v3/ticker/price")

    def test_okx_url_extraction(self) -> None:
        code = "fetch('https://www.okx.com/api/v5/account/balance')"
        result = classify_input(code)
        self.assertEqual(result.signals.get("api_path"), "/api/v5/account/balance")

    def test_no_url_no_api_path(self) -> None:
        code = "import ccxt\nexchange = ccxt.okx()\nexchange.fetch_balance()"
        result = classify_input(code)
        self.assertIsNone(result.signals.get("api_path"))

    def test_exchange_hint_from_url(self) -> None:
        code = "requests.get('https://api.kucoin.com/api/v1/market/allTickers')"
        result = classify_input(code)
        self.assertEqual(result.signals.get("exchange_hint"), "kucoin")
        self.assertEqual(result.signals.get("api_path"), "/api/v1/market/allTickers")


class TestClassifyEdgeCases(unittest.TestCase):
    def test_empty_input(self) -> None:
        result = classify_input("")
        self.assertEqual(result.input_type, "question")
        self.assertEqual(result.confidence, 0.0)

    def test_single_slash(self) -> None:
        # Single slash should not match as endpoint path.
        result = classify_input("/")
        self.assertNotEqual(result.input_type, "endpoint_path")


if __name__ == "__main__":
    unittest.main()
