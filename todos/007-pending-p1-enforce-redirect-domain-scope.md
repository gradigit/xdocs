---
status: pending
priority: p1
issue_id: "007"
tags: [code-review, security, ssrf, crawler, redirects]
dependencies: []
---

# Enforce Domain Allowlist Across Redirects (SSRF Guardrail)

## Problem Statement

`cex-api-docs crawl` is supposed to be strictly domain-scoped (allowlist), but the current HTTP fetch layer follows redirects to *any* host. This violates the project’s own spec (strict allowlist) and creates an SSRF / unintended network access risk.

## Findings

- `src/cex_api_docs/httpfetch.py` uses `requests.Session.get(..., allow_redirects=True)` and returns `final_url` + `resp.history`, but does not validate redirect targets.
- `src/cex_api_docs/crawler.py` checks `allowed_domains` only against the *requested* URL before calling `fetch(...)`. It does **not** re-check the host for `FetchResult.final_url`, nor the `redirect_chain`.
- Result: a seed URL on an allowed domain can redirect to a disallowed domain and still be fetched and stored.

## Proposed Solutions

### Option 1: Manual Redirect Following with Per-Hop Validation (Recommended)

**Approach:**
- Change `fetch(...)` to `allow_redirects=False`.
- Follow redirects manually up to `max_redirects`.
- For each redirect hop:
  - resolve absolute Location URL
  - enforce scheme `http|https`
  - enforce host in `allowed_domains`
  - (optional) enforce `robots_can_fetch` per-hop if desired
- Only fetch the terminal body once the final URL is validated.

**Pros:**
- Prevents fetching disallowed redirect targets (actual SSRF mitigation).
- Makes redirect policy explicit and testable.

**Cons:**
- More code vs `requests` built-in redirect handling.
- Must carefully replicate edge cases (relative Location, 30x loops).

**Effort:** Medium

**Risk:** Medium (redirect edge cases)

---

### Option 2: Post-Fetch Validation of `final_url` and `history` (Not Sufficient for SSRF)

**Approach:**
- Keep `allow_redirects=True`.
- After fetch, error if `final_url`/history host not in allowlist.

**Pros:**
- Minimal change.

**Cons:**
- Still fetches the disallowed target before rejecting (SSRF still happens).

**Effort:** Small

**Risk:** Low

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/httpfetch.py`
- `src/cex_api_docs/crawler.py`
- `tests/test_crawl.py`

## Resources

- Plan requirement: strict allowlist domain scoping (see `docs/plans/2026-02-09-feat-cex-api-docs-cite-only-knowledge-base-plan.md`)

## Acceptance Criteria

- [ ] Redirects never cause a fetch to a host not in the allowlist.
- [ ] Redirect loops are bounded by `max_redirects`.
- [ ] Error output is structured (`CexApiDocsError`) and includes URL + violating host.
- [ ] Add a unit/integration test that:
  - starts two local servers
  - allowed server returns a 302 to disallowed server
  - crawler does not fetch disallowed server content

## Work Log

### 2026-02-10 - Review Finding

**By:** Codex

**Actions:**
- Identified redirect allowlist gap in `src/cex_api_docs/httpfetch.py` and `src/cex_api_docs/crawler.py`.

