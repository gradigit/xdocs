# Handoff Everything — CEX API Docs

**Generated**: 2026-03-12T22:00:00+09:00
**Command**: `/handoff-fresh`
**Source path**: `/home/lechat/Projects/cex-api-docs`

## Bundle Files

| File | Size | Purpose |
|------|------|---------|
| handoff.md | ~3KB | Canonical handoff |
| claude.md | ~2KB | Claude onboarding |
| agents.md | ~2KB | Non-Claude onboarding |
| todo.md | ~2KB | Bug tracker |
| state.md | ~2KB | Git/env state |
| context.md | ~3KB | Architecture + decisions |
| reports.md | ~3KB | QA + benchmarks |
| artifacts.md | ~2KB | File inventory |
| prior-plans.md | ~2KB | Historical plans |
| read-receipt.md | ~200B | Read Gate checklist |
| session-log-digest.md | ~1.5KB | Decision digest |
| session-log-chunk.md | ~2.5KB | Raw excerpts |
| handoff-everything.md | This file | Full output |

## Source Files Consumed

- `CLAUDE.md` (symlink → `AGENTS.md`)
- `TODO.md`
- `FORGE-STATUS.md`
- `FORGE-HANDOFF.md`
- `FORGE-MEMORY.md`
- `HANDOFF.md`

## Git History (last 20 commits)

```
5687003 fix: FTS5 crash on single quotes in search_pages (BUG-21)
f600ab5 docs: BUG-20 (not_found status), cex-api-query v2.11.0
b6ba892 docs: gapfinder v2.2.0, BUG-18/19 TODOs, sync golden_qa.jsonl
aa51983 docs: gapfinder v2.1.0 + 3 new bugs from v1 QA run
953e19e feat: gapfinder skill v2.0.0
fea9994 refactor: CLAUDE.md → symlink to AGENTS.md
3c424b7 docs: update CLAUDE.md + AGENTS.md for skills/ canonical path
93c55c4 refactor: canonical skills/ dir with platform symlinks
1df67ee feat: agent-agnostic skill sync
c779d79 docs: AGENTS.md multi-platform skills
e79fee6 feat: gapfinder v1.1.0
0c59f28 feat: add cex-qa-gapfinder skill template
e32a4da fix: meta JSON trailing literal \n and CLI BrokenPipeError
2120617 feat: replace Git LFS with GitHub Releases
3521f8e fix: add peft to semantic-query for Linux
e07e16d fix: add sentence-transformers to semantic-query for Linux
f23cf0b fix: runtime repo deps
10f548a feat: CC score-aware fusion (opt-in), BUG-14 fix
a4b04ba feat: M22 clinical query optimization
9072bda eval: CLI robustness test suite, 3 new bugs, 6 golden QA entries
```

## Raw Status Snapshot

```
Branch: main
Remote: origin https://github.com/henryaxis/cex-api-docs.git
Working tree: clean (git-excluded artifacts only)
Tests: 559 pass (557 unit + 2 canary)
Schema: v6
Store: 10,727 pages, 4,963 endpoints, 46 exchanges
Pipeline: MRR=0.644, nDCG@5=1.343
Runtime repo: in sync at 390fbfc3
```

## Session-Log Continuity Budget

- `session-log-digest.md`: target 4000 tokens, actual ~3500
- `session-log-chunk.md`: target 8000 tokens, actual ~4000
- Combined: ~7500 tokens (under 12000 cap)
- Exclusions: tool noise, greetings, duplicate status, retry loops
