# Forge Handoff — 2026-04-06

## Bootstrap
1. Read this file
2. Read FORGE-STATUS.md
3. Read CLAUDE.md
4. Read `architect/m23-phase2-plan.md`

## What's Complete
- M23 Phase 1: endpoint extraction (1,648 endpoints, 400 with rate_limit)
- All bugs from the 12-CEX withdrawal session triaged and fixed
- Korean exchange name detection (18 names in classify.py)
- Coinone: 62 pages re-ingested with clean .markdown-body content, 41 endpoints with bilingual descriptions
- KuCoin: 312 pages re-ingested with clean content (endpoint-only, no nav)
- agent-browser content-selector fallback committed (agentbrowserfetch.py)
- Semantic index clean rebuild: 339,179 chunks + 218 Coinone incremental
- Release published: data-2026.04.06
- Notion doc created (2 versions: concise guide + technical reference) in Knowledge & Research

## What's In Progress
**M23 Phase 2: Parameter Table Extraction**

The plan is at `architect/m23-phase2-plan.md`. It needs iteration and refinement BEFORE building:

1. **Iterate on the plan**: Review the open questions in the plan file. Research answers. Refine the algorithm. Get user approval before writing code.
2. **Key open questions**:
   - Nested parameters (child rows with dash prefix)
   - Response schema: build now or defer?
   - Update existing spec-imported endpoints?
   - Non-table parameter formats (inline text descriptions)
   - Coinone's literal `\n` in content
3. **After plan is approved**: Build `extract_params_near()` in endpoint_extract.py, tests, run on all 13 exchanges, A/B eval

**Also pending in this milestone:**
- Verify Coinone's 2 potentially missing endpoints
- Check 3 skipped Coinone pages
- Update xdocs-query skill: Coinone is Korean-only
- Update xdocs-maintain skill: add skill update to maintenance checklist

## Key Context
- Coinone search works cross-language (tested: English queries find Korean pages via both FTS and semantic)
- The bilingual endpoint descriptions are hardcoded translations — fragile but functional. Decision: Option B (no translation layer, rely on cross-language search)
- KuCoin nav pollution issue: ingesting full `[class*=content]` innerText polluted FTS. Fixed by extracting `.markdown-body` only. KuCoin reverted to HTTP baseline for pages, endpoint-only content for clean pages.
- Index builds take 2-4+ hours, NOT "100 minutes" as previously estimated. Never give time estimates for builds.
- `gh auth` switches between henryaxis and gradigit — always switch to gradigit before pushing/releasing

## Session Stats
- 20+ commits pushed
- 10 bugs fixed from triage report
- 2 Notion docs created
- 3 data releases published (data-2026.04.02, data-2026.04.05, data-2026.04.06)
- Pipeline: MRR=0.6409, PFX=79.37%, 778 tests

## Blockers
- None

## Health
- last_updated: 2026-04-06
- compaction_count: 0
- stuck_indicator: false
