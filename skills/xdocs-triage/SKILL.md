---
name: xdocs-triage
description: >
  Ingest, validate, and fix bug reports for xdocs. Independently reproduces issues,
  challenges the reporter's severity/classification, plans fixes via forge-orchestrator,
  and implements with full A/B testing. Bug reports are evidence, not ground truth.
---

# xdocs Bug Triage

## Core Principle: Bug Reports Are Evidence, Not Ground Truth

A bug report is **one agent's interpretation** of unexpected behavior. It may be:
- **Correct** — the issue is real and classified accurately
- **Inflated** — the issue is real but severity/scope is overstated
- **Misclassified** — the root cause is wrong (e.g., blamed on xdocs-code but actually stale data)
- **Not reproducible** — environment-specific, already fixed, or intermittent
- **Not a bug** — expected behavior that the reporter didn't understand

**Every claim in the report must be independently verified.** Do not trust severity, root cause, affected scope, or reproduction steps without running them yourself.

## When to Use

Use this skill when you receive a bug report (from xdocs-bugreport skill, GitHub issue, or informal report) and need to:
1. Validate whether the issue is real
2. Determine the actual root cause and severity
3. Plan and implement a fix with proper A/B testing

## Workflow

### Phase 1: Ingest & Understand (do NOT start fixing yet)

1. **Read the full report.** Note the claimed severity, root cause, and affected scope.
2. **Read CLAUDE.md** — check "Gotchas" section. Many reported bugs are documented limitations.
3. **Read TODO.md** — check if this is a known bug (BUG-1 through BUG-21, OPT-1 through OPT-14).
4. **Check git log** — has this been fixed since the report was filed?

```bash
# Check if the report's issue area was recently touched
git log --oneline --since="<report_date>" -- src/xdocs/<relevant_module>.py
```

### Phase 2: Independent Reproduction

**Do not copy-paste the reporter's commands blindly.** Understand what they're testing, then design your own reproduction:

1. **Verify environment matches:**
```bash
xdocs --version
python3 --version
xdocs store-report 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('result',d); print(f'Pages: {r.get(\"total_pages\",\"?\")}, Endpoints: {r.get(\"total_endpoints\",\"?\")}')"
```

2. **Reproduce the exact reported behavior:**
```bash
# Run the reporter's exact command
<command from report>
# Compare output to what they reported
```

3. **Test adjacent cases** (the reporter may have missed the real pattern):
```bash
# Vary the input slightly — different exchange, different query type
# Test with and without semantic search (cold start vs warm)
# Test with --docs-dir explicitly vs auto-discovery
```

4. **Classify reproduction result:**

| Result | Meaning | Next Step |
|--------|---------|-----------|
| **Exact match** | Bug confirmed as reported | Phase 3 |
| **Partial match** | Issue exists but different than reported | Re-classify severity/scope |
| **Not reproducible** | Can't trigger the issue | Check environment diff, close or defer |
| **Already fixed** | Recent commits resolved it | Close with commit reference |
| **Expected behavior** | Working as designed | Close as NOT A BUG, update docs if confusing |

### Phase 3: Challenge the Report

Before planning any fix, explicitly challenge these claims from the report:

#### Challenge 1: Is the severity accurate?

| Reporter says | Ask yourself | Common inflation |
|--------------|--------------|-----------------|
| CRITICAL | Does it cause data loss or security risk? | Agents call everything critical |
| HIGH | Is the entire feature broken, or just one query? | "Broken" often means "suboptimal" |
| MEDIUM | Is the result wrong, or just not what they expected? | "Wrong answer" may be correct but incomplete |

**Reassess severity independently.** Count how many golden QA queries are affected:
```bash
# Run the eval to check actual impact
python3 tests/eval_answer_pipeline.py --qa-file tests/golden_qa.jsonl --save reports/triage-<bug-id>.json
```

#### Challenge 2: Is the root cause correct?

The reporter's root cause classification is a hypothesis. Verify:

| They say | Actually check |
|----------|---------------|
| `xdocs-code` | Is the data fresh? Is the dependency installed? Is the input valid? |
| `xdocs-data` | Run `xdocs quality-check`. Check `crawled_at` for the specific pages. |
| `upstream-change` | Fetch the live page and compare to stored markdown. |
| `user-environment` | Can you reproduce in the project venv? |

#### Challenge 3: Is the affected scope accurate?

Reporters often generalize from 1 failure to "all queries are broken." Verify scope:

```bash
# Test 5 similar queries across different exchanges
# If only 1 fails, scope is narrow — not "all exchanges"
```

### Phase 4: Plan the Fix

**Only proceed here if Phase 2 confirmed the bug and Phase 3 validated (or corrected) severity.**

Follow the Change Validation Protocol (CLAUDE.md):

1. **Design new test cases FIRST** — golden QA entries + unit tests for the specific bug.
2. **Capture baseline** — `python3 tests/eval_answer_pipeline.py --qa-file tests/golden_qa.jsonl --save reports/<bug-id>-baseline.json`
3. **Write the fix plan** — which files, what changes, estimated risk.
4. If the fix is non-trivial, invoke `/forge` to orchestrate research → plan → build → review.

### Phase 5: Implement & Validate

Follow the forge-orchestrator workflow:

1. **Implement the fix** — one change at a time.
2. **Run unit tests** — `pytest -q --tb=short` — all must pass.
3. **Run pipeline eval** — `--compare reports/<bug-id>-baseline.json` — no path may regress >3% MRR.
4. **Grow the test suite** — add tests that would have caught this bug.
5. **Commit with reference** — include the bug report ID in the commit message.

### Phase 6: Close the Report

Write a triage summary appended to the original report or as a separate file:

```markdown
## Triage Result

**Triaged by:** <agent model>
**Date:** YYYY-MM-DD
**Verdict:** CONFIRMED | PARTIALLY CONFIRMED | NOT REPRODUCIBLE | NOT A BUG | ALREADY FIXED

### Reproduction
- Reproduced: Yes/No/Partial
- Environment match: Yes/No (differences: ___)

### Severity Reassessment
- Reporter claimed: <their severity>
- Actual severity: <your assessment>
- Reason: <why different, if different>

### Root Cause Reassessment
- Reporter claimed: <their root cause>
- Actual root cause: <your assessment>
- Reason: <why different, if different>

### Fix
- Commit: <hash> or "deferred to M<N>" or "closed — not a bug"
- Tests added: <count> unit tests, <count> golden QA entries
- Eval impact: MRR <before> → <after>, <path> regression: none
```

## Anti-Patterns to Avoid

1. **Trusting the report blindly.** A bug report from another agent is just structured speculation. The agent that filed it may have been confused, working with stale data, or inflating severity to seem thorough.

2. **Fixing before reproducing.** Never write code based on a description alone. You might fix the wrong thing.

3. **Scope creep.** The bug report says "nav chrome in excerpts." Don't also refactor the excerpt function, add new features, or "clean up" adjacent code. Fix the reported issue only.

4. **Skipping the eval.** Every fix to the answer/search pipeline MUST have a before/after eval comparison. "It works on the one failing query" is not validation — you might have regressed 10 others.

5. **Accepting inflated severity.** If the report says CRITICAL but it's a cosmetic issue affecting 1 exchange, downgrade it. The maintainer needs accurate severity to prioritize.

6. **Assuming the reporter tested thoroughly.** They probably tested 1-3 queries. You need to test 200+ (golden QA) to know the real impact.
