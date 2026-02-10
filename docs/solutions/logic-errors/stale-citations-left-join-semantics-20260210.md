---
module: Tooling
date: 2026-02-10
problem_type: logic_error
component: tooling
symptoms:
  - "cex-api-docs detect-stale-citations reported missing_source for nearly every endpoint field even when pages existed in the store"
  - "Running detect-stale-citations with no filters (exchange/section unset) produced a huge missing_source count (false positives)"
  - "If run without --dry-run, detect-stale-citations would flood review_queue with missing_source items"
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [stale-citations, left-join, sql, citations, review-queue, cite-only]
---

# Fix: Stale Citation Sweep False Positives from LEFT JOIN Predicate Placement

## Problem

The deterministic citation sweep (`cex-api-docs detect-stale-citations`) was intended to find:

- citations to pages that no longer exist in the local store (`missing_source`)
- citations whose stored `page_content_hash` differs from the latest stored page hash (`stale_citation`)

But a subtle SQL bug caused `missing_source` to be massively over-reported (especially when no filters were provided), making the sweep unusable and unsafe to run as part of a cron-friendly sync workflow.

## Environment

- Module: Tooling (`cex-api-docs` CLI + local store)
- Date: 2026-02-10
- Store: local filesystem + SQLite (`./cex-docs/db/docs.db`)

## Symptoms

- `cex-api-docs detect-stale-citations --dry-run` returned `counts.missing_source` close to the number of total cited fields, even on a healthy store.
- The `sample` output showed `missing_source` for pages that definitely existed under `pages.canonical_url`.
- Running with no filters (`--exchange` unset, `--section` unset) amplified the false positives.

## Root Cause

The SQL for detecting missing sources used a `LEFT JOIN` from `endpoint_sources` to `pages`, but placed the "missing" predicate (`p.id IS NULL`) in the `LEFT JOIN ... ON (...)` clause (or otherwise built the join predicates in a way that made the join condition impossible).

That changes `LEFT JOIN` semantics: the join never matches, so `p.*` is NULL for every row, making every citation look like a missing source.

### Conceptual example

#### ❌ Wrong (semantics bug)

```sql
SELECT ...
FROM endpoint_sources es
LEFT JOIN pages p
  ON p.canonical_url = es.page_canonical_url
 AND p.id IS NULL;
```

#### ✅ Correct

```sql
SELECT ...
FROM endpoint_sources es
LEFT JOIN pages p
  ON p.canonical_url = es.page_canonical_url
WHERE p.id IS NULL;
```

## Solution

### 1) Keep missing/stale predicates in `WHERE`, not `LEFT JOIN ... ON`

Implementation: `src/cex_api_docs/stale_citations.py`

The missing-source query now:

- `LEFT JOIN pages p ON p.canonical_url = es.page_canonical_url`
- applies `p.id IS NULL` (and any exchange/section filters) in `WHERE`

There is an explicit code comment to prevent regressions:

- `IMPORTANT: keep predicates in WHERE, not in the LEFT JOIN ON clause, or semantics change.`

### 2) Add a regression test that fails if `missing_source` "explodes"

Test: `tests/test_stale_citations.py`

The test builds a minimal SQLite store with:

- one valid citation (page exists, hash matches)
- one missing citation (page row does not exist)
- one stale citation (page exists, hash differs)

Then asserts the sweep returns exactly:

- `missing_source == 1`
- `stale_citation == 1`
- `total_findings == 2`

## Why This Works

- `LEFT JOIN` is only a "missing row detector" when the match criteria stays in `ON` and the *missing check* stays in `WHERE`.
- Moving `p.id IS NULL` to `WHERE` restores the intended semantics: only citations with no matching page row are flagged.
- The regression test makes the failure mode loud and deterministic.

## Verification

```bash
# Unit/regression tests
./.venv/bin/pytest -q

# Sanity check: should not report "everything missing" on a healthy store
./.venv/bin/cex-api-docs detect-stale-citations --docs-dir ./cex-docs --dry-run
```

## Prevention

- Always add a test when building dynamic SQL involving `LEFT JOIN` + NULL checks.
- When adding new filters to the citation sweep, keep join-match predicates in `ON`.
- When adding new filters to the citation sweep, keep "missing" predicates in `WHERE`.
- Consider promoting this to `docs/solutions/patterns/critical-patterns.md` if the stale sweep becomes part of the default cron `sync` pipeline (so it is run frequently and must never flood review items).

## Related Docs

- `docs/solutions/integration-issues/ua-403-exchange-docs-crawler-tooling-20260210.md`
- `docs/solutions/patterns/critical-patterns.md`
- Plan: `docs/plans/2026-02-10-feat-exhaustive-cex-api-docs-sync-plan.md`
- Sample report: `docs/reports/2026-02-10-binance-spot-sync-report-2.md`
