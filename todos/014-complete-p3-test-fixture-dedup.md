---
status: complete
priority: p3
issue_id: "014"
tags: [code-review, tests, maintainability]
dependencies: []
---

# Deduplicate Local HTTP Fixture Server Helper in Tests

## Problem Statement

The test suite repeats a local HTTP server context manager in multiple files. This is small, but over time it encourages drift or inconsistent behavior between tests.

## Findings

- `tests/test_crawl.py` and `tests/test_endpoints.py` both define `serve_directory(...)` with nearly identical code.

## Proposed Solutions

### Option 1: Extract a Shared Test Helper (Recommended)

**Approach:**
- Create `tests/_http_fixture.py` containing `serve_directory`.
- Import it from both tests.

**Pros:**
- Less duplication and easier maintenance.

**Cons:**
- Small refactor with minimal value.

**Effort:** Small

**Risk:** Low

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `tests/test_crawl.py`
- `tests/test_endpoints.py`

## Acceptance Criteria

- [ ] One shared helper used by both tests.
- [ ] Tests continue to pass.

## Work Log

### 2026-02-10 - Review Finding

**By:** Codex

**Actions:**
- Noted duplication in fixture server code across tests.

