# Handoff — 2026-03-12T22:00:00+09:00

## Current Status

Session complete. All work committed and pushed. Both repos (maintainer + runtime) in sync.

**Pipeline**: MRR=0.644, nDCG@5=1.343, PFX=78%, URL=65%, domain=97%, OK=92%
**Store**: 10,727 pages, 16.75M words, 4,963 endpoints, 46 exchanges, 78 sections
**Tests**: 559 passing. **Schema**: v6.

## What Was Done This Session

1. **Gapfinder skill v1.0→v2.2.0**: answer output schema, exchange detection sweep, nav chrome gate, citation schema gate, answer grading tiers (clean/mixed/fail), runtime model stack detection, adversarial >30s threshold, multi-exchange ambiguity test
2. **3 QA runs evaluated**: v1 (46 tests, 67.4%), v2 blind-mode (108 tests, 67.6%), 10-run batch (340 tests, 61.1%)
3. **7 bugs catalogued** (BUG-15 through BUG-21) with repro steps and root cause in TODO.md
4. **BUG-21 FIXED**: FTS5 crash on `'` in `sanitize_fts_query()` — critical, found by 10-run batch (7/10)
5. **cex-api-query v2.11.0**: negative-evidence guidance + third-party vendor split (Step 5c)
6. **Sync script**: copies `tests/golden_qa.jsonl` to runtime repo
7. **Gate.io FIX protocol QA report** evaluated → BUG-20 (not_found status distinction)
8. Both repos pushed: maintainer `5687003`, runtime `390fbfc3`

## What Is Next

Priority bugs (all in TODO.md with full context):

| Bug | Severity | Summary | LOC |
|-----|----------|---------|-----|
| BUG-18 | High | Direct-route citations missing excerpts | ~15 |
| BUG-15 | High | Numeric literals → error_message misclassification | ~5 |
| BUG-16 | High | Nav chrome in excerpts (_is_nav_region threshold) | ~30 |
| BUG-19 | Medium | Multi-exchange ambiguity picks first exchange | ~15 |
| BUG-17 | Medium | Path-only endpoints return unknown | ~20 |
| BUG-20 | Medium | No not_found status for negative evidence | ~10 |

Deferred milestones: M23 (structured endpoint extraction), M24 (content quality).

## Blockers / Open Questions

None.

---

## Read Gate

**Read Gate is mandatory. Complete it before Workspace Preparation.**
**Do not run implementation steps until Read Gate is complete.**

Required files in order: `handoff.md`, `claude.md`, `todo.md`, `state.md`, `context.md`

Receipt format:
```
- [x] handoff.md — <1-line takeaway>
- [x] claude.md — <1-line takeaway>
- [x] todo.md — <1-line takeaway>
- [x] state.md — <1-line takeaway>
- [x] context.md — <1-line takeaway>
```

If user prompt only says "read handoff.md", treat as bootstrap — continue Read Gate automatically. Do not send interim summaries before receipt is complete.

Run `/handoff-fresh --validate-read-gate` after completing `read-receipt.md` and before coding.

---

## Workspace Preparation

After Read Gate:

1. Confirm project root: `/home/lechat/Projects/cex-api-docs`
2. Confirm branch: `main`, clean working tree
3. Confirm venv: `source /home/lechat/Projects/.venv/bin/activate`
4. Run `pytest tests/ -x -q` to verify 559 tests pass
5. Re-run `/sync-docs` if drift detected

**Question Gate**: If anything is missing or ambiguous, ask before coding.
