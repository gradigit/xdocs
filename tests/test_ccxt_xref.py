"""Tests for the CCXT cross-reference module."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any

from xdocs.ccxt_xref import (
    CCXT_EXCHANGE_MAP,
    _extract_ccxt_endpoints,
    _normalize_path,
    _strip_version_prefix,
    ccxt_cross_reference,
)
from xdocs.db import open_db
from xdocs.store import init_store
from xdocs.timeutil import now_iso_utc

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestNormalizePath(unittest.TestCase):
    def test_plain_path(self) -> None:
        self.assertEqual(_normalize_path("/api/v3/ticker"), "/api/v3/ticker")

    def test_strips_trailing_slash(self) -> None:
        self.assertEqual(_normalize_path("/api/v3/ticker/"), "/api/v3/ticker")

    def test_strips_host(self) -> None:
        self.assertEqual(
            _normalize_path("https://api.binance.com/api/v3/ticker"),
            "/api/v3/ticker",
        )

    def test_normalizes_path_params(self) -> None:
        self.assertEqual(_normalize_path("/api/v1/order/{orderId}"), "/api/v1/order/{}")
        self.assertEqual(_normalize_path("/api/v1/order/:orderId"), "/api/v1/order/{}")
        self.assertEqual(_normalize_path("/api/v1/order/<orderId>"), "/api/v1/order/{}")

    def test_strips_postman_url(self) -> None:
        self.assertEqual(_normalize_path("{{url}}/api/v3/order"), "/api/v3/order")

    def test_strips_postman_host(self) -> None:
        self.assertEqual(_normalize_path("{{host}}/contract/public/details"), "/contract/public/details")

    def test_strips_postman_baseurl(self) -> None:
        self.assertEqual(_normalize_path("{{baseUrl}}/v2/ticker"), "/v2/ticker")

    def test_strips_zero_width_chars(self) -> None:
        self.assertEqual(_normalize_path("/v5/market\u200b/ticker"), "/v5/market/ticker")

    def test_strips_query_string(self) -> None:
        self.assertEqual(_normalize_path("/api/v1/ticker?symbol=BTC"), "/api/v1/ticker")

    def test_root_path(self) -> None:
        self.assertEqual(_normalize_path("/"), "/")


class TestStripVersionPrefix(unittest.TestCase):
    def test_api_v3(self) -> None:
        self.assertEqual(_strip_version_prefix("/api/v3/ticker"), "/ticker")

    def test_sapi_v1(self) -> None:
        self.assertEqual(_strip_version_prefix("/sapi/v1/order"), "/order")

    def test_plain_v2(self) -> None:
        self.assertEqual(_strip_version_prefix("/v2/ticker"), "/ticker")

    def test_no_version(self) -> None:
        self.assertEqual(_strip_version_prefix("/ticker"), "/ticker")

    def test_fapi_v1(self) -> None:
        self.assertEqual(_strip_version_prefix("/fapi/v1/ticker"), "/ticker")


class TestExtractCcxtEndpoints(unittest.TestCase):
    def _make_exchange(self, api: dict[str, Any], urls: dict[str, Any] | None = None) -> MagicMock:
        obj = MagicMock()
        desc = {"api": api, "urls": urls or {"api": "https://api.example.com"}}
        obj.describe.return_value = desc
        return obj

    def test_simple_get_post(self) -> None:
        api = {
            "public": {
                "get": ["ticker", "orderbook"],
                "post": ["order"],
            },
        }
        obj = self._make_exchange(api)
        eps = _extract_ccxt_endpoints(obj)
        self.assertEqual(len(eps), 3)
        methods = {(e["method"], e["path"]) for e in eps}
        self.assertIn(("GET", "/ticker"), methods)
        self.assertIn(("GET", "/orderbook"), methods)
        self.assertIn(("POST", "/order"), methods)

    def test_nested_api_structure(self) -> None:
        api = {
            "v1": {
                "get": ["time", "depth"],
            },
        }
        obj = self._make_exchange(api)
        eps = _extract_ccxt_endpoints(obj)
        self.assertEqual(len(eps), 2)

    def test_empty_api(self) -> None:
        obj = self._make_exchange({})
        eps = _extract_ccxt_endpoints(obj)
        self.assertEqual(len(eps), 0)


def _setup_store_with_endpoints(docs_dir: Path) -> None:
    """Set up a store with test endpoint records."""
    init_store(
        docs_dir=str(docs_dir),
        schema_sql_path=REPO_ROOT / "schema" / "schema.sql",
        lock_timeout_s=1.0,
    )

    conn = open_db(docs_dir / "db" / "docs.db")
    updated_at = now_iso_utc()

    endpoints = [
        {
            "endpoint_id": "test-ep-1",
            "exchange": "binance",
            "section": "spot",
            "protocol": "http",
            "method": "GET",
            "path": "/api/v3/ticker",
            "base_url": "https://api.binance.com",
            "description": "Get ticker",
        },
        {
            "endpoint_id": "test-ep-2",
            "exchange": "binance",
            "section": "spot",
            "protocol": "http",
            "method": "POST",
            "path": "/api/v3/order",
            "base_url": "https://api.binance.com",
            "description": "Place order",
        },
    ]

    try:
        with conn:
            for ep in endpoints:
                conn.execute(
                    """
INSERT INTO endpoints (endpoint_id, exchange, section, protocol, method, path, base_url, description, json, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                    (
                        ep["endpoint_id"],
                        ep["exchange"],
                        ep["section"],
                        ep["protocol"],
                        ep["method"],
                        ep["path"],
                        ep["base_url"],
                        ep["description"],
                        json.dumps(ep, sort_keys=True),
                        updated_at,
                    ),
                )
        conn.commit()
    finally:
        conn.close()


class TestCcxtCrossReference(unittest.TestCase):
    def _mock_ccxt_module(self) -> MagicMock:
        """Create a mock ccxt module with a binance class."""
        mock_ccxt = MagicMock()

        mock_exchange = MagicMock()
        mock_exchange.describe.return_value = {
            "api": {
                "public": {
                    "get": ["ticker", "orderbook", "depth"],
                },
                "private": {
                    "post": ["order"],
                    "delete": ["order"],
                },
            },
            "urls": {"api": "https://api.binance.com/api/v3"},
            "exceptions": {
                "exact": {"-1002": "AuthenticationError", "-1003": "RateLimitExceeded"},
                "broad": {},
            },
            "rateLimit": 100,
        }

        mock_ccxt.binance = MagicMock(return_value=mock_exchange)
        return mock_ccxt

    @patch.dict("sys.modules", {"ccxt": None})
    def test_raises_without_ccxt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            from xdocs.errors import CexApiDocsError

            with self.assertRaises((CexApiDocsError, ImportError)):
                ccxt_cross_reference(docs_dir=str(docs_dir), exchange="binance")

    def test_cross_reference_single_exchange(self) -> None:
        mock_ccxt = self._mock_ccxt_module()

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            with patch.dict("sys.modules", {"ccxt": mock_ccxt}):
                result = ccxt_cross_reference(docs_dir=str(docs_dir), exchange="binance")

            self.assertEqual(result["cmd"], "ccxt-xref")
            self.assertIn("binance", result["exchanges"])

            binance = result["exchanges"]["binance"]
            self.assertEqual(binance["ccxt_id"], "binance")
            self.assertGreater(binance["ccxt_endpoints"], 0)
            self.assertEqual(binance["our_endpoints"], 2)
            self.assertIn("shared_exact", binance)
            self.assertIn("shared_suffix", binance)
            self.assertEqual(binance["shared_paths"], binance["shared_exact"] + binance["shared_suffix"])
            self.assertEqual(binance["error_codes_in_ccxt"], 2)
            self.assertEqual(binance["rate_limit_ms"], 100)

    def test_skipped_exchange(self) -> None:
        mock_ccxt = self._mock_ccxt_module()

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            _setup_store_with_endpoints(docs_dir)

            with patch.dict("sys.modules", {"ccxt": mock_ccxt}):
                result = ccxt_cross_reference(docs_dir=str(docs_dir), exchange="korbit")

            self.assertTrue(result["exchanges"]["korbit"]["skipped"])
            self.assertEqual(result["exchanges"]["korbit"]["reason"], "no CCXT class")


class TestExchangeMap(unittest.TestCase):
    def test_all_cex_ids_present(self) -> None:
        """Verify all expected CEX IDs are in the mapping."""
        expected = {
            "binance", "okx", "bybit", "bitget", "gateio", "kucoin",
            "htx", "cryptocom", "bitstamp", "bitfinex", "dydx",
            "hyperliquid", "upbit", "bithumb", "coinone", "korbit",
            "kraken", "coinbase", "bitmex", "bitmart", "whitebit",
            "bitbank", "mercadobitcoin",
            "mexc", "bingx", "deribit", "backpack", "coinex",
            "woo", "phemex", "gemini", "orderly", "bluefin", "nado",
        }
        self.assertEqual(set(CCXT_EXCHANGE_MAP.keys()), expected)

    def test_korbit_is_none(self) -> None:
        self.assertIsNone(CCXT_EXCHANGE_MAP["korbit"])

    def test_mercadobitcoin_remapped(self) -> None:
        self.assertEqual(CCXT_EXCHANGE_MAP["mercadobitcoin"], "mercado")


if __name__ == "__main__":
    unittest.main()
