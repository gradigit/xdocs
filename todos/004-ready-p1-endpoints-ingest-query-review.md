---
status: complete
priority: p1
issue_id: "004"
tags: [endpoints, jsonschema, ingest, review-queue, fts]
dependencies: ["002"]
---

# Endpoint Ingest + Query + Review Queue

## Problem Statement

Implement deterministic ingestion of agent-produced endpoint JSON into disk + SQLite, including:
- schema validation with excerpt/offset requirements
- endpoint identity `endpoint_id`
- `search-endpoints`
- review queue: list/show/resolve
- `endpoint_sources` mapping so page hash change triggers re-review.

## Proposed Solutions

### Option 1: JSON Schema validation (`jsonschema`) + strict ingest (recommended)

**Approach:** Validate endpoint JSON against `schemas/endpoint.schema.json`, then persist and index.

**Pros:**
- Enforces cite-only provenance rules mechanically
- Prevents “citation spray”

**Cons:**
- Requires maintaining schema versioning

**Effort:** 1-2 days

**Risk:** Medium (schema evolution, real-world endpoint variety)

## Recommended Action

- Define `schemas/endpoint.schema.json` matching the plan.
- Implement `save-endpoint`:
  - validate required provenance
  - verify excerpt offsets match stored markdown for cited pages (when available)
  - persist endpoint JSON to `endpoints/.../{endpoint_id}.json`
  - upsert `endpoints` + update `endpoints_fts`
  - write `endpoint_sources` rows
  - enqueue review items based on confidence/excerpt rules
- Implement `search-endpoints` and review queue commands.

## Acceptance Criteria

- [x] Ingest rejects endpoint JSON missing required provenance or excerpts for asserted high-risk fields
- [x] `search-endpoints` supports exchange/section/method/path keyword queries
- [x] Review queue can be resolved and persists state

## Work Log

### 2026-02-10 - Created

**By:** Codex

**Actions:**
- Created endpoints ingest/query todo

### 2026-02-10 - Completed

**By:** Codex

**Actions:**
- Implemented `save-endpoint`, `search-endpoints`, `review-*` commands with strict citation verification
- Persisted endpoint JSON to disk + SQLite + FTS, and wrote `endpoint_sources` mappings
- Added tests covering ingestion, search, and review queue resolution
