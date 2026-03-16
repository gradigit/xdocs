# Session Log Digest

**Generated**: 2026-03-12
**Token budget**: 4000 target / ~3500 actual

## Key Decisions

1. **Gapfinder v1 → v2 evolution**: v1 run revealed wrong claim field paths (`claim["url"]` vs `claim["citations"][0]["url"]`). Added Answer Output Schema to skill. v2 blind mode successfully rediscovered all v1 findings from scratch — validates blind mode mechanism.

2. **BUG-21 fix prioritized over other bugs**: 10-run batch revealed FTS5 crash on `'` in `search_pages` (7/10 runs). Critical severity — fixed immediately by adding `'` and `;` to `sanitize_fts_query` regex. Other bugs (BUG-15-20) catalogued for later.

3. **Runtime repo code is stale**: v1 gapfinder run showed `status=unknown` for exchanges that return `status=ok` on maintainer. Root cause: runtime has pre-M20/M22 code. Not a new bug — needs code sync (which was done this session).

4. **Negative-evidence answer mode**: Gate.io FIX protocol query exposed that `answer()` has no way to say "searched and found nothing" — only `unknown` (conflates with "can't route"). Added BUG-20 and updated cex-api-query skill with guidance.

5. **10-run batch validates bug inventory**: No new bug categories emerged from 340 tests across 10 runs. All findings map to BUG-15 through BUG-21.

## Rejected Alternatives

- Did NOT fix BUG-15-20 this session — user explicitly said "add as TODOs for later work"
- Did NOT update gapfinder to v3 — v2.2.0 incorporates all run learnings, no structural changes needed
- Golden QA cross-check was always skipping on runtime — fixed by adding golden_qa.jsonl to sync script

## User Constraints

- "Clinical in the way we proceed" — A/B test everything, catch regressions
- Bugs are catalogued with repro steps, not fixed ad-hoc
- Both repos must stay in sync after every push
