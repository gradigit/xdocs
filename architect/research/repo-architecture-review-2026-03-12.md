# Repo Architecture Review — 2026-03-12

## Purpose

`cex-api-docs` is a local-first documentation ingestion and retrieval system for exchange APIs. Its intended behavior is:

1. Discover and fetch official exchange documentation exhaustively
2. Persist normalized page content and structured endpoint records with provenance
3. Build local search indexes (SQLite FTS5, optional LanceDB vectors)
4. Answer questions in a cite-only, fail-closed way

The project is not a trading client. It is a documentation knowledge base plus maintainer/query tooling.

## Primary Entry Points

- CLI: `cex-api-docs` via [`src/cex_api_docs/cli.py`](../../src/cex_api_docs/cli.py)
- Bootstrap/setup: [`scripts/bootstrap.sh`](../../scripts/bootstrap.sh)
- Maintainer sync automation: [`scripts/sync_and_report.sh`](../../scripts/sync_and_report.sh)
- Runtime export: [`scripts/sync_runtime_repo.py`](../../scripts/sync_runtime_repo.py)
- Query entrypoint in code: [`src/cex_api_docs/answer.py`](../../src/cex_api_docs/answer.py)

The CLI currently exposes 51 subcommands spanning store init, crawl/sync, import, search, answer, validation, and packaging.

## Structural Layers

### 1. Configuration and Source-of-Truth Layer

- Registry: [`data/exchanges.yaml`](../../data/exchanges.yaml)
- Error pattern registry: [`data/error_code_patterns.yaml`](../../data/error_code_patterns.yaml)
- DB schema: [`schema/schema.sql`](../../schema/schema.sql)
- Package metadata/dependencies: [`pyproject.toml`](../../pyproject.toml)

This layer defines what should be crawled, how sections are partitioned, and what the persistent schema looks like.

### 2. Store and Persistence Layer

- Store path/layout management: [`src/cex_api_docs/store.py`](../../src/cex_api_docs/store.py)
- SQLite init/migrations/WAL/FTS config: [`src/cex_api_docs/db.py`](../../src/cex_api_docs/db.py)
- Exclusive single-writer locking: [`src/cex_api_docs/lock.py`](../../src/cex_api_docs/lock.py)
- Page extraction and storage: [`src/cex_api_docs/page_store.py`](../../src/cex_api_docs/page_store.py)
- Endpoint persistence and citation verification: [`src/cex_api_docs/endpoints.py`](../../src/cex_api_docs/endpoints.py)

Persistent entities visible in the schema:

- `pages`, `page_versions`, `pages_fts`
- `endpoints`, `endpoint_sources`, `endpoints_fts`
- `inventories`, `inventory_entries`, `inventory_scope_ownership`
- `review_queue`
- `coverage_gaps`
- `changelog_entries`, `changelog_entries_fts`

The design intent is deterministic I/O with serialized writes and mechanically checkable provenance.

### 3. Crawl and Ingestion Layer

- Registry loading: [`src/cex_api_docs/registry.py`](../../src/cex_api_docs/registry.py)
- URL inventory generation: [`src/cex_api_docs/inventory.py`](../../src/cex_api_docs/inventory.py)
- Inventory fetch + adaptive domain throttling: [`src/cex_api_docs/inventory_fetch.py`](../../src/cex_api_docs/inventory_fetch.py)
- Orchestration: [`src/cex_api_docs/sync.py`](../../src/cex_api_docs/sync.py)
- Legacy crawler path: [`src/cex_api_docs/crawler.py`](../../src/cex_api_docs/crawler.py)
- Render/fetch adapters: [`src/cex_api_docs/httpfetch.py`](../../src/cex_api_docs/httpfetch.py), [`src/cex_api_docs/playwrightfetch.py`](../../src/cex_api_docs/playwrightfetch.py), [`src/cex_api_docs/nodepwfetch.py`](../../src/cex_api_docs/nodepwfetch.py), [`src/cex_api_docs/agentbrowserfetch.py`](../../src/cex_api_docs/agentbrowserfetch.py)

This is the main maintainer pipeline:

- registry -> inventory -> fetch -> page markdown/meta storage

`inventory.py` is responsible for deterministic enumeration. `inventory_fetch.py` is responsible for actual retrieval and persistence. `sync.py` wraps both and adds cheap post-sync checks.

### 4. Structured Endpoint Import Layer

- OpenAPI import: [`src/cex_api_docs/openapi_import.py`](../../src/cex_api_docs/openapi_import.py)
- Postman import: [`src/cex_api_docs/postman_import.py`](../../src/cex_api_docs/postman_import.py)
- AsyncAPI placeholder: [`src/cex_api_docs/asyncapi_import.py`](../../src/cex_api_docs/asyncapi_import.py)
- Manual page ingest: [`src/cex_api_docs/ingest_page.py`](../../src/cex_api_docs/ingest_page.py)
- Docs URL resolution for imported endpoints: [`src/cex_api_docs/resolve_docs_urls.py`](../../src/cex_api_docs/resolve_docs_urls.py)

This layer supplements crawled pages with structured HTTP endpoint records when official specs exist. `endpoints.py` enforces exact citation matching against stored markdown.

### 5. Query and Retrieval Layer

- Input classification: [`src/cex_api_docs/classify.py`](../../src/cex_api_docs/classify.py)
- Page search and retrieval: [`src/cex_api_docs/pages.py`](../../src/cex_api_docs/pages.py)
- Endpoint lookup/error search: [`src/cex_api_docs/lookup.py`](../../src/cex_api_docs/lookup.py)
- Shared retrieval utilities: [`src/cex_api_docs/fts_util.py`](../../src/cex_api_docs/fts_util.py)
- Vector/hybrid search: [`src/cex_api_docs/semantic.py`](../../src/cex_api_docs/semantic.py)
- Reranking backends: [`src/cex_api_docs/reranker.py`](../../src/cex_api_docs/reranker.py)
- Final answer assembly: [`src/cex_api_docs/answer.py`](../../src/cex_api_docs/answer.py)

This is the query path:

- classify -> direct lookup or FTS/vector retrieval -> excerpt generation -> cite-only answer

`answer.py` is the single densest application module and acts as the query-policy layer. It contains exchange detection, direct routing, section heuristics, excerpt generation, and augmentation logic.

### 6. Validation and QA Layer

- Quality gate: [`src/cex_api_docs/quality.py`](../../src/cex_api_docs/quality.py)
- Consolidated audit runner: [`src/cex_api_docs/audit.py`](../../src/cex_api_docs/audit.py)
- Crawl target discovery/coverage/live checks: [`src/cex_api_docs/crawl_targets.py`](../../src/cex_api_docs/crawl_targets.py), [`src/cex_api_docs/crawl_coverage.py`](../../src/cex_api_docs/crawl_coverage.py), [`src/cex_api_docs/live_validate.py`](../../src/cex_api_docs/live_validate.py), [`src/cex_api_docs/link_check.py`](../../src/cex_api_docs/link_check.py)
- Retrieval evaluation: [`src/cex_api_docs/validate.py`](../../src/cex_api_docs/validate.py), [`tests/eval_answer_pipeline.py`](../../tests/eval_answer_pipeline.py)
- Coverage accounting: [`src/cex_api_docs/coverage.py`](../../src/cex_api_docs/coverage.py), [`src/cex_api_docs/coverage_gaps.py`](../../src/cex_api_docs/coverage_gaps.py), [`src/cex_api_docs/stale_citations.py`](../../src/cex_api_docs/stale_citations.py)

The project treats validation as a first-class product surface rather than a sidecar.

## Design Shape

The repo is not a monolith with a single request path. It is a toolchain with four coupled surfaces:

1. Maintainer ingestion pipeline
2. Structured endpoint/spec ingestion pipeline
3. Local query/answer pipeline
4. Validation/packaging pipeline

Those surfaces share the same store and registry. That shared state is the center of gravity of the system.

## Where Project Intent Is Encoded

- Mission and operating rules: [`AGENTS.md`](../../AGENTS.md), [`CLAUDE.md`](../../CLAUDE.md)
- User-facing framing: [`README.md`](../../README.md)
- Crawl strategy and exchange-specific truth set: [`docs/crawl-targets-bible.md`](../../docs/crawl-targets-bible.md)
- Technical truth set: [`data/exchanges.yaml`](../../data/exchanges.yaml), [`schema/schema.sql`](../../schema/schema.sql)
- Behavioral validation: [`tests/`](../../tests)

## Most Important Architectural Observations

1. The registry is the crawl scope authority, not the code. Most crawl behavior is data-driven from `exchanges.yaml`.
2. SQLite is the core store; LanceDB is an optional retrieval accelerator layered on top.
3. Structured endpoints are a parallel evidence source, not a replacement for crawled pages.
4. The answer pipeline is heuristic and retrieval-heavy, but the repo’s contract remains deterministic I/O plus fail-closed output.
5. Operational documentation is unusually important here: the bible, skills, and AGENTS/CLAUDE materially define intended behavior.
