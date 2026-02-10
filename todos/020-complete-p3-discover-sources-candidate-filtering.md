---
status: complete
priority: p3
issue_id: "020"
tags: [code-review, quality, discovery, registry]
dependencies: []
---

# Reduce noise in discover-sources output (filter/score candidates by allowed domains and scope)

## Problem Statement

`cex-api-docs discover-sources` is intended to help bootstrap registry `doc_sources`. If it emits many irrelevant candidates (off-domain or out-of-scope), it increases human/agent friction and can lead to incorrect registry edits.

## Findings

- `src/cex_api_docs/discover_sources.py` produces heuristic candidates (sitemap/spec URLs) from seed pages.
- Candidates are valuable, but should be:
  - validated as http/https
  - scored/filtered relative to registry `allowed_domains` and seed-derived scope prefixes

## Proposed Solutions

### Option 1: Filter by allowed_domains (recommended)

**Approach:**
- For each candidate URL:
  - canonicalize and validate scheme
  - reject if host is outside `allowed_domains` (or its subdomains)
  - keep a small “discarded” sample in output for debugging

**Pros:**
- Reduces false positives immediately.

**Cons:**
- Some valid sources might be hosted on vendor domains (needs allowlist expansion).

**Effort:** 1-2 hours

**Risk:** Low

---

### Option 2: Keep all candidates but add confidence scoring and explicit reason fields

**Approach:**
- Attach:
  - `in_allowed_domains: bool`
  - `in_scope_prefix: bool`
  - `reason: string[]`
- Let the consumer filter.

**Pros:**
- Max transparency, minimal false negatives.

**Cons:**
- Output stays noisy unless consumer filters.

**Effort:** 2-4 hours

**Risk:** Low

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/discover_sources.py`
- `src/cex_api_docs/cli.py` (output fields documented implicitly by JSON)

## Acceptance Criteria

- [ ] discover-sources output includes domain/scope relevance signal or filtering.
- [ ] Output remains stable and JSON-first.
- [ ] `pytest` passes.

## Work Log

### 2026-02-10 - Code Review Finding

**By:** Codex

**Actions:**
- Noted discover-sources currently emits heuristic candidates without strict domain filtering.

**Learnings:**
- Candidate discovery tools should be conservative by default to avoid incorrect registry edits.

### 2026-02-10 - Fix Implemented

**By:** Codex

**Actions:**
- Added `host` and `in_allowed_domains` signals to `discover-sources` output in `src/cex_api_docs/discover_sources.py`.
- Ran `./.venv/bin/pytest -q`.

**Learnings:**
- Keeping candidates but attaching domain relevance helps agents make safe registry edits without losing potentially valid off-domain spec links.
