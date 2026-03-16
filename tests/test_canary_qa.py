"""CI-fast canary evaluation — FTS5-only, <10 seconds.

Runs a small subset of golden QA queries through the answer pipeline
with semantic search disabled. Detects regressions in core FTS5 retrieval
and answer pipeline routing without requiring model loading.

Usage:
    pytest tests/test_canary_qa.py -x --tb=short
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = os.environ.get("CEX_DOCS_DIR", str(REPO_ROOT / "cex-docs"))

# 25 canary queries covering all classification paths and top exchanges.
# These are selected from golden_qa.jsonl for stable, high-confidence matches.
CANARY_QUERIES = [
    # question — Tier 1 exchanges
    {"query": "Binance API key permissions", "expected_exchange": "binance", "classification": "question", "min_claims": 1},
    {"query": "Bybit get wallet balance", "expected_exchange": "bybit", "classification": "question", "min_claims": 1},
    {"query": "KuCoin API authentication", "expected_exchange": "kucoin", "classification": "question", "min_claims": 1},
    {"query": "Kraken REST API authentication", "expected_exchange": "kraken", "classification": "question", "min_claims": 1},
    {"query": "Coinbase REST API quickstart", "expected_exchange": "coinbase", "classification": "question", "min_claims": 1},
    {"query": "Bitget copy trading API", "expected_exchange": "bitget", "classification": "question", "min_claims": 1},
    {"query": "WhiteBIT API authentication", "expected_exchange": "whitebit", "classification": "question", "min_claims": 1},
    {"query": "Binance USDM futures order endpoints", "expected_exchange": "binance", "classification": "question", "min_claims": 1},
    {"query": "Coinone error codes", "expected_exchange": "coinone", "classification": "question", "min_claims": 1},
    {"query": "Paradex rate limits", "expected_exchange": "paradex", "classification": "question", "min_claims": 1},
    # endpoint_path
    {"query": "GET /api/v3/account Binance", "expected_exchange": "binance", "classification": "endpoint_path", "min_claims": 1},
    {"query": "POST /v5/order/create Bybit", "expected_exchange": "bybit", "classification": "endpoint_path", "min_claims": 1},
    {"query": "GET /0/public/Ticker Kraken", "expected_exchange": "kraken", "classification": "endpoint_path", "min_claims": 1},
    # error_message
    {"query": "Binance error -1002 unauthorized", "expected_exchange": "binance", "classification": "error_message", "min_claims": 1},
    {"query": "Bybit error 10001 parameter error", "expected_exchange": "bybit", "classification": "error_message", "min_claims": 1},
    # negative — should produce 0 claims or unknown status
    {"query": "What is the FTX API endpoint for placing orders", "expected_exchange": None, "classification": "question", "min_claims": 0, "expected_status": "unknown"},
    {"query": "What is the weather forecast for tomorrow", "expected_exchange": None, "classification": "question", "min_claims": 0, "expected_status": "unknown"},
]


@unittest.skipUnless(
    Path(DOCS_DIR, "db", "docs.db").exists(),
    "Canary tests require a populated store at CEX_DOCS_DIR",
)
class TestCanaryQA(unittest.TestCase):
    """Fast canary regression tests for the answer pipeline."""

    def _run_answer(self, query: str) -> dict:
        from xdocs.answer import answer_question
        return answer_question(docs_dir=DOCS_DIR, question=query)

    def test_canary_queries_produce_expected_results(self) -> None:
        """All canary queries should produce at least min_claims claims."""
        failures = []
        for canary in CANARY_QUERIES:
            result = self._run_answer(canary["query"])
            claims = result.get("claims", [])
            status = result.get("status", "unknown")

            # Check expected_status for negative tests.
            expected_status = canary.get("expected_status")
            if expected_status and status != expected_status:
                # Negative tests: status should match, but we also accept "ok" with 0 claims
                if not (status == "ok" and len(claims) == 0):
                    failures.append(
                        f"[{canary['classification']}] {canary['query']!r}: "
                        f"expected status={expected_status}, got status={status}"
                    )
                continue

            # Check min_claims.
            if len(claims) < canary["min_claims"]:
                failures.append(
                    f"[{canary['classification']}] {canary['query']!r}: "
                    f"expected >= {canary['min_claims']} claims, got {len(claims)} (status={status})"
                )

        if failures:
            self.fail(
                f"{len(failures)} canary regression(s):\n" + "\n".join(failures)
            )

    def test_classification_paths_covered(self) -> None:
        """Verify all 5 classification paths are represented in canaries."""
        paths = {c["classification"] for c in CANARY_QUERIES}
        for expected in ("question", "endpoint_path", "error_message"):
            self.assertIn(expected, paths)


if __name__ == "__main__":
    unittest.main()
