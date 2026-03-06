# CCXT Cross-Reference Gap Analysis

**Date**: 2026-03-06
**CCXT version**: 4.5.40
**Store**: 3,399 structured endpoints across 20 CEX exchanges (per xref query)
**Tool**: `cex_api_docs.ccxt_xref.ccxt_cross_reference()`

## Executive Summary

Ran `ccxt_cross_reference()` against all 21 mapped exchanges (korbit skipped -- no CCXT class). Of 20 checked, **only 5 produced meaningful path comparisons** (bithumb, coinone, whitebit, kraken, mercadobitcoin). The remaining 15 exchanges report 0 CCXT endpoints due to a **path extraction limitation**: `_extract_ccxt_endpoints()` only walks list-type leaf nodes in the CCXT `describe().api` tree, but most major exchanges (binance, okx, bybit, etc.) use nested dict-of-dicts structures where paths are dict keys, not list items.

### Key Findings

1. **WhiteBit** is the largest gap: 100 CCXT endpoints missing from our DB (we have 0 endpoints for whitebit).
2. **Coinone** has 46 endpoints in CCXT missing from us (we have 22 via v2 API; CCXT tracks the older v1 API too).
3. **Bithumb** has 28 CCXT endpoints missing (all v1 legacy API; we have 36 via the newer v1/v2 REST API -- completely different path structure).
4. **Mercado Bitcoin** has 21 CCXT endpoints missing (all legacy v1/v3 API; we have 31 via the newer v4 API).
5. **Kraken** shows 2 "missing" endpoints that are actually Zendesk support article IDs, not API endpoints.
6. **Crypto.com** shows 0/0 due to an **exchange ID mismatch**: CCXT map uses `cryptocom` but our DB stores endpoints under `crypto_com`. Actual count in DB: 63 endpoints.
7. **Path extraction bug** affects 15/20 exchanges -- the function returns 0 CCXT endpoints for exchanges whose `describe().api` uses dict-of-dicts structure.

## Per-Exchange Results

### Exchanges With Meaningful Comparisons (5)

| Exchange | CCXT ID | CCXT EPs | Our EPs | Shared | Missing From Us | Unique To Us | Method Mismatches |
|----------|---------|----------|---------|--------|-----------------|--------------|-------------------|
| bithumb | bithumb | 28 | 36 | 0 | 28 | 32 | 0 |
| coinone | coinone | 63 | 22 | 0 | 46 | 22 | 0 |
| kraken | kraken | 2 | 0 | 0 | 2 | 0 | 0 |
| mercadobitcoin | mercado | 21 | 31 | 0 | 21 | 27 | 0 |
| whitebit | whitebit | 110 | 0 | 0 | 100 | 0 | 0 |

**Note**: Zero shared paths in every case is suspicious and indicates the path normalization is not aligning CCXT's path style with ours. For example, bithumb CCXT uses `/public/ticker/{}_{}` while we use `/v1/ticker`. These are genuinely different API versions, not normalization failures.

### Exchanges With 0 CCXT Endpoints (Extraction Bug) (15)

| Exchange | CCXT ID | Our EPs | CCXT `describe().api` Structure | Estimated CCXT EPs |
|----------|---------|---------|--------------------------------|-------------------|
| binance | binance | 1,425 | dict-of-dicts (sapi: 261 GET, 124 POST, ...) | ~500+ |
| bitbank | bitbank | 0 | dict-of-dicts (public, private, markets) | unknown |
| bitfinex | bitfinex | 81 | dict-of-dicts (public, private) | unknown |
| bitget | bitget | 233 | dict-of-dicts (public, private) | unknown |
| bitmart | bitmart | 0 | dict-of-dicts (public, private) | unknown |
| bitmex | bitmex | 95 | dict-of-dicts (public, private) | unknown |
| bitstamp | bitstamp | 82 | dict-of-dicts (public, private) | unknown |
| bybit | bybit | 129 | dict-of-dicts (public, private) | unknown |
| coinbase | coinbase | 49 | dict-of-dicts (v2, v3) | unknown |
| cryptocom | cryptocom | 0* | dict-of-dicts (base, v1, v2, derivatives) | unknown |
| gateio | gateio | 363 | dict-of-dicts (public, private) | unknown |
| htx | htx | 372 | dict-of-dicts (7 sections) | unknown |
| kucoin | kucoin | 124 | dict-of-dicts (9 sections) | unknown |
| okx | okx | 313 | dict-of-dicts (public, private) | unknown |
| upbit | upbit | 44 | dict-of-dicts (public, private) | unknown |

*Crypto.com also has an exchange ID mismatch: CCXT map key `cryptocom` vs DB key `crypto_com`, causing the query to find 0 of our 63 endpoints.

### Skipped Exchange (1)

| Exchange | Reason |
|----------|--------|
| korbit | No CCXT class exists |

### CCXT Section Sub-Classes

Some exchanges have section-specific CCXT classes. Only those using list-based API trees returned data:

| Exchange/Section | CCXT Class | Endpoints Extracted |
|-----------------|------------|-------------------|
| binance/futures_coinm | binancecoinm | 0 (dict-of-dicts) |
| binance/futures_usdm | binanceusdm | 0 (dict-of-dicts) |
| coinbase/exchange | coinbaseexchange | 79 |
| coinbase/intx | coinbaseinternational | 35 |
| kraken/futures | krakenfutures | 39 |
| kucoin/futures | kucoinfutures | 0 (dict-of-dicts) |

These section sub-classes are **not exercised** by the main `ccxt_cross_reference()` function, which only iterates `CCXT_EXCHANGE_MAP` (base exchange IDs), not `CCXT_SECTION_MAP`.

## CCXT Error Codes & Rate Limits

| Exchange | CCXT Error Codes | CCXT Rate Limit (ms) |
|----------|-----------------|---------------------|
| binance | 143 | 50 |
| bitbank | 15 | 100 |
| bitfinex | 11 | 250 |
| bitget | 495 | 50 |
| bithumb | 0 | 500 |
| bitmart | 197 | 33 |
| bitmex | 15 | 100 |
| bitstamp | 20 | 75 |
| bybit | 453 | 20 |
| coinbase | 27 | 34 |
| coinone | 0 | 50 |
| cryptocom | 54 | 10 |
| gateio | 98 | 50 |
| htx | 67 | 100 |
| kraken | 33 | 1000 |
| kucoin | 125 | 10 |
| mercadobitcoin | 0 | 1000 |
| okx | 387 | 110 |
| upbit | 13 | 50 |
| whitebit | 21 | 20 |

## Our Endpoint Coverage by Section

| Exchange | Section | Endpoint Count |
|----------|---------|---------------|
| binance | spot | 703 |
| binance | portfolio_margin | 225 |
| binance | futures_usdm | 192 |
| binance | futures_coinm | 130 |
| binance | margin_trading | 59 |
| binance | wallet | 47 |
| binance | options | 46 |
| binance | portfolio_margin_pro | 21 |
| binance | copy_trading | 2 |
| bitfinex | v2 | 81 |
| bitget | v2 | 102 |
| bitget | copy_trading | 45 |
| bitget | margin | 45 |
| bitget | earn | 27 |
| bitget | broker | 14 |
| bithumb | rest | 36 |
| bitmex | rest | 95 |
| bitstamp | rest | 82 |
| bybit | v5 | 129 |
| coinbase | intx | 49 |
| coinone | rest | 22 |
| crypto_com | exchange | 63 |
| gateio | v4 | 363 |
| htx | usdt_swap | 131 |
| htx | spot | 87 |
| htx | dm | 82 |
| htx | coin_margined_swap | 72 |
| korbit | rest | 32 |
| kucoin | spot | 70 |
| kucoin | futures | 54 |
| mercadobitcoin | v4 | 31 |
| okx | rest | 313 |
| upbit | rest_en | 44 |

**Total**: ~3,599 endpoints across 34 exchange/section pairs (CEX only, excludes DEX protocols dydx/hyperliquid).

## Actionable Gaps

### Priority 1: Fix `_extract_ccxt_endpoints()` Path Walking

The function only extracts endpoints when API paths are stored as list items. Most CCXT exchanges use a dict-of-dicts structure where the path segments are dict keys building up the full path. The `_walk_api()` function in `ccxt_xref.py` needs to handle this case -- when a dict key is not an HTTP method, it should be treated as a path segment, and the recursion should continue until it hits a list or a leaf. Currently it does this, but the resulting paths lack the base URL prefix because the `api_url` resolution fails when `urls.api` is a dict (multiple base URLs per section).

**Root cause**: When `urls.api` is a dict like `{"sapi": "https://api.binance.com/sapi", "public": "https://api.binance.com/api"}`, the code takes the first string value as `base_path`. But the path walking prepends this same base to all sections, losing the per-section prefix. The real fix is to resolve per-section base URLs.

### Priority 2: Endpoint Extraction for WhiteBit

WhiteBit has 110 endpoints in CCXT but 0 in our DB. Our pages are synced (docs are crawled) but no endpoint import has been done. Options:
- Check if WhiteBit publishes an OpenAPI spec (likely yes, given they have 110 well-structured endpoints in CCXT).
- Manual endpoint extraction from stored markdown.

### Priority 3: Fix Exchange ID Mismatch for Crypto.com

The CCXT map uses `cryptocom` but our DB stores endpoints under `crypto_com`. Either:
- Update `CCXT_EXCHANGE_MAP` to use `crypto_com`, or
- Add an alias resolution in `_our_endpoints()`.

### Priority 4: Coinone Legacy API Coverage

We have 22 endpoints (v2 API). CCXT tracks 63 including the older v1 API. The 46 "missing" endpoints are mostly v1 paths (`/account/balance`, `/order/limit_buy`, etc.) that have v2 equivalents in our store. Not a real coverage gap -- but worth verifying that every v1 endpoint has a v2 counterpart documented.

### Priority 5: Section Sub-Class Cross-Reference

The main function does not use `CCXT_SECTION_MAP` entries. This means:
- `coinbase/exchange` (79 CCXT endpoints via `coinbaseexchange`) is never compared
- `kraken/futures` (39 CCXT endpoints via `krakenfutures`) is never compared
- `kucoin/futures` (via `kucoinfutures`) is never compared
- Binance sub-classes (coinm, usdm) are never compared

Enhancing the function to iterate section sub-classes would surface additional gaps.

### Priority 6: Endpoint Extraction for Remaining 0-Count Exchanges

These exchanges have synced pages but no structured endpoints in our DB:
- **bitbank**: 0 endpoints (pages synced)
- **bitmart**: 0 endpoints (pages synced)

Both need OpenAPI import or manual endpoint extraction.

## Methodology Notes

- **Path normalization**: Both CCXT and our paths are normalized by stripping scheme+host, removing `{{url}}` prefixes, and collapsing path parameters (`{param}`, `:param`, `<param>`) to `{}`.
- **Zero shared paths**: Even for exchanges with data from both sides, shared path count is 0. This is because CCXT and our store often track different API versions (e.g., bithumb v1 legacy vs v1 REST, coinone v1 vs v2, mercado v1/v3 vs v4).
- **CCXT endpoint counts are lower bounds**: CCXT only tracks endpoints it uses for its unified API. Many exchange-specific endpoints (broker APIs, copy trading, earn products, etc.) are not in CCXT.
- **Output truncation**: The xref function caps `missing_from_us` at 50 items and `method_mismatches` at 20. Full counts are in `*_count` fields.
