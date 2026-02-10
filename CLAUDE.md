# CEX API Docs

## What This Is

A local-only, cite-only CEX API documentation knowledge base (library + CLI + agent skill) that crawls official exchange docs, stores and indexes them via SQLite FTS5, and enables agents to answer endpoint, rate limit, and permission questions with strict provenance.

## Build Commands

Quick setup (macOS):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
cex-api-docs --help
```

## Commands

```bash
# Initialize a local store (idempotent)
cex-api-docs init --docs-dir ./cex-docs

# Deterministic sync (inventory -> fetch); use --render auto for JS-heavy docs
cex-api-docs sync --docs-dir ./cex-docs --render auto

# Resume an interrupted sync (reuse existing inventories, fetch only pending/error entries)
cex-api-docs sync --docs-dir ./cex-docs --resume

# Parallel fetch (N concurrent workers with per-domain rate limiting)
cex-api-docs sync --docs-dir ./cex-docs --concurrency 4

# Resume an interrupted inventory fetch
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --resume

# Parallel inventory fetch
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --concurrency 4

# Report on current store contents (pages, inventories, endpoints, review queue)
cex-api-docs store-report --docs-dir ./cex-docs
cex-api-docs store-report --exchange binance --section spot --output report.md
```

Note: The legacy `crawl` command still works but emits a deprecation warning. Use `sync` or `inventory`+`fetch-inventory` instead.

## Project Structure

- `src/cex_api_docs/` Python package (all source modules).
- `tests/` Pytest test suite (mirrors source modules; uses `http_server.py` fixture for network tests).
- `schema/schema.sql` Authoritative SQLite DDL (pages, endpoints, inventories, FTS5, review queue, coverage_gaps).
- `schemas/` JSON Schema files used for validation (`endpoint.schema.json`, `page_meta.schema.json`).
- `data/exchanges.yaml` Registry of all 16 exchanges: seeds, allowed domains, base URLs, doc sources.
- `scripts/` Automation helpers (e.g. `sync_and_report.sh` cron runner).
- `docs/plans/` Authoritative plans and design decisions.
- `docs/runbooks/` Demo/run instructions.
- `docs/solutions/` Problem/solution write-ups (integration issues, logic errors, patterns).
- `docs/reports/` Generated sync and smoke reports.
- `skills/` Claude Code skill definitions (for agent usage).
- `todos/` File-based work tracking (source of truth for follow-ups).

## Data Flow

The pipeline has a linear progression:

1. **Registry** (`data/exchanges.yaml`) -- defines exchanges, sections, seed URLs, and allowlists.
2. **Inventory** (`inventory.py`) -- enumerates all doc URLs for a section (sitemaps first, link-follow fallback). Persists to `inventories`/`inventory_entries` tables.
3. **Fetch** (`inventory_fetch.py`) -- downloads each inventory URL, stores raw HTML + converted markdown + metadata under `cex-docs/`. Supports `--resume`, `--concurrency`, `--render auto`.
4. **Store** (`store.py`, `db.py`, `page_store.py`) -- SQLite DB with WAL mode, write-lock serialization, FTS5 indexes on pages and endpoints.
5. **Endpoint ingest** (`endpoints.py`, `openapi_import.py`, `postman_import.py`, `ingest_page.py`) -- structured endpoint records with provenance (citations back to source pages).
6. **Query / Answer** (`answer.py`, `pages.py`) -- cite-only answer assembly using FTS5 search + endpoint DB. Returns `unknown`/`undocumented`/`conflict` when sources are insufficient.
7. **Quality** (`coverage.py`, `coverage_gaps.py`, `stale_citations.py`, `fsck.py`) -- coverage gap detection, stale citation sweeps, store consistency checks.

## Conventions

- Cite-only outputs: no unsupported claims. If not backed by sources, return `unknown` / `undocumented` / `conflict`.
- Deterministic code: crawling, storage, indexing, querying, diffing.
- Agent boundary: agent does interpretation and extraction; code does deterministic I/O and validation.
- JSON-first CLI: machine-readable output to stdout; logs to stderr.

## Key Files

- `data/exchanges.yaml` Registry of exchanges/sections, doc seeds, allowlists, and base URLs
- `schema/schema.sql` SQLite schema (pages + endpoint DB + review queue + inventories + coverage_gaps)
- `src/cex_api_docs/cli.py` CLI entrypoint (30+ subcommands)
- `src/cex_api_docs/errors.py` `CexApiDocsError` dataclass -- all errors use structured codes (ENOINIT, EBADARG, EFTS5, ESCHEMAVER, etc.)
- `src/cex_api_docs/db.py` SQLite connection helper (WAL mode, FTS5 check, schema versioning via PRAGMA user_version)
- `src/cex_api_docs/store.py` Store init + `require_store_db` helper (shared across all modules)
- `src/cex_api_docs/lock.py` File-based exclusive write lock (all DB writes go through this)
- `src/cex_api_docs/inventory.py` Inventory generation (sitemaps + deterministic link-follow fallback)
- `src/cex_api_docs/inventory_fetch.py` Fetch + persist inventory entries (--resume, --concurrency with per-domain rate limiting, 3-phase locking)
- `src/cex_api_docs/playwrightfetch.py` Playwright fetch wrapper (JS-rendered docs fallback)
- `src/cex_api_docs/sync.py` Cron-friendly orchestration (inventory + fetch, --resume, --concurrency)
- `src/cex_api_docs/endpoints.py` Endpoint CRUD, FTS search, review queue management
- `src/cex_api_docs/openapi_import.py` OpenAPI/Swagger spec import into endpoint DB
- `src/cex_api_docs/postman_import.py` Postman collection import into endpoint DB
- `src/cex_api_docs/report.py` Markdown report rendering for sync JSON artifacts + store-report command
- `src/cex_api_docs/answer.py` Cite-only answer assembly (generalized to all 16 exchanges; Binance has richer heuristics)
- `src/cex_api_docs/fsck.py` Store consistency checker (DB/file mismatches, orphan detection)

## Gotchas

- `cex-docs/` and `cex-docs-*/` are local stores and must never be committed (gitignored).
- CLI JSON is printed at the end of a command; if you redirect stdout to a file, it may stay empty until completion.
- Prefer deterministic fetch first; use `--render auto` when a docs site requires JS rendering.
- **FTS5 required**: SQLite must be built with FTS5 support; the app raises `EFTS5` at init if missing. macOS system Python and Homebrew Python both include FTS5. Some minimal Docker images do not.
- **Playwright is optional**: install with `pip install -e ".[playwright]"`. Without it, `--render playwright` and `--render auto` will fail at runtime.
- **Write lock contention**: all DB writes acquire an exclusive file lock (`cex-docs/db/.write.lock`). `--lock-timeout-s` (default 10s) controls how long a command waits. Concurrent writers will queue; long fetches hold the lock in short bursts (3-phase locking in `inventory_fetch.py`).
- **Python >=3.11 required** (per pyproject.toml). Uses `match/case`, `dataclass(slots=True)`, and `X | Y` union syntax.
- **Schema path resolution**: `cli.py` resolves `schema/schema.sql` relative to the package install location (`Path(__file__).parents[2]`). This works with `pip install -e .` but will break if the source tree is moved after install.

## Current Phase

Phase: MVP hardened (inventory+fetch with --resume/--concurrency, local store+search, endpoint ingest, cite-only answer assembly for all 16 exchanges, store-report, tests). Key hardening: deduplicated `require_store_db` into store.py, narrowed write locks in fetch_inventory (3-phase locking), deprecated `crawl` in favor of `sync`, generalized answer.py beyond Binance.

Next steps live in `todos/` (prioritized), and the "wow query" demo runbook is at:
- `docs/runbooks/binance-wow-query.md`
