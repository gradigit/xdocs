# Crawl Targets Bible

**Generated**: 2026-03-06
**Coverage**: 35 exchanges (21 CEX, 13 DEX, 1 reference) + 4 recommended additions
**Store snapshot**: 5,716 pages, 7.7M words, 3,603 structured endpoints

This document catalogs ALL known crawlable API documentation sources for every exchange in the registry. It is the authoritative reference for maintaining `data/exchanges.yaml` entries, onboarding new exchanges, and planning endpoint extraction campaigns.

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

### 1a. Documentation Platforms

| Platform | Exchanges |
|----------|-----------|
| Custom SPA | Binance, OKX, Bitget, Gate.io, KuCoin, HTX (new portal), Crypto.com, Korbit, BitMart, Aster |
| ReadMe.io | Bitfinex, Upbit, Bithumb, Coinone, Aevo, ApeX, Bluefin* |
| Docusaurus | Bybit, Kraken, BitMEX, WhiteBIT |
| GitHub Pages | HTX (legacy), Gate.io (legacy) |
| GitBook | Hyperliquid, dYdX, GMX, Drift, Gains, Kwenta, GRVT, Paradex, Lighter, OKX* |
| Swagger/Redoc | Bitstamp (Redoc), MercadoBitcoin (Swagger UI) |
| GitHub Markdown | Bitbank, CCXT |
| Custom (CDP) | Coinbase |

### 1b. OpenAPI / Swagger Spec Availability

| Status | Exchange | Spec Location | Size |
|--------|----------|--------------|------|
| **Live URL** | BitMEX | bitmex.com/api/explorer/swagger.json | 183KB |
| **Live URL** | Coinbase Prime | api.prime.coinbase.com/v1/openapi.yaml | ~150KB |
| **Live URL** | Paradex | api.prod.paradex.trade/swagger/doc.json | 307KB |
| **Live URL** | MercadoBitcoin | api.mercadobitcoin.net/api/v4/docs/swagger.yaml | 76KB |
| **GitHub** | Binance | binance/binance-api-swagger (spot only) | 999KB |
| **GitHub** | BitMEX | BitMEX/api-connectors/swagger.json | 272KB |
| **GitHub** | KuCoin | Kucoin/kucoin-universal-sdk/spec/rest/api/ | 23 files |
| **GitHub** | GRVT | gravity-technologies/api-spec/apispec.json | 460KB |
| **GitHub** | Lighter | elliottech/lighter-python/openapi.json | 225KB |
| **GitHub** | dYdX | dydxprotocol/v4-chain/.../swagger.json | 115KB |
| **GitHub** | Orderly* | OrderlyNetwork (evm.openapi.yaml) | 461KB |
| **Inline** | Bitstamp | Embedded in bitstamp.net/api/ (WAF-blocked download) | ~100KB |
| **Community** | Upbit | ujhin/upbit-client/swagger.yaml | 92KB |
| **Community** | Kraken Futures | kanekoshoyu/exchange-collection | 148KB |
| **Community** | Coinbase Exchange | metalocal/coinbase-exchange-api | ~50KB |
| **Community** | Hyperliquid | bowen31337/hyperliquid-openapi | 38KB |
| **Community** | Bybit | bybit-exchange/api-connectors (V3 era, possibly outdated) | 304KB |
| **Planned** | Kraken | krakenfx/api-specs (repo exists, empty) | TBD |
| **None** | OKX, Bitget, Gate.io, HTX, Crypto.com, Bitfinex, WhiteBIT, Bitbank, Coinone, Korbit, Bithumb | — | — |

### 1c. Postman Collection Availability

| Exchange | Source | Coverage |
|----------|--------|----------|
| Binance | binance/binance-api-postman (official, 25 collections) | Spot, Futures, Options, Portfolio, Margin, Wallet, Copy Trading, Pay, Convert |
| Bybit | bybit-exchange/QuickStartWithPostman (official) | V5 + Tax V3 |
| BitMart | bitmartexchange/bitmart-postman-api (official) | Spot (45KB) + Futures (49KB) |
| KuCoin | postman.com/kucoin-api/ (official workspace) | Comprehensive |
| Bitfinex | postman.com/antoanpopoff (community) | Partial |
| Coinbase | postman.com/api-evangelist (community) | Partial |

### 1d. Changelog / RSS Feed Availability

| Exchange | Changelog URL | RSS/Atom Feed | Frequency |
|----------|--------------|---------------|-----------|
| Binance | developers.binance.com/docs/.../CHANGELOG | dev.binance.vision/latest.rss (forum) | 2-4/month |
| OKX | okx.com/docs-v5/log_en/ | None | 5+/month |
| Bybit | bybit-exchange.github.io/docs/changelog/v5 | None | Multiple/month |
| Bitget | bitget.com/api-doc/common/changelog | None (403 on auto-fetch) | Monthly |
| Gate.io | Embedded in docs + gate.com/announcements/apiupdates | None | Multiple/week |
| KuCoin | kucoin.com/docs-new/change-log | None | Multiple/month |
| HTX | htx.com/en-us/opend/ (Updates) | None | Active |
| Bitfinex | docs.bitfinex.com/docs/changelog | [DEAD] /changelog.rss (404) | Very sparse (8 entries, 7 years) |
| Crypto.com | Embedded in exchange-docs page | None | Active |
| Bitstamp | Inline in API docs | None | Low |
| Kraken | docs.kraken.com/api/docs/change-log/ | None | Very active (100+ entries) |
| Coinbase | 6 separate changelogs per product | None | Active |
| BitMEX | bitmex.com/app/apiChangelog | bitmex.com/api_announcement/feed (RSS) | Moderate |
| Upbit (EN) | global-docs.upbit.com/changelog | global-docs.upbit.com/changelog.rss (57 items) | Monthly |
| Upbit (KR) | docs.upbit.com/ko/changelog | docs.upbit.com/kr/changelog.rss (79 items) | Monthly |
| Bithumb | apidocs.bithumb.com/changelog | apidocs.bithumb.com/changelog.rss (26 items) | Periodic |
| Coinone | docs.coinone.co.kr/changelog | docs.coinone.co.kr/changelog.rss (13 items) | Periodic |
| WhiteBIT | docs.whitebit.com/changelog/ | changelog.json in GitHub repo | Monthly |
| Bitbank | github.com/bitbankinc/bitbank-api-docs/CHANGELOG.md | /commits/master.atom | Monthly-bimonthly |
| dYdX | Via GitHub releases | github.com/dydxprotocol/v4-chain/releases.atom | Very active |
| BitMEX status | status.bitmex.com | /history.atom, /history.rss | Active |

### 1e. Status Page Availability

| Exchange | Status URL | Platform | JSON API |
|----------|-----------|----------|----------|
| Bitfinex | bitfinex.statuspage.io | Statuspage.io | /api/v2/status.json |
| Kraken | status.kraken.com | Statuspage.io | /api/v2/status.json |
| Coinbase | status.coinbase.com, cdpstatus.coinbase.com, status.exchange.coinbase.com | Statuspage.io | Standard APIs |
| BitMEX | status.bitmex.com | Statuspage.io | /api/v2/status.json + Atom/RSS |
| Crypto.com | status.crypto.com | Statuspage.io | Standard APIs |
| HTX | status.huobigroup.com | Statuspage.io | /api/v2/summary.json |
| dYdX | status.dydx.trade (v4), status.dydx.exchange (v3) | Statuspage.io | Standard APIs |
| Korbit | status.korbit.co.kr | Statuspage.io | Standard APIs |
| WhiteBIT | status.whitebit.com | OpenStatus | Unknown |
| MercadoBitcoin | status.mercadobitcoin.com.br | Custom | /summary.json |
| Binance | None (only /sapi/v1/system/status API) | — | API only |
| OKX | okx.com/status (deposit/withdrawal) | Custom | /api/v5/system/status |
| Bybit | NONE (bybit.statuspage.io is FRAUDULENT) | — | /v5/system-status API |
| Bitget | None | — | — |
| Gate.io | None | — | — |
| KuCoin | None | — | /api/v1/status API |
| Bitstamp | None | — | — |
| Upbit | None | — | /v1/status/wallet API |

### 1f. GitHub Organization Summary

| Exchange | Org/User | Repos | Notable |
|----------|----------|------:|---------|
| Binance | github.com/binance | 45+ | 25 Postman collections, spot OpenAPI, FIX connector |
| OKX | github.com/okx + github.com/okxapi | 30+ | Two orgs (infra vs API SDKs) |
| Bybit | github.com/bybit-exchange | 15 | Docusaurus source, legacy Slate docs |
| Bitget | github.com/BitgetLimited | 7 | Legacy GitHub Pages, V3 SDK |
| Gate.io | github.com/gateio | 15 | 7 auto-generated SDKs (OpenAPI-first) |
| KuCoin | github.com/Kucoin | 28 | 23 OpenAPI spec files in universal-sdk |
| HTX | github.com/huobiapi (user) + github.com/HuobiRDCenter (org) | 20+ | Dual account setup |
| Bitfinex | github.com/bitfinexcom | 10+ | FIX gateway repo |
| Coinbase | github.com/coinbase | 50+ | coinbase-advanced-py SDK |
| BitMEX | github.com/BitMEX | 9 | Live + GitHub swagger.json |
| Upbit | github.com/upbit-exchange | 5 | Community OpenAPI exists separately |
| Bithumb | github.com/bithumb-pro | ? | Possibly defunct (Bithumb Global) |
| WhiteBIT | github.com/whitebit-exchange | 13 | Docusaurus source, changelog.json |
| Bitbank | github.com/bitbankinc | 13 | MCP server, dual-language docs |
| GRVT | github.com/gravity-technologies | 5+ | 460KB API spec |
| Paradex | github.com/tradeparadex | 5+ | OpenAPI + AsyncAPI |
| dYdX | github.com/dydxprotocol | 20+ | Indexer swagger.json, v4-documentation |
| CCXT | github.com/ccxt | 5+ | 33K+ stars, exchange implementations |

---

## 2. CEX Exchanges

### Binance

| Field | Value |
|-------|-------|
| **Docs URL** | https://developers.binance.com/docs/binance-spot-api-docs/ |
| **Platform** | Custom (React/Docusaurus-like) |
| **Sections** | 9 (spot, futures_usdm, futures_coinm, portfolio_margin, options, margin_trading, wallet, copy_trading, portfolio_margin_pro) |
| **Pages/Words/Endpoints** | 1,802 / 1.56M / 1,425 |
| **API version** | v3 (REST), v1 (WS), FIX 4.4 |
| **OpenAPI** | spot_api.yaml on GitHub (spot only, 999KB) |
| **Postman** | 25 collections in binance-api-postman |
| **Changelog** | developers.binance.com/docs/.../CHANGELOG (spot); /derivatives/change-log |
| **RSS** | dev.binance.vision/latest.rss (forum, not API changelog) |
| **GitHub** | github.com/binance (45+ repos) |
| **Status** | No dedicated page; /sapi/v1/system/status API |
| **FIX docs** | developers.binance.com/docs/binance-spot-api-docs/fix-api (FIX 4.4) |
| **Telegram** | @binance_api_announcements (6.39K subscribers) |
| **Discovery** | robots.txt 404, sitemap.xml 404 (link-follow fallback) |

### OKX

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.okx.com/docs-v5/en/ (single-page SPA, 224K words) |
| **Platform** | Custom SPA |
| **Sections** | 4 (rest, websocket, broker, changelog) |
| **Pages/Words/Endpoints** | 3 / 346K / 313 |
| **API version** | V5 |
| **OpenAPI** | None |
| **Changelog** | okx.com/docs-v5/log_en/ (5+/month) |
| **GitHub** | github.com/okx + github.com/okxapi |
| **Status** | okx.com/status (custom); /api/v5/system/status |
| **llms.txt** | okx.com/llms.txt |
| **Discovery** | 7 sitemaps in robots.txt; text-docs-index for doc URLs |

### Bybit

| Field | Value |
|-------|-------|
| **Docs URL** | https://bybit-exchange.github.io/docs/ (Docusaurus) |
| **Platform** | Docusaurus (source on GitHub) |
| **Sections** | 2 (v5, websocket) |
| **Pages/Words/Endpoints** | 308 / 292K / 129 |
| **API version** | V5 (unified) |
| **OpenAPI** | swagger.json in api-connectors (possibly V3-era, outdated) |
| **Postman** | QuickStartWithPostman repo (V5 + Tax V3) |
| **Changelog** | bybit-exchange.github.io/docs/changelog/v5 |
| **GitHub** | github.com/bybit-exchange (15 repos) |
| **Status** | NONE (bybit.statuspage.io is FRAUDULENT); /v5/system-status API |
| **Telegram** | @bybit_api_announcements |

### Bitget

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.bitget.com/api-doc/common/intro |
| **Platform** | Custom |
| **Sections** | 5 (v2, copy_trading, margin, earn, broker) |
| **Pages/Words/Endpoints** | 180 / 157K / 233 |
| **API version** | V2 |
| **OpenAPI** | None |
| **Changelog** | bitget.com/api-doc/common/changelog (403 on auto-fetch) |
| **GitHub** | github.com/BitgetLimited (7 repos) |
| **Status** | None |
| **Legacy** | bitgetlimited.github.io/apidoc/en/spot/ (V1 era) |

### KuCoin

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.kucoin.com/docs-new/introduction |
| **Platform** | Custom (opaque URL IDs) |
| **Sections** | 1 (spot — merged from spot+futures) |
| **Pages/Words/Endpoints** | 429 / 1.04M / 70 |
| **API version** | V1 (REST), V2 (broker), UTA (Sep 2025) |
| **OpenAPI** | 23 granular JSON specs in kucoin-universal-sdk/spec/rest/api/ |
| **Postman** | Official workspace at postman.com/kucoin-api/ |
| **Changelog** | kucoin.com/docs-new/change-log |
| **GitHub** | github.com/Kucoin (28 repos) |
| **Status** | /api/v1/status API |
| **Telegram** | t.me/KuCoin_API |

### Gate.io

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.gate.com/docs/developers/apiv4/ (single-page, 256K words) |
| **Platform** | Custom (Swagger UI-based, OpenAPI-generated) |
| **Sections** | 1 (v4) |
| **Pages/Words/Endpoints** | 1 / 182K / 363 |
| **API version** | APIv4 (v4.106.32) |
| **OpenAPI** | Architecture is OpenAPI-first, but raw spec NOT publicly downloadable |
| **Changelog** | Embedded + gate.com/announcements/apiupdates (multiple releases/week) |
| **GitHub** | github.com/gateio (15 repos, 7 auto-generated SDKs) |
| **Status** | None |
| **Legacy** | gate.com/api2 (APIv2 still live) |
| **Gotcha** | Aggressive rate-limiting (403 after sync) |

### HTX (ex-Huobi)

| Field | Value |
|-------|-------|
| **Docs URL** | Legacy: huobiapi.github.io/docs/spot/v1/en/ / New: htx.com/en-us/opend/newApiPages/ |
| **Platform** | GitHub Pages (legacy) + Custom portal (new) |
| **Sections** | 4 (spot, derivatives, coin_margined_swap, usdt_swap) |
| **Pages/Words/Endpoints** | 4 / 411K / 290 |
| **API version** | v1 |
| **OpenAPI** | None |
| **Changelog** | New portal Updates section |
| **GitHub** | github.com/huobiapi (user) + github.com/HuobiRDCenter (org) |
| **Status** | status.huobigroup.com (Statuspage.io with JSON API) |
| **Note** | Dual-system docs; base URLs still reference huobi.pro and hbdm.com |

### Crypto.com

| Field | Value |
|-------|-------|
| **Docs URL** | https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html |
| **Platform** | Custom (single-page HTML) |
| **Sections** | 1 (exchange) |
| **Pages/Words/Endpoints** | 1 / 59K / 63 |
| **API version** | Exchange API v1 |
| **OpenAPI** | None (probes return 403/400) |
| **Changelog** | Embedded in main doc page (through 2025-12-17) |
| **GitHub** | github.com/crypto-com (stub repo only) |
| **Status** | status.crypto.com (Statuspage.io) |
| **CCXT ID** | `cryptocom` (NOT `crypto_com`) |
| **Hidden** | OTC 2.0 at /index_OTC2.html; Derivatives at /derivatives/index.html |

### Bitstamp

| Field | Value |
|-------|-------|
| **Docs URL** | https://www.bitstamp.net/api/ (Redoc, inline OpenAPI 3.0.3) |
| **Platform** | Redoc |
| **Sections** | 1 (rest) |
| **Pages/Words/Endpoints** | 1 / 37K / 82 |
| **API version** | v2 |
| **OpenAPI** | Inline in page source (OpenAPI 3.0.3); download button exists but WAF blocks direct URL |
| **WebSocket** | bitstamp.net/websocket/v2/ |
| **FIX** | bitstamp.net/fix/v2/ |
| **PSD2** | bitstamp.net/api-psd2/ (Open Banking) |
| **Status** | None |
| **sitemap** | bitstamp.net/sitemap.xml (200) |

### Bitfinex

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.bitfinex.com/ (ReadMe.io) |
| **Platform** | ReadMe.io |
| **Sections** | 1 (v2) |
| **Pages/Words/Endpoints** | 118 / 56K / 81 |
| **API version** | v2 (v1 still accessible at /v1/ prefix) |
| **OpenAPI** | None |
| **Changelog** | docs.bitfinex.com/docs/changelog (sparse: 8 entries, 2017–2024) |
| **RSS** | [DEAD] /changelog.rss returns 404 |
| **GitHub** | github.com/bitfinexcom (SDKs: Python, Node, Go, Ruby; FIX gateway) |
| **Status** | bitfinex.statuspage.io |

### Kraken

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.kraken.com/ (Docusaurus) |
| **Platform** | Docusaurus |
| **Sections** | 2 (spot, futures) |
| **Pages/Words/Endpoints** | 65 / 36K / 0 |
| **API version** | Spot REST (unversioned), WS v2, FIX (spot + futures) |
| **OpenAPI** | None (krakenfx/api-specs repo exists but EMPTY) |
| **Changelog** | docs.kraken.com/api/docs/change-log/ (100+ entries, 2018–2026) |
| **GitHub** | github.com/krakenfx |
| **Status** | status.kraken.com (Statuspage.io with JSON API) |
| **Community spec** | kanekoshoyu/exchange-collection (Futures, 148KB) |
| **Embed API** | docs.kraken.com/api/docs/guides/embed-rest/ (B2B, new Feb 2026) |

### Coinbase

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.cdp.coinbase.com/ (Custom CDP) |
| **Platform** | Custom (Coinbase Developer Platform) |
| **Sections** | 4 (advanced_trade, exchange, intx, prime) |
| **Pages/Words/Endpoints** | 78 / 106K / 49 |
| **API version** | Multiple products (AT, Exchange, INTX, Prime) |
| **OpenAPI** | Prime: api.prime.coinbase.com/v1/openapi.yaml (LIVE, 98 ops); INTX: imported previously |
| **Changelogs** | 6 separate changelogs per product |
| **FIX** | Exchange FIX 5 (replaced FIX 4.2, deprecated June 2025); INTX FIX |
| **GitHub** | github.com/coinbase |
| **Status** | 3 pages: status.coinbase.com, cdpstatus.coinbase.com, status.exchange.coinbase.com |
| **Shared sitemap** | docs.cdp.coinbase.com/sitemap.xml (scope_prefixes dedup) |

### dYdX

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.dydx.xyz/ (GitBook) |
| **Platform** | GitBook + GitHub (MDX) |
| **Sections** | 1 (docs) |
| **Pages/Words/Endpoints** | 271 / 134K / 34 |
| **API version** | v4 (Chain + Indexer API v1.0.0) |
| **OpenAPI** | Indexer swagger.json in dydxprotocol/v4-chain (115KB, Swagger 2.0) |
| **Changelog** | Via v4-chain GitHub releases |
| **RSS** | github.com/dydxprotocol/v4-chain/releases.atom |
| **GitHub** | github.com/dydxprotocol (20+ repos) |
| **Status** | status.dydx.trade (v4), status.dydx.exchange (v3, inactive) |
| **Legacy** | v3 sunset Oct 28, 2024 |

### Upbit

| Field | Value |
|-------|-------|
| **Docs URL** | EN: global-docs.upbit.com / KR: docs.upbit.com |
| **Platform** | ReadMe.io |
| **Sections** | 2 (rest_en, rest_ko) |
| **Pages/Words/Endpoints** | 304 / 306K / 44 |
| **API version** | v1 |
| **OpenAPI** | Community: ujhin/upbit-client/swagger.yaml (92KB) |
| **Changelog RSS** | EN: global-docs.upbit.com/changelog.rss (57 items); KR: docs.upbit.com/kr/changelog.rss (79 items) |
| **GitHub** | github.com/upbit-exchange (5 repos) |
| **Status** | None (API: /v1/status/wallet) |
| **llms.txt** | global-docs.upbit.com/llms.txt |
| **Note** | Korean docs are 3 minor versions ahead of English |

### Bithumb

| Field | Value |
|-------|-------|
| **Docs URL** | https://apidocs.bithumb.com/ (ReadMe.io) |
| **Platform** | ReadMe.io |
| **Sections** | 2 (rest, rest_en) |
| **Pages/Words/Endpoints** | 150 / 74K / 36 |
| **Changelog RSS** | apidocs.bithumb.com/changelog.rss (26 items) |
| **Note** | English section requires Playwright (Localize.js client-side translation) |
| **Futures docs** | bithumbfutures.github.io (separate, may be Bithumb Global) |

### Coinone

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.coinone.co.kr/ (ReadMe.io) |
| **Platform** | ReadMe.io |
| **Sections** | 1 (rest) |
| **Pages/Words/Endpoints** | 91 / 67K / 22 |
| **Changelog RSS** | docs.coinone.co.kr/changelog.rss (13 items) |
| **Note** | Korean-only. No English version. Endpoint paths/params are in English (FTS5 searchable). |

### Korbit

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.korbit.co.kr/ |
| **Platform** | Custom |
| **Sections** | 1 (rest) |
| **Pages/Words/Endpoints** | 2 / 25K / 32 |
| **Status** | status.korbit.co.kr (Statuspage.io) |
| **CCXT** | No CCXT class in main library (CCXT.NET only) |
| **English** | docs.korbit.co.kr/index_en.html |

### BitMEX

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.bitmex.com/ (Docusaurus) |
| **Platform** | Docusaurus |
| **Sections** | 1 (rest) |
| **Pages/Words/Endpoints** | 142 / 54K / 95 |
| **API version** | v1 (spec version 1.2.0) |
| **OpenAPI** | LIVE: bitmex.com/api/explorer/swagger.json (183KB); GitHub: api-connectors/swagger.json (272KB) |
| **Changelog** | bitmex.com/app/apiChangelog |
| **RSS** | bitmex.com/api_announcement/feed |
| **Status** | status.bitmex.com (Statuspage.io + Atom/RSS) |
| **Maintenance** | Regular: Tue + Thu 06:00–09:00 UTC |

### BitMart

| Field | Value |
|-------|-------|
| **Docs URL** | https://developer-pro.bitmart.com/ (Custom SPA) |
| **Platform** | Custom SPA |
| **Sections** | 2 (spot, futures) |
| **Pages/Words/Endpoints** | 2 / 73K / 0 |
| **Postman** | Official: Spot (45KB) + Futures (49KB) at bitmartexchange/bitmart-postman-api |
| **Changelog** | Inline at developer-pro.bitmart.com/en/spot/#changelog |
| **GitHub** | github.com/bitmartexchange (5 SDK repos) |
| **Status** | None (has /system/service API) |
| **Note** | 73K words, 0 endpoints — MOST URGENT extraction target |

### WhiteBIT

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.whitebit.com/ (Docusaurus/Next.js) |
| **Platform** | Docusaurus |
| **Sections** | 1 (v4) |
| **Pages/Words/Endpoints** | 161 / 95K / 0 |
| **OpenAPI** | None |
| **Changelog** | docs.whitebit.com/changelog/ + changelog.json in GitHub repo |
| **GitHub** | github.com/whitebit-exchange (13 repos, Docusaurus source) |
| **Status** | status.whitebit.com (OpenStatus) |
| **CCXT gap** | 110 CCXT endpoints, 0 in DB — largest gap |

### Bitbank

| Field | Value |
|-------|-------|
| **Docs URL** | https://github.com/bitbankinc/bitbank-api-docs (GitHub Markdown) |
| **Platform** | GitHub Markdown |
| **Sections** | 1 (rest) |
| **Pages/Words/Endpoints** | 154 / 212K / 0 |
| **Changelog** | CHANGELOG.md (latest 2026-02-18) |
| **Commit feed** | github.com/bitbankinc/bitbank-api-docs/commits/master.atom |
| **GitHub** | github.com/bitbankinc (13 repos, including MCP server) |
| **Note** | Dual-language (EN + JP). Japanese is primary. PubNub for private streaming. |

### MercadoBitcoin

| Field | Value |
|-------|-------|
| **Docs URL** | https://api.mercadobitcoin.net/api/v4/docs (Swagger UI) |
| **Platform** | Swagger UI |
| **Sections** | 1 (v4) |
| **Pages/Words/Endpoints** | 1 / 16K / 31 |
| **API version** | v4 (REST), v0 (WebSocket) |
| **OpenAPI** | api.mercadobitcoin.net/api/v4/docs/swagger.yaml (76KB, LIVE) |
| **WebSocket** | ws.mercadobitcoin.net/docs/v0/ (Docsify, JS-rendered) |
| **Status** | status.mercadobitcoin.com.br (JSON API at /summary.json) |
| **CCXT ID** | `mercado` (remapped from `mercadobitcoin`) |

### Hyperliquid

| Field | Value |
|-------|-------|
| **Docs URL** | https://hyperliquid.gitbook.io/hyperliquid-docs/ (GitBook) |
| **Platform** | GitBook |
| **Sections** | 1 (api) |
| **Pages/Words/Endpoints** | 32 / 26K / 75 |
| **OpenAPI** | Community: bowen31337/hyperliquid-openapi (38KB OpenAPI 3.1.0 + 22KB AsyncAPI 3.0.0) |
| **GitHub** | github.com/hyperliquid-dex (11 repos: Python SDK, Rust SDK, ts-examples) |
| **CCXT** | Module exists but NOT in project's CCXT_EXCHANGE_MAP |
| **Note** | Technically a DEX (on-chain CLOB). Classification contested (few validators). |

---

## 3. DEX Protocols

### GRVT

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.grvt.io/ |
| **Sections** | 1 (api) |
| **Pages/Words/Endpoints** | 235 / 254K / 0 |
| **OpenAPI** | gravity-technologies/api-spec/apispec.json (460KB) — IMPORTABLE |
| **GitHub** | github.com/gravity-technologies |

### Paradex

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.paradex.trade/ |
| **Sections** | 1 (api) |
| **Pages/Words/Endpoints** | 410 / 237K / 0 |
| **OpenAPI** | api.prod.paradex.trade/swagger/doc.json (307KB, 78 paths) — IMPORTABLE |
| **AsyncAPI** | WebSocket spec in tradeparadex docs repo |
| **GitHub** | github.com/tradeparadex |

### Lighter

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.lighter.xyz/ |
| **Sections** | 1 (docs) |
| **Pages/Words/Endpoints** | 19 / 10K / 0 |
| **OpenAPI** | elliottech/lighter-python/openapi.json (225KB, 57 paths) — IMPORTABLE |
| **GitHub** | github.com/elliottech |

### ApeX Protocol

| Field | Value |
|-------|-------|
| **Docs URL** | https://api-docs.pro.apex.exchange/ (GitBook) |
| **Sections** | 1 (api) |
| **Pages/Words/Endpoints** | 5 / 134K / 0 |
| **v1 docs** | api-docs.apex.exchange/ (StarkEx, deprecated) |
| **GitHub** | github.com/ApeX-Protocol |

### Aster (ex-ApolloX)

| Field | Value |
|-------|-------|
| **Docs URL** | https://developers.aster.trade/ |
| **Sections** | 1 (api) |
| **Pages/Words/Endpoints** | 2 / 15K / 0 |
| **Note** | Rebrand of ApolloX (NOT edgeX). Thin documentation. |

### Aevo

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.aevo.xyz/ + https://api-docs.aevo.xyz/ |
| **Sections** | 1 (api) |
| **Pages/Words/Endpoints** | 144 / 79K / 0 |
| **GitHub** | github.com/aevoxyz |
| **CCXT** | `aevo` |

### GMX

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.gmx.io/ (GitBook) |
| **Sections** | 1 (docs) |
| **Pages/Words/Endpoints** | 64 / 78K / 0 |
| **GitHub** | github.com/gmx-io |
| **Note** | No REST API — smart contract + subgraph only |

### Drift

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.drift.trade/ + drift-labs.github.io/v2-teacher/ |
| **Sections** | 1 (docs) |
| **Pages/Words/Endpoints** | 132 / 218K / 0 |
| **GitHub** | github.com/drift-labs |
| **Note** | Solana-based, SDK-driven |

### Perpetual Protocol — DEFUNCT

| Field | Value |
|-------|-------|
| **Status** | DEFUNCT — docs.perp.com DNS dead (NXDOMAIN), token delisted |
| **Recommendation** | Remove from registry or mark as defunct |

### Gains Network (gTrade)

| Field | Value |
|-------|-------|
| **Docs URL** | https://gains-network.gitbook.io/docs-home/ |
| **Sections** | 1 (docs) |
| **Pages/Words/Endpoints** | 114 / 78K / 0 |
| **Note** | No REST API — smart contracts + oracle price feeds |

### Kwenta

| Field | Value |
|-------|-------|
| **Docs URL** | https://docs.kwenta.io/ |
| **Sections** | 1 (docs) |
| **Pages/Words/Endpoints** | 20 / 9K / 0 |
| **Note** | No REST API — built on Synthetix V3 perps |

---

## 4. Reference

### CCXT

| Field | Value |
|-------|-------|
| **Main docs** | https://docs.ccxt.com/ |
| **ReadTheDocs** | https://ccxt.readthedocs.io/ (additional, possibly stale) |
| **Wiki** | github.com/ccxt/ccxt/wiki (source: /blob/master/wiki/) |
| **Sections** | 1 (manual) |
| **Pages/Words** | 189 / 768K |
| **GitHub** | github.com/ccxt (33K+ stars) |
| **Releases RSS** | github.com/ccxt/ccxt/releases.atom (near-daily) |
| **Key files** | exchanges.json (master registry), ts/src/{exchange}.ts (describe() methods), ts/src/abstract/{exchange}.ts (auto-generated API surface) |
| **Bug** | ccxt_xref.py `_extract_ccxt_endpoints()` only handles list-based API trees, not dict-of-dicts (affects 15/20 exchanges) |

---

## 5. Recommended Additions

### Orderly Network — RECOMMEND ADD

- **Type**: DEX infrastructure (powers WOOFi Pro, LogX, etc.)
- **Docs**: docs.orderly.network
- **OpenAPI**: evm.openapi.yaml (461KB) — large importable spec, likely 100+ endpoints
- **SDKs**: orderly-sdk-js, orderly-sdk-py
- **Rationale**: Active protocol, large spec, immediate endpoint value

### Nado — RECOMMEND ADD

- **Type**: DEX perpetual futures
- **Docs**: docs.nado.trade
- **SDKs**: 3 languages (Python, TypeScript, Go)
- **Changelog**: Active
- **Rationale**: Active development, multiple SDK languages, growing protocol

### Bluefin — RECOMMEND ADD

- **Type**: DEX perpetual futures (Sui)
- **Docs**: bluefin-exchange.readme.io (ReadMe.io)
- **Endpoints**: ~22 REST endpoints
- **GitHub**: github.com/fireflyprotocol (was Firefly)
- **Rationale**: ReadMe.io platform (easy to crawl), active protocol

### Pacifica — RECOMMEND DEFER

- **Type**: DEX (emerging)
- **Status**: Insufficient documentation for crawling
- **Rationale**: Re-evaluate in next discovery cycle

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
- [ ] Developer portal / blog: ___
- [ ] Documentation platform: (ReadMe.io / Docusaurus / GitBook / Stoplight / Swagger / Custom)
- [ ] Rendering required: (static HTML / JS-rendered / SPA)

### Versioned APIs
- [ ] Current API version: ___
- [ ] Legacy versions still documented: ___
- [ ] Deprecation / migration notices URL: ___

### Changelogs & Updates
- [ ] API changelog URL: ___
- [ ] Changelog format: (RSS / Atom / HTML / Markdown / JSON / ReadMe.io)
- [ ] RSS/Atom feed URL (if exists): ___
- [ ] Update frequency: ___
- [ ] Telegram channel (if exists): ___
```

### Phase 2: Deep Discovery

```
### GitHub
- [ ] GitHub org URL: ___
- [ ] API docs repo: ___
- [ ] OpenAPI/Swagger spec file: ___
- [ ] Postman collection: ___
- [ ] Official SDK repos: ___
- [ ] GitHub Pages docs URL (if exists): ___
- [ ] Commit Atom feed URLs: ___

### Specs & Collections
- [ ] OpenAPI/Swagger JSON/YAML URL: ___
- [ ] Postman collection URL: ___
- [ ] AsyncAPI spec (WebSocket): ___
- [ ] GraphQL schema (if applicable): ___

### Discovery Files
- [ ] robots.txt findings: ___
- [ ] sitemap.xml findings: ___
- [ ] llms.txt (if exists): ___
- [ ] Hidden documentation paths: ___

### CCXT
- [ ] CCXT exchange ID: ___
- [ ] Added to CCXT_EXCHANGE_MAP in ccxt_xref.py: ___
```

### Phase 3: Registration

```
### Status & Incidents
- [ ] API status page URL: ___
- [ ] Status page API/feed URL: ___

### Registry Entry
- [ ] Added to data/exchanges.yaml
- [ ] Seeds configured
- [ ] Allowed domains set
- [ ] Sitemap URL (if available)
- [ ] scope_prefixes (if sharing sitemap)
- [ ] render_mode (auto if JS-rendered)
- [ ] doc_sources with import URLs
- [ ] Inventory generated (cex-api-docs fetch-inventory)
- [ ] Pages synced (cex-api-docs sync)
- [ ] OpenAPI/Postman imported (if available)
```

### Probing Checklist

```
### URL Probing
- [ ] {domain}/robots.txt
- [ ] {domain}/sitemap.xml
- [ ] {domain}/llms.txt
- [ ] {domain}/openapi.json, /swagger.json, /api-docs
- [ ] docs.{domain}/sitemap.xml
- [ ] developers.{domain}/
- [ ] api.{domain}/
- [ ] GitHub: site:github.com "{exchange}" openapi OR swagger
- [ ] Postman: site:postman.com "{exchange}" API
- [ ] ReadMe.io: {exchange}.readme.io
```

---

## 7. Implementation Priorities

### Priority 1: Import Available Specs (immediate endpoint value)

| Exchange | Spec | Est. Endpoints | Command |
|----------|------|---------------:|---------|
| KuCoin | 23 OpenAPI files in universal-sdk | 200+ | Import each spec from GitHub raw URLs |
| GRVT | apispec.json (460KB) | 100+ | `import-openapi --exchange grvt --section api` |
| Coinbase Prime | openapi.yaml (live URL) | 98 | `import-openapi --exchange coinbase --section prime` |
| Paradex | swagger/doc.json (live URL) | 78 | `import-openapi --exchange paradex --section api` |
| Lighter | openapi.json (GitHub) | 57 | `import-openapi --exchange lighter --section docs` |
| dYdX | swagger.json (GitHub) | 50+ | `import-openapi --exchange dydx --section docs` |
| BitMart | Postman Spot + Futures (official) | 80+ | `import-postman --exchange bitmart --section spot/futures` |

**Total: ~660+ new endpoints from existing specs**

### Priority 2: Community Specs (verify first)

| Exchange | Spec | Est. Endpoints |
|----------|------|---------------:|
| Coinbase Exchange | metalocal/coinbase-exchange-api | 39 |
| Kraken Futures | kanekoshoyu/exchange-collection | 51 |
| Upbit | ujhin/upbit-client/swagger.yaml | 92 |
| Hyperliquid | bowen31337/hyperliquid-openapi | 38 |

### Priority 3: New Exchange Registration

| Exchange | Rationale |
|----------|-----------|
| Orderly Network | 461KB OpenAPI spec, active protocol |
| Bluefin | ReadMe.io (easy crawl), ~22 endpoints |
| Nado | Active changelog, 3 SDKs |

### Priority 4: Changelog Monitoring Setup

| Exchange | Feed Type | URL |
|----------|-----------|-----|
| Upbit (EN) | RSS | global-docs.upbit.com/changelog.rss |
| Upbit (KR) | RSS | docs.upbit.com/kr/changelog.rss |
| Bithumb | RSS | apidocs.bithumb.com/changelog.rss |
| Coinone | RSS | docs.coinone.co.kr/changelog.rss |
| BitMEX | RSS | bitmex.com/api_announcement/feed |
| BitMEX status | Atom/RSS | status.bitmex.com/history.atom |
| dYdX releases | Atom | github.com/dydxprotocol/v4-chain/releases.atom |
| CCXT releases | Atom | github.com/ccxt/ccxt/releases.atom |
| Bitbank commits | Atom | github.com/bitbankinc/bitbank-api-docs/commits/master.atom |
| Binance forum | RSS | dev.binance.vision/latest.rss |

### Priority 5: Registry Cleanup

- Remove Perpetual Protocol (DEFUNCT — DNS dead)
- Add Hyperliquid to CCXT_EXCHANGE_MAP
- Add dYdX to CCXT_EXCHANGE_MAP
- Fix ccxt_xref.py dict-of-dicts extraction bug (affects 15/20 exchanges)

---

## 8. Confirmed Non-Existent Sources

These were systematically searched for and confirmed to NOT exist, saving future time:

| What | Exchanges Checked | Result |
|------|-------------------|--------|
| Official OpenAPI/Swagger specs | OKX, Bitget, Gate.io, HTX, Crypto.com, Bitfinex, WhiteBIT, Bitbank, Coinone, Korbit, Bithumb | None found |
| Public RSS/Atom for API changelogs | Binance, OKX, Bybit, Bitget, Gate.io, KuCoin, HTX, Crypto.com, Bitstamp, Kraken, Coinbase | None (only forum/status/commit feeds) |
| Dedicated developer forums | All 35 | Dead or nonexistent (Discord/Telegram replaced them) |
| Newsletter archives | All 35 | None exist |
| Bitfinex changelog RSS | Bitfinex | 404 (ReadMe.io may have changed paths) |
| Bybit status page | Bybit | bybit.statuspage.io is FRAUDULENT (phishing) |
| Binance sitemap | Binance | 404 (documented gotcha) |
| Binance robots.txt | Binance | 404 |
| Gate.io raw OpenAPI spec | Gate.io | Not publicly downloadable despite OpenAPI-first architecture |
| Kraken official OpenAPI | Kraken | krakenfx/api-specs repo exists but is EMPTY |
| Coinbase Advanced Trade spec | Coinbase | Not published |
| INTX OpenAPI at live URL | Coinbase | api.international.coinbase.com/v1/openapi.yaml returns 404 |
| Bitstamp direct OpenAPI download | Bitstamp | /openapi.json blocked by Incapsula WAF |
