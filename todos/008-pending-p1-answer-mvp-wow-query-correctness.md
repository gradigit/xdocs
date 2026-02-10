---
status: pending
priority: p1
issue_id: "008"
tags: [code-review, answer, correctness, cite-only, binance]
dependencies: []
---

# Fix `answer` Correctness for MVP Wow Query (Avoid False "ok" and Irrelevant Claims)

## Problem Statement

The `cex-api-docs answer` command is the showcase for the cite-only knowledge base. It must not return `status: "ok"` unless it actually answers the requested facts, and it must not emit irrelevant excerpts labeled as `required_permissions`.

Right now the assembler can return:
- `status: "ok"` with partial/irrelevant claims
- claims that do not actually answer the permissions subquestion

This undermines the “100 percent accurate, cite-only” contract and the MVP wow query requirement.

## Findings

- `src/cex_api_docs/answer.py` sets `status = "ok" if claims else "unknown"`.
  - This marks answers as OK even when a subquestion could not be answered.
- Portfolio Margin “permissions” handling is currently a best-effort FTS query:
  - query: `"permission OR permissions OR api key"`
  - excerpt selection: regex around `permission|api\s+key`
  - This can match unrelated text (e.g., “limits are based on IPs, not API keys”) and then be tagged `field_name: required_permissions`.
- The spec requires `unknown` / `undocumented` when the fact is not supported, and requires clarity on ambiguous “unified trading”.

## Proposed Solutions

### Option 1: Treat Wow Query as Multiple Required Subanswers (Recommended)

**Approach:**
- Split the wow query into explicit sub-questions:
  - (A) rate-limit comparison
  - (B) Portfolio Margin balance permissions
- Only return `status: ok` if (A) and (B) are satisfied with cite-backed claims.
- If (B) cannot be supported from stored sources:
  - return `status: unknown` (if missing sources) or `status: undocumented` (if crawled sources exist but no explicit permissions found)
  - include notes describing the exact search attempts and what to crawl next
- Do not emit a “permissions” claim unless the excerpt explicitly contains a permissions requirement.

**Pros:**
- Aligns with cite-only accuracy expectations.
- Prevents “looks correct but isn’t” responses.

**Cons:**
- Requires defining what constitutes “explicit permissions requirement” for v1.

**Effort:** Medium

**Risk:** Medium (UX expectations vs strictness)

---

### Option 2: Prefer Structured Endpoint Records for Permissions/Rates (Fallback to Page Excerpts)

**Approach:**
- If endpoints are ingested for Binance PM/Spot:
  - answer from endpoint JSON (per-field citations already validated)
- Otherwise:
  - fall back to page excerpt approach with stricter matching rules

**Pros:**
- Higher precision once endpoint records exist.
- Leverages the designed agent boundary.

**Cons:**
- Requires endpoint dataset to exist for the demo to be satisfying.

**Effort:** Medium/Large

**Risk:** Medium

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `src/cex_api_docs/answer.py`
- `tests/test_answer.py`
- `docs/runbooks/binance-wow-query.md`

## Acceptance Criteria

- [ ] `answer` returns `needs_clarification` for ambiguous “unified trading” (already present).
- [ ] After clarification, `status: ok` only if:
  - [ ] both the rate-limit comparison and the permissions requirement are answered, or
  - [ ] the response explicitly returns `unknown`/`undocumented` for the missing subanswer.
- [ ] No claim is labeled `required_permissions` unless the excerpt explicitly states permissions.
- [ ] Add tests covering:
  - [ ] partial answer should not return `ok`
  - [ ] permissions missing should return `unknown` or `undocumented` with notes

## Work Log

### 2026-02-10 - Review Finding

**By:** Codex

**Actions:**
- Identified incorrect `status` policy and overly broad permissions search in `src/cex_api_docs/answer.py`.

