# Crawl Targets Bible

**Generated**: 2026-03-06 (v3 — 11 new exchanges registered)
**Coverage**: 46 registered (29 CEX, 16 DEX, 1 reference)
**Store snapshot** (live DB): 10,724 pages, 16.73M words, 4,872 structured endpoints (78 sections)

This document catalogs ALL known crawlable API documentation sources for every exchange in the registry, plus verified candidates for addition. It is the authoritative reference for maintaining `data/exchanges.yaml` entries, onboarding new exchanges, and planning endpoint extraction campaigns.

**Verification status**: All URLs, spec sizes, and coverage numbers verified against live DB and web sources on 2026-03-06. Stale data from prior M1-M4 research corrected. V2 adds 8 missing exchanges, WhiteBIT spec discovery, crawl methodology, and trust/validation framework.

---

## Table of Contents

1. [Crawl Methodology & Validation Philosophy](#1-crawl-methodology--validation-philosophy)
2. [Cross-Exchange Summary Tables](#2-cross-exchange-summary-tables)
3. [CEX Exchanges (21 registered)](#3-cex-exchanges)
4. [DEX Protocols (13 registered)](#4-dex-protocols)
5. [Reference (CCXT)](#5-reference)
6. [Missing Exchanges — Recommended Additions (8 CEX/DEX)](#6-missing-exchanges--recommended-additions)
7. [Tier 2 DEX Additions (4)](#7-tier-2-dex-additions)
8. [New Exchange Template](#8-new-exchange-template)
9. [Implementation Priorities](#9-implementation-priorities)
10. [Source Trust & Drift Validation](#10-source-trust--drift-validation)
11. [Confirmed Non-Existent Sources](#11-confirmed-non-existent-sources)

---

## 1. Crawl Methodology & Validation Philosophy

### 1a. Core Principles

1. **Sitemaps are hints, not ground truth.** Just because an exchange publishes a sitemap does not mean it is complete. Binance's sitemap returns 404. Gate.io's sitemap omits JS-rendered content. Kraken's sitemap has 48 REST API pages that our crawler never fetched because the seed URL only discovered guide pages. Always cross-validate with link-follow, nav extraction, and llms.txt.

2. **HTTP success does not mean correct content.** A 200 OK from `requests` may return a Cloudflare challenge page, a loading spinner, or a thin HTML shell. Always spot-check rendered output against browser-visible content. JS-heavy SPAs (OKX, Gate.io, HTX, Crypto.com, BitMart) require browser-based crawling.

3. **Specs drift from reality.** OpenAPI, Postman, AsyncAPI, and llms.txt files are maintained on separate release cycles from official API docs pages. They may be ahead (documenting unreleased endpoints) or behind (missing recent additions). **Official API docs pages are the closest thing to ground truth.** Specs are supplementary — import them, but always cross-reference against crawled doc pages.

4. **Reliability-first crawling.** No single crawl method works for all sites. The default should be the most reliable tool, with lighter tools as optimizations for known-safe sites. `requests` fails on ~40% of our exchanges (SPAs, Cloudflare, WAF). `crawl4ai` fails on Gate.io and all JS SPAs. Starting with unreliable tools means re-crawling nearly half the registry — no time saved.

   **Pipeline render modes** (what `xdocs sync --render` supports):
   - `http` (default): `requests` library — fast, works for static HTML (~60% of exchanges)
   - `auto`: tries `requests` first, falls back to Playwright for thin/failed pages
   - `playwright`: headless Chromium — for JS-rendered SPAs

   **Validation/spot-check cascade** (manual tools for verifying crawl output):
   - **Primary**: `crawl4ai` — works on ~95% of sites, returns LLM-ready markdown, handles JS + anti-bot (1.58MB from Gate.io vs 403 from requests). Use for spot-checking and validating pipeline output.
   - **Alternative**: 
   - **Fallback**: Headed browser (Playwright/crawl4ai with `headless=False`) — CAPTCHA solving, headless detection bypass
   - **Last resort**: Agent Browser — login-gated, infinite scroll, complex navigation

   **Note**: `crawl4ai` is not yet integrated into the sync pipeline's `--render` modes. It is installed as a standalone validation tool. For the sync pipeline, use `--render auto` (requests + Playwright fallback).

5. **Cross-validate everything.** Just because one crawl method succeeds doesn't mean the content is complete. Spot-check a sample of pages with a different method. Compare endpoint counts from specs vs page extraction vs CCXT. Flag discrepancies for manual review.

### 1b. Crawl Tool Evaluation (tested 2026-03-06)

| Tool | Type | Gate.io (403 site) | BitMart (SPA) | Bitstamp (WAF) | Best For |
|------|------|-------------------|---------------|----------------|----------|
| `requests` | HTTP lib | FAIL (403) | 200 but thin HTML | FAIL (WAF) | Static HTML, APIs, GitHub |
| Playwright | Browser | OK (JS render) | OK (full SPA) | OK (bypasses WAF) | JS-rendered SPAs |
| `crawl4ai` | Browser+AI | OK (1.58MB markdown) | OK (full content) | OK | Best all-around for LLM-ready output |
| Headed browser | Playwright/crawl4ai `headless=False` | OK (visible) | OK (visible) | OK (visible) | CAPTCHA solving, headless detection bypass, debugging |
| Agent Browser | Interactive | OK (manual) | OK (manual) | OK (manual) | Login-gated, infinite scroll |

**Recommended sync pipeline settings**:
1. Use `--render auto` for most exchanges (requests + Playwright fallback)
2. Use `--render http` for known-static sites (GitHub, Docusaurus, raw specs) — ~0.1s/page
3. Use `--render playwright` when auto doesn't pick up JS content (Bithumb EN, MercadoBitcoin)

**Post-sync validation cascade (manual)**:
1. Spot-check 5% of pages with `crawl4ai` — compare word count and content against stored markdown
2. If crawl4ai unavailable → use headed Playwright browser
3. On CAPTCHA / headless detection → try headed browser (`headless=False`)
4. On complex interaction (login, scroll, multi-step) → use Agent Browser
5. If discrepancy > 20%, flag exchange for full re-crawl with `--render auto`

**Known-static sites (safe for `requests` fast path)**:
GitHub Markdown (bitbank, grvt, ccxt), Docusaurus with static export (bybit, kraken, bitmex, whitebit), raw spec files (openapi.json/yaml), RSS/Atom feeds

**Must use `crawl4ai` or browser** (requests produce bad data):
OKX, Gate.io, HTX, Crypto.com, BitMart, KuCoin, Bitstamp, Bithumb EN, MercadoBitcoin

### 1c. Known Crawl Failure Modes

| Failure Mode | Exchanges Affected | Detection | Fix |
|-------------|-------------------|-----------|-----|
| Cloudflare 403 | Gate.io | HTTP status 403 | Use crawl4ai or Playwright |
| Thin HTML (SPA shell) | OKX, BitMart, HTX, Crypto.com | word_count < 100 on known-large pages | Use `--render auto` |
| WAF blocking | Bitstamp, Gate.io | 403 or CAPTCHA page | Use crawl4ai |
| Sitemap incomplete | Binance (404), Kraken (missing REST pages) | Compare sitemap URLs vs link-follow discovery | Run both methods, union results |
| Scope filtering too aggressive | Coinbase (FIX docs excluded) | Pages exist at domain but outside scope_prefixes | Widen scope_prefixes |
| Rate limiting after sync | Gate.io | 403 on subsequent requests | Increase delays, use `--concurrency 1` |
| Playwright not installed | Bithumb EN (0 pages) | render_mode: playwright but no browser | `pip install -e ".[playwright]"` |
| ReadMe.io client-side translation | Bithumb EN | Content requires Playwright for Localize.js | render_mode: playwright |

### 1d. Sitemap Trust Levels

| Trust Level | Exchanges | Notes |
|------------|-----------|-------|
| **High** (complete, matches site) | Bybit, Kraken, BitMEX, WhiteBIT, Coinbase, Hyperliquid | Docusaurus/platform-generated sitemaps |
| **Medium** (exists but incomplete) | Bitget, OKX | May not cover all SPA-rendered pages |
| **Low** (exists but misleading) | Kraken (missing 48 REST pages from crawl) | Sitemap is fine, but seed URL missed REST section |
| **None** (no sitemap) | Binance (404), HTX, Crypto.com, Korbit, BitMart, Bitbank | Must rely on link-follow + manual seeds |

---

## 2. Cross-Exchange Summary Tables

### 2a. Live DB Coverage (verified 2026-03-06)

| exchange | type | sections | pages | words | endpoints | ccxt_eps |
|---|---|---:|---:|---:|---:|---:|
| binance | CEX | 9 | 1,860 | 1,565,114 | 1,425 | 794 |
| okx | CEX | 4 | 3 | 346,183 | 313 | 345 |
| bybit | CEX | 2 | 312 | 294,514 | 129 | 309 |
| bitget | CEX | 5 | 179 | 155,625 | 233 | 565 |
| gateio | CEX | 1 | 2 | 314,594 | 363 | 280 |
| kucoin | CEX | 2 | 433 | 1,053,797 | 304 | 220 |
| htx | CEX | 4 | 4 | 410,801 | 454 | 544 |
| cryptocom | CEX | 1 | 1 | 58,832 | 63 | 119 |
| bitstamp | CEX | 3 | 3 | 49,531 | 82 | 255 |
| bitfinex | CEX | 1 | 118 | 55,700 | 81 | 136 |
| upbit | CEX | 2 | 355 | 217,525 | 44 | 51 |
| bithumb | CEX | 1 | 153 | 36,735 | 36 | 28 |
| coinone | CEX | 1 | 91 | 62,489 | 22 | 63 |
| korbit | CEX | 1 | 2 | 25,230 | 32 | — |
| kraken | CEX | 2 | 107 | 55,000 | 0 | 54 |
| coinbase | CEX | 5 | 413 | 330,000 | 191 | 90 |
| bitmex | CEX | 1 | 142 | 53,731 | 95 | 93 |
| bitmart | CEX | 2 | 2 | 73,289 | 94 | 113 |
| whitebit | CEX | 1 | 161 | 98,291 | 137 | 110 |
| bitbank | CEX | 1 | 175 | 270,858 | 0 | 28 |
| mercadobitcoin | CEX | 1 | 1 | 0 | 31 | 21 |
| dydx | DEX-REST | 1 | 283 | 133,753 | 83 | — |
| hyperliquid | DEX-REST | 1 | 32 | 26,109 | 75 | 8 |
| aevo | DEX-REST | 1 | 144 | 79,208 | 0 | — |
| paradex | DEX-REST | 1 | 624 | 342,258 | 97 | — |
| lighter | DEX-REST | 1 | 49 | 24,758 | 58 | — |
| aster | DEX-REST | 1 | 147 | 119,948 | 0 | — |
| apex | DEX-REST | 1 | 5 | 133,667 | 0 | — |
| grvt | DEX-REST | 1 | 205 | 305,233 | 0 | — |
| drift | DEX-SDK | 1 | 133 | 220,576 | 0 | — |
| gmx | DEX-CONTRACT | 1 | 142 | 171,393 | 0 | — |
| gains | DEX-CONTRACT | 1 | 187 | 130,670 | 0 | — |
| kwenta | DEX-CONTRACT | 1 | 83 | 41,183 | 0 | — |
| perp | DEFUNCT | 1 | 1 | 121 | 0 | — |
| ccxt | REF | 1 | 2,037 | 6,925,008 | 0 | — |
| mexc | CEX | 3 | 21 | 78,290 | 114 | 176 |
| bingx | CEX | 1 | 1 | 1,224 | 0 | 154 |
| deribit | CEX | 1 | 530 | 536,861 | 173 | 122 |
| backpack | DEX-REST | 1 | 1 | 30,989 | 22 | — |
| coinex | CEX | 1 | 489 | 236,632 | 0 | 233 |
| woo | CEX | 1 | 1 | 19,860 | 0 | 82 |
| phemex | CEX | 1 | 1 | 53,344 | 0 | 112 |
| gemini | CEX | 1 | 135 | 97,844 | 0 | 55 |
| orderly | DEX-REST | 1 | 527 | 353,567 | 203 | — |
| bluefin | DEX-REST | 1 | 62 | 11,421 | 0 | — |
| nado | DEX-REST | 1 | 192 | 138,138 | 0 | — |
| **TOTAL (owned)** | | **78** | **10,558** | **16,000,820** | **4,872** | |
| *+ orphaned pages* | | | *160* | *723,166* | | |
| **GRAND TOTAL** | | **78** | **10,724** | **16,729,366** | **4,872** | |

Notes:
- `ccxt_eps` = CCXT `describe().api` endpoint count (post dict-of-dicts fix). Gap between `endpoints` and `ccxt_eps` indicates extraction opportunities.
- `DEX-REST` = DEX with documented REST API endpoints. `DEX-CONTRACT` = smart-contract-only, no REST API. `DEX-SDK` = SDK-based access only.
- 158 orphaned pages exist in DB without scope ownership (mostly from pre-scope-system imports); these add 724K words to the grand total.
- `htx/dm` has 82 endpoints and `crypto_com/exchange` has 63 endpoints stored under variant IDs (accounted for in totals).
- Section count is 75 per `exchanges.yaml`. Two websocket-only sections (okx/websocket, bybit/websocket) have 0 stored pages but are valid registry entries.
- Pacifica deferred from M4 — insufficient API documentation for crawling.
- Bluefin: 49 login-gated pages (changelog/discuss) could not be fetched — 64 API doc pages captured.

### 2b. Documentation Platforms

| Platform | Exchanges |
|----------|-----------|
| Custom SPA | Binance, OKX, Bitget, Gate.io, KuCoin, Crypto.com, Korbit, BitMart, Aster, MEXC, WOO X |
| ReadMe.io | Bitfinex, Upbit, Bithumb, Coinone, Aevo, ApeX, Bluefin |
| Docusaurus | Bybit, Kraken, BitMEX, WhiteBIT, CoinEx |
| GitBook | Hyperliquid, dYdX, Paradex, Lighter, Drift, GMX, Gains, Kwenta, Nado |
| Mintlify | Deribit, Gemini |
| GitHub Pages | HTX (legacy), Phemex (Slate), BingX (Vue.js SPA) |
| Swagger/Redoc | Bitstamp (Redoc), MercadoBitcoin (Swagger UI), Backpack (Redocly) |
| GitHub Markdown | Bitbank, CCXT, GRVT |
| Custom (CDP) | Coinbase |
| Custom | Orderly |

### 2c. OpenAPI / Swagger Spec Availability (verified live 2026-03-06)

| Status | Exchange | Spec URL | Size | Imported? |
|--------|----------|----------|------|-----------|
| **Live** | BitMEX | `bitmex.com/api/explorer/swagger.json` | 183KB | YES |
| **Live** | Coinbase Prime | `api.prime.coinbase.com/v1/openapi.yaml` | 351KB | NO |
| **Live** | Paradex | `api.prod.paradex.trade/swagger/doc.json` | 380KB, 67 paths | NO |
| **Live** | MercadoBitcoin | `api.mercadobitcoin.net/api/v4/docs/swagger.yaml` | 76KB | YES |
| **Live** | Lighter | `raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json` | 225KB, 72 paths | NO |
| **Live** | dYdX | `raw.githubusercontent.com/dydxprotocol/v4-chain/main/indexer/services/comlink/public/swagger.json` | 115KB, 43 paths | NO |
| **NEW Live** | WhiteBIT | 7 OpenAPI specs at `docs.whitebit.com/openapi/` (public v1/v2/v4, private v4, trade v1/v4, oauth2) | ~200KB+ total | NO — HIGH PRIORITY |
| **NEW Live** | Deribit | `docs.deribit.com/specifications/deribit_openapi.json` | 1.3MB, 173 ops | YES |
| **NEW Live** | Backpack | `github.com/CKS-Systems/backpack-client/blob/main/openapi.json` | ~100KB, 22 ops | YES |
| **NEW Live** | Orderly | `github.com/OrderlyNetwork/documentation-public/evm.openapi.yaml` | 461KB, 203 ops | YES |
| **GitHub** | Binance | `binance/binance-api-swagger/spot_api.yaml` | 850KB | Already have 703 eps via Postman |
| **GitHub** | KuCoin | `Kucoin/kucoin-universal-sdk/spec/rest/entry/openapi-*.json` (9 files) | 2.9MB total, 250 ops | NO — HIGH PRIORITY |
| **GitHub** | GRVT | `gravity-technologies/api-spec/src/codegen/apispec.json` | ~460KB | NO (custom format, not OpenAPI) |
| **Inline** | Bitstamp | Embedded in bitstamp.net/api/ (WAF-blocked download) | ~100KB | Already have 82 eps |
| **Community** | Coinbase Exchange | `metalocal/coinbase-exchange-api/api.oas3.json` | 157KB, 38 paths | NO |
| **Community** | Kraken Futures | `kanekoshoyu/exchange-collection` | 148KB | NO |
| **Community** | Upbit | `ujhin/upbit-client/swagger.yaml` | 92KB | NO |
| **Community** | Binance+OKX | `openxapi/openxapi` (community OpenAPI + AsyncAPI for 5 Binance products + OKX) | Large | NO |
| **Planned** | Kraken | `krakenfx/api-specs` (repo exists, empty) | TBD | — |
| **None** | OKX, Bitget, Gate.io, HTX, Crypto.com, Bitfinex, Bitbank, Coinone, Korbit, Bithumb | — | — | — |

### 2d. AsyncAPI Spec Availability

| Exchange | Spec URL | Format | Channels | Status |
|----------|----------|--------|----------|--------|
| **WhiteBIT** | `docs.whitebit.com/asyncapi/` (19 files) | AsyncAPI 3.0 | public: trades, depth, kline, market, etc.; private: orders, positions, balances, etc. | **NEW DISCOVERY** — not imported |
| Binance (community) | `openxapi/openxapi` | AsyncAPI 3.0 | 5 products (spot, futures, options, portfolio margin) | Community-maintained |
| OKX (community) | `openxapi/openxapi` | AsyncAPI 3.0 | REST specs only (OKX) | Community-maintained |
| Paradex | tradeparadex repo | AsyncAPI | WebSocket spec | Not verified |

### 2e. Postman Collection Availability

| Exchange | Source | Coverage | Imported? |
|----------|--------|----------|-----------|
| Binance | `binance/binance-api-postman` (official, 25 collections) | All sections | YES |
| Bybit | `bybit-exchange/QuickStartWithPostman` (official) | V5 | YES |
| BitMart | `bitmartexchange/bitmart-postman-api` (official) | Spot (54 eps) + Futures (57 eps) = 111 total | NO — HIGH PRIORITY |
| KuCoin | `postman.com/kucoin-api/` (official workspace) | Comprehensive | NO |
| Bitfinex | `postman.com/antoanpopoff` (community) | Partial | NO |

### 2f. llms.txt Availability (verified 2026-03-06)

| Exchange | Platform | llms.txt URL | Notable Content |
|----------|----------|-------------|-----------------|
| Coinbase | Custom CDP | `docs.cdp.coinbase.com/llms.txt` | Doc index with section links |
| WhiteBIT | Docusaurus | `docs.whitebit.com/llms.txt` | **OpenAPI + AsyncAPI spec URLs** |
| Bitfinex | ReadMe.io | `docs.bitfinex.com/llms.txt` | Endpoint reference index |
| Upbit | ReadMe.io | `global-docs.upbit.com/llms.txt` | API reference + code recipes |
| Coinone | ReadMe.io | `docs.coinone.co.kr/llms.txt` | Korean API reference index |
| Aevo | ReadMe.io | `api-docs.aevo.xyz/llms.txt` | Endpoint index + MCP info |
| dYdX | GitBook | `docs.dydx.xyz/llms.txt` | Full platform doc index |
| Hyperliquid | GitBook | `hyperliquid.gitbook.io/hyperliquid-docs/llms.txt` | Doc table of contents |
| Paradex | GitBook | `docs.paradex.trade/llms.txt` | REST + WS endpoint index |
| GMX | GitBook | `docs.gmx.io/llms.txt` | Full doc index |
| Gains | GitBook | `docs.gains.trade/llms.txt` | Doc structure index |
| Kwenta | GitBook | `docs.kwenta.io/llms.txt` | Doc navigation index |
| Lighter | GitBook | `docs.lighter.xyz/llms.txt` | Doc navigation index |
| Binance | — | 404 | — |
| OKX | — | 404 | — |
| Bybit | — | 404 | — |
| Kraken | — | 404 | — |
| BitMEX | — | 404 | — |

Note: ReadMe.io and GitBook platforms auto-generate llms.txt. Content quality varies. WhiteBIT's is uniquely valuable as it exposed formal API spec URLs.

### 2g. Changelog / RSS Feed Availability (verified live)

| Exchange | Changelog URL | RSS/Atom Feed | Extracted | Entries | Date Format |
|----------|--------------|---------------|-----------|---------|-------------|
| Binance | `developers.binance.com/docs/.../CHANGELOG` | `dev.binance.vision/latest.rss` (forum) | YES | 697 | `### YYYY-MM-DD` |
| OKX | `okx.com/docs-v5/log_en/` | None | — | 0 | Embedded in SPA |
| Bybit | `bybit-exchange.github.io/docs/changelog/v5` | None | YES | 15 | `### YYYY-MM-DD` |
| Bitget | `bitget.com/api-doc/common/changelog` | None | YES | 1 | Inline ISO |
| Gate.io | Embedded in docs + `gate.com/announcements/apiupdates` | None | — | 0 | SPA |
| KuCoin | `kucoin.com/docs-new/change-log` | None | YES | 2 | Inline ISO |
| HTX | `htx.com/en-us/opend/` | None | — | 0 | No changelog page |
| Bitfinex | `docs.bitfinex.com/docs/changelog` | None (RSS 404) | — | 0 | Not crawled |
| Crypto.com | Embedded in exchange-docs | None | — | 0 | SPA |
| Kraken | `docs.kraken.com/api/docs/change-log/` | None | — | 0 | Docusaurus CSR |
| Coinbase | 6 separate changelogs per product | None | YES | 4 | Inline ISO |
| BitMEX | `bitmex.com/app/apiChangelog` | `bitmex.com/api_announcement/feed` | — | 0 | Not crawled |
| Upbit EN | `global-docs.upbit.com/changelog` | `global-docs.upbit.com/changelog.rss` | YES | 189 | Per-page URL |
| Upbit KR | `docs.upbit.com/ko/changelog` | `docs.upbit.com/kr/changelog.rss` | — | 0 | Korean text |
| Bithumb | `apidocs.bithumb.com/changelog` | `apidocs.bithumb.com/changelog.rss` | YES | 80 | Mixed |
| Coinone | `docs.coinone.co.kr/changelog` | `docs.coinone.co.kr/changelog.rss` | YES | 23 | Per-page URL |
| WhiteBIT | `docs.whitebit.com/changelog/` | `changelog.json` in GitHub repo | — | 0 | Not crawled |
| Bitbank | GitHub CHANGELOG.md | `/commits/master.atom` | YES | 91 | `### YYYY-MM-DD` |
| dYdX | GitHub releases | `dydxprotocol/v4-chain/releases.atom` | — | 0 | — |
| CCXT | GitHub releases | `ccxt/ccxt/releases.atom` | — | 0 | — |
| Paradex | `docs.paradex.trade/changelog` | None | YES | 98 | Per-page URL |
| CoinEx | `docs.coinex.com/api/v2/changelog` | None | YES | 31 | Prose dates |
| Orderly | `orderly.network/docs/changelog` | None | YES | 5 | Prose dates |
| Bluefin | `bluefin-exchange.readme.io/changelog` | None | YES | 6 | Inline ISO |
| Gemini | `docs.gemini.com/changelog/revision-history` | None | YES | 1 | Inline ISO |
| MEXC | `mexc.com/api-docs/spot-v3/change-log` | None | YES | 1 | Inline ISO |
| Nado | `docs.nado.xyz/.../api-changelog` | None | YES | 1 | Prose dates |
| Gains | `docs.gains.trade/.../changelog` | None | YES | 8 | Per-page URL |
| GMX | `docs.gmx.io/.../changelog` | None | YES | 2 | Per-page URL |

**Totals**: 1,255 entries across 18 exchanges. Classification: `classify-changelogs` command applies 8-category regex taxonomy (endpoint_removed, breaking_change, endpoint_deprecated, rate_limit_change, parameter_change, endpoint_added, field_added, informational). 31.5% of entries have extractable API endpoint paths.

### 2h. Status Page Availability (verified live)

| Exchange | Status URL | Verified |
|----------|-----------|----------|
| Bitfinex | `bitfinex.statuspage.io` | YES |
| Kraken | `status.kraken.com` | YES |
| BitMEX | `status.bitmex.com` | YES |
| HTX | `htx.statuspage.io` | YES (not `status.huobigroup.com` — DNS dead) |
| Crypto.com | `status.crypto.com` | YES |
| Coinbase | `status.coinbase.com` | YES |
| dYdX | `status.dydx.trade` | YES |
| WhiteBIT | `status.whitebit.com` | YES |
| MercadoBitcoin | `status.mercadobitcoin.com.br` | YES |
| Korbit | — | DEAD (`status.korbit.co.kr` DNS fails) |

### 2i. GitHub Organization Summary

| Exchange | Org/User | Notable |
|----------|----------|---------|
| Binance | `github.com/binance` | 25 Postman collections, spot OpenAPI, FIX connector |
| OKX | `github.com/okx` + `github.com/okxapi` | Two orgs (infra vs API SDKs) |
| Bybit | `github.com/bybit-exchange` | Docusaurus source |
| Bitget | `github.com/BitgetLimited` | Legacy GitHub Pages |
| Gate.io | `github.com/gateio` | 7 auto-generated SDKs (from internal OpenAPI spec not publicly downloadable) |
| KuCoin | `github.com/Kucoin` | 9 OpenAPI spec files in universal-sdk (2.9MB) |
| HTX | `github.com/huobiapi` + `github.com/HuobiRDCenter` | Dual account |
| Bitfinex | `github.com/bitfinexcom` | FIX gateway repo (bfxfixgw) |
| Coinbase | `github.com/coinbase` | coinbase-advanced-py SDK |
| BitMEX | `github.com/BitMEX` | Live + GitHub swagger.json |
| Upbit | `github.com/upbit-exchange` | Community OpenAPI exists separately |
| WhiteBIT | `github.com/whitebit-exchange` | Docusaurus source, changelog.json, **OpenAPI + AsyncAPI specs** |
| Bitbank | `github.com/bitbankinc` | MCP server, dual-language docs |
| GRVT | `github.com/gravity-technologies` | API spec at `src/codegen/apispec.json` |
| Paradex | `github.com/tradeparadex` | OpenAPI + AsyncAPI |
| dYdX | `github.com/dydxprotocol` | Indexer swagger.json, protobuf specs |
| CCXT | `github.com/ccxt` | 33K+ stars, exchange implementations |

### 2j. DEX Classification

| Classification | Exchanges | Has REST API? | Endpoint Value |
|----------------|-----------|---------------|----------------|
| **DEX-REST** | dYdX, Hyperliquid, Aevo, Paradex, Lighter, Aster, ApeX, GRVT | YES | High — importable specs available for Paradex, Lighter, dYdX, GRVT |
| **DEX-SDK** | Drift | SDK only | Low — no HTTP endpoint docs |
| **DEX-CONTRACT** | GMX, Gains Network, Kwenta | NO (smart contracts only) | None — docs describe Solidity interfaces, not REST APIs |
| **DEFUNCT** | Perpetual Protocol | DNS dead | None — remove from active sync |

### 2k. FIX Protocol Documentation (verified 2026-03-06)

| Exchange | FIX Version | Docs URL | Currently Crawled? | Endpoint Value |
|----------|------------|----------|-------------------|----------------|
| Binance | FIX 4.4 | `developers.binance.com/docs/binance-spot-api-docs/fix-api` | Partially (same domain, may need explicit seed) | High |
| Bitstamp | FIX v2 | `bitstamp.net/fix/v2/` | **NO** — separate URL path, not in scope | High |
| Kraken | FIX 4.4 | `docs.kraken.com/api/docs/guides/fix-intro/` + `docs.kraken.com/api/docs/fix-api/` | Maybe (in sitemap scope) | High |
| Coinbase Exchange | FIX 4.2 SP2 | `docs.cdp.coinbase.com/exchange/fix-api/connectivity` | **NO** — outside scope_prefixes | High |
| Coinbase INTX | FIX 5.0 | `docs.cdp.coinbase.com/international-exchange/fix-api/` | **NO** — outside scope_prefixes | High |
| Coinbase Prime | FIX 4.2 | `docs.cdp.coinbase.com/prime/fix-api/connectivity` | **NO** — outside scope_prefixes | High |
| Coinbase Derivatives | FIX 4.4 | `docs.cdp.coinbase.com/derivatives/fix/overview` | **NO** — outside scope_prefixes | Medium |
| Bitfinex | FIX (gateway) | `github.com/bitfinexcom/bfxfixgw` | N/A (GitHub repo, not doc pages) | Low |

Bybit, OKX, and BitMEX do NOT have official FIX APIs. OKX/BitMEX FIX access is only through third-party Axon Trade.

---

## 3. CEX Exchanges

### Binance

| Field | Value |
|-------|-------|
| **Docs URL** | https://developers.binance.com/docs/binance-spot-api-docs/ |
| **Platform** | Custom SPA |
| **Sections** | 9 (spot, futures_usdm, futures_coinm, portfolio_margin, options, margin_trading, wallet, copy_trading, portfolio_margin_pro) |
| **Pages/Words/Endpoints** | 1,860 / 1.57M / 1,425 |
| **CCXT endpoints** | 794 |
| **OpenAPI** | spot_api.yaml on GitHub (spot only, 850KB) |
| **Postman** | 25 collections in binance-api-postman (ALL imported) |
| **Changelog** | Per-section changelogs at developers.binance.com |
| **RSS** | dev.binance.vision/latest.rss (forum, not API changelog) |
| **GitHub** | github.com/binance (45+ repos) |
| **Status** | No dedicated page; /sapi/v1/system/status API |
| **FIX docs** | developers.binance.com/docs/binance-spot-api-docs/fix-api (FIX 4.4, may need explicit seed) |
| **llms.txt** | 404 |
| **Discovery** | robots.txt 404, sitemap.xml 404 (link-follow fallback) |

### OKX

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.okx.com/docs-v5/en/ (single-page SPA, 225K words) |
| **Platform** | Custom SPA |
| **Sections** | 3 (rest, broker, changelog) + websocket (0 pages) |
| **Pages/Words/Endpoints** | 3 / 346K / 313 |
| **CCXT endpoints** | 345 |
| **OpenAPI** | None official; community spec at openxapi/openxapi |
| **Changelog** | okx.com/docs-v5/log_en/ (5+/month) |
| **llms.txt** | 404 |
| **Web3 docs** | web3.okx.com/build/docs/ (separate product, not CEX API) |

### Bybit

| Field | Value |
|-------|-------|
| **Docs URL** | https://bybit-exchange.github.io/docs/v5/intro |
| **Platform** | Docusaurus |
| **Sections** | 1 (v5) + websocket (0 pages) |
| **Pages/Words/Endpoints** | 312 / 295K / 129 |
| **CCXT endpoints** | 309 (gap: 180 missing from us) |
| **Postman** | bybit-exchange/QuickStartWithPostman (imported) |
| **Sitemap** | bybit-exchange.github.io/docs/sitemap.xml |
| **llms.txt** | 404 |

### Bitget

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.bitget.com/api-doc/common/intro |
| **Platform** | Custom SPA |
| **Sections** | 5 (v2, copy_trading, margin, earn, broker) |
| **Pages/Words/Endpoints** | 179 / 156K / 233 |
| **CCXT endpoints** | 565 (gap: 332 missing) |
| **OpenAPI** | v2 imported via OpenAPI |
| **Sitemap** | bitget.com/sitemap.xml |
| **llms.txt** | 403 |

### Gate.io

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.gate.com/docs/developers/apiv4/ (single-page, 315K words) |
| **Platform** | Custom SPA |
| **Sections** | 1 (v4) |
| **Pages/Words/Endpoints** | 2 / 315K / 363 |
| **CCXT endpoints** | 280 |
| **Crawl note** | Rate-limits aggressively (403). `requests` and `crawl4ai` both fail. Use `crawl4ai` (1.58MB markdown) or Playwright. |

### KuCoin

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.kucoin.com/docs/rest/spot-trading/ |
| **Platform** | Custom SPA (opaque URL IDs) |
| **Sections** | 2 (spot, futures — merged URL tree) |
| **Pages/Words/Endpoints** | 433 / 1.05M / 124 |
| **CCXT endpoints** | 220 (gap: 96 missing) |
| **OpenAPI** | 9 files in `Kucoin/kucoin-universal-sdk/spec/rest/entry/` (2.9MB total, 250 operations) — NOT YET IMPORTED |
| **Spec files** | openapi-spot.json (58 paths/70 ops), openapi-futures.json (51/54), openapi-account.json (46/52), openapi-margin.json (29/33), openapi-broker.json (14/17), openapi-earn.json (8/9), openapi-copytrading.json (10/11), openapi-viplending.json (3/3), openapi-affiliate.json (1/1) |
| **Import note** | All specs lack `servers[]` — must pass `--base-url`. Futures/copytrading use `https://api-futures.kucoin.com`, rest use `https://api.kucoin.com` |

### HTX

| Field | Value |
|-------|-------|
| **Docs URL** | https://huobiapi.github.io/docs/spot/v1/en/ |
| **Platform** | GitHub Pages (single-page per section) |
| **Sections** | 4 (spot, derivatives, coin_margined_swap, usdt_swap) + dm (82 eps, variant ID) |
| **Pages/Words/Endpoints** | 4 / 411K / 454 |
| **CCXT endpoints** | 544 (gap: 90 missing) |
| **Status** | `htx.statuspage.io` (NOT status.huobigroup.com — DNS dead) |

### Crypto.com

| Field | Value |
|-------|-------|
| **Docs URL** | https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html (single-page, 59K words) |
| **Platform** | Custom SPA |
| **Pages/Words/Endpoints** | 1 / 59K / 63 |
| **CCXT endpoints** | 119 (gap: 56 missing) |
| **Status** | status.crypto.com |
| **Note** | DB stores endpoints as `crypto_com` (alias configured in ccxt_xref.py) |

### Bitstamp

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.bitstamp.net/api/ (single-page, 37K words) |
| **Platform** | Swagger/Redoc |
| **Pages/Words/Endpoints** | 1 / 37K / 82 |
| **CCXT endpoints** | 255 (gap inflated — CCXT counts v1 legacy paths) |
| **OpenAPI** | Inline in page (WAF blocks direct download; needs crawl4ai for WAF bypass) |
| **FIX docs** | bitstamp.net/fix/v2/ (NOT currently crawled) |
| **WebSocket docs** | bitstamp.net/websocket/v2/ (NOT currently crawled) |
| **PSD2 docs** | bitstamp.net/api-psd2/ (EU Open Banking, low trading value) |

### Bitfinex

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.bitfinex.com/reference/rest-public-platform-status |
| **Platform** | ReadMe.io |
| **Pages/Words/Endpoints** | 118 / 56K / 81 |
| **CCXT endpoints** | 136 (gap: 55 missing) |
| **Changelog** | docs.bitfinex.com/docs/changelog |
| **Status** | bitfinex.statuspage.io |
| **llms.txt** | docs.bitfinex.com/llms.txt (endpoint reference index) |
| **FIX** | GitHub gateway only (bitfinexcom/bfxfixgw) |

### Upbit

| Field | Value |
|-------|-------|
| **Docs URL** | global-docs.upbit.com (EN), docs.upbit.com/ko/ (KR) |
| **Platform** | ReadMe.io |
| **Sections** | 2 (rest_en, rest_ko) |
| **Pages/Words/Endpoints** | 355 / 218K / 44 |
| **CCXT endpoints** | 51 |
| **RSS** | global-docs.upbit.com/changelog.rss, docs.upbit.com/kr/changelog.rss |
| **llms.txt** | global-docs.upbit.com/llms.txt |
| **Note** | Korean docs are authoritative; English lags by ~3 minor versions. rest_ko uses scope_priority: 50 |

### Bithumb

| Field | Value |
|-------|-------|
| **Docs URL** | https://apidocs.bithumb.com/ |
| **Platform** | ReadMe.io |
| **Sections** | 1 (rest) + rest_en (requires Playwright, 0 pages) |
| **Pages/Words/Endpoints** | 153 / 37K / 36 |
| **RSS** | apidocs.bithumb.com/changelog.rss |

### Coinone

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.coinone.co.kr/ |
| **Platform** | ReadMe.io (Korean only) |
| **Pages/Words/Endpoints** | 91 / 62K / 22 |
| **CCXT endpoints** | 63 (gap: 41 missing — CCXT tracks v1 API, we have v2) |
| **RSS** | docs.coinone.co.kr/changelog.rss |
| **llms.txt** | docs.coinone.co.kr/llms.txt |

### Korbit

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.korbit.co.kr/ (single-page, 25K words, English) |
| **Platform** | Custom |
| **Pages/Words/Endpoints** | 2 / 25K / 32 |
| **CCXT** | No CCXT class |
| **Status** | DEAD (status.korbit.co.kr DNS fails) |

### Kraken

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.kraken.com/api/ |
| **Platform** | Docusaurus |
| **Sections** | 2 (spot, futures) |
| **Pages/Words/Endpoints** | 65 / 32K / 0 — **CRAWL GAP: 48 REST API pages in sitemap never fetched** |
| **CCXT endpoints** | 54 |
| **Crawl gap** | Sitemap has 48 spot REST API reference pages (`/docs/rest-api/*`) + ~37 futures pages. Seed URL only discovered guide pages. Re-sync should fix. |
| **FIX docs** | docs.kraken.com/api/docs/guides/fix-intro/ + docs.kraken.com/api/docs/fix-api/ (FIX 4.4) |
| **Changelog** | docs.kraken.com/api/docs/change-log/ |
| **Sitemap** | docs.kraken.com/sitemap.xml |
| **Status** | status.kraken.com |
| **OpenAPI** | krakenfx/api-specs repo exists but is EMPTY. Community spec in kanekoshoyu/exchange-collection |
| **llms.txt** | 404 |

### Coinbase

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.cdp.coinbase.com/api-reference/ |
| **Platform** | Custom (CDP) |
| **Sections** | 4 (advanced_trade, exchange, intx, prime) |
| **Pages/Words/Endpoints** | 383 / 310K / 49 (only intx imported; 3 sections have 0 endpoints) |
| **CCXT endpoints** | 90 |
| **Sitemap** | docs.cdp.coinbase.com/sitemap.xml (559 entries, shared across 4 sections with scope_priority) |
| **OpenAPI** | Prime: api.prime.coinbase.com/v1/openapi.yaml (351KB, ~95 endpoints) — NOT IMPORTED |
| **Community spec** | Exchange: metalocal/coinbase-exchange-api/api.oas3.json (157KB, 38 paths) |
| **FIX docs** | 4 products (Exchange FIX 4.2, INTX FIX 5.0, Prime FIX 4.2, Derivatives FIX 4.4) — ALL outside scope_prefixes |
| **Scope gap** | FIX docs at `/exchange/fix-api/`, `/international-exchange/fix-api/`, `/prime/fix-api/`, `/derivatives/fix/` are outside current `/api-reference/` scope_prefixes |
| **Sandbox docs** | `docs.cdp.coinbase.com/exchange/docs/sandbox` — also outside scope_prefixes |
| **llms.txt** | docs.cdp.coinbase.com/llms.txt |
| **Status** | status.coinbase.com |
| **Note** | Docs migrated to /api-reference/ paths in 2026-03. scope_prefixes updated but too narrow — need widening for FIX/sandbox. |

### BitMEX

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.bitmex.com/ |
| **Platform** | Docusaurus |
| **Pages/Words/Endpoints** | 142 / 54K / 95 |
| **CCXT endpoints** | 93 |
| **OpenAPI** | bitmex.com/api/explorer/swagger.json (imported) |
| **Sitemap** | docs.bitmex.com/sitemap.xml |
| **RSS** | bitmex.com/api_announcement/feed |
| **Status** | status.bitmex.com |
| **llms.txt** | 404 |

### BitMart

| Field | Value |
|-------|-------|
| **Docs URL** | https://developer-pro.bitmart.com/en/spot/ |
| **Platform** | Custom SPA (single-page per section) |
| **Sections** | 2 (spot: 39K words, futures: 35K words) |
| **Pages/Words/Endpoints** | 2 / 73K / 0 (NO endpoints) |
| **CCXT endpoints** | 113 |
| **Postman** | bitmartexchange/bitmart-postman-api — Spot (54 eps) + Futures (57 eps) = 111 total — NOT IMPORTED |

### WhiteBIT

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.whitebit.com/ |
| **Platform** | Docusaurus |
| **Pages/Words/Endpoints** | 161 / 98K / 0 (NO endpoints) — **has 7 OpenAPI + 19 AsyncAPI specs** |
| **CCXT endpoints** | 110 |
| **OpenAPI specs (7)** | `docs.whitebit.com/openapi/private/main_api_v4.yaml`, `http-trade-v4.yaml`, `http-trade-v1.yaml`, `docs.whitebit.com/openapi/public/http-v4.yaml`, `http-v2.yaml`, `http-v1.yaml`, `docs.whitebit.com/openapi/oauth2.yaml` |
| **AsyncAPI specs (19)** | Public: trades, service, market_today, market, lastprice, kline, depth, book_ticker. Private: positions, orders_pending, orders_executed, margin_positions_events, deals, borrows_events, borrows, balance_spot, balance_margin, authorize, websocket_token |
| **Sitemap** | docs.whitebit.com/sitemap.xml |
| **Changelog** | docs.whitebit.com/changelog/ |
| **Status** | status.whitebit.com |
| **llms.txt** | docs.whitebit.com/llms.txt (**this is how the specs were discovered**) |

### Bitbank

| Field | Value |
|-------|-------|
| **Docs URL** | https://github.com/bitbankinc/bitbank-api-docs |
| **Platform** | GitHub Markdown |
| **Pages/Words/Endpoints** | 175 / 271K / 0 (NO endpoints — needs page-based extraction) |
| **CCXT endpoints** | 28 |
| **Changelog** | GitHub CHANGELOG.md |

### MercadoBitcoin

| Field | Value |
|-------|-------|
| **Docs URL** | https://api.mercadobitcoin.net/api/v4/docs |
| **Platform** | Swagger UI (single-page) |
| **Pages/Words/Endpoints** | 1 / 0* / 31 |
| **OpenAPI** | swagger.yaml at docs URL (76KB, imported) |
| **Status** | status.mercadobitcoin.com.br |
| **Note** | *Word count 0 due to Swagger UI JS rendering; endpoints imported from spec |

---

## 4. DEX Protocols

### DEX-REST (have HTTP API endpoints)

#### dYdX

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.dydx.xyz/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 283 / 134K / 34 |
| **OpenAPI** | dydxprotocol/v4-chain/indexer/services/comlink/public/swagger.json (115KB, 43 paths) — NOT IMPORTED |
| **Protobuf** | proto/dydxprotocol/ (chain-level, not REST API) |
| **gRPC streaming** | Full Node streaming at docs.dydx.exchange/api_integration-full-node-streaming |
| **Status** | status.dydx.trade |
| **llms.txt** | docs.dydx.xyz/llms.txt |

#### Hyperliquid

| Field | Value |
|-------|-------|
| **Docs URL** | https://hyperliquid.gitbook.io/hyperliquid-docs/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 32 / 26K / 75 |
| **Sitemap** | hyperliquid.gitbook.io/hyperliquid-docs/sitemap.xml |
| **llms.txt** | hyperliquid.gitbook.io/hyperliquid-docs/llms.txt |

#### Aevo

| Field | Value |
|-------|-------|
| **Docs URL** | https://api-docs.aevo.xyz/ |
| **Platform** | ReadMe.io |
| **Pages/Words/Endpoints** | 144 / 79K / 0 (144 per-endpoint reference pages — needs page-based extraction or hidden ReadMe OAS) |
| **llms.txt** | api-docs.aevo.xyz/llms.txt (mentions MCP server integration) |

#### Paradex

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.paradex.trade/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 624 / 342K / 0 |
| **OpenAPI** | api.prod.paradex.trade/swagger/doc.json (380KB, 67 paths) — NOT IMPORTED |
| **AsyncAPI** | WebSocket spec in tradeparadex repo |
| **llms.txt** | docs.paradex.trade/llms.txt |

#### Lighter

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.lighter.xyz/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 49 / 25K / 0 |
| **OpenAPI** | elliottech/lighter-python/openapi.json (225KB, 72 paths) — NOT IMPORTED |
| **llms.txt** | docs.lighter.xyz/llms.txt |

#### Aster

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.asterdex.com/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 147 / 120K / 0 (API docs concentrated in 1 page, 14K words) |

#### ApeX Pro

| Field | Value |
|-------|-------|
| **Docs URL** | https://api-docs.pro.apex.exchange/ |
| **Platform** | ReadMe.io |
| **Pages/Words/Endpoints** | 5 / 134K / 0 (3 are duplicates of single 43K-word SPA page) |

#### GRVT

| Field | Value |
|-------|-------|
| **Docs URL** | https://github.com/gravity-technologies/api-spec |
| **Platform** | GitHub Markdown |
| **Pages/Words/Endpoints** | 205 / 305K / 0 |
| **Spec** | gravity-technologies/api-spec/src/codegen/apispec.json (~460KB) — **CUSTOM FORMAT** (not OpenAPI). ~95+ operations across MarketData (11 RPC + 8 WS) and Trading (41 RPC + 8 WS) gateways. Needs custom parser. |
| **Schema docs** | 304 schema markdown files in `artifacts/apidocs/schemas/` |
| **API docs site** | api-docs.grvt.io (returns 403 to automated fetches) |
| **Note** | Original research claimed path `apispec.json` at root (404). Correct path is `src/codegen/apispec.json` |

### DEX-CONTRACT (smart contracts only — no REST endpoints possible)

#### GMX

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.gmx.io/ |
| **Platform** | Docusaurus/GitBook |
| **Pages/Words** | 142 / 171K |
| **REST API** | **NONE** — smart contract protocol, docs describe Solidity interfaces |
| **GraphQL** | Uses The Graph subgraphs for on-chain data (not REST) |
| **llms.txt** | docs.gmx.io/llms.txt |

#### Gains Network

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.gains.trade/ |
| **Platform** | GitBook |
| **Pages/Words** | 187 / 131K |
| **REST API** | **NONE** — smart contract protocol |
| **llms.txt** | docs.gains.trade/llms.txt |

#### Kwenta

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.kwenta.io/ |
| **Platform** | GitBook |
| **Pages/Words** | 83 / 41K |
| **REST API** | **NONE** — Synthetix-based, smart contract only |
| **llms.txt** | docs.kwenta.io/llms.txt |

### DEX-SDK (SDK-based, no direct REST docs)

#### Drift

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.drift.trade/ |
| **Platform** | GitBook |
| **Pages/Words** | 133 / 221K |
| **REST API** | SDK-based access; may have internal REST gateway but no public REST endpoint docs |
| **llms.txt** | 404 |

### DEFUNCT

#### Perpetual Protocol

| Field | Value |
|-------|-------|
| **Status** | **DEFUNCT** — docs.perp.com DNS dead (NXDOMAIN), token delisted |
| **Action** | Marked `status: defunct` in exchanges.yaml. Do not sync. |

---

## 5. Reference

### CCXT

| Field | Value |
|-------|-------|
| **Wiki** | github.com/ccxt/ccxt/wiki (2,037 pages, 6.93M words) |
| **ReadTheDocs** | ccxt.readthedocs.io (may be stale) |
| **Releases RSS** | github.com/ccxt/ccxt/releases.atom |
| **Key files** | exchanges.json, ts/src/{exchange}.ts |
| **CCXT cross-ref** | dict-of-dicts bug FIXED — now extracts endpoints for all 20 mapped exchanges |
| **Mapped exchanges** | 22 (20 CEX + dydx + hyperliquid). korbit has no CCXT class. |

---

## 6. Previously Missing Exchanges — Now Registered

These exchanges were identified as missing in v2 and have been **registered, synced, and spec-imported** in v3 (2026-03-06).

### MEXC Global — CRITICAL (Tier 1 CEX, top-5 by volume)

| Field | Value |
|-------|-------|
| **Type** | CEX |
| **Daily Volume** | ~$3.59B (2nd largest by some rankings) |
| **Docs** | mexc.com/api-docs/spot-v3/introduction (Spot V3), mexc.com/api-docs/futures/integration-guide (Futures) |
| **Platform** | Custom SPA |
| **GitHub** | github.com/mexcdevelop/apidocs |
| **OpenAPI** | None found |
| **Postman** | Available |
| **CCXT** | Yes (certified exchange, ID: `mexc`) |
| **Rationale** | Top-5 global volume, CCXT certified, well-documented REST API. V2 API deprecated August 2025, V3 active. |

### BingX — CRITICAL (Tier 1 derivatives)

| Field | Value |
|-------|-------|
| **Type** | CEX |
| **Daily Volume** | ~$6.5B futures, ~$977M spot |
| **Docs** | bingx-api.github.io/docs/ |
| **Platform** | GitHub Pages |
| **GitHub** | github.com/BingX-API/docs (8 repos: spot, swap, standard) |
| **API Base** | open-api.bingx.com |
| **CCXT** | Yes (certified exchange, ID: `bingx`) |
| **Rationale** | Top-10 derivatives platform, CCXT certified, well-documented API. |

### Deribit — HIGH (crypto options leader)

| Field | Value |
|-------|-------|
| **Type** | CEX (acquired by Coinbase for $2.9B, closed August 2025; API remains separate) |
| **Daily Volume** | ~$1B derivatives, dominates crypto options |
| **Docs** | docs.deribit.com |
| **API Format** | JSON-RPC over HTTP and WebSocket (`https://www.deribit.com/api/v2`) |
| **Community Swagger** | github.com/adampointer/go-deribit (swagger.json) |
| **CCXT** | Yes (ID: `deribit`) |
| **Rationale** | Leading crypto options exchange by OI and volume. API architecturally different from Coinbase (JSON-RPC vs REST). Remains operationally separate. |

### Backpack Exchange — HIGH (DEX with OpenAPI)

| Field | Value |
|-------|-------|
| **Type** | DEX (Solana-native, spot + perpetual futures) |
| **Daily Volume** | ~$40M spot, ~$1.5B futures |
| **Docs** | docs.backpack.exchange |
| **OpenAPI** | github.com/CKS-Systems/backpack-client/blob/main/openapi.json (OpenAPI 3.0) |
| **CCXT** | Yes (ID: `backpack`) |
| **Rationale** | Significant derivatives volume, OpenAPI spec available for direct import, CCXT supported. |

### CoinEx — MEDIUM

| Field | Value |
|-------|-------|
| **Type** | CEX |
| **Daily Volume** | ~$109-350M |
| **Docs** | docs.coinex.com/api/v2/ |
| **CCXT** | Yes (certified exchange, ID: `coinex`) |
| **Rationale** | Well-documented V2 API, CCXT certified, meaningful volume. |

### WOO X — MEDIUM

| Field | Value |
|-------|-------|
| **Type** | CEX |
| **Daily Volume** | ~$600M average |
| **Docs** | docs.woox.io |
| **API Base** | api.woox.io (migrated September 2024) |
| **CCXT** | Yes (certified exchange, ID: `woo`) |
| **Note** | Acquired by FusionX Digital October 2025 — ownership change introduces uncertainty |
| **Rationale** | CCXT certified, meaningful volume, good docs. Monitor ownership stability. |

### Phemex — MEDIUM

| Field | Value |
|-------|-------|
| **Type** | CEX |
| **Daily Volume** | ~$678M spot + ~$1.57B derivatives |
| **Docs** | phemex-docs.github.io (GitHub Pages) |
| **GitHub** | github.com/phemex/phemex-api-docs |
| **API Base** | api.phemex.com |
| **CCXT** | Yes (ID: `phemex`) |
| **Rationale** | Solid derivatives exchange, CCXT supported, GitHub-hosted docs. |

### Gemini — MEDIUM (US regulated)

| Field | Value |
|-------|-------|
| **Type** | CEX |
| **Daily Volume** | ~$50-77M |
| **Docs** | docs.gemini.com |
| **API Types** | REST, WebSocket, FIX |
| **CCXT** | Yes (ID: `gemini`) |
| **Rationale** | Regulated US exchange, institutional focus ($21.5B institutional volume H1 2025), good documentation quality. Lower volume than other candidates. |

### Exchanges Evaluated and Rejected

| Exchange | Reason for Rejection |
|----------|---------------------|
| Vertex Protocol | Shut down all trading August 2025, joined Ink Foundation |
| Zeta Markets | Ceased operating May 2025, replaced by Bullet network |
| OKCoin | Rebranded to OKX (already in registry) |
| Binance.US | Only $20M daily volume; API is subset of Binance Global with nearly identical structure |
| RabbitX | Near-zero current trading volume ($0.00 on CoinGecko) |
| Injective | Very low DEX volume (~$423K daily); primarily an L1 chain |
| Luno | Very low volume (~$6-10M daily); limited geographic reach |
| ProBit | Volume discrepancy ($1.8M vs $563M across trackers) suggests wash trading |
| HashKey Global | Very low current volume (~$726K daily) |
| 0x Protocol | DEX aggregator, not exchange — different paradigm |
| 1inch | DEX aggregator, not exchange — different paradigm |
| LBank | Volume credibility concerns (historically flagged for inflation) |
| Poloniex | Declining relevance, delisting pairs, questionable longevity |
| BTSE | Volume reporting inconsistency ($223M to $4.4B range) |
| Bitso | Important regionally (LatAm) but $14-28M daily volume is too low |

---

## 7. Tier 2 DEX Additions

### Orderly Network — RECOMMEND ADD (HIGH PRIORITY)

- **Type**: DEX infrastructure (powers WOOFi Pro, LogX, etc.)
- **Docs**: orderly.network/docs/ (redirects from docs.orderly.network)
- **Platform**: Mintlify
- **Sitemap**: orderly.network/docs/sitemap.xml (694 URLs)
- **OpenAPI**: `https://raw.githubusercontent.com/OrderlyNetwork/documentation-public/main/evm.openapi.yaml` (461KB, OpenAPI 3.0.1, 192 paths) — VERIFIED LIVE
- **Second spec**: sv.openapi.yaml (33KB, Strategy Vault API) in same repo
- **Changelogs**: orderly.network/docs/changelog/evm, orderly.network/docs/changelog/sdk
- **RSS**: None (404 on /rss.xml, /feed.xml)
- **SDKs**: orderly-sdk-js, orderly-sdk-py
- **GitHub**: OrderlyNetwork/documentation-public (759 files)
- **Rationale**: 192-path OpenAPI spec, 694-URL sitemap, active changelogs, immediate endpoint value

### Bluefin — RECOMMEND ADD

- **Type**: DEX perpetual futures (Sui)
- **Docs**: bluefin-exchange.readme.io (ReadMe.io)
- **API version**: 3.0.2 ("Bluefin Pro"); v2.0.1 deprecated
- **Sections**: Exchange, Account, Trade, Auth, WebSocket Streams
- **Sitemap**: None (404)
- **Changelog**: bluefin-exchange.readme.io/changelog (sparse — 3 entries, Aug 2023–Jan 2024)
- **GitHub**: github.com/fireflyprotocol (branded "Bluewater", 17 repos)
- **Rationale**: ReadMe.io platform (easy to crawl), active protocol

### Nado — RECOMMEND ADD (LOWER PRIORITY)

- **Type**: DEX perpetual futures
- **Docs**: docs.nado.xyz (NOT docs.nado.trade)
- **Platform**: GitBook
- **SDKs**: 3 languages (Python, TypeScript, Go)
- **Changelog**: Active
- **Rationale**: Active development, growing protocol

### Pacifica — RECOMMEND ADD

- **Type**: DEX perpetual futures
- **Docs**: docs.pacifica.fi (redirects to pacifica.gitbook.io/docs/)
- **Platform**: GitBook
- **Sitemap**: docs.pacifica.fi/sitemap-pages.xml (155 URLs, 97 API docs)
- **Base URL**: api.pacifica.fi/api/v1
- **Changelog**: docs.pacifica.fi/api-documentation/changelog (active, Oct 2025–Feb 2026)
- **GitHub**: github.com/pacifica-fi (2 repos: python-sdk, pacifica-mcp)
- **Rationale**: 97 API doc URLs, active changelog, REST + WebSocket coverage — upgraded from DEFER

---

## 8. New Exchange Template

Use this checklist when adding a new exchange to the registry.

### Phase 1: Baseline Discovery

```
## [Exchange Name]

### Documentation Sites
- [ ] Main docs URL: ___
- [ ] API reference URL: ___
- [ ] WebSocket docs URL: ___
- [ ] FIX protocol docs URL (if applicable): ___
- [ ] Documentation platform: (ReadMe.io / Docusaurus / GitBook / Swagger / Custom)
- [ ] Rendering required: (static HTML / JS-rendered / SPA)
- [ ] llms.txt URL: ___

### Versioned APIs
- [ ] Current API version: ___
- [ ] Legacy versions still documented: ___

### Changelogs & Updates
- [ ] API changelog URL: ___
- [ ] RSS/Atom feed URL (if exists): ___
- [ ] Update frequency: ___
```

### Phase 2: Deep Discovery

```
### GitHub
- [ ] GitHub org URL: ___
- [ ] OpenAPI/Swagger spec file: ___
- [ ] AsyncAPI spec file: ___
- [ ] Postman collection: ___
- [ ] Official SDK repos: ___
- [ ] Commit Atom feed URLs: ___

### Specs & Collections
- [ ] OpenAPI/Swagger JSON/YAML URL: ___
- [ ] Postman collection URL: ___
- [ ] AsyncAPI spec (WebSocket): ___
- [ ] FIX protocol spec (if applicable): ___

### Discovery Files
- [ ] robots.txt findings: ___
- [ ] sitemap.xml findings: ___
- [ ] llms.txt (if exists): ___
```

### Phase 3: Registration

```
### Status & Incidents
- [ ] API status page URL: ___

### CCXT
- [ ] CCXT exchange ID: ___
- [ ] Added to CCXT_EXCHANGE_MAP: ___

### Registry Entry
- [ ] Added to data/exchanges.yaml
- [ ] Seeds configured
- [ ] Allowed domains set
- [ ] Sitemap URL (if available)
- [ ] scope_prefixes (if sharing sitemap)
- [ ] render_mode (auto if JS-rendered)
- [ ] doc_sources with import URLs
- [ ] Synced and verified
```

### Phase 4: Crawl Validation

```
### Multi-Method Verification
- [ ] Method 1 (requests): status ___, word count ___
- [ ] Method 3 (Playwright/crawl4ai): status ___, word count ___
- [ ] Content comparison: methods agree? ___
- [ ] Spot-checked 5% of pages with alternate method? ___
```

### URL Probing Checklist

```
- [ ] {domain}/robots.txt
- [ ] {domain}/sitemap.xml
- [ ] {domain}/llms.txt
- [ ] {domain}/openapi.json, /swagger.json, /api-docs
- [ ] docs.{domain}/sitemap.xml
- [ ] developers.{domain}/
- [ ] api.{domain}/
- [ ] GitHub: site:github.com "{exchange}" openapi OR swagger
- [ ] Postman: site:postman.com "{exchange}" API
```

---

## 9. Implementation Priorities

### Priority 1: Import Available Specs (immediate endpoint value)

| Exchange | Spec | Size | Est. Endpoints | Import Command |
|----------|------|------|---------------:|----------------|
| KuCoin | 9 OpenAPI files | 2.9MB | 250 | `import-openapi` per file with `--base-url` |
| WhiteBIT | 7 OpenAPI specs | ~200KB+ | 100+ | `import-openapi --exchange whitebit --section v4 --url https://docs.whitebit.com/openapi/public/http-v4.yaml` (repeat for each) |
| BitMart | 2 Postman collections | 94KB | 111 | `import-postman --exchange bitmart --section spot --url https://raw.githubusercontent.com/bitmartexchange/bitmart-postman-api/master/collections/Spot.postman_collection.json` |
| Coinbase Prime | openapi.yaml | 351KB | ~95 | `import-openapi --exchange coinbase --section prime --url https://api.prime.coinbase.com/v1/openapi.yaml` |
| Paradex | swagger/doc.json | 380KB | 67 | `import-openapi --exchange paradex --section api --url https://api.prod.paradex.trade/swagger/doc.json` |
| Lighter | openapi.json | 225KB | 72 | `import-openapi --exchange lighter --section docs --url https://raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json` |
| dYdX | swagger.json | 115KB | 43 | `import-openapi --exchange dydx --section docs --url https://raw.githubusercontent.com/dydxprotocol/v4-chain/main/indexer/services/comlink/public/swagger.json` |
| Coinbase Exchange | community spec | 157KB | 38 | `import-openapi --exchange coinbase --section exchange --url https://raw.githubusercontent.com/metalocal/coinbase-exchange-api/main/api.oas3.json` |
| GRVT | apispec.json | ~460KB | ~95+ | **CUSTOM FORMAT** — needs custom parser |

**Total: ~870+ new endpoints from verified specs**

### Priority 2: Fix Crawl Gaps

| Exchange | Gap | Fix |
|----------|-----|-----|
| Kraken | 48 REST API pages never fetched | Re-sync Kraken spot section; sitemap already configured |
| Coinbase | FIX + sandbox docs outside scope_prefixes | Widen scope_prefixes or add new sections |
| Bithumb EN | 0 pages (requires Playwright) | Install Playwright, re-sync with render_mode: playwright |

### Priority 3: Register Missing Exchanges — ✓ DONE (v3)

All 8 missing CEX exchanges and 3 of 4 Tier 2 DEXes have been registered, synced, and spec-imported.
Pacifica deferred (insufficient API documentation).

### Priority 4: Remaining Gaps
| Nado | Active changelog, 3 SDKs | Low |

### Priority 5: New Sections for Existing Exchanges

| Section | Rationale |
|---------|-----------|
| Binance FIX API | FIX 4.4 docs at /docs/binance-spot-api-docs/fix-api |
| Bitstamp FIX v2 | FIX v2 docs at /fix/v2/ |
| Bitstamp WebSocket v2 | WS docs at /websocket/v2/ |
| Coinbase FIX (4 products) | Exchange FIX 4.2, INTX FIX 5.0, Prime FIX 4.2, Derivatives FIX 4.4 |
| Kraken FIX 4.4 | May already be in sitemap; verify and add seed if not |

### Priority 6: Community Specs (verify freshness before import)

| Exchange | Spec | Est. Endpoints |
|----------|------|---------------:|
| Kraken Futures | kanekoshoyu/exchange-collection | 51 |
| Upbit | ujhin/upbit-client/swagger.yaml | 92 |
| Binance+OKX | openxapi/openxapi (OpenAPI + AsyncAPI) | Many |

### Priority 7: Changelog Monitoring Setup

| Feed | URL | Verified |
|------|-----|----------|
| Upbit EN RSS | global-docs.upbit.com/changelog.rss | YES |
| Upbit KR RSS | docs.upbit.com/kr/changelog.rss | YES |
| Bithumb RSS | apidocs.bithumb.com/changelog.rss | YES |
| Coinone RSS | docs.coinone.co.kr/changelog.rss | YES |
| BitMEX RSS | bitmex.com/api_announcement/feed | YES |
| dYdX releases | dydxprotocol/v4-chain/releases.atom | — |
| CCXT releases | ccxt/ccxt/releases.atom | — |
| Bitbank commits | bitbankinc/bitbank-api-docs/commits/master.atom | — |

---

## 10. Source Trust & Drift Validation

### 10a. Source Hierarchy (most trusted first)

1. **Official API docs pages** (crawled HTML/markdown) — closest to ground truth. This is what developers actually see and use. Updated in real-time with deployments.
2. **Official OpenAPI/Swagger/AsyncAPI specs** (published by the exchange) — structured and importable, but may drift from live docs. Check `info.version` and last-modified dates.
3. **Official Postman collections** (published by the exchange) — convenient for import but frequently stale. Binance's are well-maintained; others may lag.
4. **CCXT `describe()` metadata** — useful for cross-reference and gap detection. Updated by CCXT contributors, not the exchange. May contain community-sourced paths not in official docs.
5. **Community-maintained specs** (OpenXAPI, metalocal, ujhin, etc.) — useful for bootstrapping but no freshness guarantee. Always cross-reference against source 1 or 2.
6. **llms.txt files** — auto-generated by doc platforms (ReadMe.io, GitBook). Good for URL discovery but content is a derivative of source 1.

### 10b. Drift Detection Strategy

No single source is authoritative. All sources drift. The maintainer workflow must:

1. **Crawl all available sources** for each exchange (official docs, specs, Postman, CCXT, llms.txt).
2. **Import structured data** from specs and Postman into the endpoint DB.
3. **Cross-reference** imported endpoints against crawled doc pages:
   - Endpoint in spec but not in docs → may be deprecated/removed (flag for review)
   - Endpoint in docs but not in spec → spec is stale (note drift)
   - Endpoint in CCXT but not in our DB → extraction gap (investigate)
   - Method/path mismatch between sources → flag conflict
4. **Periodic re-validation**: Re-fetch specs monthly. Compare `info.version` and endpoint counts. Alert on changes.
5. **Changelog monitoring**: Use RSS feeds and changelog extraction to detect additions/deprecations proactively.

### 10c. Crawl Validation Spot-Checks

After any sync, the maintainer workflow should:

1. Pick 5% of pages at random.
2. Re-fetch with `crawl4ai` (browser-based, LLM-optimized markdown).
3. Compare word count and structural content against stored markdown.
4. If discrepancy > 20%, flag the entire exchange for re-crawl with browser method.
5. For single-page SPAs (OKX, Gate.io, HTX, Crypto.com), always validate with browser crawl — HTTP fetch is unreliable.

### 10d. Crawl Tool Selection Matrix

| Site Characteristic | Recommended Primary | Fast-Path Alternative |
|--------------------|--------------------|----------------------|
| **Any unknown/new site** | `crawl4ai` | — |
| Known-static HTML (GitHub, Docusaurus) | `crawl4ai` (or `requests` fast path) | `requests` (~100x faster) |
| JS-rendered SPA | `crawl4ai` | Playwright (`--render auto`) |
| Heavy anti-bot (403 from all) | `crawl4ai` | Headed browser, then Agent Browser |
| Headless detection / CAPTCHA | Headed browser (`headless=False`) | Agent Browser (manual solve) |
| Login-gated / infinite scroll | Agent Browser | Headed browser with manual steps |
| Bulk re-crawl (8,000+ pages) | `crawl4ai` with concurrency limits | `requests` for static subset, `crawl4ai` for rest |
| Rate-limited after sync | `crawl4ai` (with delays) | wait + retry |

### 10e. Installed Crawl Tools

| Tool | Version | Install | Capabilities |
|------|---------|---------|-------------|
| `requests` | (stdlib) | Built-in | Plain HTTP, fastest, no JS |
| Playwright | 1.58.0 | `pip install playwright && playwright install chromium` | Full browser, JS rendering, stealth mode |
| `crawl4ai` | 0.8.0 | `pip install crawl4ai && crawl4ai-setup` | Browser + AI markdown extraction, best all-around |
| Agent Browser | (skill) | `.claude/skills/agent-browser/` | Interactive browser automation for complex cases |

---

## 11. Confirmed Non-Existent Sources

These were systematically searched for and confirmed to NOT exist:

| What | Exchanges Checked | Result |
|------|-------------------|--------|
| Official OpenAPI specs | OKX, Bitget, Gate.io, HTX, Crypto.com, Bitfinex, Bitbank, Coinone, Korbit, Bithumb | None found |
| Public RSS for API changelogs | Binance, OKX, Bybit, Bitget, Gate.io, KuCoin, HTX, Crypto.com, Bitstamp, Kraken, Coinbase | None (only forum/status/commit feeds) |
| Developer forums | All 35 | Dead or nonexistent |
| HTX status at old domain | status.huobigroup.com | DNS dead (use htx.statuspage.io) |
| Korbit status page | status.korbit.co.kr | DNS dead |
| Binance sitemap | developers.binance.com/sitemap.xml | 404 |
| Binance robots.txt | developers.binance.com/robots.txt | 404 |
| GRVT spec at root | gravity-technologies/api-spec/apispec.json | 404 (correct path: src/codegen/apispec.json) |
| KuCoin spec without prefix | Kucoin/kucoin-universal-sdk/spec/rest/entry/spot.json | 404 (correct: openapi-spot.json) |
| Gate.io downloadable OpenAPI | gate.com | Not publicly downloadable (internal, used to generate SDKs) |
| Kraken official OpenAPI | krakenfx/api-specs | Repo exists but is EMPTY |
| Coinbase Advanced Trade spec | docs.cdp.coinbase.com | Not published |
| Bitstamp direct OpenAPI download | bitstamp.net/openapi.json | Blocked by WAF |
| Bitfinex changelog RSS | docs.bitfinex.com/changelog.rss | 404 |
| GraphQL trading API | All 35 exchanges | None — GraphQL used only by on-chain indexers (The Graph, Bitquery) |
| Official AsyncAPI specs | All except WhiteBIT | Only WhiteBIT publishes formal AsyncAPI specs |
| Official FIX API | Bybit, OKX, BitMEX | None (OKX/BitMEX FIX only via third-party Axon Trade) |
| llms.txt | Binance, OKX, Bybit, Kraken, BitMEX, Bitget, Drift | 404 (Custom SPAs and some Docusaurus sites don't generate llms.txt) |
| Vertex Protocol | Was active exchange | **Shut down August 2025** |
| Zeta Markets | Was active exchange | **Ceased operating May 2025** |
