---
status: complete
priority: p2
issue_id: "010"
tags: [code-review, reliability, storage, sqlite]
dependencies: []
---

# Improve Store Atomicity (Prevent DB/File Divergence) or Add `fsck` Reconciliation

## Problem Statement

The spec calls out atomicity: raw/meta/page/DB should not diverge. Today, file writes and DB writes are not transactionally linked, which can leave:
- orphaned files without DB rows
- DB rows pointing at missing files (if a write fails mid-flight)

This is mostly a crash-consistency problem, but it matters for long-running crawls and trust in provenance.

## Findings

- `src/cex_api_docs/crawler.py` writes `raw_path` and `md_path` before DB upsert, then writes `meta_path` during the DB transaction.
  - If the DB transaction fails, raw/markdown may still exist without DB row.
- `src/cex_api_docs/endpoints.py` writes endpoint JSON file before DB upsert.

## Proposed Solutions

### Option 1: Add `cex-api-docs fsck` (Recommended v1)

**Approach:**
- Add a deterministic reconciliation command that scans:
  - DB rows whose referenced files are missing
  - files on disk with no corresponding DB rows
- Report as JSON and optionally repair (delete or re-index) behind an explicit flag.

**Pros:**
- Solves operational integrity without complex cross-resource transactions.
- Keeps v1 simple while still meeting reliability needs.

**Cons:**
- Does not prevent divergence, only detects/remediates.

**Effort:** Medium

**Risk:** Low/Medium (repair safety)

---

### Option 2: Two-Phase Writes With Temporary Paths

**Approach:**
- Stage writes to temp paths.
- Perform DB write referencing final paths.
- After DB commit, rename staged files into place.
- On crash, fsck cleans staged artifacts.

**Pros:**
- Stronger crash consistency.

**Cons:**
- More complexity; still not a true cross-resource transaction.

**Effort:** Large

**Risk:** Medium

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/crawler.py`
- `src/cex_api_docs/endpoints.py`
- `src/cex_api_docs/cli.py` (new command wiring)

## Acceptance Criteria

- [ ] Provide a way to detect inconsistencies between disk and DB.
- [ ] Document how to recover from partial crawls/ingests.
- [ ] Add tests for fsck detection (and repair, if implemented).

## Work Log

### 2026-02-10 - Review Finding

**By:** Codex

**Actions:**
- Identified non-atomic file/DB write patterns in crawler and endpoint ingest.

