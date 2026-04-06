---
milestone: M23-Phase2
phase: planning
updated: 2026-04-06T18:00:00+09:00
run_id: m23p2-2026-04-06
---
## Current State
M23 Phase 1 complete. Phase 2 (parameter table extraction) in planning stage.

## Phase 1 Deliverables (complete)
- endpoint_extract.py: 5 regex patterns, rate limit extraction, save orchestrator
- scan-endpoints CLI with --dry-run
- xdocs-extract skill
- 1,648 endpoints extracted, 400 with rate_limit
- agent-browser content-selector fallback for SPAs
- Korean exchange name detection (18 names)
- Coinone: 62 pages re-ingested, 41 endpoints with bilingual descriptions

## Phase 2 Plan
See `architect/m23-phase2-plan.md` — needs iteration before building.

## Store Stats
- Pages: 17,429
- Endpoints: 6,406
- With rate_limit: 400
- Tests: 778
- Pipeline: MRR=0.6409, PFX=79.37%
- Semantic index: 339,179 chunks + 218 Coinone incremental, 2.5 GB

## Decisions Made
- Translation: Option B — rely on cross-language search (proven working), no translation layer
- Parameter extraction: Build now (Phase 2), not defer
- Coinone: Korean-only documented in skills, search works cross-language
- Skills: update after every data change (add to maintenance checklist)

## Active Agents
- None

## Last Update: 2026-04-06T18:00:00+09:00
