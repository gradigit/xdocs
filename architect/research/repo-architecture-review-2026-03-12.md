# Repo Architecture Review — 2026-03-12

## Purpose

`xdocs` is a local-first documentation ingestion and retrieval system for exchange APIs. Its intended behavior is:

1. Discover and fetch official exchange documentation exhaustively
2. Persist normalized page content and structured endpoint records with provenance
3. Build local search indexes (SQLite FTS5, optional LanceDB vectors)
4. Answer questions in a cite-only, fail-closed way

The project is not a trading client. It is a documentation knowledge base plus maintainer/query tooling.

## Primary Entry Points

- CLI: `xdocs` via [`src/xdocs/cli.py`](../../src/xdocs/cli.py)
- Bootstrap/setup: [`scripts/bootstrap.sh`](../../scripts/bootstrap.sh)
- Maintainer sync automation: [`scripts/sync_and_report.sh`](../../scripts/sync_and_report.sh)
- Runtime export: [`scripts/sync_runtime_repo.py`](../../scripts/sync_runtime_repo.py)
- Query entrypoint in code: [`src/xdocs/answer.py`](../../src/xdocs/answer.py)

The CLI currently exposes 51 subcommands spanning store init, crawl/sync, import, search, answer, validation, and packaging.

## Structural Layers

### 1. Configuration and Source-of-Truth Layer

- Registry: [`data/exchanges.yaml`](../../data/exchanges.yaml)
- Error pattern registry: [`data/error_code_patterns.yaml`](../../data/error_code_patterns.yaml)
- DB schema: [`schema/schema.sql`](../../schema/schema.sql)
- Package metadata/dependencies: [`pyproject.toml`](../../pyproject.toml)

This layer defines what should be crawled, how sections are partitioned, and what the persistent schema looks like.

### 2. Store and Persistence Layer

- Store path/layout management: [`src/xdocs/store.py`](../../src/xdocs/store.py)
- SQLite init/migrations/WAL/FTS config: [`src/xdocs/db.py`](../../src/xdocs/db.py)
- Exclusive single-writer locking: [`src/xdocs/lock.py`](../../src/xdocs/lock.py)
- Page extraction and storage: [`src/xdocs/page_store.py`](../../src/xdocs/page_store.py)
- Endpoint persistence and citation verification: [`src/xdocs/endpoints.py`](../../src/xdocs/endpoints.py)

Persistent entities visible in the schema:

- `pages`, `page_versions`, `pages_fts`
- `endpoints`, `endpoint_sources`, `endpoints_fts`
- `inventories`, `inventory_entries`, `inventory_scope_ownership`
- `review_queue`
- `coverage_gaps`
- `changelog_entries`, `changelog_entries_fts`

The design intent is deterministic I/O with serialized writes and mechanically checkable provenance.

### 3. Crawl and Ingestion Layer

- Registry loading: [`src/xdocs/registry.py`](../../src/xdocs/registry.py)
- URL inventory generation: [`src/xdocs/inventory.py`](../../src/xdocs/inventory.py)
- Inventory fetch + adaptive domain throttling: [`src/xdocs/inventory_fetch.py`](../../src/xdocs/inventory_fetch.py)
- Orchestration: [`src/xdocs/sync.py`](../../src/xdocs/sync.py)
- Legacy crawler path: [`src/xdocs/crawler.py`](../../src/xdocs/crawler.py)
- Render/fetch adapters: [`src/xdocs/httpfetch.py`](../../src/xdocs/httpfetch.py), [`src/xdocs/playwrightfetch.py`](../../src/xdocs/playwrightfetch.py), [`src/xdocs/nodepwfetch.py`](../../src/xdocs/nodepwfetch.py), [`src/xdocs/agentbrowserfetch.py`](../../src/xdocs/agentbrowserfetch.py)

This is the main maintainer pipeline:

- registry -> inventory -> fetch -> page markdown/meta storage

`inventory.py` is responsible for deterministic enumeration. `inventory_fetch.py` is responsible for actual retrieval and persistence. `sync.py` wraps both and adds cheap post-sync checks.

### 4. Structured Endpoint Import Layer

- OpenAPI import: [`src/xdocs/openapi_import.py`](../../src/xdocs/openapi_import.py)
- Postman import: [`src/xdocs/postman_import.py`](../../src/xdocs/postman_import.py)
- AsyncAPI placeholder: [`src/xdocs/asyncapi_import.py`](../../src/xdocs/asyncapi_import.py)
- Manual page ingest: [`src/xdocs/ingest_page.py`](../../src/xdocs/ingest_page.py)
- Docs URL resolution for imported endpoints: [`src/xdocs/resolve_docs_urls.py`](../../src/xdocs/resolve_docs_urls.py)

This layer supplements crawled pages with structured HTTP endpoint records when official specs exist. `endpoints.py` enforces exact citation matching against stored markdown.

### 5. Query and Retrieval Layer

- Input classification: [`src/xdocs/classify.py`](../../src/xdocs/classify.py)
- Page search and retrieval: [`src/xdocs/pages.py`](../../src/xdocs/pages.py)
- Endpoint lookup/error search: [`src/xdocs/lookup.py`](../../src/xdocs/lookup.py)
- Shared retrieval utilities: [`src/xdocs/fts_util.py`](../../src/xdocs/fts_util.py)
- Vector/hybrid search: [`src/xdocs/semantic.py`](../../src/xdocs/semantic.py)
- Reranking backends: [`src/xdocs/reranker.py`](../../src/xdocs/reranker.py)
- Final answer assembly: [`src/xdocs/answer.py`](../../src/xdocs/answer.py)

This is the query path:

- classify -> direct lookup or FTS/vector retrieval -> excerpt generation -> cite-only answer

`answer.py` is the single densest application module and acts as the query-policy layer. It contains exchange detection, direct routing, section heuristics, excerpt generation, and augmentation logic.

### 6. Validation and QA Layer

- Quality gate: [`src/xdocs/quality.py`](../../src/xdocs/quality.py)
- Consolidated audit runner: [`src/xdocs/audit.py`](../../src/xdocs/audit.py)
- Crawl target discovery/coverage/live checks: [`src/xdocs/crawl_targets.py`](../../src/xdocs/crawl_targets.py), [`src/xdocs/crawl_coverage.py`](../../src/xdocs/crawl_coverage.py), [`src/xdocs/live_validate.py`](../../src/xdocs/live_validate.py), [`src/xdocs/link_check.py`](../../src/xdocs/link_check.py)
- Retrieval evaluation: [`src/xdocs/validate.py`](../../src/xdocs/validate.py), [`tests/eval_answer_pipeline.py`](../../tests/eval_answer_pipeline.py)
- Coverage accounting: [`src/xdocs/coverage.py`](../../src/xdocs/coverage.py), [`src/xdocs/coverage_gaps.py`](../../src/xdocs/coverage_gaps.py), [`src/xdocs/stale_citations.py`](../../src/xdocs/stale_citations.py)

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
