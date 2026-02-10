---
status: complete
priority: p2
issue_id: "018"
tags: [code-review, performance, crawling, config]
dependencies: []
---

# Fix sync create-inventory max_bytes policy (avoid forcing 50MB for link-follow page fetches)

## Problem Statement

`cex-api-docs sync` currently forces `create_inventory(max_bytes=max(50MB, user_max_bytes))`. This was likely intended to allow large sitemaps/specs, but it also applies to link-follow inventory page fetching, which only needs small HTML to extract links.

This can make inventory generation unexpectedly expensive (bandwidth, time, memory) and can increase the likelihood of triggering WAF protections.

## Findings

- `src/cex_api_docs/sync.py` calls:
  - `create_inventory(..., max_bytes=max(50_000_000, int(max_bytes)), ...)`
- `src/cex_api_docs/inventory.py` link-follow uses `cfg.max_bytes` for fetching each page to extract links.
- Fetch phase (`fetch_inventory`) uses the user-provided `--max-bytes` (default 10MB), so inventory generation can be *more expensive* than the actual fetch phase.

## Proposed Solutions

### Option 1: Split inventory max-bytes into sitemap/spec vs page-link extraction (recommended)

**Approach:**
- Introduce separate limits:
  - `inventory_sitemap_max_bytes` (default 50MB)
  - `inventory_page_max_bytes` (default 2-5MB)
- In link-follow mode, use `inventory_page_max_bytes`.
- In sitemap/openapi/postman downloads, use `inventory_sitemap_max_bytes`.

**Pros:**
- Predictable resource usage.
- Maintains support for large sitemaps/specs without bloating link-follow.

**Cons:**
- Adds additional configuration surface area (needs CLI + config decision).

**Effort:** 2-4 hours

**Risk:** Low/Medium

---

### Option 2: Remove the 50MB floor and rely on user max-bytes everywhere

**Approach:**
- Pass `max_bytes=int(max_bytes)` to create_inventory.
- Document that large sitemaps/specs may require a larger `--max-bytes`.

**Pros:**
- Very simple and consistent.

**Cons:**
- Users may hit failures on large sitemaps unless they know to increase the limit.

**Effort:** 30-60 minutes

**Risk:** Low

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/sync.py`
- `src/cex_api_docs/inventory.py`
- `src/cex_api_docs/cli.py` (if adding new flags)

## Acceptance Criteria

- [ ] `sync` does not force link-follow inventory to fetch up to 50MB per page by default.
- [ ] Large sitemap/spec use cases remain supported (documented knob + tests/fixtures).
- [ ] `pytest` passes.

## Work Log

### 2026-02-10 - Code Review Finding

**By:** Codex

**Actions:**
- Confirmed `sync` forces a 50MB minimum max_bytes for create_inventory in `src/cex_api_docs/sync.py`.

**Learnings:**
- Resource limits should reflect the job (sitemap/spec downloads vs link extraction) rather than sharing one global cap.

### 2026-02-10 - Fix Implemented

**By:** Codex

**Actions:**
- Introduced `link_follow_max_bytes` in `src/cex_api_docs/inventory.py` so sitemap/spec enumeration can keep a higher cap without forcing the same cap on link-follow HTML link extraction.
- Updated `src/cex_api_docs/sync.py` to pass:
  - `max_bytes=max(50MB, user_max_bytes)` for sitemap/spec downloads
  - `link_follow_max_bytes=user_max_bytes` for link-follow page fetches
- Ran `./.venv/bin/pytest -q`.

**Learnings:**
- Splitting “enumeration payload size” from “page fetch payload size” avoids surprising resource spikes in link-follow mode.
