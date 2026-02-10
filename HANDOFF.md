# Context Handoff — 2026-02-11

## First Steps (Read in Order)
1. Read CLAUDE.md — project context, architecture, conventions
2. Read TODO.md — current task list (points to `todos/` directory)
3. Read deep-review-cex-api-docs-readable.md — full deep-review findings and status

## Session Summary

### What Was Done
- Ran deep adversarial review (`/deep-review`) of the entire cex-api-docs codebase
- Produced two review artifacts: clinical findings + human-readable report
- Fixed all 9 actionable findings (of 12 total) — 1 CRITICAL, 4 SIGNIFICANT, 4 MINOR
- All 20 tests pass after fixes
- Updated CLAUDE.md and .doc-manifest.yaml via `/wrap` chain

### Deep-Review Fixes Applied (commit e38a0c9)

| ID | Severity | Fix |
|----|----------|-----|
| F1 | CRITICAL | Fixed double-escaped regex in raw strings across 6 files (`r"\\w"` -> `r"\w"`) |
| F2 | SIGNIFICANT | Rewrote stale_citations.py with 2-phase locking (reads outside lock) |
| F4 | SIGNIFICANT | Thread-safe robots_cache with `threading.Lock()` in inventory_fetch.py |
| F5 | SIGNIFICANT | Schema migration framework in db.py (MIGRATIONS dict, sequential apply) |
| F6 | MINOR | Removed dead `links` table from schema.sql |
| F7 | MINOR | Removed `_ensure_table()` from coverage_gaps.py (table in schema.sql only) |
| F8 | MINOR | Extracted shared `url_host()` into new urlutil.py (7 files deduped) |
| F9 | MINOR | Replaced pages.py `_require_db` with `store.require_store_db` |
| F12 | MINOR | Replaced 30 `raise SystemExit(0)` with `return` in cli.py |

### Not Fixed (intentional)
- F3: Deprecated crawl code — not a bug, deprecation is the plan
- F10: Already correct behavior upon re-examination
- F11: Architectural observation, not a code fix

### Current State
- Branch: main
- Last commit: e38a0c9 — fix: deep-review bugfixes — regex, locking, dead code, dedup
- Working tree: clean (except this HANDOFF.md)

### What's Next
1. Continue with items in `todos/` (file-based work tracking)
2. The "wow query" demo runbook is at docs/runbooks/binance-wow-query.md
3. Consider running a real sync against an exchange to validate the regex fixes in production

### Failed Approaches
- Initial regex fix pass missed discover_sources.py:178 (second sitemap regex instance). Found via final `Grep` sweep for `r".*\\\\[wWsSdDbB]` pattern.
- Import placement: when replacing `def _host()` with `from .urlutil import url_host as _host`, imports were initially placed mid-file at the old function location. Had to move them to the top import section.

### Key Context
- All regex in raw strings should use single backslash (`r"\w"` not `r"\\w"`) — the `r` prefix already handles escaping
- `urlutil.py` is now the canonical location for `url_host()` — all 7 modules import from there
- Schema migration framework is in place but MIGRATIONS dict is empty (current version is v1). Ready for future schema changes.
- stale_citations.py uses a read-only connection for phase 1 (analysis) and only acquires write lock for phase 2 (review_queue inserts)

## Reference Files
| File | Purpose |
|------|---------|
| CLAUDE.md | Project context, architecture, conventions |
| TODO.md | Points to `todos/` for work tracking |
| deep-review-cex-api-docs-readable.md | Human-readable deep review report |
| deep-review-cex-api-docs.md | Clinical deep review findings |
| src/cex_api_docs/urlutil.py | New shared `url_host()` utility |
| src/cex_api_docs/stale_citations.py | Rewritten with 2-phase locking |
| src/cex_api_docs/db.py | Schema migration framework |
| schema/schema.sql | Authoritative DDL (links table removed) |
| docs/runbooks/binance-wow-query.md | Demo runbook for "wow query" |
