---
status: complete
priority: p1
issue_id: "005"
tags: [answer, clarification, binance, runbook]
dependencies: ["003", "004"]
---

# `answer` Assembler + Binance Wow Query Runbook

## Problem Statement

Implement the `answer` assembler command and a reproducible Binance demo runbook that proves:
- clarification flow for “unified trading”
- cite-only claims with excerpts/offsets
- `[DERIVED]` computations only over cited inputs
- `unknown` / `undocumented` / `conflict` handling

## Recommended Action

- Implement `answer` output schema exactly as documented in the plan.
- Implement clarification selection based on Binance sections present in local store.
- Write `docs/runbooks/binance-wow-query.md` covering crawl -> extract -> ingest -> answer.

## Acceptance Criteria

- [x] `answer` returns `needs_clarification` for ambiguous “unified trading”
- [x] After clarification, output contains only cite-backed claims
- [x] Derived claims include explicit input claim references

## Work Log

### 2026-02-10 - Created

**By:** Codex

**Actions:**
- Created answer/runbook todo

### 2026-02-10 - Completed

**By:** Codex

**Actions:**
- Implemented `answer` assembler with clarification + cite-only claims + optional `[DERIVED]` diff over cited inputs
- Updated Binance wow query runbook to match current CLI flags
- Added tests for clarification flow and derived claim wiring
