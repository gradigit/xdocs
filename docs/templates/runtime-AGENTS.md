# Runtime AGENTS Guide

This runtime repo is for **querying** and **QA testing** the CEX API docs knowledge base.

## Skills

| Skill | Purpose |
|-------|---------|
| `cex-api-query` | Answer questions about exchange API documentation with citations |
| `cex-qa-gapfinder` | Discover bugs, gaps, and quality issues in the knowledge base |

## Teammate Workflow (Querying)

1. `git pull`
2. Start fresh agent session
3. `Use cex-api-query skill.`
4. Ask your question

## QA Workflow (Gap Finding)

This is an iterative loop between this runtime repo and the maintainer repo:

```
Runtime agent (here)          Maintainer agent (cex-api-docs)
──────────────────────        ───────────────────────────────
1. Run cex-qa-gapfinder  ──→  2. Read qa-findings.jsonl
   Designs own tests              Verify findings
   Generates reports              Fix real issues
                           ──→  3. Sync fixes to runtime
4. Re-run gapfinder       ←──     Publish new data release
   Verify fixes landed
   Find new issues
   Update skill suggestions
                           ──→  5. Apply skill updates
```

### Running QA

```
Use cex-qa-gapfinder skill.
```

The agent will explore the data store, design tests, run them, and produce:
- `qa-findings.jsonl` — structured findings (one JSON object per line)
- `QA-REPORT.md` — human-readable summary with metrics and reproduction steps

### Handing off to maintainer

After a QA run, the maintainer reads the report and findings file. Findings are verified independently before any code changes. The gapfinder report is reference material, not ground truth.

### Rules

- Do not run crawling, syncing, or indexing commands in this repo.
- Do not modify source code — QA is read-only.
- If data looks stale, run `./scripts/bootstrap-data.sh` to refresh.
- If the smoke test fails, stop and report the failure.
