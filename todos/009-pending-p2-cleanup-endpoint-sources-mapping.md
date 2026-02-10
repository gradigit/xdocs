---
status: pending
priority: p2
issue_id: "009"
tags: [code-review, sqlite, review-queue, endpoints]
dependencies: []
---

# Keep `endpoint_sources` In Sync With Current Endpoint Citations

## Problem Statement

`endpoint_sources` is used to trigger re-review when source pages change. If it accumulates stale mappings after endpoint updates, it can:
- enqueue unnecessary review items
- inflate DB size over time
- reduce trust in the review queue signal

## Findings

- `src/cex_api_docs/endpoints.py` inserts into `endpoint_sources` using `INSERT OR IGNORE`.
- There is no cleanup step on endpoint update, so old `(endpoint_id, field_name, page_canonical_url, page_content_hash)` rows remain even when the endpoint JSON has been updated to cite newer content.

## Proposed Solutions

### Option 1: Replace Mappings On Save (Recommended)

**Approach:**
- In `save_endpoint`, inside the write transaction:
  - `DELETE FROM endpoint_sources WHERE endpoint_id = ?;`
  - insert the current citations’ mappings.

**Pros:**
- Accurate: mapping reflects what the endpoint currently cites.
- Simplifies reasoning about `source_changed` review triggers.

**Cons:**
- Loses historical mapping data (unless stored separately).

**Effort:** Small/Medium

**Risk:** Low

---

### Option 2: Keep History With an `active` Flag

**Approach:**
- Add `active` boolean column (schema change).
- Deactivate previous mappings on update, activate new ones.

**Pros:**
- Retains history while keeping current mappings accurate.

**Cons:**
- Schema migration and more logic.

**Effort:** Medium

**Risk:** Medium

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/endpoints.py`
- `schema/schema.sql` (only for Option 2)

## Acceptance Criteria

- [ ] Updating an endpoint replaces its `endpoint_sources` mappings (Option 1) or updates active mappings (Option 2).
- [ ] `source_changed` review items are only created for endpoints that currently cite the changed page hash.
- [ ] Add/extend tests to cover updating an endpoint and verifying mapping behavior.

## Work Log

### 2026-02-10 - Review Finding

**By:** Codex

**Actions:**
- Noted stale mapping accumulation risk in `src/cex_api_docs/endpoints.py`.

