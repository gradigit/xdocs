---
status: complete
priority: p2
issue_id: "019"
tags: [code-review, performance, sqlite, coverage]
dependencies: []
---

# Reduce lock scope and memory usage in coverage gaps computation

## Problem Statement

`sync` runs `compute_and_persist_coverage_gaps()` as a post-step. As written, it acquires the global write lock and then reads/parses every endpoint row, which can block concurrent operations and get slower as the endpoint DB grows.

The tool is intended to be cron-friendly and scale-safe; coverage aggregation should minimize lock duration and avoid large in-memory loads when possible.

## Findings

- `src/cex_api_docs/coverage_gaps.py`:
  - wraps the full read + JSON parse + aggregation inside `acquire_write_lock(...)`
  - executes `SELECT endpoint_id, exchange, section, protocol, json FROM endpoints ...` and `fetchall()`
  - then JSON-parses each row in Python while holding the lock
- The lock is only required for the final upsert into `coverage_gaps`, not for the entire scan.

## Proposed Solutions

### Option 1: Compute outside the write lock, upsert inside (recommended)

**Approach:**
- Open DB without write lock and stream rows (iterate cursor) to compute aggregates.
- Acquire write lock only for:
  - ensuring `coverage_gaps` table exists
  - upserting computed rows
- Optionally add a cap/limit for extremely large endpoint sets (documented).

**Pros:**
- Minimizes time under exclusive lock.
- Better for cron and interactive use.

**Cons:**
- Small race window: endpoints may change between compute and persist (acceptable for reporting).

**Effort:** 2-4 hours

**Risk:** Low/Medium

---

### Option 2: Keep lock but avoid `fetchall()` and reduce parsing overhead

**Approach:**
- Iterate cursor results instead of `fetchall()`.
- Consider JSON extraction in SQL for common keys (if schema stable).

**Pros:**
- Smaller change.

**Cons:**
- Still blocks writers for the full scan.

**Effort:** 1-2 hours

**Risk:** Low

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/coverage_gaps.py`
- `src/cex_api_docs/sync.py` (calls coverage gaps in post-processing)

## Acceptance Criteria

- [ ] Coverage gaps computation holds the write lock only for table creation + upsert.
- [ ] Avoids loading all endpoint rows into memory at once.
- [ ] `pytest` passes.
- [ ] `sync` runtime does not regress on small DBs.

## Work Log

### 2026-02-10 - Code Review Finding

**By:** Codex

**Actions:**
- Confirmed `compute_and_persist_coverage_gaps()` reads and parses endpoints under a write lock and uses `fetchall()`.

**Learnings:**
- Reporting/aggregation steps should be designed as “eventually consistent” and avoid global locks.

### 2026-02-10 - Fix Implemented

**By:** Codex

**Actions:**
- Refactored `compute_and_persist_coverage_gaps()` in `src/cex_api_docs/coverage_gaps.py`:
  - compute aggregates outside the write lock
  - upsert results under the lock only
  - avoid `fetchall()` by iterating the cursor
- Ran `./.venv/bin/pytest -q`.

**Learnings:**
- Minimizing exclusive lock time matters more than perfect snapshot consistency for coverage reporting.
