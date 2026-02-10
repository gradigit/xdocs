---
status: complete
priority: p1
issue_id: "002"
tags: [sqlite, fts5, schema, init, locking]
dependencies: ["001"]
---

# Store + SQLite Schema + `init` Command

## Problem Statement

Implement the deterministic local store root (`./cex-docs/`) and authoritative SQLite schema + FTS5, including:
- idempotent `init`
- FTS5 availability checks
- single-writer lockfile for mutating commands

## Findings

- Plan requires `schema/schema.sql` as authoritative DDL.
- Plan requires a lock at `cex-docs/db/.write.lock` and `ELOCKED` behavior.

## Proposed Solutions

### Option 1: `sqlite3` + explicit DDL apply + PRAGMA user_version (recommended)

**Approach:** Apply `schema/schema.sql` to a fresh DB; store schema version via `PRAGMA user_version`.

**Pros:**
- Simple, explicit
- Easy to test and audit

**Cons:**
- Manual migration handling later (acceptable for v1)

**Effort:** 4-8 hours

**Risk:** Low

## Recommended Action

- Create `schema/schema.sql` defining required tables + FTS5 virtual tables.
- Implement `cex-api-docs init`:
  - create store dirs (`db/`, `raw/`, `pages/`, `meta/`, `endpoints/`, `review/`)
  - create/open DB, verify FTS5 support, apply schema idempotently
  - set/verify schema version
- Implement lockfile acquisition for mutating commands.

## Acceptance Criteria

- [x] `cex-api-docs init` is idempotent
- [x] FTS5 missing -> clear error
- [x] Mutating commands fail fast with `ELOCKED` when lock cannot be acquired

## Work Log

### 2026-02-10 - Created

**By:** Codex

**Actions:**
- Created init/schema todo

### 2026-02-10 - Completed

**By:** Codex

**Actions:**
- Implemented `cex-api-docs init` (dirs, lockfile, SQLite schema apply, PRAGMA user_version)
- Added `unittest` coverage for init idempotence + schema presence + cross-process lock contention
