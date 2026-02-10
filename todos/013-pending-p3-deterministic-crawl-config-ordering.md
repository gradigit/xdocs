---
status: pending
priority: p3
issue_id: "013"
tags: [code-review, determinism, cli, polish]
dependencies: []
---

# Make Crawl Config Output More Deterministic (Ordering/Dedup)

## Problem Statement

The project positions itself as deterministic. Some CLI assembly paths currently use `set(...)` which can produce non-deterministic ordering in JSON outputs (lists). This is small, but it makes diffs/noise worse for automation.

## Findings

- `src/cex_api_docs/cli.py` merges `allowed_domains` using `list(set(...))`, which yields arbitrary list ordering.
- Seeds may be duplicated when multiple sections share URLs (minor).

## Proposed Solutions

### Option 1: Sort and Dedup Before Calling `crawl_store` (Recommended)

**Approach:**
- Replace `list(set(...))` with deterministic `sorted(set(...))`.
- Dedup seeds in stable order.

**Pros:**
- Minimal change, less noisy output.

**Cons:**
- None meaningful.

**Effort:** Small

**Risk:** Low

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/cli.py`

## Acceptance Criteria

- [ ] `crawl` output lists (`allowed_domains`, `seeds`) have stable ordering across runs.

## Work Log

### 2026-02-10 - Review Finding

**By:** Codex

**Actions:**
- Flagged nondeterministic list ordering risk in CLI crawl arg assembly.

