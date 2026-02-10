---
status: complete
priority: p2
issue_id: "006"
tags: [tests, pytest, quality]
dependencies: ["002", "003", "004", "005"]
---

# Tests and Quality Gates

## Problem Statement

Lock down deterministic behavior and contracts with tests:
- hashing determinism
- URL canonicalization determinism
- robots semantics behavior
- schema validation behavior
- CLI golden JSON shapes

## Recommended Action

- Add pytest suite with fixture crawl site tests.
- Add golden tests for CLI outputs (success + error).
- Avoid relying on live exchange docs as the only signal.

## Acceptance Criteria

- [x] Test suite runs locally with `pytest`
- [x] Core contracts are covered by tests

## Work Log

### 2026-02-10 - Created

**By:** Codex

**Actions:**
- Created tests todo

### 2026-02-10 - Completed

**By:** Codex

**Actions:**
- Added unit + integration tests covering init/locking, crawl/search/diff, endpoint ingest + review queue, and answer clarification/derived wiring
- Verified `pytest` runs green on the unittest-based suite
