# Handoff Everything (Full Snapshot)

Generated: 2026-02-27 03:17 UTC
Generation command (logical): `/handoff-fresh`
Project root: `/Users/aaaaa/Projects/cex-api-docs`
Bundle: `/Users/aaaaa/Projects/cex-api-docs/.handoff-fresh/current`

## File List (Bundle)

- handoff.md
- claude.md
- agents.md
- todo.md
- context.md
- reports.md
- artifacts.md
- state.md
- prior-plans.md
- read-receipt.md
- session-log-digest.md
- session-log-chunk.md
- handoff-everything.md

## Source Files Consumed

- CLAUDE.md
- AGENTS.md
- README.md
- docs/ops/production-readiness-and-rollout.md
- docs/ops/maintainer-vs-runtime-repo-split.md
- data/exchanges.yaml
- .claude/skills/cex-api-query/SKILL.md
- reports/2026-02-26-maintenance-run-summary.md
- reports/2026-02-26T2001-pre-share-check.log
- reports/2026-02-26T200246Z-crawl-refresh-benchmark.json
- reports/2026-02-26T200239Z-extraction-quality-benchmark.json
- reports/2026-02-26T2003-validate-retrieval-no-rerank.json
- reports/2026-02-26T2003-validate-retrieval-rerank.json
- reports/2026-02-26T2002-runtime-sync.log

## Git History Excerpt

```
729b106 feat: API Assistant v2 — input classification, endpoint lookup, error search, enhanced answers
1af0eb8 refactor: clean repo for distribution
76d22ce docs: sync CLAUDE.md + HANDOFF for semantic search session
d2b5027 feat: LanceDB semantic search module + POC evaluation
7e27a93 docs: endpoint extraction complete + research reports + CLAUDE.md sync
f5555f9 feat: --force-refetch flag + content quality gate
31d2592 docs: add validator ground truth report and summary
36c59b4 feat: cex-api-query skill + evaluation reports
```

## Raw Status Snapshot

```
M .claude/skills/cex-api-query/EVALUATIONS.md
 M .claude/skills/cex-api-query/SKILL.md
 M README.md
 M data/exchanges.yaml
 M pyproject.toml
 M schema/schema.sql
 M src/cex_api_docs/answer.py
 M src/cex_api_docs/classify.py
 M src/cex_api_docs/cli.py
 M src/cex_api_docs/db.py
 M src/cex_api_docs/httpfetch.py
 M src/cex_api_docs/inventory_fetch.py
 M src/cex_api_docs/markdown.py
 M src/cex_api_docs/page_store.py
 M src/cex_api_docs/registry.py
 M src/cex_api_docs/report.py
 M src/cex_api_docs/semantic.py
 M src/cex_api_docs/store.py
 M src/cex_api_docs/sync.py
 M tests/test_init.py
 M tests/test_inventory.py
 M tests/test_semantic.py
?? .codex/
?? .github/
?? .playwright-mcp/
?? AGENTS.md
?? docs/
?? logs/
?? ops/
?? poc-binance-account-endpoints.jpeg
?? reports/
?? scripts/bench_crawl_refresh.py
?? scripts/bench_extraction_quality.py
?? scripts/pre_share_check.sh
?? scripts/run_sync_preset.sh
?? scripts/sync_demo_skills.py
?? scripts/sync_runtime_repo.py
?? security_best_practices_report.md
?? src/cex_api_docs/chunker.py
?? src/cex_api_docs/embeddings.py
?? src/cex_api_docs/reranker.py
?? src/cex_api_docs/validate.py
?? tests/golden_qa.jsonl
?? tests/test_chunker.py
?? tests/test_markdown.py
?? tests/test_reranker.py
?? tests/test_retry_after.py
?? tests/test_validate.py
?? uv.lock
```

## Session-Log Continuity Budget

- Configured budget: 12000 tokens
- Digest target: 3000-4000
- Chunk target: 6000-8000
- Actual estimate: ~5000
- Exclusions: low-signal chatter, repeated no-op retries, generic command noise

## Sync/Preflight Note

`/sync-docs` command not directly available in this Codex environment; equivalent validation was satisfied using fresh maintenance checks and pre-share gate.
