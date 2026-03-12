# Runtime AGENTS Guide

This runtime repo is for **querying** and **QA testing** the CEX API docs knowledge base.

## Multi-Platform Skills

All skills in this repo work with **both Claude Code and Codex CLI** (and any other agent platform). The canonical skill definitions live in `.claude/skills/` but are written to be platform-agnostic.

- **Claude Code**: Reads skills from `.claude/skills/<name>/SKILL.md` automatically.
- **Codex CLI**: Reads this `AGENTS.md` file. Skill references below point to the same `.claude/skills/` files — read the linked SKILL.md for full instructions.
- **Other agents**: Read the linked SKILL.md files directly.

When creating, updating, or maintaining skills, always ensure they work on both platforms. Do not use Claude-specific or Codex-specific features in skill definitions.

## Skills

| Skill | Path | Purpose |
|-------|------|---------|
| `cex-api-query` | `.claude/skills/cex-api-query/SKILL.md` | Answer questions about exchange API documentation with citations |
| `cex-qa-gapfinder` | `.claude/skills/cex-qa-gapfinder/SKILL.md` | Discover bugs, gaps, and quality issues in the knowledge base |

## Teammate Workflow (Querying)

1. `git pull`
2. Start fresh agent session
3. Ask: `Use cex-api-query skill.` (Claude) or reference the skill file path (Codex)
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

**Claude Code:**
```
Use cex-qa-gapfinder skill.
```

**Codex CLI:**
```
Read .claude/skills/cex-qa-gapfinder/SKILL.md and follow its instructions.
```

The agent will explore the data store, design tests, run them, and produce:
- `qa-findings.jsonl` — structured findings (one JSON object per line)
- `QA-REPORT.md` — human-readable summary with metrics and reproduction steps
- A concise human brief as the final message (readable in 30 seconds)

### Handing off to maintainer

After a QA run, the maintainer reads the report and findings file. Findings are verified independently before any code changes. The gapfinder report is reference material, not ground truth.

**Same machine:** Tell the maintainer agent the file paths — it reads them directly.
**Different machine (e.g., MacBook):** Push findings to a `qa/YYYY-MM-DD` branch and tell the maintainer to fetch it.

### Rules

- Do not run crawling, syncing, or indexing commands in this repo.
- Do not modify source code — QA is read-only.
- If data looks stale, run `./scripts/bootstrap-data.sh` to refresh.
- If the smoke test fails, stop and report the failure.
