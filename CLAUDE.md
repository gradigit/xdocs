# CEX API Docs

## What This Is

A local-only, cite-only CEX API documentation knowledge base (library + CLI + agent skill) that crawls official exchange docs, stores and indexes them via SQLite FTS5, and enables agents to answer endpoint, rate limit, and permission questions with strict provenance.

## Agent Rules

- **Cite-only**: never assert unsupported facts. If not backed by sources, return `unknown` / `undocumented` / `conflict`.
- **Exhaustive coverage**: no pages missing, no content missing, no endpoints missing, no partial data. If a crawl method fails, escalate through the cascade. A 0-page section is a bug.
- Keep deterministic behavior in crawling, storage, indexing, and query paths.
- Prefer machine-readable JSON command output to stdout; logs to stderr.
- Agent boundary: agent does interpretation and extraction; code does deterministic I/O and validation.

## Skills

Skills are agent-agnostic. Canonical source is `skills/` at the repo root. Platform auto-discovery directories (`.claude/skills/`, `.agents/skills/`) are symlinks to the canonical source.

| Skill | Purpose |
|-------|---------|
| `xdocs-maintain` | Maintainer workflow (sync, spec imports, validation, doc updates) |
| `xdocs-query` | Query/answer (classification → search → cite-only answer) |
| `xdocs-discovery` | Exhaustive crawl target discovery (new exchange onboarding) |
| `xdocs-qa` | QA gap finder (iterative testing loop) |
| `xdocs-bugreport` | Structured bug report generation (environment, reproduction, root cause classification) |
| `xdocs-triage` | Bug report triage and fix (independent reproduction, severity challenge, A/B validated fix) |

When creating, updating, or maintaining skills, edit the canonical file in `skills/<name>/SKILL.md`. The symlinks ensure both Claude Code and Codex CLI discover them automatically. All SKILL.md files must include YAML frontmatter (`name` + `description`) for Codex progressive disclosure.

### xdocs-query routing

- CLI auto-discovers the data store. Only pass `--docs-dir` to override.
- Execute the classify-first routing flow from the skill
- For natural-language questions, prefer `semantic-search --mode hybrid --rerank-policy auto` first, then targeted endpoint/page fetch
- Keep retrieval bounded (avoid broad markdown scans unless retrieval fails)

## Repository

- **Remote**: `github.com/gradigit/xdocs`
- **Dev install**: `uv pip install -e ".[dev,semantic]"`
- **User install**: `uv tool install -e .` (global CLI, no venv needed)
- Data is distributed via GitHub Releases as a zstd-compressed tarball. Users run `./scripts/bootstrap-data.sh` to download and extract.

### Publishing a data release

After crawling new pages or rebuilding the index:

```bash
python scripts/sync_runtime_repo.py \
  --runtime-root . --docs-dir ./cex-docs --publish
```

## Environment

- Python: **3.11+** (per pyproject.toml). Uses `match/case`, `dataclass(slots=True)`, and `X | Y` union syntax.
- Use `python3` (not `python`)

Quick setup:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,semantic]"
pytest
pytest tests/test_endpoints.py -x    # single module, stop on first failure
pytest -k "test_stale" -x            # run tests matching pattern
xdocs --help
```

## Commands

```bash
# Initialize a local store (idempotent)
xdocs init --docs-dir ./cex-docs

# Deterministic sync (inventory -> fetch, render default: auto)
xdocs sync --docs-dir ./cex-docs

# Resume an interrupted sync (reuse existing inventories, fetch only pending/error entries)
xdocs sync --docs-dir ./cex-docs --resume

# Parallel fetch (N concurrent workers with per-domain rate limiting)
xdocs sync --docs-dir ./cex-docs --concurrency 4

# Force re-download all pages to detect content changes
xdocs sync --docs-dir ./cex-docs --force-refetch

# Resume an interrupted inventory fetch
xdocs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --resume

# Parallel inventory fetch
xdocs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --concurrency 4

# Report on current store contents (pages, inventories, endpoints, review queue)
xdocs store-report --docs-dir ./cex-docs
xdocs store-report --exchange binance --section spot --output report.md

# Import endpoints from OpenAPI spec (use --base-url if spec lacks servers[].url)
xdocs import-openapi --exchange binance --section spot --url <spec-url> --docs-dir ./cex-docs --continue-on-error

# Import endpoints from Postman collection
xdocs import-postman --exchange bybit --section v5 --url <collection-url> --docs-dir ./cex-docs --continue-on-error

# Search endpoints by keyword
xdocs search-endpoints "rate limit" --exchange binance --docs-dir ./cex-docs

# Get full endpoint record by ID
xdocs get-endpoint <endpoint_id> --docs-dir ./cex-docs

# List endpoint summaries by exchange/section
xdocs list-endpoints --exchange binance --section spot --limit 20 --docs-dir ./cex-docs

# Lookup endpoint by HTTP path (SQL LIKE, handles {{url}} prefix)
xdocs lookup-endpoint /sapi/v1/convert/getQuote --method POST --exchange binance --docs-dir ./cex-docs

# Search error code across endpoints + pages
# Use -- only for negative codes (dash would be parsed as a flag)
xdocs search-error -- -1002 --exchange binance --docs-dir ./cex-docs
# Positive codes: no -- needed
xdocs search-error 60029 --exchange okx --docs-dir ./cex-docs

# Classify input text (error, endpoint, payload, code, question)
xdocs classify "POST /sapi/v1/convert/getQuote" --docs-dir ./cex-docs

# Content quality check (empty/thin/tiny_html pages)
xdocs quality-check --docs-dir ./cex-docs

# Build LanceDB semantic search index (requires uv pip install -e ".[semantic]")
xdocs build-index --docs-dir ./cex-docs
xdocs build-index --exchange binance --limit 500 --docs-dir ./cex-docs

# Compact LanceDB index (merge fragments + cleanup old versions)
xdocs compact-index --docs-dir ./cex-docs

# Semantic search via LanceDB (vector, fts, or hybrid mode)
xdocs semantic-search "check wallet balance" --docs-dir ./cex-docs
xdocs semantic-search "funding rate" --exchange okx --mode vector --docs-dir ./cex-docs

# Cite-only answer from local store
xdocs answer "What permissions does the Binance API key need?" --docs-dir ./cex-docs

# Crawl target validation
xdocs sanitize-check --docs-dir ./cex-docs
xdocs validate-sitemaps [--exchange X] --docs-dir ./cex-docs
xdocs validate-crawl-targets --exchange X [--enable-nav] [--enable-wayback] --docs-dir ./cex-docs
xdocs crawl-coverage [--exchange X] [--enable-live] [--enable-nav] [--backfill] --docs-dir ./cex-docs
xdocs check-links [--exchange X] [--sample N] --docs-dir ./cex-docs

# Enhanced audit
xdocs audit --docs-dir ./cex-docs --include-crawl-coverage --include-live-validation --exchange X

# Schema migration (dry-run by default, --apply to execute)
xdocs migrate-schema --docs-dir ./cex-docs
xdocs migrate-schema --docs-dir ./cex-docs --apply

# Diff pages between crawl runs
xdocs diff --docs-dir ./cex-docs

# Classify changelog entries by impact type
xdocs classify-changelogs --docs-dir ./cex-docs
xdocs classify-changelogs --exchange binance --since 2026-01-01 --severity err --docs-dir ./cex-docs

# Discover sitemap/spec URLs from registry seeds
xdocs discover-sources --docs-dir ./cex-docs

# Render sync JSON artifact into Markdown report
xdocs report <sync-artifact.json>

# Ingest a browser-captured page into the store (HTML or markdown)
xdocs ingest-page --exchange binance --section spot --url <page-url> --html-file page.html --docs-dir ./cex-docs

# Import AsyncAPI spec (stub — no CEX specs implemented yet)
xdocs import-asyncapi --exchange whitebit --section v4 --url <spec-url> --docs-dir ./cex-docs

# Endpoint field coverage aggregation
xdocs coverage --docs-dir ./cex-docs

# Compute + persist endpoint completeness gaps
xdocs coverage-gaps --docs-dir ./cex-docs
xdocs coverage-gaps-list --docs-dir ./cex-docs

# Detect stale endpoint citations vs current page content
xdocs detect-stale-citations --docs-dir ./cex-docs

# Rebuild FTS5 indexes from stored markdown
xdocs fts-rebuild --docs-dir ./cex-docs

# Golden QA retrieval validation (requires [semantic])
xdocs validate-retrieval --qa-file tests/golden_qa.jsonl --limit 5 --docs-dir ./cex-docs

# Resolve docs_url for spec-imported endpoints
xdocs link-endpoints --docs-dir ./cex-docs

# Validate registry/base URLs
xdocs validate-registry
xdocs validate-base-urls

# CCXT cross-reference
xdocs ccxt-xref --docs-dir ./cex-docs
```

Note: The legacy `crawl` command still works but emits a deprecation warning. Use `sync` or `inventory`+`fetch-inventory` instead.

## Project Structure

- `src/xdocs/` Python package (all source modules).
- `tests/` Pytest test suite (mirrors source modules; uses `http_server.py` fixture for network tests).
- `schema/schema.sql` Authoritative SQLite DDL (pages, endpoints, inventories, FTS5, review queue, coverage_gaps).
- `schemas/` JSON Schema files used for validation (`endpoint.schema.json`, `page_meta.schema.json`).
- `data/exchanges.yaml` Registry of all 46 exchanges (78 sections): seeds, allowed domains, base URLs, doc sources.
- `scripts/` Automation helpers (`sync_runtime_repo.py`, `run_sync_preset.sh`, benchmarks).
- `skills/` Agent-agnostic skill definitions (canonical source). `.claude/skills/` and `.agents/skills/` are symlinks for platform auto-discovery.

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
- **No unverified data.** Alternative sources (llms-full.txt, GitHub repos, AI skill repos, raw markdown endpoints) are useful but are NOT ground truth. They may be auto-generated, outdated, or simplified. Every alternative source must be cross-referenced against the official docs page. Endpoints imported from specs without matching page content should be flagged as `spec_only` (unverified). Source trust hierarchy: official docs page > OpenAPI spec on docs domain > GitHub raw docs > llms-full.txt > community specs > AI skill repos.
- **No partial data.** If an exchange has FIX docs, WebSocket docs, changelogs, or multiple API versions — they all get crawled and indexed. Scope gaps (like Coinbase FIX docs outside scope_prefixes) must be fixed, not documented as known issues.
- **No nav-chrome-only pages.** A stored page must contain actual documentation content (endpoint descriptions, parameter tables, code examples), not just navigation sidebar links or SPA shell HTML. Pages with >0 words but only nav/menu content are worse than empty — they give false confidence. The sync pipeline must detect and flag these.
- **Everything verified and validated.** After every sync: quality-check, spot-check with alternate crawl method, cross-reference endpoint counts against CCXT. After every spec import: verify endpoint count matches spec. After every new exchange: validate-crawl-targets with --enable-nav.

The crawl cascade exists precisely so that nothing falls through the cracks. "This exchange needs Playwright" is not an excuse for 0 pages — it means install Playwright and re-sync.

## Conventions

- Cite-only outputs: no unsupported claims. If not backed by sources, return `unknown` / `undocumented` / `conflict`.
- Deterministic code: crawling, storage, indexing, querying, diffing.
- Agent boundary: agent does interpretation and extraction; code does deterministic I/O and validation.
- JSON-first CLI: machine-readable output to stdout; logs to stderr.
- **Skills and docs stay in sync with the store.** After any significant change (new exchange, spec import, crawl gap fix, new CLI command), update AGENTS.md, README.md, all SKILL.md files, and the bible. Run `store-report` for current numbers. See "Updating Skills & Documentation" in `skills/xdocs-maintain/SKILL.md` for the full checklist.

## Change Validation Protocol

Every code change to the query/answer pipeline MUST follow this protocol. No exceptions.

### Before implementing

1. **Design targeted test cases** for the specific fix. Don't rely solely on existing golden QA — create new entries that exercise the exact behavior being changed.
   - Add golden QA entries to `tests/golden_qa.jsonl` covering the fix scenario (positive + negative).
   - Add unit tests in `tests/` that verify the fix at the function level (not just end-to-end).
   - For classification changes: add cases to `tests/test_classify.py`.
   - For answer pipeline changes: add cases to `tests/test_answer_enhanced.py`.
   - For FTS/scoring changes: add cases to `tests/test_fts_util.py`.

2. **Capture baseline** before any code change:
   ```bash
   python3 tests/eval_answer_pipeline.py --qa-file tests/golden_qa.jsonl --save reports/<milestone>-baseline.json
   ```

### After implementing

3. **Run unit tests** — all must pass, zero regressions:
   ```bash
   pytest -q --tb=short
   ```

4. **Run full pipeline eval** with comparison:
   ```bash
   python3 tests/eval_answer_pipeline.py --qa-file tests/golden_qa.jsonl --save reports/<milestone>-post.json --compare reports/<milestone>-baseline.json
   ```

5. **Check per-path regression** — no classification path may regress >3% MRR without explicit justification:
   - `question`, `endpoint_path`, `error_message`, `code_snippet`, `request_payload`
   - If a path regresses: investigate, fix, or revert. Document in TODO.md.

6. **If A/B testing multiple options** — use env var toggles (e.g., `CEX_FUSION_MODE`, `CEX_SECTION_BOOST`) or file-level reverts (`scripts/ab_test_m20.py` pattern). Never test multiple changes simultaneously.

### Test suite growth

Each milestone MUST grow the test suite:
- **Unit tests**: Cover the specific fix logic (e.g., regex patterns, scoring functions, routing decisions).
- **Golden QA entries**: Add queries that would have caught the bug being fixed. Include both positive (should match) and negative (should not match) cases.
- **Regression guards**: Add tests that prevent the specific failure mode from recurring.

The test suite is cumulative — tests from M1 through current milestone all run on every commit. Never delete passing tests without justification.

### Eval reports

All eval reports go in `reports/` with naming convention `<milestone>-<variant>.json`. Key reports:
- `baseline-pre-forge.json` — M29 starting point
- `m32-post.json` — current best (MRR=0.6394, PFX=77.78%)
- `m35-post.json` — latest (MRR=0.6434, PFX=77.78%)

### Infrastructure

| File | Purpose |
|------|---------|
| `tests/golden_qa.jsonl` | 206+ query benchmark (TREC 0-3 graded, 5 classification paths, 17 negatives) |
| `tests/eval_answer_pipeline.py` | Full pipeline eval: MRR, nDCG@5, per-path breakdown, --compare |
| `tests/test_canary_qa.py` | CI-fast canary (FTS-only, <10s) |
| `scripts/ab_test_m20.py` | File-level revert A/B pattern |
| `scripts/benchmark_rerankers.py` | Isolated reranker benchmark (fixed candidate set, bootstrap CI) |
| `scripts/benchmark_embeddings.py` | Isolated embedding benchmark (Hit@k, MRR, bootstrap CI) |

## Key Files

- `data/exchanges.yaml` Registry of exchanges/sections, doc seeds, allowlists, and base URLs
- `schema/schema.sql` SQLite schema (pages, endpoints, FTS5, review queue, inventories, coverage_gaps)
- `src/xdocs/cli.py` CLI entrypoint (51 subcommands)
- `src/xdocs/errors.py` `XDocsError` dataclass -- all errors use structured codes (ENOINIT, EBADARG, EFTS5, ESCHEMAVER, etc.)
- `src/xdocs/db.py` SQLite connection helper (WAL mode, FTS5 check, schema versioning via PRAGMA user_version, forward migration support)
- `src/xdocs/urlutil.py` Shared `url_host()` utility (used by 7+ modules for hostname extraction)
- `src/xdocs/store.py` Store init + `require_store_db` helper (shared across all modules)
- `src/xdocs/lock.py` File-based exclusive write lock (all DB writes go through this)
- `src/xdocs/inventory.py` Inventory generation (sitemaps + deterministic link-follow fallback)
- `src/xdocs/inventory_fetch.py` Fetch + persist inventory entries (--resume, --concurrency with per-domain rate limiting, 3-phase locking)
- `src/xdocs/playwrightfetch.py` Playwright fetch wrapper (JS-rendered docs fallback)
- `src/xdocs/sync.py` Cron-friendly orchestration (inventory + fetch, --resume, --concurrency)
- `src/xdocs/endpoints.py` Endpoint CRUD (`get_endpoint`, `list_endpoints`, `search_endpoints`), FTS search, review queue management
- `src/xdocs/openapi_import.py` OpenAPI/Swagger spec import into endpoint DB
- `src/xdocs/postman_import.py` Postman collection import into endpoint DB
- `src/xdocs/report.py` Markdown report rendering for sync JSON artifacts + store-report command
- `src/xdocs/lookup.py` Endpoint path lookup (SQL LIKE) and error code search (FTS5 across endpoints + pages)
- `src/xdocs/classify.py` Deterministic input classification (error_message, endpoint_path, request_payload, code_snippet, question)
- `src/xdocs/answer.py` Cite-only answer assembly with endpoint integration + semantic fallback (generalized to all 46 exchanges; Binance has richer heuristics)
- `data/error_code_patterns.yaml` Exchange-specific error code formats and common codes (used by classify + xdocs-query skill)
- `src/xdocs/quality.py` Content quality gate (empty/thin/tiny_html detection, integrated into post-sync), source validation (`classify_source_type`, `detect_content_flags`)
- `src/xdocs/semantic.py` LanceDB semantic search (build_index, semantic_search, fts5_search) — optional `[semantic]` dependency
- `src/xdocs/fsck.py` Store consistency checker (DB/file mismatches, orphan detection)
- `src/xdocs/url_sanitize.py` URL sanitization filter (template artifacts, CDN paths, bad schemes)
- `src/xdocs/extraction_verify.py` Structural extraction verification (HTML vs markdown quality scoring)
- `src/xdocs/sitemap_validate.py` Sitemap health checks + cross-validation against store
- `src/xdocs/nav_extract.py` Nav extraction via agent-browser + HTTP/BS4 fallback
- `src/xdocs/crawl_targets.py` Multi-method URL discovery (sitemap + link-follow + nav + Wayback CDX)
- `src/xdocs/live_validate.py` Live site nav comparison against store
- `src/xdocs/crawl_coverage.py` Coverage audit + gap backfill
- `src/xdocs/link_check.py` Stored page URL reachability checks (HEAD requests)
- `src/xdocs/ccxt_xref.py` CCXT cross-reference validation against endpoint DB
- `src/xdocs/embeddings.py` Embedding backend selection (Jina MLX primary, SentenceTransformers fallback)
- `src/xdocs/chunker.py` Heading-aware markdown chunking (mistune AST) for semantic index
- `src/xdocs/fts_util.py` Shared FTS5 query utilities (sanitize, build, extract terms, BM25 normalization, RRF fusion, position-aware blend, strong-signal shortcut)
- `src/xdocs/reranker.py` Backend-agnostic reranking (auto | cross-encoder | qwen3 | jina-v3 | jina-v3-mlx | flashrank). OS auto-detection: macOS+MLX→jina-v3-mlx→jina-v3→cross-encoder→flashrank, Linux→jina-v3→cross-encoder→flashrank. M10 benchmark (163 queries): Jina v3 MRR=0.556 (+15.6% over MiniLM, p=0.0014), 218ms/query.
- `scripts/sync_runtime_repo.py` Sync maintainer repo → query-only runtime repo (compaction, strip-maintenance, manifest)
- `src/xdocs/changelog.py` Changelog extraction from stored pages (extract-changelogs, list-changelogs) — supports ISO + prose date formats, 18 exchanges, 1,255 entries
- `src/xdocs/changelog_classify.py` Changelog impact classification (8-category regex taxonomy: endpoint_removed, breaking_change, deprecated, rate_limit, parameter, added, field_added, informational)
- `src/xdocs/audit.py` Consolidated audit runner (combines quality, coverage, crawl-coverage, link-check)
- `src/xdocs/coverage.py` Endpoint field_status coverage aggregation
- `src/xdocs/coverage_gaps.py` Endpoint completeness gap computation + persistence
- `src/xdocs/stale_citations.py` Stale citation detection (endpoint citations vs current page content)
- `src/xdocs/resolve_docs_urls.py` Docs URL resolution for spec-imported endpoints (link-endpoints command)
- `src/xdocs/asyncapi_import.py` AsyncAPI spec import (stub — no CEX specs implemented yet)
- `src/xdocs/ingest_page.py` Manual page ingestion from browser capture (HTML or markdown input)
- `src/xdocs/validate.py` Golden QA retrieval validation (exact/prefix/domain matching)
- `src/xdocs/registry.py` Registry loader (parses data/exchanges.yaml into typed objects)
- `src/xdocs/page_store.py` Page storage operations (upsert, markdown extraction, word count)
- `skills/xdocs-maintain/SKILL.md` Maintainer workflow skill (full sync, spec imports, validation, doc updates)
- `skills/xdocs-query/SKILL.md` Query/answer agent skill (classification → search → cite-only answer)
- `skills/xdocs-discovery/SKILL.md` Exhaustive crawl target discovery skill (new exchange onboarding)
- `skills/xdocs-qa/SKILL.md` QA gap finder skill (iterative testing loop, runtime repo)
- `skills/xdocs-bugreport/SKILL.md` Bug report generation skill (structured, objective, shareable)
- `skills/xdocs-triage/SKILL.md` Bug report triage and fix skill (reproduce, challenge, implement)

## Gotchas

- `cex-docs/`, `cex-docs-*/`, and `poc-binance-full/` are local data and must never be committed (gitignored).
- CLI JSON is printed at the end of a command; if you redirect stdout to a file, it may stay empty until completion.
- Default render mode is `auto` (HTTP first, Playwright fallback for pages <50 words or HTTP errors). Use `--render http` to skip Playwright.
- **FTS5 required**: SQLite must be built with FTS5 support; the app raises `EFTS5` at init if missing. macOS system Python and Homebrew Python both include FTS5. Some minimal Docker images do not.
- **Playwright required for default sync**: `auto` render mode needs Playwright. Install with `uv pip install -e ".[playwright]"`. Without it, thin/JS-rendered pages are recorded as errors instead of crashing the sync.
- **Semantic search model**: `jina-embeddings-v5-text-small` (1024 dims, Qwen3-0.6B-Base backbone). Upgraded from v5-text-nano (768 dims, EuroBERT backbone) — +27.3% MRR, +22.3% Hit@5 on 163-query benchmark. MLX path: Jina's own loader (`jinaai/jina-embeddings-v5-text-small-mlx`), not mlx-embeddings. Query-only install: `uv pip install -e ".[semantic-query]"` (Mac). Full install: `uv pip install -e ".[semantic]"` (Mac or PC/CUDA). Primary build: PC (CUDA via sentence-transformers). Fallback build: MacBook (Jina MLX loader). Env overrides: `CEX_EMBEDDING_BACKEND` (auto|jina-mlx|sentence-transformers), `CEX_EMBEDDING_MODEL` (jina-mlx repo ID), `CEX_EMBEDDING_FALLBACK_MODEL` (ST model name), `CEX_JINA_MLX_REVISION` (pin HF revision). First run downloads model from HuggingFace (cached after that). LanceDB index: 334,935 rows, 1024d, 2.3 GB compacted, stored at `cex-docs/lancedb-index/`. Build: ~100 min at batch_size=64 on RTX 4070 Ti SUPER (CUDA). Extreme pages (>50K words) may OOM at batch_size=64 — use incremental batch_size=1 to add them. batch_size=16 is 15x slower — avoid.
- **LanceDB compaction**: Use `table.optimize(cleanup_older_than=timedelta(days=0))` not the deprecated `compact_files()` + `cleanup_old_versions()`. The CLI `compact-index` command wraps this. Run periodically after large index builds to reduce fragment count and disk usage.
- **Write lock contention**: all DB writes acquire an exclusive file lock (`cex-docs/db/.write.lock`). `--lock-timeout-s` (default 10s) controls how long a command waits. Concurrent writers will queue; long fetches hold the lock in short bursts (3-phase locking in `inventory_fetch.py`).
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

Phase: API Assistant Tool v2. 46 exchanges (29 CEX, 16 DEX, 1 ref), 78 sections in registry. Synced: **17,422 pages, 18.05M words, 5,034 structured endpoints**. Store is at `cex-docs/`. Pipeline: **MRR=0.6368, PFX=78.31%, 672 tests**. Schema: v7.

Latest:

- **M39 gap fixes + source validation (2026-03-24)** — Gemini 71 endpoints (rest.yaml), BingX 47 AI skill pages, CCXT 110 raw markdown files (665K words), Bluefin 40 reference pages, Bitstamp WebSocket docs, Bitget 7/8 thin pages fixed, Kraken thin 30→11, Paradex 404 cleaned. Schema v7 adds `source_type` and `content_flags` columns. `_parse_openapi` handles YAML tabs. `classify_source_type()` and `detect_content_flags()` in quality.py.
- **M36-M38 pipeline health (2026-03-22)** — curl-cffi as default HTTP client (TLS fingerprint bypass), parallel sync (4 concurrent), changelog intelligence (18 exchanges, 1,255 entries), stale lock cleanup, review queue auto-resolve.
- **M29-M35 query optimization (2026-03-19–20)** — Batch bug fixes, FAQ URL demotion, CC fusion A/B (rejected), nav chrome detection, classification improvements. MRR 0.635→0.644.

Research decisions (archived in docs/research/): LanceDB validated, LlamaIndex rejected, Jina v3 reranker (MRR=0.556), jina-v5-text-small embeddings (+12.5% Hit@5), RRF k=60 fusion, 206-query golden QA with TREC graded relevance.

Next (see TODO.md): Semantic index rebuild (new pages not yet indexed). Score-aware fusion (TopK benchmark +4.58% nDCG@10 on BEIR). Structured endpoint extraction from crawled docs.

## Source Validation

Pages in the store have `source_type` and `content_flags` columns (schema v7).

**Source types** (trust hierarchy, highest first):
1. `official_docs` — exchange's own documentation site
2. `spec` — OpenAPI/Swagger/AsyncAPI spec files
3. `github_repo` — GitHub-hosted docs (e.g., BingX api-ai-skills)
4. `ccxt_ref` — CCXT community documentation (docs.ccxt.com raw markdown)
5. `llms_txt` — LLM discovery files (auto-generated by ReadMe.io/GitBook)

**Content flags** (comma-separated, empty string = clean):
- `empty` — word_count = 0
- `thin` — word_count < 50
- `nav_chrome` — page contains only navigation links, not documentation content
- `spa_shell` — page is an empty SPA wrapper (JS not rendered)

After ingesting alternative sources (GitHub repos, CCXT, llms.txt), cross-reference key claims against official docs. Endpoints from non-official sources should be flagged as unverified until confirmed.

## Non-Goals / Safety

- No hosted service.
- No real API key storage.
- No authenticated trading calls or trading logic.

## Platform-Specific: Claude Code

When compacting, preserve:

- The current forge pipeline stage and substep
- All file paths from the last 10 tool calls
- All test results and their pass/fail status
- Any error messages being actively debugged
- The exact milestone name and number from FORGE-STATUS.md

After any context compaction, re-read these files immediately:

1. FORGE-HANDOFF.md — what you were doing when compaction occurred
2. FORGE-STATUS.md — current milestone and phase
3. TODO.md — task checklist with completion status
4. FORGE-MEMORY.md — cross-session learnings

Then continue from the point described in FORGE-HANDOFF.md "What's In Progress".
