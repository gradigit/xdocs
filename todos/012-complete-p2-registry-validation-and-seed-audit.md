---
status: complete
priority: p2
issue_id: "012"
tags: [code-review, registry, crawler, reliability]
dependencies: []
---

# Add Registry Validation (Seeds/Domains) and Audit Exchange Entries

## Problem Statement

The exchange registry (`data/exchanges.yaml`) is critical. If seeds redirect, require JS rendering, or point at deprecated pages, the crawler silently stores low-signal “redirect stubs” (empty markdown) and downstream answer/extraction fails.

We already had to update Binance from `binance-docs.github.io` redirect stubs to `developers.binance.com`. Other exchanges likely drift over time too.

## Findings

- There is no automated validation for registry entries:
  - seed URLs reachable?
  - final URL host in `allowed_domains`?
  - content yields non-empty markdown?
  - obvious “meta refresh redirect stub” detected?
- This increases maintenance cost and causes confusing “unknown” answers.

## Proposed Solutions

### Option 1: Add `cex-api-docs validate-registry` (Recommended)

**Approach:**
- Implement a command that iterates registry seeds and emits a JSON report:
  - HTTP status
  - final URL and redirect chain
  - host allowlist compliance
  - extracted markdown length/word_count
  - detected redirect stub heuristics (optional)

**Pros:**
- Fast feedback loop for maintaining the 16-exchange registry.
- Can be run periodically or in CI.

**Cons:**
- Network-dependent command (expected for validation).

**Effort:** Medium

**Risk:** Low/Medium (false positives on JS-heavy sites)

---

### Option 2: Add a Lightweight Script + Document Manual Audit Procedure

**Approach:**
- Keep CLI surface minimal; add a script in `scripts/`.

**Pros:**
- Less API surface.

**Cons:**
- Harder for agents to discover and use.

**Effort:** Small/Medium

**Risk:** Low

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `data/exchanges.yaml`
- `src/cex_api_docs/cli.py` (if adding command)
- `src/cex_api_docs/crawler.py` / `src/cex_api_docs/httpfetch.py`

## Acceptance Criteria

- [ ] Validation identifies redirect stubs and off-domain redirects.
- [ ] Report is deterministic and JSON-first.
- [ ] Document how to update seeds/allowed_domains safely.

## Work Log

### 2026-02-10 - Review Finding

**By:** Codex

**Actions:**
- Noted registry maintenance risk; Binance entry already required a fix.

