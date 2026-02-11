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
pytest tests/test_endpoints.py -x    # single module, stop on first failure
pytest -k "test_stale" -x            # run tests matching pattern
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

# Force re-download all pages to detect content changes
cex-api-docs sync --docs-dir ./cex-docs --force-refetch

# Resume an interrupted inventory fetch
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --resume

# Parallel inventory fetch
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --concurrency 4

# Report on current store contents (pages, inventories, endpoints, review queue)
cex-api-docs store-report --docs-dir ./cex-docs
cex-api-docs store-report --exchange binance --section spot --output report.md

# Import endpoints from OpenAPI spec (use --base-url if spec lacks servers[].url)
cex-api-docs import-openapi --exchange binance --section spot --url <spec-url> --docs-dir ./cex-docs --continue-on-error

# Import endpoints from Postman collection
cex-api-docs import-postman --exchange bybit --section v5 --url <collection-url> --docs-dir ./cex-docs --continue-on-error

# Search endpoints by keyword
cex-api-docs search-endpoints "rate limit" --exchange binance --docs-dir ./cex-docs

# Content quality check (empty/thin/tiny_html pages)
cex-api-docs quality-check --docs-dir ./cex-docs

# Cite-only answer from local store
cex-api-docs answer "What permissions does the Binance API key need?" --docs-dir ./cex-docs
```

Note: The legacy `crawl` command still works but emits a deprecation warning. Use `sync` or `inventory`+`fetch-inventory` instead.

## Project Structure

- `src/cex_api_docs/` Python package (all source modules).
- `tests/` Pytest test suite (mirrors source modules; uses `http_server.py` fixture for network tests).
- `schema/schema.sql` Authoritative SQLite DDL (pages, endpoints, inventories, FTS5, review queue, coverage_gaps).
- `schemas/` JSON Schema files used for validation (`endpoint.schema.json`, `page_meta.schema.json`).
- `data/exchanges.yaml` Registry of all 16 exchanges (37 sections): seeds, allowed domains, base URLs, doc sources.
- `scripts/` Automation helpers (e.g. `sync_and_report.sh` cron runner).
- `docs/plans/` Authoritative plans and design decisions.
- `docs/runbooks/` Demo/run instructions.
- `docs/solutions/` Problem/solution write-ups (integration issues, logic errors, patterns).
- `docs/reports/` Generated sync and smoke reports.
- `docs/research/` Technology research notes (LanceDB, LlamaIndex, CEX OpenAPI landscape).
- `skills/` Claude Code skill definitions (for agent usage).
- `todos/` File-based work tracking (source of truth for follow-ups).

## Data Flow

The pipeline has a linear progression:

1. **Registry** (`data/exchanges.yaml`) -- defines exchanges, sections, seed URLs, and allowlists.
2. **Inventory** (`inventory.py`) -- enumerates all doc URLs for a section (sitemaps first, link-follow fallback). Persists to `inventories`/`inventory_entries` tables.
3. **Fetch** (`inventory_fetch.py`) -- downloads each inventory URL, stores raw HTML + converted markdown + metadata under `cex-docs/`. Supports `--resume`, `--concurrency`, `--render auto`, `--force-refetch`.
4. **Store** (`store.py`, `db.py`, `page_store.py`) -- SQLite DB with WAL mode, write-lock serialization, FTS5 indexes on pages and endpoints.
5. **Endpoint ingest** (`endpoints.py`, `openapi_import.py`, `postman_import.py`, `ingest_page.py`) -- structured endpoint records with provenance (citations back to source pages).
6. **Query / Answer** (`answer.py`, `pages.py`) -- cite-only answer assembly using FTS5 search + endpoint DB. Returns `unknown`/`undocumented`/`conflict` when sources are insufficient.
7. **Quality** (`quality.py`, `coverage.py`, `coverage_gaps.py`, `stale_citations.py`, `fsck.py`) -- content quality gate (empty/thin/tiny_html detection), coverage gap detection, stale citation sweeps, store consistency checks.

## Conventions

- Cite-only outputs: no unsupported claims. If not backed by sources, return `unknown` / `undocumented` / `conflict`.
- Deterministic code: crawling, storage, indexing, querying, diffing.
- Agent boundary: agent does interpretation and extraction; code does deterministic I/O and validation.
- JSON-first CLI: machine-readable output to stdout; logs to stderr.

## Key Files

- `data/exchanges.yaml` Registry of exchanges/sections, doc seeds, allowlists, and base URLs
- `schema/schema.sql` SQLite schema (pages, endpoints, FTS5, review queue, inventories, coverage_gaps)
- `src/cex_api_docs/cli.py` CLI entrypoint (30+ subcommands)
- `src/cex_api_docs/errors.py` `CexApiDocsError` dataclass -- all errors use structured codes (ENOINIT, EBADARG, EFTS5, ESCHEMAVER, etc.)
- `src/cex_api_docs/db.py` SQLite connection helper (WAL mode, FTS5 check, schema versioning via PRAGMA user_version, forward migration support)
- `src/cex_api_docs/urlutil.py` Shared `url_host()` utility (used by 7+ modules for hostname extraction)
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
- `src/cex_api_docs/quality.py` Content quality gate (empty/thin/tiny_html detection, integrated into post-sync)
- `src/cex_api_docs/fsck.py` Store consistency checker (DB/file mismatches, orphan detection)

## Gotchas

- `cex-docs/`, `cex-docs-*/`, and `poc-binance-full/` are local data and must never be committed (gitignored).
- CLI JSON is printed at the end of a command; if you redirect stdout to a file, it may stay empty until completion.
- Prefer deterministic fetch first; use `--render auto` when a docs site requires JS rendering.
- **FTS5 required**: SQLite must be built with FTS5 support; the app raises `EFTS5` at init if missing. macOS system Python and Homebrew Python both include FTS5. Some minimal Docker images do not.
- **Playwright is optional**: install with `pip install -e ".[playwright]"`. Without it, `--render playwright` and `--render auto` will fail at runtime.
- **Write lock contention**: all DB writes acquire an exclusive file lock (`cex-docs/db/.write.lock`). `--lock-timeout-s` (default 10s) controls how long a command waits. Concurrent writers will queue; long fetches hold the lock in short bursts (3-phase locking in `inventory_fetch.py`).
- **Python >=3.11 required** (per pyproject.toml). Uses `match/case`, `dataclass(slots=True)`, and `X | Y` union syntax.
- **Schema path resolution**: `cli.py` resolves `schema/schema.sql` relative to the package install location (`Path(__file__).parents[2]`). This works with `pip install -e .` but will break if the source tree is moved after install.
- **`extract_page_markdown` return order**: Returns `(html, title, md_norm, word_count)` — first element is decoded HTML string, not markdown. The normalized markdown is the third element.
- **Raw string regex**: In `r"..."` strings, use single backslash for regex escapes (`\w`, `\s`, `\S`). Double backslash (`\\w`) matches literal backslash + letter. Previously caused silent failures in charset detection and robots.txt sitemap parsing.
- **Single-page doc exchanges**: OKX (224K words), Gate.io (256K), HTX (325K across 4 pages), Crypto.com (35K), Bitstamp (22K), Korbit (25K) serve their entire API reference from 1-2 HTML files. This is correct — the pipeline handles them fine. Don't treat low page counts as errors.
- **Gate.io rate-limits aggressively**: After syncing, HTTP requests return 403 ("Access Denied"). Content is already in the store; re-sync may need longer delays or `--render auto`.
- **Binance sitemap is 404**: Despite being configured in `exchanges.yaml`, `developers.binance.com/sitemap.xml` returns 404. The pipeline falls back to link-follow automatically.
- **OpenAPI import needs `--base-url` for some specs**: KuCoin official OpenAPI specs have no `servers[].url` field. Pass `--base-url` explicitly or the import fails with `EBADOPENAPI`.
- **Endpoint extraction citations must be exact**: `save-endpoint` verifies that `excerpt` matches the stored markdown at `[excerpt_start:excerpt_end]` byte-for-byte. Off-by-one errors or whitespace mismatches cause `EBADCITE`.
- **`extracted_endpoints/` is gitignored**: Agent-extracted endpoint JSON files live here. They are regenerable from stored markdown and should not be committed.

## Current Phase

Phase: Endpoint extraction complete across all sections. 16 exchanges, 37 sections synced: 3,813 pages, 4.48M words, **3,431 structured endpoints**. Store is at `cex-docs/`.

Latest: All 9 newly added sections now have endpoints:
- **Binance** options (46 via openxapi OpenAPI), margin_trading (59), wallet (47), copy_trading (2), portfolio_margin_pro (21) — all via official Postman collections.
- **Bitget** broker (14), copy_trading (45), earn (27), margin (45) — via automated markdown extraction with cite-only provenance.
- Added `--force-refetch` flag and `quality-check` command for content change detection and quality validation.

Research completed (docs/research/):
- LanceDB: Strong fit as supplementary semantic index alongside SQLite FTS5.
- LlamaIndex: Not recommended — LLM-based retrieval conflicts with deterministic cite-only design.
- CEX OpenAPI specs: Mapped all 16 exchanges; identified Bitstamp official spec and Gate.io SDK spec as remaining import opportunities.

Next: LanceDB POC (embed 100 pages, test 20 queries) to quantify semantic search improvement over FTS5 alone.
