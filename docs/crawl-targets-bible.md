# Crawl Targets Bible

**Generated**: 2026-03-06 (verified refresh)
**Coverage**: 35 exchanges (21 CEX, 13 DEX, 1 reference) + 4 recommended additions
**Store snapshot** (live DB): 8,673 pages, 14.85M words, 3,603 structured endpoints

This document catalogs ALL known crawlable API documentation sources for every exchange in the registry. It is the authoritative reference for maintaining `data/exchanges.yaml` entries, onboarding new exchanges, and planning endpoint extraction campaigns.

**Verification status**: All URLs, spec sizes, and coverage numbers verified against live DB and web sources on 2026-03-06. Stale data from prior M1-M4 research corrected.

---

## Table of Contents

1. [Cross-Exchange Summary Tables](#1-cross-exchange-summary-tables)
2. [CEX Exchanges (21)](#2-cex-exchanges)
3. [DEX Protocols (13)](#3-dex-protocols)
4. [Reference (CCXT)](#4-reference)
5. [Recommended Additions (4)](#5-recommended-additions)
6. [New Exchange Template](#6-new-exchange-template)
7. [Implementation Priorities](#7-implementation-priorities)
8. [Confirmed Non-Existent Sources](#8-confirmed-non-existent-sources)

---

## 1. Cross-Exchange Summary Tables

### 1a. Live DB Coverage (verified 2026-03-06)

| exchange | type | sections | pages | words | endpoints | ccxt_eps |
|---|---|---:|---:|---:|---:|---:|
| binance | CEX | 9 | 1,860 | 1,565,114 | 1,425 | 794 |
| okx | CEX | 3 | 3 | 346,183 | 313 | 345 |
| bybit | CEX | 1 | 312 | 294,514 | 129 | 309 |
| bitget | CEX | 5 | 179 | 155,625 | 233 | 565 |
| gateio | CEX | 1 | 2 | 314,594 | 363 | 280 |
| kucoin | CEX | 2 | 433 | 1,053,797 | 124 | 220 |
| htx | CEX | 4 | 4 | 410,801 | 454 | 544 |
| cryptocom | CEX | 1 | 1 | 58,832 | 63 | 119 |
| bitstamp | CEX | 1 | 1 | 37,256 | 82 | 255 |
| bitfinex | CEX | 1 | 118 | 55,700 | 81 | 136 |
| upbit | CEX | 2 | 355 | 217,525 | 44 | 51 |
| bithumb | CEX | 1 | 153 | 36,735 | 36 | 28 |
| coinone | CEX | 1 | 91 | 62,489 | 22 | 63 |
| korbit | CEX | 1 | 2 | 25,230 | 32 | — |
| kraken | CEX | 2 | 65 | 32,228 | 0 | 54 |
| coinbase | CEX | 4 | 383 | 310,207 | 49 | 90 |
| bitmex | CEX | 1 | 142 | 53,731 | 95 | 93 |
| bitmart | CEX | 2 | 2 | 73,289 | 0 | 113 |
| whitebit | CEX | 1 | 161 | 98,291 | 0 | 110 |
| bitbank | CEX | 1 | 175 | 270,858 | 0 | 28 |
| mercadobitcoin | CEX | 1 | 1 | 0 | 31 | 21 |
| dydx | DEX-REST | 1 | 283 | 133,753 | 34 | — |
| hyperliquid | DEX-REST | 1 | 32 | 26,109 | 75 | 8 |
| aevo | DEX-REST | 1 | 144 | 79,208 | 0 | — |
| paradex | DEX-REST | 1 | 624 | 342,258 | 0 | — |
| lighter | DEX-REST | 1 | 49 | 24,758 | 0 | — |
| aster | DEX-REST | 1 | 147 | 119,948 | 0 | — |
| apex | DEX-REST | 1 | 5 | 133,667 | 0 | — |
| grvt | DEX-REST | 1 | 205 | 305,233 | 0 | — |
| drift | DEX-SDK | 1 | 133 | 220,576 | 0 | — |
| gmx | DEX-CONTRACT | 1 | 142 | 171,393 | 0 | — |
| gains | DEX-CONTRACT | 1 | 187 | 130,670 | 0 | — |
| kwenta | DEX-CONTRACT | 1 | 83 | 41,183 | 0 | — |
| perp | DEFUNCT | 1 | 1 | 121 | 0 | — |
| ccxt | REF | 1 | 2,037 | 6,925,008 | 0 | — |
| **TOTAL** | | **59** | **8,515** | **14,126,884** | **3,603** | |

Notes:
- `ccxt_eps` = CCXT `describe().api` endpoint count (post dict-of-dicts fix). Gap between `endpoints` and `ccxt_eps` indicates extraction opportunities.
- `DEX-REST` = DEX with documented REST API endpoints. `DEX-CONTRACT` = smart-contract-only, no REST API. `DEX-SDK` = SDK-based access only.
- 158 orphaned pages exist in DB without scope ownership (mostly from pre-scope-system imports).
- `htx/dm` has 82 endpoints and `crypto_com/exchange` has 63 endpoints stored under variant IDs (accounted for in totals).

### 1b. Documentation Platforms

| Platform | Exchanges |
|----------|-----------|
| Custom SPA | Binance, OKX, Bitget, Gate.io, KuCoin, Crypto.com, Korbit, BitMart, Aster |
| ReadMe.io | Bitfinex, Upbit, Bithumb, Coinone, Aevo, ApeX |
| Docusaurus | Bybit, Kraken, BitMEX, WhiteBIT |
| GitBook | Hyperliquid, dYdX, Paradex, Lighter, Drift, GMX, Gains, Kwenta |
| GitHub Pages | HTX (legacy) |
| Swagger/Redoc | Bitstamp (Redoc), MercadoBitcoin (Swagger UI) |
| GitHub Markdown | Bitbank, CCXT, GRVT |
| Custom (CDP) | Coinbase |

### 1c. OpenAPI / Swagger Spec Availability (verified live 2026-03-06)

| Status | Exchange | Spec URL | Size | Imported? |
|--------|----------|----------|------|-----------|
| **Live** | BitMEX | `bitmex.com/api/explorer/swagger.json` | 183KB | YES |
| **Live** | Coinbase Prime | `api.prime.coinbase.com/v1/openapi.yaml` | 351KB | NO |
| **Live** | Paradex | `api.prod.paradex.trade/swagger/doc.json` | 380KB | NO |
| **Live** | MercadoBitcoin | `api.mercadobitcoin.net/api/v4/docs/swagger.yaml` | 76KB | YES |
| **Live** | Lighter | `raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json` | 225KB | NO |
| **Live** | dYdX | `raw.githubusercontent.com/dydxprotocol/v4-chain/main/indexer/services/comlink/public/swagger.json` | 115KB | NO |
| **GitHub** | Binance | `binance/binance-api-swagger/spot_api.yaml` | 850KB | Already have 703 eps via Postman |
| **GitHub** | KuCoin | `Kucoin/kucoin-universal-sdk/spec/rest/entry/openapi-*.json` (9 files) | 2.9MB total | NO — HIGH PRIORITY |
| **GitHub** | GRVT | `gravity-technologies/api-spec/src/codegen/apispec.json` | ~460KB | NO (custom format, not OpenAPI) |
| **Inline** | Bitstamp | Embedded in bitstamp.net/api/ (WAF-blocked download) | ~100KB | Already have 82 eps |
| **Community** | Coinbase Exchange | `metalocal/coinbase-exchange-api/api.oas3.json` | 157KB | NO |
| **Community** | Kraken Futures | `kanekoshoyu/exchange-collection` | 148KB | NO |
| **Community** | Upbit | `ujhin/upbit-client/swagger.yaml` | 92KB | NO |
| **Community** | Hyperliquid | `bowen31337/hyperliquid-openapi` | 38KB | NO |
| **Planned** | Kraken | `krakenfx/api-specs` (repo exists, empty) | TBD | — |
| **None** | OKX, Bitget, Gate.io, HTX, Crypto.com, Bitfinex, WhiteBIT, Bitbank, Coinone, Korbit, Bithumb | — | — | — |

### 1d. Postman Collection Availability

| Exchange | Source | Coverage | Imported? |
|----------|--------|----------|-----------|
| Binance | `binance/binance-api-postman` (official, 25 collections) | All sections | YES |
| Bybit | `bybit-exchange/QuickStartWithPostman` (official) | V5 | YES |
| BitMart | `bitmartexchange/bitmart-postman-api` (official) | Spot (45KB) + Futures (49KB) | NO |
| KuCoin | `postman.com/kucoin-api/` (official workspace) | Comprehensive | NO |
| Bitfinex | `postman.com/antoanpopoff` (community) | Partial | NO |

### 1e. Changelog / RSS Feed Availability (verified live)

| Exchange | Changelog URL | RSS/Atom Feed | Verified |
|----------|--------------|---------------|----------|
| Binance | `developers.binance.com/docs/.../CHANGELOG` | `dev.binance.vision/latest.rss` (forum) | — |
| OKX | `okx.com/docs-v5/log_en/` | None | — |
| Bybit | `bybit-exchange.github.io/docs/changelog/v5` | None | — |
| Bitget | `bitget.com/api-doc/common/changelog` | None | — |
| Gate.io | Embedded in docs + `gate.com/announcements/apiupdates` | None | — |
| KuCoin | `kucoin.com/docs-new/change-log` | None | — |
| HTX | `htx.com/en-us/opend/` | None | — |
| Bitfinex | `docs.bitfinex.com/docs/changelog` | None (RSS 404) | YES |
| Crypto.com | Embedded in exchange-docs | None | — |
| Kraken | `docs.kraken.com/api/docs/change-log/` | None | YES |
| Coinbase | 6 separate changelogs per product | None | — |
| BitMEX | `bitmex.com/app/apiChangelog` | `bitmex.com/api_announcement/feed` | YES |
| Upbit EN | `global-docs.upbit.com/changelog` | `global-docs.upbit.com/changelog.rss` | YES |
| Upbit KR | `docs.upbit.com/ko/changelog` | `docs.upbit.com/kr/changelog.rss` | YES |
| Bithumb | `apidocs.bithumb.com/changelog` | `apidocs.bithumb.com/changelog.rss` | YES |
| Coinone | `docs.coinone.co.kr/changelog` | `docs.coinone.co.kr/changelog.rss` | YES |
| WhiteBIT | `docs.whitebit.com/changelog/` | `changelog.json` in GitHub repo | YES |
| Bitbank | GitHub CHANGELOG.md | `/commits/master.atom` | — |
| dYdX | GitHub releases | `dydxprotocol/v4-chain/releases.atom` | — |
| CCXT | GitHub releases | `ccxt/ccxt/releases.atom` | — |

### 1f. Status Page Availability (verified live)

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

### 1g. GitHub Organization Summary

| Exchange | Org/User | Notable |
|----------|----------|---------|
| Binance | `github.com/binance` | 25 Postman collections, spot OpenAPI, FIX connector |
| OKX | `github.com/okx` + `github.com/okxapi` | Two orgs (infra vs API SDKs) |
| Bybit | `github.com/bybit-exchange` | Docusaurus source |
| Bitget | `github.com/BitgetLimited` | Legacy GitHub Pages |
| Gate.io | `github.com/gateio` | 7 auto-generated SDKs |
| KuCoin | `github.com/Kucoin` | 9 OpenAPI spec files in universal-sdk (2.9MB) |
| HTX | `github.com/huobiapi` + `github.com/HuobiRDCenter` | Dual account |
| Bitfinex | `github.com/bitfinexcom` | FIX gateway repo |
| Coinbase | `github.com/coinbase` | coinbase-advanced-py SDK |
| BitMEX | `github.com/BitMEX` | Live + GitHub swagger.json |
| Upbit | `github.com/upbit-exchange` | Community OpenAPI exists separately |
| WhiteBIT | `github.com/whitebit-exchange` | Docusaurus source, changelog.json |
| Bitbank | `github.com/bitbankinc` | MCP server, dual-language docs |
| GRVT | `github.com/gravity-technologies` | API spec at `src/codegen/apispec.json` |
| Paradex | `github.com/tradeparadex` | OpenAPI + AsyncAPI |
| dYdX | `github.com/dydxprotocol` | Indexer swagger.json |
| CCXT | `github.com/ccxt` | 33K+ stars, exchange implementations |

### 1h. DEX Classification

| Classification | Exchanges | Has REST API? | Endpoint Value |
|----------------|-----------|---------------|----------------|
| **DEX-REST** | dYdX, Hyperliquid, Aevo, Paradex, Lighter, Aster, ApeX, GRVT | YES | High — importable specs available for Paradex, Lighter, dYdX, GRVT |
| **DEX-SDK** | Drift | SDK only | Low — no HTTP endpoint docs |
| **DEX-CONTRACT** | GMX, Gains Network, Kwenta | NO (smart contracts only) | None — docs describe Solidity interfaces, not REST APIs |
| **DEFUNCT** | Perpetual Protocol | DNS dead | None — remove from active sync |

---

## 2. CEX Exchanges

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
| **FIX docs** | developers.binance.com/docs/binance-spot-api-docs/fix-api (FIX 4.4, NOT currently crawled) |
| **Discovery** | robots.txt 404, sitemap.xml 404 (link-follow fallback) |

### OKX

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.okx.com/docs-v5/en/ (single-page SPA, 225K words) |
| **Platform** | Custom SPA |
| **Sections** | 3 (rest, broker, changelog) + websocket (0 pages) |
| **Pages/Words/Endpoints** | 3 / 346K / 313 |
| **CCXT endpoints** | 345 |
| **OpenAPI** | None |
| **Changelog** | okx.com/docs-v5/log_en/ (5+/month) |

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

### Gate.io

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.gate.com/docs/developers/apiv4/ (single-page, 315K words) |
| **Platform** | Custom SPA |
| **Sections** | 1 (v4) |
| **Pages/Words/Endpoints** | 2 / 315K / 363 |
| **CCXT endpoints** | 280 |
| **Note** | Rate-limits aggressively; re-sync may need --render auto |

### KuCoin

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.kucoin.com/docs/rest/spot-trading/ |
| **Platform** | Custom SPA (opaque URL IDs) |
| **Sections** | 2 (spot, futures — merged URL tree) |
| **Pages/Words/Endpoints** | 433 / 1.05M / 124 |
| **CCXT endpoints** | 220 (gap: 96 missing) |
| **OpenAPI** | 9 files in `Kucoin/kucoin-universal-sdk/spec/rest/entry/` (2.9MB total) — NOT YET IMPORTED |
| **Spec files** | openapi-spot.json (849KB), openapi-futures.json (694KB), openapi-account.json (536KB), openapi-margin.json (386KB), openapi-broker.json (211KB), openapi-earn.json (154KB), openapi-copytrading.json (98KB), openapi-viplending.json (23KB), openapi-affiliate.json (12KB) |
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
| **CCXT endpoints** | 255 (gap: 173 missing — CCXT tracks many v1 legacy paths) |
| **OpenAPI** | Inline in page (WAF blocks direct download) |
| **FIX docs** | bitstamp.net/fix/v2/ (NOT currently crawled) |
| **WebSocket docs** | bitstamp.net/websocket/v2/ (NOT currently crawled) |

### Bitfinex

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.bitfinex.com/reference/rest-public-platform-status |
| **Platform** | ReadMe.io |
| **Pages/Words/Endpoints** | 118 / 56K / 81 |
| **CCXT endpoints** | 136 (gap: 55 missing) |
| **Changelog** | docs.bitfinex.com/docs/changelog |
| **Status** | bitfinex.statuspage.io |

### Upbit

| Field | Value |
|-------|-------|
| **Docs URL** | global-docs.upbit.com (EN), docs.upbit.com/ko/ (KR) |
| **Platform** | ReadMe.io |
| **Sections** | 2 (rest_en, rest_ko) |
| **Pages/Words/Endpoints** | 355 / 218K / 44 |
| **CCXT endpoints** | 51 |
| **RSS** | global-docs.upbit.com/changelog.rss, docs.upbit.com/kr/changelog.rss |
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
| **Pages/Words/Endpoints** | 65 / 32K / 0 (NO endpoints extracted) |
| **CCXT endpoints** | 54 |
| **Changelog** | docs.kraken.com/api/docs/change-log/ |
| **Sitemap** | docs.kraken.com/sitemap.xml |
| **Status** | status.kraken.com |
| **OpenAPI** | krakenfx/api-specs repo exists but is EMPTY. Community spec in kanekoshoyu/exchange-collection |

### Coinbase

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.cdp.coinbase.com/api-reference/ |
| **Platform** | Custom (CDP) |
| **Sections** | 4 (advanced_trade, exchange, intx, prime) |
| **Pages/Words/Endpoints** | 383 / 310K / 49 (only intx imported) |
| **CCXT endpoints** | 90 |
| **Sitemap** | docs.cdp.coinbase.com/sitemap.xml (559 entries, shared across 4 sections with scope_priority) |
| **OpenAPI** | Prime: api.prime.coinbase.com/v1/openapi.yaml (351KB) — NOT IMPORTED |
| **Community spec** | Exchange: metalocal/coinbase-exchange-api/api.oas3.json (157KB) |
| **Status** | status.coinbase.com |
| **Note** | Docs migrated to /api-reference/ paths in 2026-03. scope_prefixes updated. |

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

### BitMart

| Field | Value |
|-------|-------|
| **Docs URL** | https://developer-pro.bitmart.com/en/spot/ |
| **Platform** | Custom SPA (single-page per section) |
| **Sections** | 2 (spot: 39K words, futures: 35K words) |
| **Pages/Words/Endpoints** | 2 / 73K / 0 (NO endpoints) |
| **CCXT endpoints** | 113 |
| **Postman** | bitmartexchange/bitmart-postman-api — Spot + Futures collections — NOT IMPORTED |

### WhiteBIT

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.whitebit.com/ |
| **Platform** | Docusaurus |
| **Pages/Words/Endpoints** | 161 / 98K / 0 (NO endpoints) |
| **CCXT endpoints** | 110 |
| **Sitemap** | docs.whitebit.com/sitemap.xml |
| **Changelog** | docs.whitebit.com/changelog/ |
| **Status** | status.whitebit.com |

### Bitbank

| Field | Value |
|-------|-------|
| **Docs URL** | https://github.com/bitbankinc/bitbank-api-docs |
| **Platform** | GitHub Markdown |
| **Pages/Words/Endpoints** | 175 / 271K / 0 (NO endpoints) |
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

## 3. DEX Protocols

### DEX-REST (have HTTP API endpoints)

#### dYdX

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.dydx.xyz/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 283 / 134K / 34 |
| **OpenAPI** | dydxprotocol/v4-chain/indexer/services/comlink/public/swagger.json (115KB) — NOT IMPORTED |
| **Status** | status.dydx.trade |

#### Hyperliquid

| Field | Value |
|-------|-------|
| **Docs URL** | https://hyperliquid.gitbook.io/hyperliquid-docs/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 32 / 26K / 75 |
| **Sitemap** | hyperliquid.gitbook.io/hyperliquid-docs/sitemap.xml |

#### Aevo

| Field | Value |
|-------|-------|
| **Docs URL** | https://api-docs.aevo.xyz/ |
| **Platform** | ReadMe.io |
| **Pages/Words/Endpoints** | 144 / 79K / 0 |

#### Paradex

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.paradex.trade/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 624 / 342K / 0 |
| **OpenAPI** | api.prod.paradex.trade/swagger/doc.json (380KB) — NOT IMPORTED |
| **AsyncAPI** | WebSocket spec in tradeparadex repo |

#### Lighter

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.lighter.xyz/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 49 / 25K / 0 |
| **OpenAPI** | elliottech/lighter-python/openapi.json (225KB) — NOT IMPORTED |

#### Aster

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.asterdex.com/ |
| **Platform** | GitBook |
| **Pages/Words/Endpoints** | 147 / 120K / 0 |

#### ApeX Pro

| Field | Value |
|-------|-------|
| **Docs URL** | https://api-docs.pro.apex.exchange/ |
| **Platform** | ReadMe.io |
| **Pages/Words/Endpoints** | 5 / 134K / 0 |

#### GRVT

| Field | Value |
|-------|-------|
| **Docs URL** | https://github.com/gravity-technologies/api-spec |
| **Platform** | GitHub Markdown |
| **Pages/Words/Endpoints** | 205 / 305K / 0 |
| **Spec** | gravity-technologies/api-spec/src/codegen/apispec.json (~460KB) — **CUSTOM FORMAT** (not OpenAPI). Defines ~60+ operations across MarketData and Trading gateways. May need custom parser. |
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
| **Value for our DB** | Low — no HTTP endpoints to extract. Pages may be useful for contract ABI reference only. |

#### Gains Network

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.gains.trade/ |
| **Platform** | GitBook |
| **Pages/Words** | 187 / 131K |
| **REST API** | **NONE** — smart contract protocol |

#### Kwenta

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.kwenta.io/ |
| **Platform** | GitBook |
| **Pages/Words** | 83 / 41K |
| **REST API** | **NONE** — Synthetix-based, smart contract only |

### DEX-SDK (SDK-based, no direct REST docs)

#### Drift

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.drift.trade/ |
| **Platform** | GitBook |
| **Pages/Words** | 133 / 221K |
| **REST API** | SDK-based access; may have internal REST gateway but no public REST endpoint docs |

### DEFUNCT

#### Perpetual Protocol

| Field | Value |
|-------|-------|
| **Status** | **DEFUNCT** — docs.perp.com DNS dead (NXDOMAIN), token delisted |
| **Action** | Marked `status: defunct` in exchanges.yaml. Do not sync. |

---

## 4. Reference

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

## 5. Recommended Additions

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

## 6. New Exchange Template

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
- [ ] Postman collection: ___
- [ ] Official SDK repos: ___
- [ ] Commit Atom feed URLs: ___

### Specs & Collections
- [ ] OpenAPI/Swagger JSON/YAML URL: ___
- [ ] Postman collection URL: ___
- [ ] AsyncAPI spec (WebSocket): ___

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

## 7. Implementation Priorities

### Priority 1: Import Available Specs (immediate endpoint value)

| Exchange | Spec | Size | Est. Endpoints | Import Command |
|----------|------|------|---------------:|----------------|
| KuCoin | 9 OpenAPI files | 2.9MB | 300+ | `import-openapi` per file with `--base-url` |
| Coinbase Prime | openapi.yaml | 351KB | 98 | `import-openapi --exchange coinbase --section prime --url https://api.prime.coinbase.com/v1/openapi.yaml` |
| Paradex | swagger/doc.json | 380KB | 78 | `import-openapi --exchange paradex --section api --url https://api.prod.paradex.trade/swagger/doc.json` |
| Lighter | openapi.json | 225KB | 57 | `import-openapi --exchange lighter --section docs --url https://raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json` |
| dYdX | swagger.json | 115KB | 50+ | `import-openapi --exchange dydx --section docs --url https://raw.githubusercontent.com/dydxprotocol/v4-chain/main/indexer/services/comlink/public/swagger.json` |
| BitMart | Postman Spot+Futures | 94KB | 80+ | `import-postman --exchange bitmart --section spot/futures` |
| GRVT | apispec.json | ~460KB | ~60+ | **CUSTOM FORMAT** — not standard OpenAPI. May need custom parser or manual extraction. URL: `https://raw.githubusercontent.com/gravity-technologies/api-spec/main/src/codegen/apispec.json` |

**Total: ~760+ new endpoints from verified specs**

### Priority 2: Community Specs (verify before import)

| Exchange | Spec | Est. Endpoints |
|----------|------|---------------:|
| Coinbase Exchange | metalocal/coinbase-exchange-api (157KB) | 39 |
| Kraken Futures | kanekoshoyu/exchange-collection | 51 |
| Upbit | ujhin/upbit-client/swagger.yaml | 92 |
| Hyperliquid | bowen31337/hyperliquid-openapi | 38 |

### Priority 3: New Exchange Registration

| Exchange | Rationale | Effort |
|----------|-----------|--------|
| Orderly Network | 192-path OpenAPI, 694-URL sitemap, Mintlify | Medium |
| Pacifica | 97 API doc URLs in sitemap, active changelog | Low |
| Bluefin | ReadMe.io (easy crawl), ~22 endpoints | Low |
| Nado | Active changelog, 3 SDKs | Low |

### Priority 4: New Sections for Existing Exchanges

| Section | Rationale |
|---------|-----------|
| Binance FIX API | FIX 4.4 docs at /docs/binance-spot-api-docs/fix-api |
| Bitstamp FIX v2 | FIX v2 docs at /fix/v2/ |
| Bitstamp WebSocket v2 | WS docs at /websocket/v2/ |

### Priority 5: Changelog Monitoring Setup

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

## 8. Confirmed Non-Existent Sources

These were systematically searched for and confirmed to NOT exist:

| What | Exchanges Checked | Result |
|------|-------------------|--------|
| Official OpenAPI specs | OKX, Bitget, Gate.io, HTX, Crypto.com, Bitfinex, WhiteBIT, Bitbank, Coinone, Korbit, Bithumb | None found |
| Public RSS for API changelogs | Binance, OKX, Bybit, Bitget, Gate.io, KuCoin, HTX, Crypto.com, Bitstamp, Kraken, Coinbase | None (only forum/status/commit feeds) |
| Developer forums | All 35 | Dead or nonexistent |
| HTX status at old domain | status.huobigroup.com | DNS dead (use htx.statuspage.io) |
| Korbit status page | status.korbit.co.kr | DNS dead |
| Binance sitemap | developers.binance.com/sitemap.xml | 404 |
| Binance robots.txt | developers.binance.com/robots.txt | 404 |
| GRVT spec at root | gravity-technologies/api-spec/apispec.json | 404 (correct path: src/codegen/apispec.json) |
| KuCoin spec without prefix | Kucoin/kucoin-universal-sdk/spec/rest/entry/spot.json | 404 (correct: openapi-spot.json) |
| Gate.io downloadable OpenAPI | gate.com | Not publicly downloadable |
| Kraken official OpenAPI | krakenfx/api-specs | Repo exists but is EMPTY |
| Coinbase Advanced Trade spec | docs.cdp.coinbase.com | Not published |
| Bitstamp direct OpenAPI download | bitstamp.net/openapi.json | Blocked by WAF |
| Bitfinex changelog RSS | docs.bitfinex.com/changelog.rss | 404 |
