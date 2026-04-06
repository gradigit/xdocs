---
milestone: M24
phase: complete
updated: 2026-04-07T17:00:00+09:00
run_id: m24-2026-04-07
---
## Current State
M24: Data Quality Cleanup & Parameter Extraction. Complete.

## Deliverables
1. [done] Deleted 5,797 CCXT empty pages (17,391 files, 31 MB freed)
2. [done] Exchange-less queries return needs_clarification with top exchanges (was dead-end unknown)
3. [done] Gemini 13 empty pages: deferred (needs pipeline fix for re-rendering unchanged 0-word pages)
4. [done] extract_params_near() — pipe tables + tab tables + nested params + Coinone \n unescaping
5. [done] Wired into _build_endpoint_record() for new scan-endpoints extractions
6. [done] backfill-params CLI command — updated 760 existing endpoints
7. [done] A/B eval — regressions are from broken LanceDB index, not code changes
8. [done] Coinone: no missing endpoints (41 in DB matches 40 unique paths + duplicates)
9. [done] Skill updates: xdocs-query (Coinone Korean-only note), xdocs-maintain (backfill-params in post-sync)

## Store Stats (post-M24)
- Pages: 11,632 (was 17,429 — removed 5,797 CCXT empties)
- Endpoints: 6,406
- With request_schema: 3,046 (47.5%, was 35.7%)
- With rate_limit: 400
- Tests: 796 (was 778)
- Pipeline (FTS-only): MRR=0.553, PFX=67.2%, OK=92.2%
- Pipeline note: LanceDB index has only 2,579/339,179 rows — needs full rebuild for semantic search
- request_payload improved +25.2% MRR from param backfill

## Known Issues
- LanceDB index is partial (2,579 rows vs expected 339,179). Full rebuild needed (~2-4 hours on GPU)
- 13 Gemini pages remain empty — sync pipeline doesn't re-render unchanged 0-word pages with Playwright
- 27 sections have pages but 0 endpoints (Kraken futures, Coinbase advanced, Upbit Korean, DEX docs)

## Last Update: 2026-04-07T17:00:00+09:00
