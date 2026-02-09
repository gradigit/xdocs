---
status: ready
priority: p1
issue_id: "003"
tags: [crawler, robots, indexing, diff, pages]
dependencies: ["002"]
---

# Crawl + Page Index + Diff

## Problem Statement

Implement deterministic crawling and page-level retrieval:
- `crawl` (domain allowlist, robots semantics, retry/backoff, limits)
- persistence of raw/meta/pages with hashes
- `search-pages`, `get-page`, `diff`
- `fts-optimize`, `fts-rebuild`

## Findings

- Robots semantics are specified (RFC9309 error handling posture).
- `path_hash` depends on defined URL canonicalization.
- Excerpts must be mechanically verifiable against stored markdown (verbatim + offsets).

## Proposed Solutions

### Option 1: BFS crawler using `requests` + `bs4` (recommended)

**Approach:** BFS crawl from seeds; parse `<a href>` for same-domain links; store each fetched page; update SQLite in a transaction.

**Pros:**
- Straightforward and deterministic
- Works for most static doc sites

**Cons:**
- Needs Playwright fallback for JS-rendered docs (optional in v1)

**Effort:** 1-2 days

**Risk:** Medium (edge cases: JS docs, redirects, robots quirks)

## Recommended Action

Implement:
- `crawl` with safe defaults and flags (`--url`, `--domain-scope`, `--max-depth`, `--max-pages`, `--delay`, `--ignore-robots`, `--render`)
- Page ingestion:
  - write raw bytes to `raw/`
  - extract markdown via html2text, normalize, compute `content_hash`
  - write markdown to `pages/` and metadata to `meta/`
  - upsert `pages` row + update `pages_fts`
  - append JSONL crawl log
- Diff based on `prev_content_hash` vs current `content_hash`.

## Acceptance Criteria

- [ ] Fixture crawl integration test passes offline
- [ ] `search-pages` returns ranked results with snippets
- [ ] `diff` reports updated/new/stale pages stably

## Work Log

### 2026-02-10 - Created

**By:** Codex

**Actions:**
- Created crawl/index/diff todo

