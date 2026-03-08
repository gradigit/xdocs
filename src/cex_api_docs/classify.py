from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_exchange_names: list[str] | None = None

def _get_exchange_names() -> list[str]:
    """Load exchange names from registry, with hardcoded fallback."""
    global _exchange_names
    if _exchange_names is not None:
        return _exchange_names

    try:
        from .registry import load_registry
        registry_path = Path(__file__).resolve().parents[2] / "data" / "exchanges.yaml"
        reg = load_registry(registry_path)
        names = [ex.exchange_id for ex in reg.exchanges]
        # Add common aliases.
        alias_map = {
            "gateio": "gate.io",
            "cryptocom": "crypto.com",
            "mercadobitcoin": "mercado bitcoin",
        }
        for ex_id, alias in alias_map.items():
            if ex_id in names and alias not in names:
                names.append(alias)
        # Add legacy names.
        if "htx" in names and "huobi" not in names:
            names.append("huobi")
        _exchange_names = names
        return _exchange_names
    except Exception:
        # Fallback to hardcoded list if registry loading fails.
        _exchange_names = [
            "binance", "okx", "bybit", "bitget", "kucoin", "gate.io", "gateio",
            "htx", "huobi", "crypto.com", "bitstamp", "bitfinex", "dydx",
            "hyperliquid", "gmx", "drift", "aevo", "perp", "perpetual protocol",
            "gains", "gains network", "kwenta", "lighter", "ccxt",
            "upbit", "bithumb", "coinone", "korbit",
        ]
        return _exchange_names


@dataclass(frozen=True, slots=True)
class InputClassification:
    input_type: str       # "error_message" | "endpoint_path" | "request_payload" | "code_snippet" | "question"
    confidence: float     # 0.0-1.0
    signals: dict[str, Any] = field(default_factory=dict)


# Exchange-specific error code patterns.
_ERROR_CODE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Binance: negative integers like -1002, -2015
    ("binance", re.compile(r"-\d{4}\b")),
    # OKX: 5-digit codes like 50004, 58237
    ("okx", re.compile(r"\b5\d{4}\b")),
    # Generic HTTP status
    ("http", re.compile(r"\bHTTP\s+[45]\d{2}\b", re.IGNORECASE)),
    # Generic numeric error codes (4-6 digits)
    ("generic", re.compile(r"\b\d{5,6}\b")),
]

_ERROR_PHRASES: list[str] = [
    "not authorized",
    "permission denied",
    "rate limit",
    "api key",
    "invalid signature",
    "unauthorized",
    "forbidden",
    "access denied",
    "insufficient",
    "enable .+ permission",
    "ip .+ not .+ whitelist",
]

_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

_CODE_INDICATORS: list[re.Pattern[str]] = [
    re.compile(r"\bimport\s+\w+", re.IGNORECASE),
    re.compile(r"\brequire\s*\("),
    re.compile(r"\bcurl\s+", re.IGNORECASE),
    re.compile(r"\bccxt\b", re.IGNORECASE),
    re.compile(r"\bbinance[-_]connector\b", re.IGNORECASE),
    re.compile(r"\bfetch\s*\("),
    re.compile(r"\brequests\.\w+"),
    re.compile(r"\baxios\b", re.IGNORECASE),
    re.compile(r"\baiohttp\b", re.IGNORECASE),
    re.compile(r"^\s*const\s+\w+\s*=", re.MULTILINE),
    re.compile(r"^\s*let\s+\w+\s*=", re.MULTILINE),
    re.compile(r"^\s*var\s+\w+\s*=", re.MULTILINE),
    re.compile(r"^\s*def\s+\w+", re.MULTILINE),
    re.compile(r"^\s*async\s+def\s+\w+", re.MULTILINE),
    re.compile(r"\bwebsocket\.WebSocket", re.IGNORECASE),
    re.compile(r"\bWebSocketApp\b"),
    re.compile(r"\bnew\s+\w+Client\b"),
]


# Exchange-specific payload parameter signatures.
# Key fields that uniquely identify which exchange a request payload belongs to.
_PAYLOAD_EXCHANGE_SIGNATURES: dict[str, list[set[str]]] = {
    "okx": [{"instId"}, {"tdMode"}, {"instType"}],
    "bybit": [{"category", "symbol"}, {"category", "orderType"}],
    "kucoin": [{"clientOid"}, {"tradeType"}],
    "bitget": [{"marginCoin"}, {"productType"}],
    "gateio": [{"currency_pair"}, {"settle"}],
    "kraken": [{"pair", "ordertype"}],
    "bitmex": [{"orderQty", "ordType"}, {"orderQty", "symbol"}],
    "bitstamp": [{"currency_pair", "type"}],
}

# Method name to documentation topic mapping for code snippets.
_CODE_METHOD_TOPICS: dict[str, str] = {
    "fetch_balance": "account balance",
    "fetch_ticker": "ticker market data",
    "fetch_tickers": "tickers market data",
    "fetch_order_book": "orderbook",
    "fetch_ohlcv": "klines candlestick",
    "create_order": "place order trading",
    "cancel_order": "cancel order",
    "fetch_orders": "orders list",
    "fetch_open_orders": "open orders",
    "fetch_my_trades": "trades history",
    "fetch_positions": "positions",
    "fetch_deposits": "deposit history",
    "fetch_withdrawals": "withdrawal history",
    "withdraw": "withdraw",
    "load_markets": "exchange info symbols",
    "getOrderbook": "orderbook",
    "getWalletBalance": "wallet balance",
    "submitOrder": "place order",
    "getTickers": "tickers",
    "getKline": "klines candlestick",
}


def _detect_exchange_from_payload(payload: dict) -> str | None:
    """Detect exchange from JSON payload parameter names."""
    keys = set(payload.keys())
    for exchange, signatures in _PAYLOAD_EXCHANGE_SIGNATURES.items():
        for sig in signatures:
            if sig.issubset(keys):
                return exchange
    # Default: if has "symbol" + common trading fields, likely Binance
    if "symbol" in keys and keys & {"timeInForce", "recvWindow", "timestamp"}:
        return "binance"
    return None


def _extract_code_context(text: str) -> dict[str, Any]:
    """Extract exchange name and method from code snippets."""
    context: dict[str, Any] = {}

    # Extract exchange from ccxt.XXX() pattern
    m = re.search(r"\bccxt\.(\w+)\s*\(", text)
    if m:
        context["exchange_hint"] = m.group(1).lower()
        context["code_source"] = "ccxt"

    # Extract exchange from import/require patterns
    if "exchange_hint" not in context:
        for pat, exch in [
            (r"\bokx\.\w+", "okx"),
            (r"\bbybit[-_]api\b", "bybit"),
            (r"\bbinance[-_]connector\b", "binance"),
            (r"RestClientV5", "bybit"),
            (r"KuCoinClient", "kucoin"),
            (r"new\s+Binance\b", "binance"),
        ]:
            if re.search(pat, text, re.IGNORECASE):
                context["exchange_hint"] = exch
                context["code_source"] = "library"
                break

    # Extract exchange from API base URLs
    if "exchange_hint" not in context:
        for pat, exch in [
            (r"api\.binance\.com", "binance"),
            (r"stream\.binance\.com", "binance"),
            (r"api\.bybit\.com", "bybit"),
            (r"api\.kucoin\.com", "kucoin"),
            (r"api\.gate\.io|api\.gateio\.ws", "gateio"),
            (r"api\.kraken\.com", "kraken"),
            (r"api\.bitfinex\.com", "bitfinex"),
            (r"www\.okx\.com", "okx"),
        ]:
            if re.search(pat, text, re.IGNORECASE):
                context["exchange_hint"] = exch
                context["code_source"] = "url"
                break

    # Extract method names for topic mapping
    methods_found = []
    for method_name, topic in _CODE_METHOD_TOPICS.items():
        if method_name in text:
            methods_found.append({"method": method_name, "topic": topic})
    if methods_found:
        context["code_methods"] = methods_found

    return context


def classify_input(text: str) -> InputClassification:
    """Classify user input deterministically (no LLM)."""
    text = text.strip()
    if not text:
        return InputClassification(input_type="question", confidence=0.0, signals={})

    signals: dict[str, Any] = {}
    scores: dict[str, float] = {
        "error_message": 0.0,
        "endpoint_path": 0.0,
        "request_payload": 0.0,
        "code_snippet": 0.0,
        "question": 0.2,  # baseline
    }

    # --- Request payload detection (JSON) ---
    # Must run BEFORE error code detection so that numeric values inside JSON
    # payloads (e.g. "price":"30000") don't trigger false error_message matches.
    is_json_payload = False
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            is_json_payload = True
            signals["payload_format"] = "json"
            signals["payload_keys"] = list(parsed.keys())[:10]
            scores["request_payload"] += 0.7
            # Detect exchange from payload parameter names.
            payload_exchange = _detect_exchange_from_payload(parsed)
            if payload_exchange:
                signals["exchange_hint"] = payload_exchange
                signals["payload_exchange_source"] = "parameter_names"
    except (json.JSONDecodeError, ValueError):
        pass

    # --- Error message detection (skip if input is a JSON payload) ---
    if not is_json_payload:
        error_codes: list[dict[str, str]] = []
        for exchange_hint, pat in _ERROR_CODE_PATTERNS:
            for m in pat.finditer(text):
                error_codes.append({"code": m.group(), "exchange_hint": exchange_hint})
                scores["error_message"] += 0.4

        for phrase in _ERROR_PHRASES:
            if re.search(phrase, text, re.IGNORECASE):
                scores["error_message"] += 0.3
                break

        if error_codes:
            signals["error_codes"] = error_codes
            # Error codes are a strong signal — boost significantly when present.
            scores["error_message"] = max(scores["error_message"], 0.7)

    # --- Endpoint path detection ---
    path_match = re.search(
        r"(?:^|\s)((?:GET|POST|PUT|DELETE|PATCH)\s+)?(\/[a-zA-Z0-9_\-/{}.:]+)",
        text,
        re.IGNORECASE,
    )
    if path_match:
        method_str = (path_match.group(1) or "").strip().upper() or None
        path_str = path_match.group(2)
        # Require at least 2 path segments to avoid false positives on plain "/" references.
        if path_str.count("/") >= 2:
            signals["method"] = method_str
            signals["path"] = path_str
            scores["endpoint_path"] += 0.6
            if method_str:
                scores["endpoint_path"] += 0.2

    # --- Request payload detection (URL-encoded) ---

    if not is_json_payload and re.match(r"^[a-zA-Z_]\w*=[^&\s]+(&[a-zA-Z_]\w*=[^&\s]+)+$", text):
        signals["payload_format"] = "url_encoded"
        scores["request_payload"] += 0.6

    # --- Code snippet detection ---
    code_hits = 0
    for pat in _CODE_INDICATORS:
        if pat.search(text):
            code_hits += 1
    if code_hits > 0:
        scores["code_snippet"] += min(0.3 + code_hits * 0.15, 0.9)
        # Extract structured context from code snippets.
        code_ctx = _extract_code_context(text)
        if code_ctx.get("exchange_hint"):
            signals["exchange_hint"] = code_ctx["exchange_hint"]
            signals["code_source"] = code_ctx.get("code_source", "")
        if code_ctx.get("code_methods"):
            signals["code_methods"] = code_ctx["code_methods"]

    # --- Exchange hint detection (skip if already set by payload/code detection) ---
    if "exchange_hint" not in signals:
        exchange_names = _get_exchange_names()
        for name in exchange_names:
            if re.search(re.escape(name), text, re.IGNORECASE):
                hint = name.lower()
                # Normalize aliases to canonical exchange_id.
                alias_to_id = {
                    "gate.io": "gateio", "huobi": "htx",
                    "crypto.com": "cryptocom",
                    "mercado bitcoin": "mercadobitcoin",
                    "perpetual protocol": "perp", "gains network": "gains",
                }
                signals["exchange_hint"] = alias_to_id.get(hint, hint)
                break

    # --- Question detection ---
    if text.rstrip().endswith("?") or re.match(r"^(what|how|when|where|why|which|can|does|is|are)\b", text, re.IGNORECASE):
        scores["question"] += 0.3

    # Pick the highest-scoring type.
    best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score = scores[best_type]

    # Clamp confidence to [0, 1].
    confidence = min(max(best_score, 0.0), 1.0)

    return InputClassification(
        input_type=best_type,
        confidence=round(confidence, 2),
        signals=signals,
    )
