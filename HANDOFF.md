# Context Handoff — 2026-02-11

## First Steps (Read in Order)
1. Read CLAUDE.md — project context, architecture, conventions
2. Read TODO.md — current task queue (file-based in `todos/`)
3. Read docs/reports/poc-full-binance-http-playwright-jina.md — POC findings

## Session Summary

### What Was Done
- **Wow query demo**: Tested end-to-end cite-only answer pipeline. "Unified trading" correctly returns `needs_clarification`; with `--clarification binance:portfolio_margin` returns `status: ok` with 3 cited claims (rate limits for portfolio_margin + spot, API key permissions from derivatives quick-start).
- **Endpoint ingest — 3,125 endpoints across all 16 exchanges**:
  - Tier 1 (OpenAPI/Postman specs): Binance official spot OpenAPI (340) + openxapi (PM 102, USDM 97, COINM 65) + 24 Postman collections + OKX openxapi (313) + Bitget community (102) + Bybit official Postman (140) + KuCoin official (spot 70, futures 54) → 1,918 endpoints
  - Tier 2 (agent extraction from markdown): HTX (372), Gate.io (374), Bitstamp (82), Bitfinex (81), Crypto.com (65), Hyperliquid (75), Upbit (44), Bithumb (36), dYdX (34), Korbit (32), Coinone (22) → 1,207 endpoints
  - Tier 3 (registry expansion): 9 new sections added to data/exchanges.yaml, 1,527 new pages synced
    - Binance: options (73p), margin_trading (79p), wallet (1,044p), copy_trading (122p), portfolio_margin_pro (27p)
    - Bitget: copy_trading (51p), margin (52p), earn (28p), broker (16p)
- **Gate.io re-sync**: Confirmed already complete — 0 pending entries, data intact
- **Docs sync**: Updated CLAUDE.md (37 sections, 3,125 endpoints, new commands, new gotchas), added extracted_endpoints/ to .gitignore

### Current State
- **Store**: 3,813 pages, 4,483,424 words, 3,125 endpoints across 16 exchanges (37 sections) in `cex-docs/`
- **Branch**: main
- **Tests**: 20/20 passing

### What's Next
1. Extract endpoints for the 9 newly added sections (Binance options/margin_trading/wallet/copy_trading/portfolio_margin_pro + Bitget copy_trading/margin/earn/broker)
2. Import Binance Options OpenAPI spec (openxapi has `options.yaml`)
3. Improve answer.py to use the endpoint DB (currently only uses page FTS)
4. Run coverage-gaps to identify incomplete endpoint records
5. Consider adding more exchanges (e.g., Kraken, Coinbase, MEXC)

### Failed Approaches / Gotchas Learned
- **KuCoin OpenAPI needs `--base-url`**: Their specs have no `servers[].url` field. Must pass `--base-url "https://api.kucoin.com"` explicitly.
- **Endpoint citation verification is strict**: `save-endpoint` checks excerpt matches stored markdown byte-for-byte at given offsets. Agent extractors must use exact string matching, not approximations.
- **Gate.io re-sync is a no-op**: `--resume` finds 0 pending entries because the data is already complete. The 403 rate-limiting only affects new requests.

### Key Context
- **Single-page doc exchanges**: OKX, Gate.io, HTX, Crypto.com, Bitstamp, Korbit serve full API refs from 1-4 HTML files. Low page counts are not errors.
- **Binance wallet section is huge**: 1,044 pages (covers wallet, sub-account, deposits, withdrawals, travel rule).
- **OpenAPI/Postman spec URLs** are documented in the import commands run this session.

## Reference Files
| File | Purpose |
|------|---------|
| data/exchanges.yaml | Exchange registry — 16 exchanges, 37 sections |
| CLAUDE.md | Project context, architecture, conventions |
| schemas/endpoint.schema.json | Endpoint record JSON schema |
| docs/runbooks/binance-wow-query.md | Wow query demo runbook |
| docs/reports/poc-full-binance-http-playwright-jina.md | Full POC comparison report |
| todos/ | Prioritized work queue (all 20 complete) |
