---
milestone: M23
phase: phase1-complete
updated: 2026-03-27T11:30:00+09:00
run_id: m23-extract-2026-03-27
---
## Current State
M23 Phase 1 complete. Endpoint extraction from crawled docs is operational.

## Results
- **+863 new endpoints** extracted from 6 exchanges (5,067 → 5,930 total)
- All endpoints have `docs_url` set to source page
- All citations pass `_verify_citation_against_store()` (enforced by save pipeline)
- 35 new tests, 737 total passing, zero regressions

## Per-Exchange Breakdown
| Exchange | Section | Extracted | Pattern | Notes |
|----------|---------|-----------|---------|-------|
| aevo | api | 110 | P4 | Per-endpoint ReadMe.io pages, clean |
| phemex | api | 120 | P3+P2 | Slate monolith, code blocks after `> Request` |
| coinex | api | 134 | P1 | Docusaurus, dedup 660→134 |
| bitbank | rest | 389 | P2 | GitHub markdown, includes ccxt_ref pages |
| woo | api | 73 | P5+P2 | SPA monolith, backtick + code block |
| apex | api | 37 | P5 | ReadMe.io, dedup 113→37 (3 lang dupes) |

## Deliverables
- `src/xdocs/endpoint_extract.py` — regex scan + record construction (~310 lines)
- `skills/xdocs-extract/SKILL.md` — extraction skill
- `tests/test_endpoint_extract.py` — 35 tests
- CLI: `xdocs scan-endpoints --exchange X --section Y [--dry-run]`
- CLAUDE.md updated

## Store Stats
- Pages: 17,422
- Endpoints: 5,930 (+863 from extraction)
- Tests: 737

## Next
- Commit M23 changes
- Phase 2 (follow-up): parameter table extraction, rate limits

## Active Agents
- None

## Last Update: 2026-03-27T11:30:00+09:00
