# CEX API Docs — Coverage Audit

Generated: 2026-03-06 03:15

- **Exchanges in registry**: 35
- **Sections in registry**: 61
- **Total pages stored**: 5,716
- **Total words**: 7,760,059
- **Total structured endpoints**: 3,603
- **Open review items**: 7,496

## 1. Per-Exchange Summary

| exchange_id | display_name | sections | pages | words | endpoints | sitemap | openapi | render | platform |
|---|---|---:|---:|---:|---:|---|---|---|---|
| binance | Binance | 9 | 1,802 | 1,559,587 | 1425 | Y | Y | N | Custom |
| okx | OKX | 4 | 3 | 346,296 | 313 | Y | Y | N | Custom |
| bybit | Bybit | 2 | 308 | 291,679 | 129 | Y | Y | N | GitHub Pages |
| bitget | Bitget | 5 | 180 | 156,891 | 233 | Y | Y | N | Custom |
| gateio | Gate.io | 1 | 1 | 182,339 | 363 | N | N | Y | Custom |
| kucoin | KuCoin | 1 | 429 | 1,043,457 | 70 | N | Y | Y | Custom |
| htx | HTX | 4 | 4 | 410,801 | 290 | N | N | Y | GitHub Pages |
| cryptocom | Crypto.com | 1 | 1 | 58,832 | 63 | N | N | Y | Custom |
| bitstamp | Bitstamp | 1 | 1 | 37,246 | 82 | N | Y | Y | Custom |
| bitfinex | Bitfinex | 1 | 118 | 55,700 | 81 | N | N | Y | ReadMe.io |
| dydx | dYdX | 1 | 271 | 133,657 | 34 | N | N | Y | GitBook |
| hyperliquid | Hyperliquid | 1 | 32 | 26,109 | 75 | Y | N | N | GitBook |
| gmx | GMX | 1 | 64 | 78,360 | 0 | N | N | Y | Docusaurus |
| drift | Drift | 1 | 132 | 217,523 | 0 | N | N | Y | GitBook |
| aevo | Aevo | 1 | 144 | 79,208 | 0 | N | N | Y | ReadMe.io |
| perp | Perpetual Protocol | 1 | 36 | 43,169 | 0 | Y | N | N | Docusaurus |
| gains | Gains Network | 1 | 114 | 77,664 | 0 | N | N | Y | GitBook |
| kwenta | Kwenta | 1 | 20 | 8,929 | 0 | N | N | Y | GitBook |
| lighter | Lighter | 1 | 19 | 9,932 | 0 | N | N | Y | GitBook |
| ccxt | CCXT | 1 | 189 | 767,751 | 0 | N | N | Y | GitHub |
| upbit | Upbit | 2 | 304 | 305,960 | 44 | N | N | Y | ReadMe.io |
| bithumb | Bithumb | 2 | 150 | 74,433 | 36 | N | N | Y | ReadMe.io |
| coinone | Coinone | 1 | 91 | 67,036 | 22 | N | N | Y | Custom |
| korbit | Korbit | 1 | 2 | 25,230 | 32 | N | N | Y | Custom |
| kraken | Kraken | 2 | 65 | 35,919 | 0 | Y | N | N | Docusaurus |
| coinbase | Coinbase | 4 | 78 | 106,118 | 49 | Y | Y | Y | Custom (CDP) |
| bitmex | BitMEX | 1 | 142 | 53,731 | 95 | Y | Y | N | Docusaurus |
| bitmart | BitMart | 2 | 2 | 73,289 | 0 | N | N | Y | Custom |
| whitebit | WhiteBIT | 1 | 161 | 95,382 | 0 | Y | N | N | Docusaurus |
| bitbank | Bitbank | 1 | 154 | 211,597 | 0 | N | N | N | GitHub |
| mercadobitcoin | MercadoBitcoin | 1 | 1 | 15,834 | 31 | N | Y | Y | Swagger UI |
| aster | Aster | 1 | 2 | 14,943 | 0 | N | N | Y | GitBook |
| apex | ApeX Pro | 1 | 5 | 133,667 | 0 | N | N | Y | ReadMe.io |
| grvt | GRVT | 1 | 235 | 254,253 | 0 | N | N | N | GitHub |
| paradex | Paradex | 1 | 410 | 237,243 | 0 | N | N | Y | GitBook |

## 2. Sections With 0 Endpoints

These sections have crawled pages but no structured endpoint records in the database.

| exchange_id | section_id | pages | words | known_single_page | openapi_potential | notes |
|---|---|---:|---:|---|---|---|
| okx | websocket | 0 | 0 | Y | N/A | Shares OKX docs page |
| okx | broker | 1 | 7,678 | Y | High | Shares OKX docs page |
| okx | changelog | 1 | 113,973 | Y | N/A | Shares OKX docs page |
| bybit | websocket | 0 | 0 | N | N/A | WebSocket section (not REST) |
| htx | derivatives | 1 | 124,166 | Y | Medium | Single-page doc (124K words) |
| gmx | docs | 64 | 78,360 | N | Low |  |
| drift | docs | 132 | 217,523 | N | Low |  |
| aevo | api | 144 | 79,208 | N | Low |  |
| perp | docs | 36 | 43,169 | N | Low |  |
| gains | docs | 114 | 77,664 | N | Low |  |
| kwenta | docs | 20 | 8,929 | N | Low |  |
| lighter | docs | 19 | 9,932 | N | Low |  |
| ccxt | manual | 189 | 767,751 | N | N/A | Reference wiki, not an exchange API |
| upbit | rest_ko | 2 | 660 | N | Low |  |
| bithumb | rest_en | 1 | 309 | N | Low |  |
| kraken | spot | 18 | 13,921 | N | High |  |
| kraken | futures | 47 | 21,998 | N | High |  |
| coinbase | advanced_trade | 1 | 314 | N | High |  |
| coinbase | exchange | 33 | 47,199 | N | High |  |
| coinbase | prime | 43 | 58,327 | N | High |  |
| bitmart | spot | 1 | 38,695 | Y | Low | Single-page doc |
| bitmart | futures | 1 | 34,594 | Y | Low | Single-page doc |
| whitebit | v4 | 161 | 95,382 | N | Low |  |
| bitbank | rest | 154 | 211,597 | N | Low |  |
| aster | api | 2 | 14,943 | N | Low |  |
| apex | api | 5 | 133,667 | N | Low |  |
| grvt | api | 235 | 254,253 | N | Low |  |
| paradex | api | 410 | 237,243 | N | Low |  |

**Total sections with 0 endpoints: 28** (out of 61 total)

## 3. Sections With 0 or Thin Pages

Sections with 2 or fewer fetched pages that are NOT known single-page sites.

| exchange_id | section_id | fetched_pages | words | inventory_urls | inv_skipped | inv_errors | notes |
|---|---|---:|---:|---:|---:|---:|---|
| binance | copy_trading | 0 | 0 | 1853 | 1853 | 0 | No pages fetched |
| binance | portfolio_margin_pro | 0 | 0 | 28 | 28 | 0 | No pages fetched |
| bybit | websocket | 0 | 0 | 1 | 1 | 0 | No pages fetched |
| upbit | rest_ko | 2 | 660 | 60 | 57 | 0 | scope_dedup skipped 57 |
| bithumb | rest_en | 1 | 309 | 1 | 0 | 0 |  |
| coinbase | advanced_trade | 1 | 314 | 1 | 0 | 0 |  |
| coinbase | intx | 1 | 278 | 1 | 0 | 0 |  |
| aster | api | 2 | 14,943 | 2 | 0 | 0 |  |

**Total thin sections: 8**

## 4. Coverage Gap Summary

### Tier 1: Well-Covered (50+ endpoints, OpenAPI/Postman import)

| exchange | pages | words | endpoints | import |
|---|---:|---:|---:|---|
| Binance | 1,802 | 1,559,587 | 1425 | OpenAPI+Postman |
| OKX | 3 | 346,296 | 313 | OpenAPI+Postman |
| Bitget | 180 | 156,891 | 233 | OpenAPI+Postman |
| Bybit | 308 | 291,679 | 129 | OpenAPI+Postman |
| BitMEX | 142 | 53,731 | 95 | OpenAPI+Postman |
| Bitstamp | 1 | 37,246 | 82 | OpenAPI+Postman |
| KuCoin | 429 | 1,043,457 | 70 | OpenAPI+Postman |

### Tier 2: Moderate Coverage (endpoints extracted, no bulk import)

| exchange | pages | words | endpoints | notes |
|---|---:|---:|---:|---|
| Gate.io | 1 | 182,339 | 363 |  |
| HTX | 4 | 410,801 | 290 |  |
| Bitfinex | 118 | 55,700 | 81 |  |
| Hyperliquid | 32 | 26,109 | 75 |  |
| Crypto.com | 1 | 58,832 | 63 |  |
| Coinbase | 78 | 106,118 | 49 | < 50 endpoints |
| Upbit | 304 | 305,960 | 44 | < 50 endpoints |
| Bithumb | 150 | 74,433 | 36 | < 50 endpoints |
| dYdX | 271 | 133,657 | 34 | < 50 endpoints |
| Korbit | 2 | 25,230 | 32 | < 50 endpoints |
| MercadoBitcoin | 1 | 15,834 | 31 | < 50 endpoints |
| Coinone | 91 | 67,036 | 22 | < 50 endpoints |

### Tier 3: Pages Only (crawled but no endpoints extracted)

| exchange | pages | words | sections | notes |
|---|---:|---:|---:|---|
| Paradex | 410 | 237,243 | 1 | DEX protocol |
| GRVT | 235 | 254,253 | 1 | DEX protocol |
| WhiteBIT | 161 | 95,382 | 1 |  |
| Bitbank | 154 | 211,597 | 1 |  |
| Aevo | 144 | 79,208 | 1 |  |
| Drift | 132 | 217,523 | 1 | DEX protocol |
| Gains Network | 114 | 77,664 | 1 | DEX protocol |
| Kraken | 65 | 35,919 | 2 |  |
| GMX | 64 | 78,360 | 1 | DEX protocol |
| Perpetual Protocol | 36 | 43,169 | 1 | DEX protocol |
| Kwenta | 20 | 8,929 | 1 | DEX protocol |
| Lighter | 19 | 9,932 | 1 | DEX protocol |

### Tier 4: Under-Covered (few pages, no endpoints)

| exchange | pages | words | sections | notes |
|---|---:|---:|---:|---|
| BitMart | 2 | 73,289 | 2 |  |
| Aster | 2 | 14,943 | 1 | DEX, stub docs |
| ApeX Pro | 5 | 133,667 | 1 |  |

### Reference (non-exchange)

| name | pages | words | notes |
|---|---:|---:|---|
| CCXT | 189 | 767,751 | Cross-reference wiki |

## 5. Detailed Section-Level Breakdown

| exchange_id | section_id | pages | words | endpoints | inv_fetched | inv_skipped | inv_errors | import_type |
|---|---|---:|---:|---:|---:|---:|---:|---|
| binance | spot | 93 | 273,306 | 703 | 93 | 0 | 0 | openapi, postman |
| binance | futures_usdm | 167 | 96,789 | 192 | 167 | 0 | 0 | openapi, postman |
| binance | futures_coinm | 121 | 63,034 | 130 | 121 | 0 | 0 | openapi, postman |
| binance | portfolio_margin | 122 | 79,825 | 225 | 122 | 0 | 0 | openapi, postman |
| binance | options | 74 | 29,544 | 46 | 74 | 0 | 0 | openapi |
| binance | margin_trading | 80 | 53,135 | 59 | 80 | 0 | 0 | postman |
| binance | wallet | 1145 | 963,954 | 47 | 1200 | 653 | 0 | postman |
| binance | copy_trading | 0 | 0 | 2 | 0 | 1853 | 0 | postman |
| binance | portfolio_margin_pro | 0 | 0 | 21 | 0 | 28 | 0 | postman |
| okx | rest | 1 | 224,645 | 313 | 1 | 0 | 0 | openapi |
| okx | websocket | 0 | 0 | 0 | 0 | 1 | 0 | -- |
| okx | broker | 1 | 7,678 | 0 | 1 | 0 | 0 | -- |
| okx | changelog | 1 | 113,973 | 0 | 1 | 0 | 0 | -- |
| bybit | v5 | 308 | 291,679 | 129 | 308 | 0 | 0 | postman |
| bybit | websocket | 0 | 0 | 0 | 0 | 1 | 0 | -- |
| bitget | v2 | 35 | 24,199 | 102 | 35 | 0 | 0 | openapi |
| bitget | copy_trading | 48 | 46,615 | 45 | 51 | 0 | 0 | -- |
| bitget | margin | 53 | 49,639 | 45 | 53 | 0 | 0 | -- |
| bitget | earn | 28 | 12,634 | 27 | 28 | 0 | 0 | -- |
| bitget | broker | 16 | 23,804 | 14 | 16 | 0 | 0 | -- |
| gateio | v4 | 1 | 182,339 | 363 | 1 | 0 | 0 | -- |
| kucoin | spot | 429 | 1,043,457 | 70 | 434 | 0 | 0 | openapi |
| htx | spot | 1 | 83,921 | 87 | 1 | 0 | 0 | -- |
| htx | derivatives | 1 | 124,166 | 0 | 1 | 0 | 0 | -- |
| htx | coin_margined_swap | 1 | 72,641 | 72 | 1 | 0 | 0 | -- |
| htx | usdt_swap | 1 | 130,073 | 131 | 1 | 0 | 0 | -- |
| cryptocom | exchange | 1 | 58,832 | 63 | 1 | 0 | 0 | -- |
| bitstamp | rest | 1 | 37,246 | 82 | 1 | 0 | 0 | openapi |
| bitfinex | v2 | 118 | 55,700 | 81 | 118 | 0 | 0 | -- |
| dydx | docs | 271 | 133,657 | 34 | 284 | 0 | 0 | -- |
| hyperliquid | api | 32 | 26,109 | 75 | 32 | 0 | 0 | -- |
| gmx | docs | 64 | 78,360 | 0 | 122 | 0 | 0 | -- |
| drift | docs | 132 | 217,523 | 0 | 134 | 0 | 0 | -- |
| aevo | api | 144 | 79,208 | 0 | 144 | 0 | 0 | -- |
| perp | docs | 36 | 43,169 | 0 | 36 | 0 | 0 | -- |
| gains | docs | 114 | 77,664 | 0 | 118 | 0 | 0 | -- |
| kwenta | docs | 20 | 8,929 | 0 | 20 | 0 | 0 | -- |
| lighter | docs | 19 | 9,932 | 0 | 20 | 0 | 0 | -- |
| ccxt | manual | 189 | 767,751 | 0 | 204 | 0 | 0 | -- |
| upbit | rest_en | 302 | 305,300 | 44 | 464 | 0 | 0 | -- |
| upbit | rest_ko | 2 | 660 | 0 | 3 | 57 | 0 | -- |
| bithumb | rest | 149 | 74,124 | 36 | 304 | 0 | 0 | -- |
| bithumb | rest_en | 1 | 309 | 0 | 1 | 0 | 0 | -- |
| coinone | rest | 91 | 67,036 | 22 | 107 | 0 | 0 | -- |
| korbit | rest | 2 | 25,230 | 32 | 2 | 0 | 0 | -- |
| kraken | spot | 18 | 13,921 | 0 | 19 | 0 | 0 | -- |
| kraken | futures | 47 | 21,998 | 0 | 48 | 0 | 0 | -- |
| coinbase | advanced_trade | 1 | 314 | 0 | 1 | 0 | 0 | -- |
| coinbase | exchange | 33 | 47,199 | 0 | 34 | 0 | 0 | -- |
| coinbase | intx | 1 | 278 | 49 | 1 | 0 | 0 | openapi |
| coinbase | prime | 43 | 58,327 | 0 | 44 | 0 | 0 | -- |
| bitmex | rest | 142 | 53,731 | 95 | 142 | 0 | 0 | openapi |
| bitmart | spot | 1 | 38,695 | 0 | 1 | 0 | 0 | -- |
| bitmart | futures | 1 | 34,594 | 0 | 1 | 0 | 0 | -- |
| whitebit | v4 | 161 | 95,382 | 0 | 161 | 0 | 0 | -- |
| bitbank | rest | 154 | 211,597 | 0 | 154 | 0 | 0 | -- |
| mercadobitcoin | v4 | 1 | 15,834 | 31 | 1 | 0 | 0 | openapi |
| aster | api | 2 | 14,943 | 0 | 2 | 0 | 0 | -- |
| apex | api | 5 | 133,667 | 0 | 5 | 0 | 0 | -- |
| grvt | api | 235 | 254,253 | 0 | 247 | 0 | 0 | -- |
| paradex | api | 410 | 237,243 | 0 | 422 | 0 | 1 | -- |

## 6. OpenAPI/Postman Import Coverage

Which exchanges have structured imports, and which sections are covered.

- **Exchanges with OpenAPI imports**: 8 (binance, bitget, bitmex, bitstamp, coinbase, kucoin, mercadobitcoin, okx)
- **Exchanges with Postman imports**: 2 (binance, bybit)

| exchange | section | openapi | postman | endpoint_count |
|---|---|---|---|---:|
| binance | copy_trading | N | Y | 2 |
| binance | futures_coinm | Y | Y | 130 |
| binance | futures_usdm | Y | Y | 192 |
| binance | margin_trading | N | Y | 59 |
| binance | options | Y | N | 46 |
| binance | portfolio_margin | Y | Y | 225 |
| binance | portfolio_margin_pro | N | Y | 21 |
| binance | spot | Y | Y | 703 |
| binance | wallet | N | Y | 47 |
| bitget | v2 | Y | N | 102 |
| bitmex | rest | Y | N | 95 |
| bitstamp | rest | Y | N | 82 |
| bybit | v5 | N | Y | 129 |
| coinbase | intx | Y | N | 49 |
| kucoin | futures | Y | N | 54 |
| kucoin | spot | Y | N | 70 |
| mercadobitcoin | v4 | Y | N | 31 |
| okx | rest | Y | N | 313 |

## 7. Observations and Recommendations

### High-Priority Gaps

1. **Bybit websocket section**: Inventory has 1 entry, 0 fetched (skipped). WebSocket docs may need separate crawl strategy.
2. **Binance copy_trading/portfolio_margin_pro/wallet**: Large inventories but heavy scope dedup skipping (1,853 copy_trading URLs scoped out). Verify scope_prefixes are correct.
3. **KuCoin futures**: Only 1 page fetched out of 434 inventory URLs (433 skipped). Likely scope overlap with spot section.
4. **Upbit rest_ko**: Only 2 pages fetched out of 60 inventory entries (57 skipped). Scope_prefixes may be too narrow.
5. **Coinbase advanced_trade/intx**: Only 1 page each despite having scope_prefixes configured. May need re-crawl.
6. **KuCoin futures endpoints orphaned**: 54 endpoints exist in the DB under `kucoin/futures` (via OpenAPI import) but KuCoin has only a `spot` section in the registry. The futures inventory (434 URLs) had 433 entries skipped by scope dedup. Consider adding a `futures` section to the registry or verifying that spot pages cover futures endpoints.

### Missing Endpoint Extraction

The following CEX exchanges have pages crawled but **0 structured endpoints** and are not covered by OpenAPI/Postman import:

- **grvt/api**: 235 pages, 254,253 words
- **paradex/api**: 410 pages, 237,243 words
- **bitbank/rest**: 154 pages, 211,597 words
- **apex/api**: 5 pages, 133,667 words
- **htx/derivatives**: 1 pages, 124,166 words
- **whitebit/v4**: 161 pages, 95,382 words
- **aevo/api**: 144 pages, 79,208 words
- **coinbase/prime**: 43 pages, 58,327 words
- **coinbase/exchange**: 33 pages, 47,199 words
- **bitmart/spot**: 1 pages, 38,695 words
- **bitmart/futures**: 1 pages, 34,594 words
- **kraken/futures**: 47 pages, 21,998 words
- **aster/api**: 2 pages, 14,943 words
- **kraken/spot**: 18 pages, 13,921 words
- **okx/broker**: 1 pages, 7,678 words
- **upbit/rest_ko**: 2 pages, 660 words
- **coinbase/advanced_trade**: 1 pages, 314 words
- **bithumb/rest_en**: 1 pages, 309 words

### DEX Protocol Docs (No REST Endpoints Expected)

These are documentation sites for DeFi protocols. They may contain contract ABIs or SDK references rather than traditional REST endpoints:

- **gmx/docs**: 64 pages, 78,360 words
- **drift/docs**: 132 pages, 217,523 words
- **perp/docs**: 36 pages, 43,169 words
- **gains/docs**: 114 pages, 77,664 words
- **kwenta/docs**: 20 pages, 8,929 words
- **lighter/docs**: 19 pages, 9,932 words
- **aster/api**: 2 pages, 14,943 words
- **apex/api**: 5 pages, 133,667 words
- **grvt/api**: 235 pages, 254,253 words
- **paradex/api**: 410 pages, 237,243 words

### Single-Page Doc Sites

These exchanges serve their entire API reference from 1-2 HTML files. Low page counts are expected and correct:

- **bitmart/futures**: 1 page(s), 34,594 words -- Single-page doc
- **bitmart/spot**: 1 page(s), 38,695 words -- Single-page doc
- **bitstamp/rest**: 1 page(s), 37,246 words -- Single-page doc (37K words)
- **cryptocom/exchange**: 1 page(s), 58,832 words -- Single-page doc (58K words)
- **gateio/v4**: 1 page(s), 182,339 words -- 256K words in 1 HTML file
- **htx/coin_margined_swap**: 1 page(s), 72,641 words -- Single-page doc (72K words)
- **htx/derivatives**: 1 page(s), 124,166 words -- Single-page doc (124K words)
- **htx/spot**: 1 page(s), 83,921 words -- Single-page doc (83K words)
- **htx/usdt_swap**: 1 page(s), 130,073 words -- Single-page doc (130K words)
- **korbit/rest**: 2 page(s), 25,230 words -- Single-page doc (25K words)
- **mercadobitcoin/v4**: 1 page(s), 15,834 words -- Swagger UI (single page)
- **okx/broker**: 1 page(s), 7,678 words -- Shares OKX docs page
- **okx/changelog**: 1 page(s), 113,973 words -- Shares OKX docs page
- **okx/rest**: 1 page(s), 224,645 words -- 224K words in 1 HTML file
- **okx/websocket**: 0 page(s), 0 words -- Shares OKX docs page

