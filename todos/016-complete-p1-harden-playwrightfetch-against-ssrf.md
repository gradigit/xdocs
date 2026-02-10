---
status: complete
priority: p1
issue_id: "016"
tags: [code-review, security, playwright, ssrf]
dependencies: []
---

# Harden Playwright fetching against SSRF via subresource requests

## Problem Statement

When using Playwright to render JS-heavy docs pages, the browser may issue subresource requests (scripts, images, XHR/fetch) to arbitrary URLs embedded in the page. If unrestricted, this creates an SSRF-like risk (hitting localhost, private IPs, or sensitive metadata endpoints) from the machine running the crawler.

## Findings

- `src/cex_api_docs/playwrightfetch.py` explicitly:
  - enforces `allowed_domains` only for navigation (document) requests via `request.is_navigation_request()`
  - allows all non-navigation subresource requests to proceed
- This means a docs page can cause the crawler host to request:
  - `http://127.0.0.1/...`
  - `http://169.254.169.254/...` (cloud metadata)
  - private RFC1918 ranges
  - other internal services reachable from the crawler network

## Proposed Solutions

### Option 1: Block local/private network destinations for ALL requests (recommended baseline)

**Approach:**
- In the Playwright route handler, abort any request whose host is:
  - `localhost`
  - an IP literal in loopback/link-local/private ranges
- Optionally: resolve DNS for hostnames and block if resolution returns private/link-local/loopback.

**Pros:**
- Mitigates the highest-risk SSRF cases without breaking legitimate CDN usage.
- Minimal impact on render success for typical docs.

**Cons:**
- DNS resolution can be slow and can introduce flakiness if done on every request (needs caching).

**Effort:** 2-4 hours

**Risk:** Medium

---

### Option 2: Enforce `allowed_domains` for all requests (strict allowlist)

**Approach:**
- Abort any request (navigation or subresource) whose host is not in `allowed_domains`.
- Expand `allowed_domains` in `data/exchanges.yaml` to include required CDNs per exchange.

**Pros:**
- Strongest policy.

**Cons:**
- Likely to break rendering on many sites unless allowlists include multiple CDNs.
- Ongoing maintenance burden as docs stacks change.

**Effort:** 1-2 days (including allowlist tuning)

**Risk:** Medium/High

---

### Option 3: Make it configurable with a safe default

**Approach:**
- Add config flag(s) for Playwright:
  - `--playwright-network-policy private_only|allowed_domains|open`
- Default to `private_only` (Option 1).

**Pros:**
- Keeps compatibility while enabling stricter mode when needed.

**Cons:**
- More surface area and config complexity.

**Effort:** 4-6 hours

**Risk:** Medium

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/playwrightfetch.py`
- Potential callers: `src/cex_api_docs/inventory.py`, `src/cex_api_docs/inventory_fetch.py`, `src/cex_api_docs/registry_validate.py`

## Resources

- Playwright routing currently only blocks disallowed hosts for navigation requests.

## Acceptance Criteria

- [ ] Subresource requests to localhost/private/link-local IPs are blocked.
- [ ] Navigation requests remain restricted to `allowed_domains`.
- [ ] Rendering still works for at least one JS-heavy docs site in the registry.
- [ ] `pytest` passes.
- [ ] Add a unit test for IP-literal blocking (and DNS-rebinding prevention if implemented).

## Work Log

### 2026-02-10 - Code Review Finding

**By:** Codex

**Actions:**
- Confirmed Playwright route handler only enforces `allowed_domains` on `request.is_navigation_request()`.

**Learnings:**
- Crawling untrusted HTML/JS should treat the browser as a network-capable agent and apply SSRF defenses.

### 2026-02-10 - Fix Implemented

**By:** Codex

**Actions:**
- Added SSRF hardening in `src/cex_api_docs/playwrightfetch.py`:
  - block localhost and non-global IP literals
  - block hostnames that resolve to non-public IPs (DNS rebinding defense; cached per fetch)
- Added unit tests for the security helpers in `tests/test_playwrightfetch_security.py`.
- Ran `./.venv/bin/pytest -q`.

**Learnings:**
- The safest default is to treat DNS resolution failures as unsafe for subresources in a crawler context.
