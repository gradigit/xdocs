# State

Generated: 2026-02-27 03:17 UTC

## Git

- Repo root: `/Users/aaaaa/Projects/cex-api-docs`
- Branch: `main`
- Last commit: `729b106 feat: API Assistant v2 — input classification, endpoint lookup, error search, enhanced answers`
- Remote(s):

```
(no remotes configured)
```

- Working tree entries (tracked + untracked): `49`

### `git status --short`

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

## Active Phase

Post-maintenance stabilization + handoff packaging.

## Current Risks / Blockers

1. Golden QA mismatch suppresses retrieval quality score confidence.
2. Playwright optional dependency absent in this environment.
3. Large uncommitted tree should be curated/committed before broader sharing.
