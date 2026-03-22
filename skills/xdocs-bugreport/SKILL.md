---
name: xdocs-bugreport
description: >
  Generate a structured, objective bug report for xdocs issues. Collects environment
  info, reproduces the issue, classifies root cause and severity without inflation,
  and outputs a shareable markdown file. Use when encountering unexpected xdocs behavior.
---

# xdocs Bug Report

## When to Use

Use this skill when you or a user encounters unexpected behavior from xdocs — wrong answers, crashes, missing data, performance issues, or confusing output. The skill produces a structured report that a maintainer can act on without needing to reproduce the issue from scratch.

## What This Skill Does NOT Do

- **Does not assume the bug is in xdocs.** Many issues are user environment, stale data, missing dependencies, or upstream exchange changes. The report must classify the root cause honestly.
- **Does not inflate severity.** A cosmetic issue is LOW, not HIGH. A query returning slightly wrong results is MEDIUM, not CRITICAL. Only data loss, security issues, or complete feature breakage is HIGH/CRITICAL.
- **Does not prescribe fixes.** The report describes what happened and why. The maintainer decides what to do.

## Severity Scale (strict)

| Level | Meaning | Examples |
|-------|---------|---------|
| **CRITICAL** | Data loss, security vulnerability, or complete system failure | DB corruption, credential exposure, all queries crash |
| **HIGH** | Feature completely broken for a class of inputs | All error_message queries return unknown, sync hangs indefinitely |
| **MEDIUM** | Feature partially broken or produces incorrect results | Wrong exchange detected, excerpt contains nav chrome, docs_url points to wrong page |
| **LOW** | Cosmetic, minor inconvenience, or edge case | Formatting issue in output, slow cold start, deprecation warning |
| **NOT A BUG** | Expected behavior, user error, or upstream issue | Exchange changed their docs, query too vague, dependency not installed |

## Root Cause Classification

Every report MUST classify the root cause as one of:

| Category | Description | Action |
|----------|-------------|--------|
| **xdocs-code** | Bug in xdocs source code | File GitHub issue |
| **xdocs-data** | Stale/missing/corrupt data in the store | Re-sync or re-import |
| **user-environment** | Missing deps, wrong Python version, stale install | User fixes their setup |
| **user-input** | Query too vague, wrong syntax, unsupported input | User adjusts their query |
| **upstream-change** | Exchange changed their docs/API after last crawl | Re-crawl the exchange |
| **known-limitation** | Documented limitation (e.g., SPA not rendered, login-gated) | Check CLAUDE.md gotchas |
| **unknown** | Can't determine root cause from available info | Needs maintainer investigation |

## Report Template

When invoked, follow this exact sequence:

### Step 1: Collect Environment

```bash
xdocs --version
python3 --version
uname -s -m
cat cex-docs/.data-tag 2>/dev/null || echo "no data tag"
xdocs store-report 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('result',d); print(f'Pages: {r.get(\"total_pages\",\"?\")}, Endpoints: {r.get(\"total_endpoints\",\"?\")}, Schema: v{r.get(\"schema_version\",\"?\")}')" 2>/dev/null || echo "store-report failed"
```

### Step 2: Reproduce the Issue

Run the exact command or code that triggered the issue. Capture:
- The full command/code
- The full output (stdout + stderr)
- The expected output
- Whether it's reproducible (run it 3 times)

### Step 3: Classify Root Cause

Before writing the report, investigate:

1. **Is the data stale?** Check `crawled_at` for relevant pages. If >30 days, it's likely `upstream-change` or `xdocs-data`.
2. **Is the dependency installed?** If semantic search fails, check `pip show lancedb sentence-transformers`. If missing, it's `user-environment`.
3. **Is the input valid?** If the query is gibberish or unsupported format, it's `user-input`.
4. **Is this a known limitation?** Check CLAUDE.md "Gotchas" section. Single-page SPAs, login-gated pages, Korean text — all documented.
5. **Does it reproduce on a fresh install?** If not, it's likely `user-environment`.

Only classify as `xdocs-code` if you've ruled out all other categories.

### Step 4: Assess Severity

Use the severity scale above. Be honest:
- If the issue affects 1 query out of 200, it's LOW.
- If it affects an entire classification path (all error_message queries), it's HIGH.
- If you're unsure, default to MEDIUM — never default to HIGH/CRITICAL.

### Step 5: Write the Report

Output a file at `bug-reports/BUG-YYYY-MM-DD-<slug>.md` with this format:

```markdown
# Bug Report: <one-line title>

**Date:** YYYY-MM-DD
**Reporter:** <agent model or user>
**Severity:** LOW | MEDIUM | HIGH | CRITICAL | NOT A BUG
**Root cause:** xdocs-code | xdocs-data | user-environment | user-input | upstream-change | known-limitation | unknown

## Environment

- xdocs version: X.Y.Z
- Python: X.Y.Z
- Platform: <os> <arch>
- Data tag: <tag or "none">
- Store: <pages> pages, <endpoints> endpoints, schema vN

## Issue

<2-3 sentences describing what happened>

## Reproduction

```bash
<exact command>
```

**Output:**
```
<actual output>
```

**Expected:**
```
<what should have happened>
```

**Reproducible:** Yes / No / Intermittent (N/N runs)

## Investigation

<What you checked to determine root cause. Include:>
- Data freshness check (crawled_at for relevant pages)
- Dependency check (if relevant)
- Known limitation check (CLAUDE.md reference if applicable)
- Any SQL queries you ran to investigate

## Root Cause Analysis

<1-2 paragraphs explaining WHY this happens, not just WHAT happens.
If xdocs-code: identify the specific module/function.
If xdocs-data: identify which pages/endpoints are stale.
If user-environment: identify what's missing.
If upstream-change: identify what changed on the exchange side.>

## Affected Scope

- Exchanges: <which exchanges affected, or "all">
- Query types: <which classification paths, or "all">
- Estimated queries affected: <number or percentage>

## Workaround

<If one exists, describe it. Otherwise: "None known.">
```

### Step 6: Do NOT Do These Things

- **Do not open a GitHub issue automatically.** The report is a file. The maintainer decides whether to file it.
- **Do not suggest a fix.** You can note which module is involved, but prescribing code changes is the maintainer's job.
- **Do not chain multiple issues into one report.** One report per issue.
- **Do not include the full store-report JSON.** Just the summary stats.
- **Do not include API keys, tokens, or sensitive data** in reproduction steps.

## Example: Good vs Bad Reports

### Bad (inflated, prescriptive)
> **Severity: CRITICAL**
> The answer pipeline is fundamentally broken. Query "rate limit" returns wrong results.
> Fix: rewrite the FTS5 scoring algorithm to use BM25F instead of BM25.

### Good (objective, investigative)
> **Severity: MEDIUM**
> **Root cause: xdocs-data**
> Query "Bitget rate limits" returns changelog page instead of the rate limit docs page.
> Investigation: The rate limit page (bitget.com/api-doc/common/intro) was crawled 2026-02-15
> and has word_count=1 (thin content — JS rendering required). The changelog page has
> higher BM25 score because it contains more text mentioning "rate limit".
> Workaround: Re-crawl Bitget with `--render auto`.
