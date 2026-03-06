"""CCXT cross-reference module.

Compares our endpoint DB against CCXT ``describe()`` metadata to detect
coverage gaps and method mismatches.  CCXT is used strictly as a
*validation* tool — the cite-only constraint means we never create
endpoint records from CCXT data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .db import open_db
from .errors import CexApiDocsError
from .store import require_store_db


# ---------------------------------------------------------------------------
# Exchange ID mapping: our registry ID → CCXT class ID
# ---------------------------------------------------------------------------

CCXT_EXCHANGE_MAP: dict[str, str | None] = {
    "binance": "binance",
    "okx": "okx",
    "bybit": "bybit",
    "bitget": "bitget",
    "gateio": "gateio",
    "kucoin": "kucoin",
    "htx": "htx",
    "cryptocom": "cryptocom",
    "bitstamp": "bitstamp",
    "bitfinex": "bitfinex",
    "dydx": "dydx",
    "hyperliquid": "hyperliquid",
    "upbit": "upbit",
    "bithumb": "bithumb",
    "coinone": "coinone",
    "korbit": None,  # no CCXT class
    "kraken": "kraken",
    "coinbase": "coinbase",
    "bitmex": "bitmex",
    "bitmart": "bitmart",
    "whitebit": "whitebit",
    "bitbank": "bitbank",
    "mercadobitcoin": "mercado",
}

# Sub-exchange classes that match specific sections.
CCXT_SECTION_MAP: dict[tuple[str, str], str] = {
    ("kraken", "futures"): "krakenfutures",
    ("kucoin", "futures"): "kucoinfutures",
    ("binance", "futures_coinm"): "binancecoinm",
    ("binance", "futures_usdm"): "binanceusdm",
    ("coinbase", "exchange"): "coinbaseexchange",
    ("coinbase", "intx"): "coinbaseinternational",
}


def _load_ccxt_exchange(ccxt_id: str) -> Any:
    """Instantiate a CCXT exchange class by ID."""
    try:
        import ccxt  # type: ignore[import-untyped]
    except ImportError:
        raise CexApiDocsError(
            code="ENOCCXT",
            message="ccxt package not installed. Install with: pip install ccxt",
        )

    cls = getattr(ccxt, ccxt_id, None)
    if cls is None:
        raise CexApiDocsError(
            code="ENOCCXT",
            message=f"CCXT exchange class not found: {ccxt_id}",
            details={"ccxt_id": ccxt_id},
        )
    return cls()


def _normalize_path(path: str) -> str:
    """Normalize an API path for comparison.

    Strips leading scheme+host, removes Postman ``{{url}}`` prefix,
    collapses path parameter placeholders to ``{}``.
    """
    # Strip scheme + host if present.
    if path.startswith("http://") or path.startswith("https://"):
        path = urlsplit(path).path

    # Strip Postman {{url}} prefix.
    path = re.sub(r"^\{\{url\}\}", "", path)

    # Normalize path parameters: {param}, :param, <param> → {}
    path = re.sub(r"\{[^}]+\}", "{}", path)
    path = re.sub(r":([A-Za-z_]\w*)", "{}", path)
    path = re.sub(r"<[^>]+>", "{}", path)

    # Strip trailing slash for consistency.
    return path.rstrip("/") or "/"


def _extract_ccxt_endpoints(exchange_obj: Any) -> list[dict[str, str]]:
    """Extract endpoint list from a CCXT exchange's ``describe()`` output.

    Returns list of ``{"method": "GET", "path": "/api/v3/ticker"}``.

    Handles two CCXT API tree formats:
    - List-based: ``{"get": ["ticker", "orderbook"]}``
    - Dict-with-costs: ``{"get": {"ticker": 1, "orderbook": 0.5}}``
    """
    desc = exchange_obj.describe()
    api = desc.get("api", {})
    urls = desc.get("urls", {})

    # Build per-section base path map from urls.api.
    section_base_paths: dict[str, str] = {}
    default_base_path = ""
    if isinstance(urls, dict):
        api_val = urls.get("api", "")
        if isinstance(api_val, str):
            default_base_path = urlsplit(api_val).path.rstrip("/")
        elif isinstance(api_val, dict):
            for section_name, url in api_val.items():
                if isinstance(url, str) and url.startswith("http"):
                    section_base_paths[section_name] = urlsplit(url).path.rstrip("/")
            # Use first URL as default fallback.
            if not default_base_path and section_base_paths:
                default_base_path = next(iter(section_base_paths.values()))

    endpoints: list[dict[str, str]] = []

    def _walk_api(node: Any, method: str, prefix: str) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                upper = key.upper()
                if upper in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    _walk_api(val, upper, prefix)
                elif isinstance(val, (int, float)):
                    # Dict-with-costs format: {path_string: numeric_cost}.
                    full_path = f"{prefix}/{key}" if key else prefix
                    endpoints.append({"method": method, "path": full_path})
                else:
                    _walk_api(val, method, f"{prefix}/{key}")
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, str):
                    full_path = f"{prefix}/{item}" if item else prefix
                    endpoints.append({"method": method, "path": full_path})
                elif isinstance(item, dict):
                    # Some CCXT endpoints are dicts with more info.
                    path = str(item.get("path", item.get("url", "")))
                    if path:
                        full_path = f"{prefix}/{path}" if not path.startswith("/") else path
                        endpoints.append({"method": method, "path": full_path})

    for api_type, methods in api.items():
        if not isinstance(methods, dict):
            continue
        # Resolve per-section base path.
        base_path = section_base_paths.get(api_type, default_base_path)
        for method_or_group, paths in methods.items():
            upper = method_or_group.upper()
            if upper in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                _walk_api(paths, upper, base_path)
            else:
                # Assume GET for unspecified method groups.
                _walk_api(paths, "GET", f"{base_path}/{method_or_group}")

    return endpoints


# Exchange ID aliases: registry ID → DB endpoint exchange value.
# Needed when exchanges.yaml uses a different ID than what endpoint imports stored.
_EXCHANGE_ID_ALIASES: dict[str, list[str]] = {
    "cryptocom": ["cryptocom", "crypto_com"],
}


def _our_endpoints(conn: Any, exchange: str) -> list[dict[str, Any]]:
    """Fetch our endpoint records for an exchange."""
    ids = _EXCHANGE_ID_ALIASES.get(exchange, [exchange])
    placeholders = ",".join("?" for _ in ids)
    cur = conn.execute(
        f"SELECT endpoint_id, method, path, base_url, section FROM endpoints WHERE exchange IN ({placeholders});",
        ids,
    )
    return [dict(r) for r in cur.fetchall()]


def ccxt_cross_reference(
    docs_dir: str,
    exchange: str | None = None,
) -> dict[str, Any]:
    """Compare endpoint DB against CCXT describe() metadata.

    Parameters
    ----------
    docs_dir : str
        Path to the local store.
    exchange : str | None
        If provided, only cross-reference this exchange.

    Returns
    -------
    dict
        Per-exchange comparison plus summary statistics.
    """
    try:
        import ccxt  # type: ignore[import-untyped]
    except ImportError:
        raise CexApiDocsError(
            code="ENOCCXT",
            message="ccxt package not installed. Install with: pip install ccxt",
        )

    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)

    try:
        exchanges_to_check: list[str] = []
        if exchange:
            if exchange not in CCXT_EXCHANGE_MAP:
                raise CexApiDocsError(
                    code="ENOREG",
                    message=f"Exchange {exchange!r} not in CCXT mapping.",
                    details={"exchange": exchange, "known": sorted(CCXT_EXCHANGE_MAP.keys())},
                )
            exchanges_to_check = [exchange]
        else:
            exchanges_to_check = sorted(CCXT_EXCHANGE_MAP.keys())

        results: dict[str, Any] = {}
        total_ccxt = 0
        total_ours = 0

        for ex_id in exchanges_to_check:
            ccxt_id = CCXT_EXCHANGE_MAP.get(ex_id)
            if ccxt_id is None:
                results[ex_id] = {
                    "ccxt_id": None,
                    "skipped": True,
                    "reason": "no CCXT class",
                }
                continue

            try:
                exchange_obj = _load_ccxt_exchange(ccxt_id)
                ccxt_eps = _extract_ccxt_endpoints(exchange_obj)
            except Exception as e:
                results[ex_id] = {
                    "ccxt_id": ccxt_id,
                    "skipped": True,
                    "reason": f"CCXT load error: {e}",
                }
                continue

            our_eps = _our_endpoints(conn, ex_id)

            # Build normalized path sets for comparison.
            ccxt_paths: dict[str, set[str]] = {}  # normalized_path → methods
            for ep in ccxt_eps:
                norm = _normalize_path(ep["path"])
                ccxt_paths.setdefault(norm, set()).add(ep["method"].upper())

            our_paths: dict[str, set[str]] = {}  # normalized_path → methods
            for ep in our_eps:
                if ep["path"]:
                    norm = _normalize_path(ep["path"])
                    our_paths.setdefault(norm, set()).add((ep["method"] or "").upper())

            ccxt_path_set = set(ccxt_paths.keys())
            our_path_set = set(our_paths.keys())

            missing_from_us = sorted(ccxt_path_set - our_path_set)
            unique_to_us = sorted(our_path_set - ccxt_path_set)

            # Method mismatches on shared paths.
            method_mismatches: list[dict[str, Any]] = []
            for path in sorted(ccxt_path_set & our_path_set):
                ccxt_methods = ccxt_paths[path]
                our_methods = our_paths[path]
                if ccxt_methods != our_methods:
                    method_mismatches.append({
                        "path": path,
                        "ccxt_methods": sorted(ccxt_methods),
                        "our_methods": sorted(our_methods),
                    })

            # Extract error codes and rate limit from describe().
            desc = exchange_obj.describe()
            exceptions = desc.get("exceptions", {})
            error_count = 0
            if isinstance(exceptions, dict):
                for category in exceptions.values():
                    if isinstance(category, dict):
                        error_count += len(category)
                    elif isinstance(category, list):
                        error_count += len(category)

            rate_limit = desc.get("rateLimit")

            results[ex_id] = {
                "ccxt_id": ccxt_id,
                "ccxt_endpoints": len(ccxt_eps),
                "our_endpoints": len(our_eps),
                "shared_paths": len(ccxt_path_set & our_path_set),
                "missing_from_us": missing_from_us[:50],
                "missing_from_us_count": len(missing_from_us),
                "unique_to_us": unique_to_us[:50],
                "unique_to_us_count": len(unique_to_us),
                "method_mismatches": method_mismatches[:20],
                "error_codes_in_ccxt": error_count,
                "rate_limit_ms": rate_limit,
            }
            total_ccxt += len(ccxt_eps)
            total_ours += len(our_eps)

        return {
            "cmd": "ccxt-xref",
            "schema_version": "v1",
            "exchanges": results,
            "summary": {
                "exchanges_checked": len([r for r in results.values() if not r.get("skipped")]),
                "exchanges_skipped": len([r for r in results.values() if r.get("skipped")]),
                "total_ccxt_endpoints": total_ccxt,
                "total_our_endpoints": total_ours,
            },
        }
    finally:
        conn.close()
