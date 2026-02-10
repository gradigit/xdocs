---
status: complete
priority: p1
issue_id: "015"
tags: [code-review, bug, sqlite, citations]
dependencies: []
---

# Fix stale-citations SQL semantics when no filters are applied

## Problem Statement

`cex-api-docs detect-stale-citations` can incorrectly report that *every* endpoint source is missing when no `--exchange/--section` filters are provided. This can flood `review_queue` with false positives and make the sync output unusable for cron/alerts.

## Findings

- `src/cex_api_docs/stale_citations.py` builds `where_sql` as either `""` or `"WHERE ..."` and then appends `AND p.id IS NULL` after `{where_sql}`.
- When `where_sql == ""`, SQLite parses the query as:
  - `LEFT JOIN pages p ON p.canonical_url = es.page_canonical_url AND p.id IS NULL`
  - This forces the join to never match, producing `p.* IS NULL` for all rows, so every citation is treated as a missing source.
- The same pattern exists for the stale-hash query (`AND ...`) and has similar risk if query shape changes.
- `limit` is currently applied after `fetchall()` and after building all findings in Python, which can be memory-heavy on large DBs.

## Proposed Solutions

### Option 1: Always construct a `WHERE` clause with explicit predicates (recommended)

**Approach:**
- Build a list of predicates and always render `WHERE` once, e.g.:
  - missing sources: predicates include `p.id IS NULL`
  - stale sources: predicates include `es.page_content_hash != p.content_hash`
- Add `LIMIT ?` in SQL when `limit` is provided and push limiting into the DB.

**Pros:**
- Fixes the semantic bug deterministically.
- Faster and more memory-safe.

**Cons:**
- Requires careful updates to keep both queries consistent.

**Effort:** 1-2 hours

**Risk:** Low

---

### Option 2: Keep current query strings but conditionally prefix `WHERE` for trailing predicates

**Approach:**
- If `where_sql` is empty, emit `WHERE p.id IS NULL`; else append `AND p.id IS NULL`.

**Pros:**
- Smallest patch.

**Cons:**
- Easy to regress later as queries evolve (more footguns).

**Effort:** 30-60 minutes

**Risk:** Medium

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/stale_citations.py`
- `src/cex_api_docs/sync.py` (calls `detect_stale_citations` on every sync)

**Notes:**
- Add/adjust tests to cover the unfiltered case and ensure missing sources are not over-reported.

## Resources

- Review finding: `LEFT JOIN` predicate attached to `ON` clause when `where_sql` is empty.

## Acceptance Criteria

- [ ] Running `cex-api-docs detect-stale-citations` with no filters does not report all sources as missing.
- [ ] `limit` is enforced at SQL level (or otherwise proven not to load unbounded results).
- [ ] `pytest` passes.
- [ ] Add a regression test covering the no-filter path.

## Work Log

### 2026-02-10 - Code Review Finding

**By:** Codex

**Actions:**
- Identified `LEFT JOIN ... AND p.id IS NULL` bug when `where_sql` is empty in `src/cex_api_docs/stale_citations.py`.

**Learnings:**
- Trailing `AND ...` without a `WHERE` can silently alter join semantics in SQLite.

### 2026-02-10 - Fix Implemented

**By:** Codex

**Actions:**
- Fixed `LEFT JOIN` semantic bug and pushed `limit` into SQL in `src/cex_api_docs/stale_citations.py`.
- Added regression test covering the no-filter case in `tests/test_stale_citations.py`.
- Ran `./.venv/bin/pytest -q`.

**Learnings:**
- Keeping predicates exclusively in `WHERE` avoids accidental changes to `LEFT JOIN` behavior.
