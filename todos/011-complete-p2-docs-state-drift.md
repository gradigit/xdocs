---
status: complete
priority: p2
issue_id: "011"
tags: [code-review, docs, onboarding]
dependencies: []
---

# Fix Repo Documentation Drift (CLAUDE.md / TODO.md vs Actual State)

## Problem Statement

Team onboarding and agent usage depends on repo docs being accurate. Currently, `CLAUDE.md` and `TODO.md` state that execution hasn’t started, but the MVP is implemented and tests pass. This will confuse new contributors and agents.

## Findings

- `CLAUDE.md`:
  - “Current Phase: not started (planning complete, execution not started)”
- `TODO.md`:
  - “Current Phase: Mode 2 plan iteration”
- Reality:
  - MVP plan is implemented (`docs/plans/2026-02-09-feat-cex-api-docs-cite-only-knowledge-base-plan.md` has all phases checked).
  - CLI exists and tests pass.

## Proposed Solutions

### Option 1: Update `CLAUDE.md` + `TODO.md` to Reflect Current State (Recommended)

**Approach:**
- Update “Current Phase” and progress sections to reflect:
  - MVP complete
  - current branch/next roadmap items
- Link to the authoritative plan + runbook.

**Pros:**
- Minimal churn; keeps docs useful.

**Cons:**
- Requires discipline to keep updated.

**Effort:** Small

**Risk:** Low

---

### Option 2: Replace `TODO.md` With a Pointer to `todos/` and `docs/plans/`

**Approach:**
- Make `TODO.md` minimal and non-duplicative.

**Pros:**
- Reduces drift surface area.

**Cons:**
- Less “one-file overview”.

**Effort:** Small

**Risk:** Low

## Recommended Action

To be filled during triage.

## Technical Details

**Affected files:**
- `CLAUDE.md`
- `TODO.md`

## Acceptance Criteria

- [ ] Top-level docs accurately represent current state and next steps.
- [ ] No references implying “execution not started” after MVP is implemented.

## Work Log

### 2026-02-10 - Review Finding

**By:** Codex

**Actions:**
- Flagged drift between CLAUDE/TODO and implemented repo state.

