# Importable OpenAPI/Postman Specs for Zero-Endpoint Sections

**Date**: 2026-03-06
**Context**: 28 of 61 sections have 0 structured endpoints. This research identifies which have importable specs available.

## Confirmed Importable (3)

### Coinbase Prime — Official OpenAPI
- **URL**: `https://api.prime.coinbase.com/v1/openapi.yaml`
- **Operations**: 98
- **Section**: `coinbase/prime` (43 pages, 58,327 words, 0 endpoints)
- **Status**: Official, published by Coinbase
- **Import command**: `xdocs import-openapi --exchange coinbase --section prime --url https://api.prime.coinbase.com/v1/openapi.yaml --docs-dir ./cex-docs --continue-on-error`

### Paradex — Official Swagger
- **URL**: `https://api.prod.paradex.trade/swagger/doc.json`
- **Operations**: 78 paths
- **Section**: `paradex/api` (410 pages, 237,243 words, 0 endpoints)
- **Status**: Official, served from production API
- **Import command**: `xdocs import-openapi --exchange paradex --section api --url https://api.prod.paradex.trade/swagger/doc.json --docs-dir ./cex-docs --continue-on-error`

### Lighter — SDK OpenAPI
- **URL**: `https://raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json`
- **Operations**: 57 paths
- **Section**: `lighter/docs` (19 pages, 9,932 words, 0 endpoints)
- **Status**: In official Python SDK repo
- **Import command**: `xdocs import-openapi --exchange lighter --section docs --url https://raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json --docs-dir ./cex-docs --continue-on-error`

## Community Specs Worth Attempting (2)

### Coinbase Exchange — Community OpenAPI
- **URL**: `https://raw.githubusercontent.com/metalocal/coinbase-exchange-api/main/api.oas3.json`
- **Operations**: 39 paths
- **Section**: `coinbase/exchange` (33 pages, 47,199 words, 0 endpoints)
- **Status**: Community-maintained, may be outdated
- **Risk**: Needs manual verification against live docs

### Kraken Futures — Community Collection
- **URL**: `https://github.com/kanekoshoyu/exchange-collection` (contains Kraken futures spec)
- **Operations**: ~51 paths
- **Section**: `kraken/futures` (47 pages, 21,998 words, 0 endpoints)
- **Status**: Community collection, last updated ~2024
- **Note**: Kraken official repo `krakenfx/api-specs` exists but is currently empty

## Not Found / No Spec Available (23 sections)

| Section | Pages | Words | Notes |
|---------|------:|------:|-------|
| okx/websocket | 0 | 0 | WebSocket, no REST spec |
| okx/broker | 1 | 7,678 | Embedded in OKX single page |
| okx/changelog | 1 | 113,973 | Changelog, not API spec |
| bybit/websocket | 0 | 0 | WebSocket, no REST spec |
| htx/derivatives | 1 | 124,166 | No known spec |
| gmx/docs | 64 | 78,360 | DEX — smart contracts, no REST |
| drift/docs | 132 | 217,523 | DEX — SDK-based, no REST spec |
| aevo/api | 144 | 79,208 | No public spec found |
| perp/docs | 36 | 43,169 | DEX — smart contracts |
| gains/docs | 114 | 77,664 | DEX — smart contracts |
| kwenta/docs | 20 | 8,929 | DEX — smart contracts |
| ccxt/manual | 189 | 767,751 | Reference wiki, not an exchange |
| upbit/rest_ko | 2 | 660 | Korean duplicate of rest_en |
| bithumb/rest_en | 1 | 309 | Playwright-rendered translation |
| kraken/spot | 18 | 13,921 | No spec found (official repo empty) |
| coinbase/advanced_trade | 1 | 314 | Thin crawl, may have spec on re-crawl |
| bitmart/spot | 1 | 38,695 | Single-page SPA, no known spec |
| bitmart/futures | 1 | 34,594 | Single-page SPA, no known spec |
| whitebit/v4 | 161 | 95,382 | No public spec found (likely exists) |
| bitbank/rest | 154 | 211,597 | No public spec found |
| aster/api | 2 | 14,943 | Stub docs, no spec |
| apex/api | 5 | 133,667 | No public spec found |
| grvt/api | 235 | 254,253 | No public spec found |

## Summary

- **3 confirmed importable specs** → would add ~233 endpoints (Coinbase Prime 98 + Paradex 78 + Lighter 57)
- **2 community specs** → would add ~90 endpoints if viable (Coinbase Exchange 39 + Kraken Futures 51)
- **23 sections** have no known importable spec — need manual extraction or further discovery in M2/M3
