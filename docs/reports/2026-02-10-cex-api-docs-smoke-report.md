---
title: "CEX API Docs Smoke Report"
type: report
date: 2026-02-10
generated_at_utc: 2026-02-10T04:24:04Z
git_branch: feat/cex-api-docs-mvp
git_head: c0e3e65
python: "Python 3.14.2"
---

# CEX API Docs Smoke Report

This report is a reproducible sample run demonstrating that the local cite-only knowledge base is working end-to-end.

## Summary

- Registry seeds/domains: `23/23` ok
- Base URLs reachable: `26/26` ok
- Store integrity (fsck): `0` issues across `58` pages
- Wow query: `needs_clarification` without clarification; `ok` with `--clarification binance:portfolio_margin`

## From Scratch (Minimal Repro)

Notes:
- `validate-registry` / `validate-base-urls` are networked health checks; they do not populate `./cex-docs`.
- Minimal crawl below is sufficient to reproduce the cite-only wow query behavior.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cex-api-docs init --docs-dir ./cex-docs

# Minimal Binance crawl for the wow query
cex-api-docs crawl --exchange binance --section spot --docs-dir ./cex-docs --max-depth 1
cex-api-docs crawl --exchange binance --section portfolio_margin --docs-dir ./cex-docs --max-depth 1

# Ensure the permissions source page is present in the store (cite-only requirement)
cex-api-docs crawl --url "https://developers.binance.com/docs/derivatives/quick-start" --domain-scope developers.binance.com --docs-dir ./cex-docs --max-depth 0 --max-pages 5
```

## Sample Commands

```bash
./.venv/bin/pytest -q

./.venv/bin/cex-api-docs validate-registry
./.venv/bin/cex-api-docs validate-base-urls

./.venv/bin/cex-api-docs fsck --docs-dir ./cex-docs

q="What's the rate limit difference between Binance unified trading endpoint and the Binance spot endpoint? And in order to look up the balance of our Binance subaccount in Portfolio Margin mode, what permissions does the API key need?"
./.venv/bin/cex-api-docs answer "$q" --docs-dir ./cex-docs
./.venv/bin/cex-api-docs answer "$q" --clarification binance:portfolio_margin --docs-dir ./cex-docs
```

## Registry Validation (`validate-registry`)

Expected invariant: every seed URL returns HTTP 2xx and extracts non-empty markdown (strict).

```json
{
  "counts": {
    "errors": 0,
    "ok": 23,
    "suspected_redirect_stubs": 0,
    "total": 23
  }
}
```

| exchange | section | seed_url | http | render | words | status |
|---|---|---|---:|---|---:|---|
| binance | futures_coinm | https://developers.binance.com/docs/derivatives/coin-margined-futures/ | 200 | http | 2368 | ok |
| binance | futures_usdm | https://developers.binance.com/docs/derivatives/usds-margined-futures/ | 200 | http | 2540 | ok |
| binance | portfolio_margin | https://developers.binance.com/docs/derivatives/portfolio-margin/ | 200 | http | 2227 | ok |
| binance | spot | https://developers.binance.com/docs/binance-spot-api-docs/ | 200 | http | 16856 | ok |
| bitfinex | v2 | https://docs.bitfinex.com/reference/rest-public-platform-status | 200 | http | 532 | ok |
| bitget | v2 | https://www.bitget.com/api-doc/common/intro | 200 | http | 256 | ok |
| bithumb | rest | https://apidocs.bithumb.com/ | 200 | http | 24 | ok |
| bitstamp | rest | https://www.bitstamp.net/api/ | 200 | http | 22201 | ok |
| bybit | v5 | https://bybit-exchange.github.io/docs/v5/intro | 200 | http | 656 | ok |
| bybit | websocket | https://bybit-exchange.github.io/docs/v5/ws/connect | 200 | http | 1087 | ok |
| coinone | rest | https://docs.coinone.co.kr/ | 200 | http | 101 | ok |
| cryptocom | exchange | https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html | 200 | http | 34628 | ok |
| dydx | docs | https://docs.dydx.xyz/ | 200 | http | 241 | ok |
| gateio | v4 | https://www.gate.com/docs/apiv4/index.html | 200 | http | 74441 | ok |
| htx | spot | https://huobiapi.github.io/docs/spot/v1/en/ | 200 | http | 48457 | ok |
| hyperliquid | api | https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api | 200 | http | 201 | ok |
| korbit | rest | https://docs.korbit.co.kr/ | 200 | http | 12087 | ok |
| kucoin | futures | https://www.kucoin.com/docs/rest/futures-trading/orders/place-order | 200 | http | 2735 | ok |
| kucoin | spot | https://www.kucoin.com/docs/rest/spot-trading/spot-hf-trade-pro-account/place-hf-order | 200 | http | 2735 | ok |
| okx | rest | https://www.okx.com/docs-v5/en/ | 200 | http | 224360 | ok |
| okx | websocket | https://www.okx.com/docs-v5/en/#websocket-api | 200 | http | 224360 | ok |
| upbit | rest_en | https://docs.upbit.com/reference | 200 | http | 1254 | ok |
| upbit | rest_ko | https://docs.upbit.com/ko/reference | 200 | http | 1254 | ok |

## Base URL Validation (`validate-base-urls`)

Expected invariant: every `base_url` is reachable (unauthenticated).

Notes:
- For `https://` entries, `ok` means "an HTTP response was obtained" (any status code). Some hosts return 403/404 on `/` but are still reachable.
- For `wss://` entries, this command is DNS-only (no websocket handshake).
- This does not use API keys and does not call authenticated endpoints.

```json
{
  "counts": {
    "errors": 0,
    "ok": 26,
    "total": 26
  }
}
```

| exchange | section | base_url | scheme | http | mode | status |
|---|---|---|---|---:|---|---|
| binance | futures_coinm | https://dapi.binance.com | https | 403 | http | ok |
| binance | futures_usdm | https://fapi.binance.com | https | 403 | http | ok |
| binance | portfolio_margin | https://papi.binance.com | https | 403 | http | ok |
| binance | spot | https://api.binance.com | https | 200 | http | ok |
| bitfinex | v2 | https://api-pub.bitfinex.com/v2 | https | 301 | http | ok |
| bitget | v2 | https://api.bitget.com | https | 404 | http | ok |
| bithumb | rest | https://api.bithumb.com | https | 200 | http | ok |
| bitstamp | rest | https://www.bitstamp.net/api | https | 200 | http | ok |
| bybit | v5 | https://api.bybit.com | https | 200 | http | ok |
| bybit | websocket | wss://stream.bybit.com/v5/private | wss |  | dns-only | ok |
| bybit | websocket | wss://stream.bybit.com/v5/public | wss |  | dns-only | ok |
| coinone | rest | https://api.coinone.co.kr | https | 404 | http | ok |
| cryptocom | exchange | https://api.crypto.com/exchange/v1 | https | 404 | http | ok |
| dydx | docs | https://indexer.dydx.trade/v4 | https | 404 | http | ok |
| gateio | v4 | https://api.gateio.ws/api/v4 | https | 404 | http | ok |
| htx | spot | https://api.huobi.pro | https | 404 | http | ok |
| hyperliquid | api | https://api.hyperliquid.xyz | https | 404 | http | ok |
| korbit | rest | https://api.korbit.co.kr/v1 | https | 404 | http | ok |
| kucoin | futures | https://api-futures.kucoin.com | https | 404 | http | ok |
| kucoin | spot | https://api.kucoin.com | https | 404 | http | ok |
| okx | rest | https://www.okx.com | https | 200 | http | ok |
| okx | websocket | wss://ws.okx.com:8443/ws/v5/business | wss |  | dns-only | ok |
| okx | websocket | wss://ws.okx.com:8443/ws/v5/private | wss |  | dns-only | ok |
| okx | websocket | wss://ws.okx.com:8443/ws/v5/public | wss |  | dns-only | ok |
| upbit | rest_en | https://api.upbit.com/v1 | https | 404 | http | ok |
| upbit | rest_ko | https://api.upbit.com/v1 | https | 404 | http | ok |

## Store Integrity (`fsck`)

Expected invariant: no DB/file mismatches; fsck is detection-only.

```json
{
  "counts": {
    "endpoints": 0,
    "issues": 0,
    "pages": 58
  },
  "issues": []
}
```

## Wow Query (Cite-Only)

Query:

```
What's the rate limit difference between Binance unified trading endpoint and the Binance spot endpoint? And in order to look up the balance of our Binance subaccount in Portfolio Margin mode, what permissions does the API key need?
```

### 1) Without clarification

Expected behavior: tool returns `needs_clarification` with concrete section choices derived from local store.

```json
{
  "clarification_prompt": "What does 'unified trading' refer to in Binance docs for this question?",
  "options": [
    {
      "exchange": "binance",
      "id": "binance:spot",
      "label": "binance:spot",
      "section": "spot"
    },
    {
      "exchange": "binance",
      "id": "binance:futures_usdm",
      "label": "binance:futures_usdm",
      "section": "futures_usdm"
    },
    {
      "exchange": "binance",
      "id": "binance:futures_coinm",
      "label": "binance:futures_coinm",
      "section": "futures_coinm"
    },
    {
      "exchange": "binance",
      "id": "binance:portfolio_margin",
      "label": "binance:portfolio_margin",
      "section": "portfolio_margin"
    }
  ],
  "status": "needs_clarification"
}
```

### 2) With clarification (`binance:portfolio_margin`)

Expected behavior: tool returns `ok` and all factual claims have citations.

```json
{
  "claims_count": 3,
  "missing": [],
  "status": "ok"
}
```

#### Citations (verbatim excerpts + offsets)

1. `rate_limit`
   - url: `https://developers.binance.com/docs/derivatives/portfolio-margin/common-definition`
   - crawled_at: `2026-02-10T03:55:32+00:00`
   - content_hash: `d20cb89a3bac521e25abe55672bb406acfb92f62e13f396f7658b87abb1e0275`
   - excerpt_start/excerpt_end: `5397`/`5797`

   ```
TER
  * PERPETUAL_DELIVERING


**Contract status (contractStatus, status):**

  * PENDING_TRADING
  * TRADING
  * PRE_DELIVERING
  * DELIVERING
  * DELIVERED
  * PRE_SETTLE
  * SETTLING
  * CLOSE


**Rate limiters (rateLimitType)**

  * REQUEST_WEIGHT
  * ORDERS


> **REQUEST_WEIGHT**
[code]
      {
        "rateLimitType": "REQUEST_WEIGHT",
        "interval": "MINUTE",
        "intervalNum": 1,
   ```

2. `rate_limit`
   - url: `https://developers.binance.com/docs/binance-spot-api-docs/websocket-api/account-requests`
   - crawled_at: `2026-02-10T03:56:42+00:00`
   - content_hash: `8a50ddec6f2e91691424fb7f321afcdf6723730a2e5dc1210a434970e9381883`
   - excerpt_start/excerpt_end: `2433`/`2833`

   ```
-api-docs/websocket-api/response-format>)
    * [Event format](https://developers.binance.com/docs/binance-spot-api-docs/websocket-api/</docs/binance-spot-api-docs/websocket-api/event-format>)
    * [Rate limits](https://developers.binance.com/docs/binance-spot-api-docs/websocket-api/</docs/binance-spot-api-docs/websocket-api/rate-limits>)
    * [Request security](https://developers.binance.com/do
   ```

3. `required_permissions`
   - url: `https://developers.binance.com/docs/derivatives/quick-start`
   - crawled_at: `2026-02-10T03:55:30+00:00`
   - content_hash: `501ed095237338d98309e61535231b89c6e6e565d495761f1cff7bc4d1414b92`
   - excerpt_start/excerpt_end: `2153`/`2553`

   ```
tps://developers.binance.com/docs/derivatives/</docs/derivatives/quick-start#api-key-restrictions> "Direct link to API Key Restrictions")

  * After creating the API key, the default restrictions is `Enable Reading`.
  * To **enable withdrawals via the API** , the API key restriction needs to be modified through the Binance UI.


## Enabling Accounts[​](https://developers.binance.com/docs/derivati
   ```
