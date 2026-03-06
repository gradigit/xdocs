---
milestone: 5
phase: complete
updated: 2026-03-06T18:30:00Z
---
## Current State
M5: Verified Bible Refinement — COMPLETE

## Milestones
- [x] Milestone 1: Audit Existing Coverage & Gap Analysis — COMPLETE
- [x] Milestone 2: Deep Discovery — CEX Exchanges — COMPLETE
- [x] Milestone 3: Deep Discovery — DEX Protocols + CCXT — COMPLETE
- [x] Milestone 4: Compile Bible Document + Registry Updates — COMPLETE
- [x] Milestone 5: Verified Bible Refinement — COMPLETE

## M5 Deliverables
- `docs/crawl-targets-bible.md` — 802 lines, all numbers from live DB, all URLs verified
- `src/cex_api_docs/ccxt_xref.py` — dict-of-dicts bug fixed, dydx+hyperliquid added, crypto_com alias
- `data/exchanges.yaml` — Perpetual Protocol marked defunct
- `tests/test_ccxt_xref.py` — updated for new map entries

## Code Fixes Applied
- CCXT _walk_api() handles numeric leaf values (dict-with-costs format)
- CCXT per-section base URL resolution from urls.api
- dydx + hyperliquid added to CCXT_EXCHANGE_MAP
- _EXCHANGE_ID_ALIASES for crypto_com/cryptocom mismatch
- Perpetual Protocol status: defunct in exchanges.yaml

## Key Verified Findings
- Orderly OpenAPI: raw.githubusercontent.com/OrderlyNetwork/documentation-public/main/evm.openapi.yaml (461KB, 192 paths)
- GRVT spec: src/codegen/apispec.json — CUSTOM FORMAT, not OpenAPI
- KuCoin: 9 spec files at openapi-*.json (2.9MB total), all need --base-url
- Pacifica upgraded from DEFER to RECOMMEND ADD (97 API doc URLs, active changelog)
- Nado docs at docs.nado.xyz (not docs.nado.trade)
- HTX status at htx.statuspage.io (not status.huobigroup.com — DNS dead)
- Korbit status page DNS dead

## Last Update: 2026-03-06T18:30:00Z
