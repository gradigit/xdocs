# Workflow Review — 2026-03-12

## Overview

This repo has two distinct operator contexts:

1. **Maintainer repo workflow**: crawl, sync, import, validate, benchmark, and package
2. **Runtime repo workflow**: query the prepared snapshot with minimal local setup

The workflows are documented in both code and repo docs, but the strongest operational instructions live in [`AGENTS.md`](../../AGENTS.md), [`README.md`](../../README.md), [`skills/cex-api-docs/SKILL.md`](../../skills/cex-api-docs/SKILL.md), and [`docs/crawl-targets-bible.md`](../../docs/crawl-targets-bible.md).

## Maintainer Workflow

### 1. Environment Bootstrap

Primary setup path:

- [`scripts/bootstrap.sh`](../../scripts/bootstrap.sh)
- `uv pip install -e ".[dev,semantic]"`
- `cex-api-docs init --docs-dir ./cex-docs`

Bootstrap verifies the Python environment, initializes the store, and runs tests.

### 2. Crawl / Sync Workflow

Primary command surface:

- `cex-api-docs inventory`
- `cex-api-docs fetch-inventory`
- `cex-api-docs sync`

Automation wrappers:

- [`scripts/run_sync_preset.sh`](../../scripts/run_sync_preset.sh)
- [`scripts/sync_and_report.sh`](../../scripts/sync_and_report.sh)

Operational intent:

- `inventory`: deterministic URL enumeration per exchange/section
- `fetch-inventory`: fetch and persist pages
- `sync`: orchestrate inventory + fetch and run cheap post-sync checks

`run_sync_preset.sh` codifies two operator modes:

- `fast-daytime`: resume, concurrency 2, shorter delays
- `overnight-safe`: force-refetch, concurrency 1, longer delays

`sync_and_report.sh` is the cron-friendly wrapper that adds:

- markdown sync report generation
- quality check
- changelog extraction
- incremental semantic indexing

### 3. Spec Import Workflow

When a section has official specs, the maintainer imports them through:

- `cex-api-docs import-openapi`
- `cex-api-docs import-postman`
- `cex-api-docs import-asyncapi`
- `cex-api-docs link-endpoints`

Relevant modules:

- [`src/cex_api_docs/openapi_import.py`](../../src/cex_api_docs/openapi_import.py)
- [`src/cex_api_docs/postman_import.py`](../../src/cex_api_docs/postman_import.py)
- [`src/cex_api_docs/resolve_docs_urls.py`](../../src/cex_api_docs/resolve_docs_urls.py)

This workflow is how the repo closes endpoint coverage gaps when raw crawled docs are incomplete or harder to parse structurally.

### 4. Validation Workflow

Fast/local checks:

- `cex-api-docs quality-check`
- `cex-api-docs fsck`
- `cex-api-docs coverage`
- `cex-api-docs coverage-gaps`
- `cex-api-docs detect-stale-citations`

Network/coverage checks:

- `cex-api-docs validate-registry`
- `cex-api-docs validate-base-urls`
- `cex-api-docs validate-sitemaps`
- `cex-api-docs validate-crawl-targets`
- `cex-api-docs crawl-coverage`
- `cex-api-docs check-links`
- `cex-api-docs audit`

The important shape here is that validation is layered:

- content quality
- storage consistency
- crawl completeness
- retrieval quality
- live-link/site drift

### 5. Benchmark and Evaluation Workflow

Main files:

- [`tests/eval_answer_pipeline.py`](../../tests/eval_answer_pipeline.py)
- [`tests/golden_qa.jsonl`](../../tests/golden_qa.jsonl)
- [`scripts/benchmark_embeddings.py`](../../scripts/benchmark_embeddings.py)
- [`scripts/benchmark_rerankers.py`](../../scripts/benchmark_rerankers.py)
- [`scripts/benchmark_mlx.py`](../../scripts/benchmark_mlx.py)

This repo evaluates both retrieval quality and model/backend choices. The golden QA set is part of the product workflow, not just a developer nicety.

### 6. Documentation Maintenance Workflow

The maintainer skill makes this explicit: after significant changes, update:

- [`CLAUDE.md`](../../CLAUDE.md)
- [`AGENTS.md`](../../AGENTS.md)
- [`README.md`](../../README.md)
- canonical skills under [`skills/`](../../skills)
- [`docs/crawl-targets-bible.md`](../../docs/crawl-targets-bible.md)

That makes documentation state part of the operational workflow.

## Runtime Workflow

### 1. Runtime Repo Export

Export entrypoint:

- [`scripts/sync_runtime_repo.py`](../../scripts/sync_runtime_repo.py)

This script:

- copies query-only runtime code and runtime docs/templates
- copies selected skills into both `.claude/skills/` and `.agents/skills/`
- generates a runtime-specific `pyproject.toml`
- copies the store snapshot (DB, pages, meta, optional LanceDB/raw)
- optionally strips maintenance tables
- writes a runtime manifest
- optionally smoke-tests, commits, pushes, tags, and publishes a release

This is the most important cross-repo workflow in the project.

### 2. Runtime Bootstrap

Runtime consumers are expected to:

- install query-only deps
- download the `cex-docs` tarball from GitHub Releases
- extract it via `bootstrap-data.sh`
- verify it via `runtime_query_smoke.py`

Relevant templates:

- [`docs/templates/runtime-bootstrap-data.sh`](../../docs/templates/runtime-bootstrap-data.sh)
- [`docs/templates/runtime-query-smoke.py`](../../docs/templates/runtime-query-smoke.py)

The smoke test enforces minimum viable runtime expectations:

- DB present and large enough
- schema version >= 6
- page count >= 10000
- endpoint count >= 4500
- FTS5 operational

## Query Workflow

The end-user query workflow is:

1. classify input
2. route to targeted lookup or semantic/hybrid search
3. fetch endpoint/page context
4. assemble a cite-only answer

Primary command path:

- `cex-api-docs classify`
- `cex-api-docs semantic-search`
- `cex-api-docs search-pages`
- `cex-api-docs lookup-endpoint`
- `cex-api-docs search-error`
- `cex-api-docs answer`

This workflow is also mirrored in [`skills/cex-api-query/SKILL.md`](../../skills/cex-api-query/SKILL.md).

## New Exchange Workflow

The intended onboarding path is:

1. run the discovery skill
2. add bible entry
3. add registry entry
4. sync the new exchange/section with proper render mode
5. validate crawl targets and coverage
6. import specs if available
7. rebuild/compact the semantic index
8. update repo docs and skills

This is spread across:

- [`skills/cex-discovery/SKILL.md`](../../skills/cex-discovery/SKILL.md)
- [`skills/cex-api-docs/SKILL.md`](../../skills/cex-api-docs/SKILL.md)
- [`docs/crawl-targets-bible.md`](../../docs/crawl-targets-bible.md)

## Operator Checkpoints and Gotchas

1. The repo assumes `./cex-docs` as the default store, but almost every command can override it.
2. The runtime repo sync is mandatory after maintainer-repo pushes that affect code or data.
3. Some workflows rely on optional extras (`[semantic]`, `[ccxt]`, Playwright), so operational capability depends on environment.
4. Some commands are intended for cron/automation and emit machine-readable JSON to stdout, with logs to stderr.
5. The legacy `crawl` command still exists, but the intended workflow is `inventory` + `fetch-inventory` or `sync`.

## Net Assessment

The repo’s workflows are mature and explicit. The project behaves less like a typical library and more like an operating system for exchange-doc capture, validation, and local retrieval.
