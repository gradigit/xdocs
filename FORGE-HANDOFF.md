# Forge Handoff — 2026-04-07

## Bootstrap
1. Read this file
2. Read FORGE-STATUS.md
3. Read CLAUDE.md

## What's Complete
- M24: Data Quality Cleanup & Parameter Extraction
  - 5,797 CCXT empty pages deleted (store: 17,429 → 11,632 pages)
  - Exchange-less queries return `needs_clarification` with top-15 exchanges by endpoint count
  - `extract_params_near()` in endpoint_extract.py: pipe tables, tab tables, Coinone literal \n, nested params
  - Wired into `_build_endpoint_record()` for new scan-endpoints runs
  - `backfill-params` CLI command: filled request_schema for 760 endpoints (35.7% → 47.5% coverage)
  - request_payload MRR improved +25.2% (0.284 → 0.355) from backfill
  - Skills updated: xdocs-query (Coinone note), xdocs-maintain (backfill-params in post-sync)
  - 796 tests passing (was 778)

## What's In Progress
Nothing in progress. Next priorities:

1. **Rebuild LanceDB semantic index** — current index has only 2,579/339,179 rows. Full rebuild needed (~2-4 hours on GPU). This will restore semantic search and recover the MRR regression (0.553 → expected ~0.64).

2. **Fix sync pipeline for 0-word pages** — Gemini's 13 empty pages need Playwright but `--force-refetch` only re-fetches via HTTP when the page was originally fetched that way. Need to add logic: if word_count=0 and render_mode was not playwright, force Playwright on refetch.

3. **Endpoint extraction for 0-endpoint sections** — 27 sections have pages but no endpoints. Biggest gaps: Kraken futures (725 pages), Coinbase advanced_trade (469), Upbit Korean (363).

4. **M23 Phase 2 remaining** — response_schema extraction (deferred from this milestone).

## Key Context
- LanceDB index is broken — semantic search returns 0 results. FTS-only pipeline works.
- `backfill-params` can be re-run safely (skips endpoints that already have request_schema).
- Coinone has no missing endpoints (41 in DB = all unique paths in pages).
- The `needs_clarification` change updated canary test expectations (was unknown → needs_clarification).

## Session Stats
- 7 tasks completed
- 5,797 pages cleaned, 760 endpoints enriched
- 18 new tests added (778 → 796)

## Blockers
- LanceDB rebuild requires GPU (~2-4 hours). Without it, semantic search is non-functional.

## Health
- last_updated: 2026-04-07
- compaction_count: 0
- stuck_indicator: false
