---
milestone: 6
phase: complete
updated: 2026-03-06T20:00:00Z
---
## Current State
M6: Exhaustive Audit & Methodology — COMPLETE

## Milestones
- [x] Milestone 1: Audit Existing Coverage & Gap Analysis — COMPLETE
- [x] Milestone 2: Deep Discovery — CEX Exchanges — COMPLETE
- [x] Milestone 3: Deep Discovery — DEX Protocols + CCXT — COMPLETE
- [x] Milestone 4: Compile Bible Document + Registry Updates — COMPLETE
- [x] Milestone 5: Verified Bible Refinement — COMPLETE
- [x] Milestone 6: Exhaustive Audit & Methodology — COMPLETE

## M6 Deliverables
- `docs/crawl-targets-bible.md` — 1,172 lines (v2), adds 8 missing exchanges, crawl methodology, trust framework
- Installed and evaluated: cloudscraper 1.2.71, crawl4ai 0.8.0, Playwright 1.58.0
- Tool evaluation: crawl4ai > Playwright > cloudscraper > requests (for anti-bot sites)

## M6 Key Findings
### Missing Exchanges (8)
- MEXC (~$3.59B daily, CCXT certified) — CRITICAL
- BingX (~$6.5B futures, CCXT certified) — CRITICAL
- Deribit (~$1B derivatives, Coinbase-owned but separate API) — HIGH
- Backpack (~$1.5B futures, has OpenAPI, CCXT) — HIGH
- CoinEx, WOO X, Phemex, Gemini — MEDIUM

### New Discoveries
- WhiteBIT: 7 OpenAPI + 19 AsyncAPI specs (found via llms.txt)
- Kraken: 48 REST API pages in sitemap never fetched (crawl gap)
- Coinbase: FIX docs for 4 products outside scope_prefixes
- FIX protocol: 5 exchanges have docs, not 2 (add Kraken, Coinbase, Bitfinex)
- llms.txt: 13 of 35 exchanges have it
- 15 exchanges evaluated and rejected with reasons

### Crawl Methodology Added
- 5-method crawl cascade: requests → cloudscraper → Playwright → crawl4ai → Agent Browser
- Source trust hierarchy (official docs > specs > Postman > CCXT > community)
- Drift detection strategy (cross-ref all sources, flag conflicts)
- Spot-check validation (5% re-crawl with browser method)
- Sitemap trust levels documented per exchange

## Prior Code Fixes (M5)
- CCXT _walk_api() handles numeric leaf values (dict-with-costs format)
- CCXT per-section base URL resolution from urls.api
- dydx + hyperliquid added to CCXT_EXCHANGE_MAP
- _EXCHANGE_ID_ALIASES for crypto_com/cryptocom mismatch
- Perpetual Protocol status: defunct in exchanges.yaml

## Last Update: 2026-03-06T20:00:00Z
