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

# Get full endpoint record by ID
cex-api-docs get-endpoint <endpoint_id> --docs-dir ./cex-docs

# List endpoint summaries by exchange/section
cex-api-docs list-endpoints --exchange binance --section spot --limit 20 --docs-dir ./cex-docs

# Lookup endpoint by HTTP path (SQL LIKE, handles {{url}} prefix)
cex-api-docs lookup-endpoint /sapi/v1/convert/getQuote --method POST --exchange binance --docs-dir ./cex-docs

# Search error code across endpoints + pages
cex-api-docs search-error -- -1002 --exchange binance --docs-dir ./cex-docs

# Classify input text (error, endpoint, payload, code, question)
cex-api-docs classify "POST /sapi/v1/convert/getQuote" --docs-dir ./cex-docs

# Content quality check (empty/thin/tiny_html pages)
cex-api-docs quality-check --docs-dir ./cex-docs

# Build LanceDB semantic search index (requires pip install -e ".[semantic]")
cex-api-docs build-index --docs-dir ./cex-docs
cex-api-docs build-index --exchange binance --limit 500 --docs-dir ./cex-docs

# Compact LanceDB index (merge fragments + cleanup old versions)
cex-api-docs compact-index --docs-dir ./cex-docs

# Semantic search via LanceDB (vector, fts, or hybrid mode)
cex-api-docs semantic-search "check wallet balance" --docs-dir ./cex-docs
cex-api-docs semantic-search "funding rate" --exchange okx --mode vector --docs-dir ./cex-docs

# Cite-only answer from local store
cex-api-docs answer "What permissions does the Binance API key need?" --docs-dir ./cex-docs

# Crawl target validation
cex-api-docs sanitize-check --docs-dir ./cex-docs
cex-api-docs validate-sitemaps [--exchange X] --docs-dir ./cex-docs
cex-api-docs validate-crawl-targets --exchange X [--enable-nav] [--enable-wayback] --docs-dir ./cex-docs
cex-api-docs crawl-coverage [--exchange X] [--enable-live] [--enable-nav] [--backfill] --docs-dir ./cex-docs
cex-api-docs check-links [--exchange X] [--sample N] --docs-dir ./cex-docs

# Enhanced audit
cex-api-docs audit --docs-dir ./cex-docs --include-crawl-coverage --include-live-validation --exchange X
```

Note: The legacy `crawl` command still works but emits a deprecation warning. Use `sync` or `inventory`+`fetch-inventory` instead.

## Project Structure

- `src/cex_api_docs/` Python package (all source modules).
- `tests/` Pytest test suite (mirrors source modules; uses `http_server.py` fixture for network tests).
- `schema/schema.sql` Authoritative SQLite DDL (pages, endpoints, inventories, FTS5, review queue, coverage_gaps).
- `schemas/` JSON Schema files used for validation (`endpoint.schema.json`, `page_meta.schema.json`).
- `data/exchanges.yaml` Registry of all 35 exchanges (61 sections): seeds, allowed domains, base URLs, doc sources.
- `scripts/` Automation helpers (`sync_runtime_repo.py`, `run_sync_preset.sh`, benchmarks).
- `.claude/skills/` Claude Code skill definitions (auto-discovered by Claude Code).

## Data Flow

The pipeline has a linear progression:

1. **Registry** (`data/exchanges.yaml`) -- defines exchanges, sections, seed URLs, and allowlists.
2. **Inventory** (`inventory.py`) -- enumerates all doc URLs for a section (sitemaps first, link-follow fallback). Persists to `inventories`/`inventory_entries` tables.
3. **Fetch** (`inventory_fetch.py`) -- downloads each inventory URL, stores raw HTML + converted markdown + metadata under `cex-docs/`. Supports `--resume`, `--concurrency`, `--render auto`, `--force-refetch`.
4. **Store** (`store.py`, `db.py`, `page_store.py`) -- SQLite DB with WAL mode, write-lock serialization, FTS5 indexes on pages and endpoints.
5. **Endpoint ingest** (`endpoints.py`, `openapi_import.py`, `postman_import.py`, `ingest_page.py`) -- structured endpoint records with provenance (citations back to source pages).
6. **Semantic Index** (`semantic.py`) -- optional LanceDB vector index built from page markdown. Enables vector/hybrid search alongside FTS5 for natural language queries where keyword matching fails.
7. **Query / Answer** (`answer.py`, `lookup.py`, `classify.py`, `pages.py`) -- cite-only answer assembly using FTS5 search + endpoint DB + semantic fallback. Input classification routes errors, paths, payloads, code, and questions to appropriate search commands. Returns `unknown`/`undocumented`/`conflict` when sources are insufficient.
8. **Quality & Validation** (`quality.py`, `fsck.py`, `extraction_verify.py`, `crawl_targets.py`, `crawl_coverage.py`, `live_validate.py`, `link_check.py`) -- content quality gate, structural extraction verification, multi-method crawl target discovery, coverage audit with gap backfill, live site validation, stored page reachability checks.

## Conventions

- Cite-only outputs: no unsupported claims. If not backed by sources, return `unknown` / `undocumented` / `conflict`.
- Deterministic code: crawling, storage, indexing, querying, diffing.
- Agent boundary: agent does interpretation and extraction; code does deterministic I/O and validation.
- JSON-first CLI: machine-readable output to stdout; logs to stderr.

## Key Files

- `data/exchanges.yaml` Registry of exchanges/sections, doc seeds, allowlists, and base URLs
- `schema/schema.sql` SQLite schema (pages, endpoints, FTS5, review queue, inventories, coverage_gaps)
- `src/cex_api_docs/cli.py` CLI entrypoint (35+ subcommands)
- `src/cex_api_docs/errors.py` `CexApiDocsError` dataclass -- all errors use structured codes (ENOINIT, EBADARG, EFTS5, ESCHEMAVER, etc.)
- `src/cex_api_docs/db.py` SQLite connection helper (WAL mode, FTS5 check, schema versioning via PRAGMA user_version, forward migration support)
- `src/cex_api_docs/urlutil.py` Shared `url_host()` utility (used by 7+ modules for hostname extraction)
- `src/cex_api_docs/store.py` Store init + `require_store_db` helper (shared across all modules)
- `src/cex_api_docs/lock.py` File-based exclusive write lock (all DB writes go through this)
- `src/cex_api_docs/inventory.py` Inventory generation (sitemaps + deterministic link-follow fallback)
- `src/cex_api_docs/inventory_fetch.py` Fetch + persist inventory entries (--resume, --concurrency with per-domain rate limiting, 3-phase locking)
- `src/cex_api_docs/playwrightfetch.py` Playwright fetch wrapper (JS-rendered docs fallback)
- `src/cex_api_docs/sync.py` Cron-friendly orchestration (inventory + fetch, --resume, --concurrency)
- `src/cex_api_docs/endpoints.py` Endpoint CRUD (`get_endpoint`, `list_endpoints`, `search_endpoints`), FTS search, review queue management
- `src/cex_api_docs/openapi_import.py` OpenAPI/Swagger spec import into endpoint DB
- `src/cex_api_docs/postman_import.py` Postman collection import into endpoint DB
- `src/cex_api_docs/report.py` Markdown report rendering for sync JSON artifacts + store-report command
- `src/cex_api_docs/lookup.py` Endpoint path lookup (SQL LIKE) and error code search (FTS5 across endpoints + pages)
- `src/cex_api_docs/classify.py` Deterministic input classification (error_message, endpoint_path, request_payload, code_snippet, question)
- `src/cex_api_docs/answer.py` Cite-only answer assembly with endpoint integration + semantic fallback (generalized to all 35 exchanges; Binance has richer heuristics)
- `data/error_code_patterns.yaml` Exchange-specific error code formats and common codes (used by classify + cex-api-query skill)
- `src/cex_api_docs/quality.py` Content quality gate (empty/thin/tiny_html detection, integrated into post-sync)
- `src/cex_api_docs/semantic.py` LanceDB semantic search (build_index, semantic_search, fts5_search) — optional `[semantic]` dependency
- `src/cex_api_docs/fsck.py` Store consistency checker (DB/file mismatches, orphan detection)
- `src/cex_api_docs/url_sanitize.py` URL sanitization filter (template artifacts, CDN paths, bad schemes)
- `src/cex_api_docs/extraction_verify.py` Structural extraction verification (HTML vs markdown quality scoring)
- `src/cex_api_docs/sitemap_validate.py` Sitemap health checks + cross-validation against store
- `src/cex_api_docs/nav_extract.py` Nav extraction via agent-browser + HTTP/BS4 fallback
- `src/cex_api_docs/crawl_targets.py` Multi-method URL discovery (sitemap + link-follow + nav + Wayback CDX)
- `src/cex_api_docs/live_validate.py` Live site nav comparison against store
- `src/cex_api_docs/crawl_coverage.py` Coverage audit + gap backfill
- `src/cex_api_docs/link_check.py` Stored page URL reachability checks (HEAD requests)
- `src/cex_api_docs/ccxt_xref.py` CCXT cross-reference validation against endpoint DB
- `src/cex_api_docs/embeddings.py` Embedding backend selection (Jina MLX primary, SentenceTransformers fallback)
- `src/cex_api_docs/chunker.py` Heading-aware markdown chunking (mistune AST) for semantic index
- `src/cex_api_docs/reranker.py` Cross-encoder reranking (jina-reranker-v3-mlx)
- `scripts/sync_runtime_repo.py` Sync maintainer repo → query-only runtime repo (compaction, strip-maintenance, manifest)

## Gotchas

- `cex-docs/`, `cex-docs-*/`, and `poc-binance-full/` are local data and must never be committed (gitignored).
- CLI JSON is printed at the end of a command; if you redirect stdout to a file, it may stay empty until completion.
- Prefer deterministic fetch first; use `--render auto` when a docs site requires JS rendering.
- **FTS5 required**: SQLite must be built with FTS5 support; the app raises `EFTS5` at init if missing. macOS system Python and Homebrew Python both include FTS5. Some minimal Docker images do not.
- **Playwright is optional**: install with `pip install -e ".[playwright]"`. Without it, `--render playwright` and `--render auto` will fail at runtime.
- **Semantic search model**: `jina-embeddings-v5-text-nano` (768 dims, last-token pooling, EuroBERT backbone). MLX path: Jina's own loader (`jinaai/jina-embeddings-v5-text-nano-mlx`), not mlx-embeddings. Query-only install: `pip install -e ".[semantic-query]"` (Mac). Full install: `pip install -e ".[semantic]"` (Mac or PC/CUDA). Primary build: PC (CUDA via sentence-transformers). Fallback build: MacBook (Jina MLX loader). Env overrides: `CEX_EMBEDDING_BACKEND` (auto|jina-mlx|sentence-transformers), `CEX_EMBEDDING_MODEL` (jina-mlx repo ID), `CEX_EMBEDDING_FALLBACK_MODEL` (ST model name), `CEX_JINA_MLX_REVISION` (pin HF revision). First run downloads ~495MB model from HuggingFace (cached after that). LanceDB index stored at `cex-docs/lancedb-index/`.
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
- **Korean exchange doc coverage**:
  - **Upbit**: English docs (`global-docs.upbit.com`, `rest_en`) lag Korean (`docs.upbit.com/kr/`, `rest_ko`) by ~3 minor versions (v1.3.1 vs v1.6.1 as of 2026-02). English is missing 4 endpoints, has stale response schemas, and omits per-endpoint rate limits and changelogs. Treat Korean as authoritative; English is supplementary for keyword search.
  - **Bithumb**: Korean docs (`apidocs.bithumb.com`, `rest`) are the default. English (`rest_en`) uses Localize.js client-side translation (1,723 entries) and **requires Playwright** to render. Coverage may be partial since translations lag Korean updates.
  - **Coinone**: Korean-only (`docs.coinone.co.kr`). No English version exists. Endpoint paths and parameter names are in English and searchable via FTS5.
  - **Korbit**: Already in English (`docs.korbit.co.kr`). No language issue.

## Current Phase

Phase: API Assistant Tool v2. 35 exchanges (21 CEX, 13 DEX, 1 ref), 61 sections in registry. Synced: **5,716+ pages, 7.6M words, ~3,600 structured endpoints**. Store is at `cex-docs/`.

Latest:
- **Crawl validation pipeline** (10 phases: sanitization, extraction verification, sitemap health, nav extraction, multi-method URL discovery, live validation, coverage audit, gap backfill, link reachability checks).
- **7 new CEXes synced** (kraken, coinbase, bitmex, bitmart, whitebit, bitbank, mercadobitcoin) with OpenAPI imports for bitmex, mercadobitcoin, coinbase/intx.
- **4 Tier 1 DEX protocols synced** (aster, apex, grvt, paradex).
- **CCXT wiki synced** (188 pages) + cross-reference module (`ccxt_xref.py`).
- **Coinbase scope dedup** — added `scope_priority` + `scope_prefixes` to 4 Coinbase sections sharing one sitemap.
- **LanceDB semantic index** — jina-embeddings-v5-text-nano (768 dims, Jina MLX / sentence-transformers) with heading context injection. Chunks prepend `[Page Title > Section Heading]` for disambiguation.
- **API Assistant v2** — input classification (`classify.py`), endpoint path lookup (`lookup.py`), error code search, and enhanced answer assembly with endpoint integration + semantic fallback.

Research completed (docs/research/):
- LanceDB: Validated via POC — clear value as supplementary semantic index alongside SQLite FTS5.
- LlamaIndex: Not recommended — LLM-based retrieval conflicts with deterministic cite-only design.
- CEX OpenAPI specs: Mapped all 16 original exchanges; all viable imports completed.
- CCXT as cross-reference: Built `ccxt_xref.py` — 20/21 CEXes mapped (korbit has no CCXT class, mercadobitcoin remaps to `mercado`).
- DEX expansion: 4 Tier 1 perp DEXes added (Aster, ApeX, GRVT, Paradex). edgeX deferred (stub docs only).

Next: Rebuild semantic index with new Jina v5 model (full rebuild required — 1024→768 dim change). Add link validation to maintainer workflow. Periodic CCXT docs refresh. Add Tier 2 DEXes (Orderly, Pacifica, Nado, Bluefin). Structured changelog extraction for drift detection (404 changelog pages already in store, no structured schema yet).
