---
status: complete
priority: p2
issue_id: "017"
tags: [code-review, crawling, robots, performance]
dependencies: []
---

# Make link-follow inventory generation robots-aware and throttle requests

## Problem Statement

For exchanges without usable sitemaps, `inventory_policy.mode=link_follow` is used to generate a URL inventory. As implemented, link-follow can:

- issue high volumes of requests quickly (no throttling)
- ignore robots.txt allow/deny rules
- fetch large pages (especially with current sync defaults)

This creates unnecessary load, increases the chance of blocking/WAF triggers, and makes “cron-friendly deterministic acquisition” less reliable.

## Findings

- `src/cex_api_docs/inventory.py` link-follow loop:
  - does not check robots rules (even when `ignore_robots` is false)
  - does not sleep/delay between requests
  - can enqueue many links; `queued`/`heap` may grow large even with `max_pages`
- The repo already has a robots helper used by fetch:
  - `src/cex_api_docs/robots.py`
  - `src/cex_api_docs/inventory_fetch.py` respects robots and sleeps `delay_s`
- Link-follow render mode is controlled only by `inventory_policy.render_mode`, not by sync `--render`, which can surprise users.

## Proposed Solutions

### Option 1: Reuse the same robots + delay behavior as `fetch-inventory` (recommended)

**Approach:**
- Add `delay_s` to inventory link-follow config (policy + CLI override).
- Implement per-host robots cache using `fetch_robots_policy`.
- Skip disallowed URLs (or mark as discovered-but-skipped in sources metadata).
- Add a cap on queued URLs to prevent runaway memory usage (e.g. `max_queue`).
- Clarify render_mode precedence (sync flag vs policy default).

**Pros:**
- Aligns inventory generation with fetch behavior (predictable).
- Reduces risk of blocks and improves stability.

**Cons:**
- Slower inventory generation (intended tradeoff).

**Effort:** 4-8 hours

**Risk:** Medium

---

### Option 2: Keep inventory “fast” but enforce queue caps + best-effort robots

**Approach:**
- Only apply robots checks for seed hosts, skip delay, rely on `max_pages`/queue caps.

**Pros:**
- Faster runs.

**Cons:**
- Still risks WAF triggers and inconsistent behavior.

**Effort:** 2-4 hours

**Risk:** Medium

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/inventory.py`
- `src/cex_api_docs/registry.py` (InventoryPolicy shape if extended)
- `src/cex_api_docs/cli.py` (if exposing new options)

## Resources

- Existing reference implementation for robots+delay: `src/cex_api_docs/inventory_fetch.py`.

## Acceptance Criteria

- [ ] Link-follow inventory respects robots.txt unless `--ignore-robots` is set.
- [ ] Link-follow inventory supports throttling (delay) with a sensible default.
- [ ] Queue growth is bounded (documented cap + metrics in inventory sources).
- [ ] Behavior is documented and stable for agents (JSON output includes relevant policy + decisions).
- [ ] `pytest` passes.

## Work Log

### 2026-02-10 - Code Review Finding

**By:** Codex

**Actions:**
- Confirmed link-follow inventory loop lacks robots checks and throttling in `src/cex_api_docs/inventory.py`.

**Learnings:**
- Treat inventory generation as production crawling; it should behave at least as safely as the fetch phase.

### 2026-02-10 - Fix Implemented

**By:** Codex

**Actions:**
- Updated link-follow inventory generation in `src/cex_api_docs/inventory.py`:
  - robots-aware skipping (unless `--ignore-robots`)
  - per-URL throttling (`delay_s`, default 0.25s)
  - queue growth cap with dropped-link metrics
  - link-follow uses a separate `link_follow_max_bytes` cap
- Wired `sync` to pass `delay_s`, `default_render_mode`, and `link_follow_max_bytes` into inventory generation in `src/cex_api_docs/sync.py`.
- Ran `./.venv/bin/pytest -q`.

**Learnings:**
- Even “inventory only” crawling needs safety controls, since it still drives network traffic at scale.
