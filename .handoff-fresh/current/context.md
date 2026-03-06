# Context

## Project Purpose

`cex-api-docs` is a local, cite-only API documentation knowledge base for exchange APIs.
It crawls official docs, stores normalized markdown + metadata, and supports deterministic querying with citations.

## Architecture Snapshot

- Registry: `data/exchanges.yaml`
- Inventory/fetch: `inventory` + `fetch-inventory` + `sync`
- Storage: SQLite (pages/endpoints, FTS5), filesystem raw/pages/meta
- Semantic: LanceDB index via `build-index` and `semantic-search`
- Query UX: `cex-api-query` skill with classify-first routing and citation rules

## Major Recent Decisions

1. Keep maintainer/runtime split:
   - maintainer repo handles crawl/sync/index/validation
   - runtime workspace is query-first for team use
2. Expand source coverage beyond CEX docs:
   - added perp DEX sources and CCXT docs
3. Preserve deterministic and cite-only behavior even with expanded corpus

## Known Gaps

- Offline retrieval QA baseline needs rework (exact-URL set drift).
- Playwright extras not installed in this environment.
