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

# Schema migration (dry-run by default, --apply to execute)
cex-api-docs migrate-schema --docs-dir ./cex-docs
cex-api-docs migrate-schema --docs-dir ./cex-docs --apply

# Diff pages between crawl runs
cex-api-docs diff --docs-dir ./cex-docs

# Discover sitemap/spec URLs from registry seeds
cex-api-docs discover-sources --docs-dir ./cex-docs

# Render sync JSON artifact into Markdown report
cex-api-docs report <sync-artifact.json>

# Ingest a browser-captured page into the store (HTML or markdown)
cex-api-docs ingest-page --exchange binance --section spot --url <page-url> --html-file page.html --docs-dir ./cex-docs

# Import AsyncAPI spec (stub — no CEX specs implemented yet)
cex-api-docs import-asyncapi --exchange whitebit --section v4 --url <spec-url> --docs-dir ./cex-docs

# Endpoint field coverage aggregation
cex-api-docs coverage --docs-dir ./cex-docs

# Compute + persist endpoint completeness gaps
cex-api-docs coverage-gaps --docs-dir ./cex-docs
cex-api-docs coverage-gaps-list --docs-dir ./cex-docs

# Detect stale endpoint citations vs current page content
cex-api-docs detect-stale-citations --docs-dir ./cex-docs

# Rebuild FTS5 indexes from stored markdown
cex-api-docs fts-rebuild --docs-dir ./cex-docs

# Golden QA retrieval validation (requires [semantic])
cex-api-docs validate-retrieval --qa-file tests/golden_qa.jsonl --limit 5 --docs-dir ./cex-docs

# Resolve docs_url for spec-imported endpoints
cex-api-docs link-endpoints --docs-dir ./cex-docs
```

Note: The legacy `crawl` command still works but emits a deprecation warning. Use `sync` or `inventory`+`fetch-inventory` instead.

## Project Structure

- `src/cex_api_docs/` Python package (all source modules).
- `tests/` Pytest test suite (mirrors source modules; uses `http_server.py` fixture for network tests).
- `schema/schema.sql` Authoritative SQLite DDL (pages, endpoints, inventories, FTS5, review queue, coverage_gaps).
- `schemas/` JSON Schema files used for validation (`endpoint.schema.json`, `page_meta.schema.json`).
- `data/exchanges.yaml` Registry of all 46 exchanges (78 sections): seeds, allowed domains, base URLs, doc sources.
- `scripts/` Automation helpers (`sync_runtime_repo.py`, `run_sync_preset.sh`, benchmarks).
- `.claude/skills/` Claude Code skill definitions: `cex-api-docs` (maintainer), `cex-api-query` (query/answer), `cex-discovery` (new exchange discovery).

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

## Exhaustive Coverage Mandate

**The goal is 100% exhaustive coverage. No exceptions.**

- **No pages missing.** Every documented page for every registered exchange must be in the store. If a crawl method fails, escalate through the cascade until it works: `--render auto` → Playwright → crawl4ai → headed browser → Agent Browser. A 0-page section is a bug, not an acceptable state.
- **No content missing.** If a page renders in a browser but our stored markdown is empty/thin, the crawl method is wrong. Fix it. Single-page SPAs (OKX, Gate.io, HTX) must be crawled with browser rendering. Swagger UIs (MercadoBitcoin) must have their specs imported. Localize.js sites (Bithumb EN) must use Playwright to get translated content.
- **No endpoints missing.** Every available spec (OpenAPI, Postman, AsyncAPI) must be imported. Every CCXT endpoint gap must be investigated. If an exchange has 200 CCXT endpoints and we have 0, that's a failure.
- **No inaccurate data.** Cross-reference all sources. Specs drift from docs. Postman collections go stale. CCXT metadata is community-maintained. Official API doc pages are closest to ground truth. Flag conflicts, never silently accept one source.
- **No partial data.** If an exchange has FIX docs, WebSocket docs, changelogs, or multiple API versions — they all get crawled and indexed. Scope gaps (like Coinbase FIX docs outside scope_prefixes) must be fixed, not documented as known issues.
- **Everything verified and validated.** After every sync: quality-check, spot-check with alternate crawl method, cross-reference endpoint counts against CCXT. After every spec import: verify endpoint count matches spec. After every new exchange: validate-crawl-targets with --enable-nav.

The crawl cascade exists precisely so that nothing falls through the cracks. "This exchange needs Playwright" is not an excuse for 0 pages — it means install Playwright and re-sync.

## Conventions

- Cite-only outputs: no unsupported claims. If not backed by sources, return `unknown` / `undocumented` / `conflict`.
- Deterministic code: crawling, storage, indexing, querying, diffing.
- Agent boundary: agent does interpretation and extraction; code does deterministic I/O and validation.
- JSON-first CLI: machine-readable output to stdout; logs to stderr.
- **Skills and docs stay in sync with the store.** After any significant change (new exchange, spec import, crawl gap fix, new CLI command), update CLAUDE.md, README.md, AGENTS.md, all three SKILL.md files (cex-api-docs, cex-api-query, cex-discovery), and the bible. Run `store-report` for current numbers. See "Updating Skills & Documentation" in `.claude/skills/cex-api-docs/SKILL.md` for the full checklist.

## Key Files

- `data/exchanges.yaml` Registry of exchanges/sections, doc seeds, allowlists, and base URLs
- `schema/schema.sql` SQLite schema (pages, endpoints, FTS5, review queue, inventories, coverage_gaps)
- `src/cex_api_docs/cli.py` CLI entrypoint (51 subcommands)
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
- `src/cex_api_docs/answer.py` Cite-only answer assembly with endpoint integration + semantic fallback (generalized to all 46 exchanges; Binance has richer heuristics)
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
- `src/cex_api_docs/fts_util.py` Shared FTS5 query utilities (sanitize, build, extract terms, BM25 normalization, RRF fusion, position-aware blend, strong-signal shortcut)
- `src/cex_api_docs/reranker.py` Backend-agnostic reranking (auto | cross-encoder | qwen3 | jina-v3 | jina-v3-mlx | flashrank). OS auto-detection: macOS+MLX→jina-v3-mlx→jina-v3→cross-encoder→flashrank, Linux→jina-v3→cross-encoder→flashrank. M10 benchmark (163 queries): Jina v3 MRR=0.556 (+15.6% over MiniLM, p=0.0014), 218ms/query.
- `scripts/sync_runtime_repo.py` Sync maintainer repo → query-only runtime repo (compaction, strip-maintenance, manifest)
- `src/cex_api_docs/changelog.py` Changelog extraction from stored pages (extract-changelogs, list-changelogs)
- `src/cex_api_docs/audit.py` Consolidated audit runner (combines quality, coverage, crawl-coverage, link-check)
- `src/cex_api_docs/coverage.py` Endpoint field_status coverage aggregation
- `src/cex_api_docs/coverage_gaps.py` Endpoint completeness gap computation + persistence
- `src/cex_api_docs/stale_citations.py` Stale citation detection (endpoint citations vs current page content)
- `src/cex_api_docs/resolve_docs_urls.py` Docs URL resolution for spec-imported endpoints (link-endpoints command)
- `src/cex_api_docs/asyncapi_import.py` AsyncAPI spec import (stub — no CEX specs implemented yet)
- `src/cex_api_docs/ingest_page.py` Manual page ingestion from browser capture (HTML or markdown input)
- `src/cex_api_docs/validate.py` Golden QA retrieval validation (exact/prefix/domain matching)
- `src/cex_api_docs/registry.py` Registry loader (parses data/exchanges.yaml into typed objects)
- `src/cex_api_docs/page_store.py` Page storage operations (upsert, markdown extraction, word count)
- `.claude/skills/cex-api-docs/SKILL.md` Maintainer workflow skill (full sync, spec imports, validation, doc updates)
- `.claude/skills/cex-api-query/SKILL.md` Query/answer agent skill (classification → search → cite-only answer)
- `.claude/skills/cex-discovery/SKILL.md` Exhaustive crawl target discovery skill (new exchange onboarding)

## Gotchas

- `cex-docs/`, `cex-docs-*/`, and `poc-binance-full/` are local data and must never be committed (gitignored).
- CLI JSON is printed at the end of a command; if you redirect stdout to a file, it may stay empty until completion.
- Prefer deterministic fetch first; use `--render auto` when a docs site requires JS rendering.
- **FTS5 required**: SQLite must be built with FTS5 support; the app raises `EFTS5` at init if missing. macOS system Python and Homebrew Python both include FTS5. Some minimal Docker images do not.
- **Playwright is optional**: install with `pip install -e ".[playwright]"`. Without it, `--render playwright` and `--render auto` will fail at runtime.
- **Semantic search model**: `jina-embeddings-v5-text-small` (1024 dims, EuroBERT backbone). Upgraded from v5-text-nano (768 dims) — +27.3% MRR, +22.3% Hit@5 on 163-query benchmark. MLX path: Jina's own loader (`jinaai/jina-embeddings-v5-text-small-mlx`), not mlx-embeddings. Query-only install: `pip install -e ".[semantic-query]"` (Mac). Full install: `pip install -e ".[semantic]"` (Mac or PC/CUDA). Primary build: PC (CUDA via sentence-transformers). Fallback build: MacBook (Jina MLX loader). Env overrides: `CEX_EMBEDDING_BACKEND` (auto|jina-mlx|sentence-transformers), `CEX_EMBEDDING_MODEL` (jina-mlx repo ID), `CEX_EMBEDDING_FALLBACK_MODEL` (ST model name), `CEX_JINA_MLX_REVISION` (pin HF revision). First run downloads model from HuggingFace (cached after that). LanceDB index: 334,935 rows, 1024d, 2.3 GB compacted, stored at `cex-docs/lancedb-index/`. Build: ~100 min at batch_size=64 on RTX 4070 Ti SUPER (CUDA). Extreme pages (>50K words) may OOM at batch_size=64 — use incremental batch_size=1 to add them. batch_size=16 is 15x slower — avoid.
- **LanceDB compaction**: Use `table.optimize(cleanup_older_than=timedelta(days=0))` not the deprecated `compact_files()` + `cleanup_old_versions()`. The CLI `compact-index` command wraps this. Run periodically after large index builds to reduce fragment count and disk usage.
- **Write lock contention**: all DB writes acquire an exclusive file lock (`cex-docs/db/.write.lock`). `--lock-timeout-s` (default 10s) controls how long a command waits. Concurrent writers will queue; long fetches hold the lock in short bursts (3-phase locking in `inventory_fetch.py`).
- **Python >=3.11 required** (per pyproject.toml). Uses `match/case`, `dataclass(slots=True)`, and `X | Y` union syntax.
- **Schema path resolution**: `cli.py` resolves `schema/schema.sql` relative to the package install location (`Path(__file__).parents[2]`). This works with `pip install -e .` but will break if the source tree is moved after install.
- **`extract_page_markdown` return order**: Returns `(html, title, md_norm, word_count)` — first element is decoded HTML string, not markdown. The normalized markdown is the third element.
- **Raw string regex**: In `r"..."` strings, use single backslash for regex escapes (`\w`, `\s`, `\S`). Double backslash (`\\w`) matches literal backslash + letter. Previously caused silent failures in charset detection and robots.txt sitemap parsing.
- **Single-page doc exchanges**: OKX (224K words), Gate.io (256K), HTX (325K across 4 pages), Crypto.com (35K), Bitstamp (22K), Korbit (25K), Phemex (53K), Backpack (31K), WOO X (20K), BingX (1K) serve their entire API reference from 1-2 HTML files. This is correct — the pipeline handles them fine. Don't treat low page counts as errors.
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

Phase: API Assistant Tool v2. 46 exchanges (29 CEX, 16 DEX, 1 ref), 78 sections in registry. Synced: **10,724 pages, 16.73M words, 4,872 structured endpoints**. Store is at `cex-docs/`.

Latest:

- **Crawl targets bible v2** (`docs/crawl-targets-bible.md`, 1,175 lines) — exhaustive reference with crawl methodology, source trust framework, and 8 missing exchange candidates.
- **CCXT cross-reference fixed** — dict-of-dicts bug, per-section base URLs, dydx+hyperliquid mapping, crypto_com alias, Postman `{{variable}}` stripping, suffix-based version matching. 15 exchanges went from 0→3,945 CCXT endpoints. Match rate: 32.9% (1,698/5,160).
- **Multi-method crawl cascade** — Pipeline: `--render auto` (requests + Playwright fallback). Validation: `crawl4ai` (primary, ~95% sites) → `cloudscraper` → headed browser → Agent Browser. Installed: crawl4ai 0.8.0, cloudscraper 1.2.71, Playwright 1.58.0.
- **WhiteBIT spec discovery** — 7 OpenAPI + 19 AsyncAPI specs found via `docs.whitebit.com/llms.txt` (currently 0 endpoints).
- **Kraken crawl gap** — 48 REST API pages in sitemap never fetched; seed URL only reached guide pages.
- **Coinbase scope gap** — FIX docs for 4 products outside `scope_prefixes`.
- **llms.txt mapped** — 13 of 46 exchanges have it (ReadMe.io / GitBook auto-generate).
- **11 new exchanges registered** — MEXC (21p, 114ep), BingX (1p), Deribit (530p, 173ep), Backpack (1p, 22ep), CoinEx (489p), WOO X (1p), Phemex (1p), Gemini (135p), Orderly (527p, 203ep), Bluefin (62p), Nado (192p). Pacifica deferred (insufficient docs).
- **3 new OpenAPI spec imports** — Deribit (173 ops), Orderly (203 ops), Backpack (22 ops).
- **Crawl validation pipeline** (10 phases: sanitization, extraction verification, sitemap health, nav extraction, multi-method URL discovery, live validation, coverage audit, gap backfill, link reachability checks).
- **API Assistant v2** — input classification (`classify.py`), endpoint path lookup (`lookup.py`), error code search, and enhanced answer assembly with endpoint integration + semantic fallback.
- **Verification fixes** — Semantic FTS cold-start (14.1s → 1.0s via deferred embedder loading), render cascade validation (`_find_node_pw_module()` at selection time), LanceDB compaction (3,568 → 9 fragments, 2.4GB → 908MB via `table.optimize()`).
- **Query pipeline overhaul (M2)** — 18 quality issues fixed across 4 phases: shared `fts_util.py` (FTS5 sanitization, hyphen/colon quoting, AND/OR query logic), values-only `search_text` (no JSON key pollution), porter stemming + BM25 column weights on FTS5 tables (schema v4→v5), classification augmentation in answer pipeline, pages-first error code search with URL boost, directory prefix matching, FlashRank reranker (ms-marco-MiniLM-L-12-v2, 302ms/20 docs on CPU), BM25 score normalization, excerpt boundary snapping, word-boundary exchange detection.
- **Score fusion & routing (M5)** — RRF k=60 fusion (replaces interleaved merge), query_type="vector" to avoid double-RRF with LanceDB, strong-signal BM25 shortcut, position-aware reranker blending (max-normalized RRF + sigmoid reranker, 75/25→60/40→40/60), direct routing for high-confidence endpoint_path/error_message (>= 0.7), Binance section keyword detection, multi-section routing, LanceDB SQL injection prevention, spec URL suppression, schema v5→v6 (changelog FTS porter stemming). 415 tests.
- **Production benchmark suite (M6)** — 180-query golden QA (88 question, 28 endpoint_path, 30 error_message, 14 code_snippet, 15 request_payload, 5 cross-section), graded relevance (TREC 0-3), 17 negative test cases, CI-fast canary tests, nDCG@5/MRR/per-path eval, pre/post comparison with regression alerts.
- **Model benchmarks (M9-M10)** — Reranker: Jina v3 winner (MRR=0.556, +15.6% over MiniLM, p=0.0014). Auto cascade: jina-v3 → cross-encoder → flashrank (Linux), jina-v3-mlx first (macOS). Embedding: v5-small +12.5% Hit@5 over v5-nano. Benchmark harnesses: `scripts/benchmark_embeddings.py`, `scripts/benchmark_rerankers.py`, `scripts/benchmark_mlx.py`. Bootstrap BCa CI + paired permutation tests.
- **Pre-rebuild confidence (M11)** — 4 bugs fixed (embeddings defaults, _DOMAIN_MAP, incremental build scope, vector memory), benchmark metrics corrected (negative dilution), golden QA URLs fixed (90% match rate), schema v6 migrated.
- **Classification routing (M12)** — request_payload routing (0%→73% ok, 40% URL hit), code_snippet routing (50%→100% ok, 29% URL hit), exchange detection from payload parameter signatures and ccxt code patterns, multi-exchange disambiguation (CCXT reference exchange auto-dropped). Pipeline eval: MRR 0.543→0.580 (+6.8%), OK rate 82.78%→92.78% (+10pp), domain hit 86.50%→96.93% (+10.4pp), nDCG@5 1.218→1.358 (+11.5%).
- **Query quality refinement (M15)** — Domain synonym expansion (30+ terms, ws→websocket, auth→authentication, ohlc→candlestick etc.), FTS5 AND-first with OR fallback, Binance section routing pass-through to generic search, docs_url resolver overhaul (changelog filtering, path-in-URL scoring, language deprioritization, 4,358 endpoints resolved), direct route fallback for empty docs_url, position-aware blend wired into semantic.py. Pipeline eval: MRR 0.611 (+5.3%), code_snippet url 21%→36%, endpoint_path url 50%→61%, request_payload url 40%→47%. 428 tests.

Research completed (docs/research/ and architect/research/):

- LanceDB: Validated via POC — clear value as supplementary semantic index alongside SQLite FTS5.
- LlamaIndex: Not recommended — LLM-based retrieval conflicts with deterministic cite-only design.
- CEX OpenAPI specs: Mapped all 16 original exchanges; all viable imports completed.
- CCXT as cross-reference: Built `ccxt_xref.py` — 33 exchanges mapped (korbit/orderly/bluefin/nado have no CCXT class, mercadobitcoin remaps to `mercado`, dydx/backpack removed in ccxt 4.x).
- DEX expansion: 4 Tier 1 perp DEXes added (Aster, ApeX, GRVT, Paradex). edgeX deferred (stub docs only).
- Reranker survey: Jina Reranker v3 winner (MRR=0.556, +15.6% over CrossEncoder MiniLM, p=0.0014 on 163 queries). Auto cascade: jina-v3 → cross-encoder → flashrank (Linux), jina-v3-mlx first (macOS). CEX_RERANKER_BACKEND env var selects backend.
- Embedding models: jina-embeddings-v5-text-small (1024d) confirmed +12.5% Hit@5 over v5-text-nano (768d). Index rebuild required for dimension change. ColBERT deferred (17.5 GB storage, not justified).
- Score fusion: RRF k=60 industry standard. Position-aware blending from qmd. Strong-signal shortcut for keyword matches.
- Benchmark design: 200-query target, TREC graded relevance, ranx for nDCG, two-tier CI (canary + full).

Next: Periodic CCXT docs refresh. Changelog drift detection. Remaining query quality gaps: code_snippet (36% url hit) and request_payload (47% url hit) need parameter-combination matching. Pacifica re-evaluation when docs mature.

## Compact Instructions

When compacting, preserve:

- The current forge pipeline stage and substep
- All file paths from the last 10 tool calls
- All test results and their pass/fail status
- Any error messages being actively debugged
- The exact milestone name and number from FORGE-STATUS.md

## Forge Pipeline State

After any context compaction, re-read these files immediately:

1. FORGE-HANDOFF.md — what you were doing when compaction occurred
2. FORGE-STATUS.md — current milestone and phase
3. TODO.md — task checklist with completion status
4. FORGE-MEMORY.md — cross-session learnings

Then continue from the point described in FORGE-HANDOFF.md "What's In Progress".
