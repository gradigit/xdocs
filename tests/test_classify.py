from __future__ import annotations

import unittest

from cex_api_docs.classify import InputClassification, classify_input


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
