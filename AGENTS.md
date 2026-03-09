# CEX API Docs — AGENTS Guide

## Project Summary

`cex-api-docs` is a local-only, cite-only CEX API documentation knowledge base.
It crawls official exchange docs, stores/indexes them (SQLite FTS5 + optional LanceDB), and answers endpoint/rate-limit/permission questions with strict provenance.

## Agent Rules

- **Cite-only**: never assert unsupported facts.
- If sources are insufficient, return `unknown`, `undocumented`, or `conflict`.
- **Exhaustive coverage**: no pages missing, no content missing, no endpoints missing, no partial data. If a crawl method fails, escalate through the cascade. A 0-page section is a bug. See CLAUDE.md for the full mandate.
- Keep deterministic behavior in crawling, storage, indexing, and query paths.
- Prefer machine-readable JSON command output.

## Local Skill Mapping (project)

If a user asks for `cex-api-query` skill, treat it as a local project skill and run:

- Open and follow `.claude/skills/cex-api-query/SKILL.md`
- Use `--docs-dir ./cex-docs` unless user explicitly asks for another store
- Execute the classify-first routing flow from that skill
- For natural-language questions, prefer `semantic-search --mode hybrid --rerank-policy auto` first, then targeted endpoint/page fetch
- Keep retrieval bounded (avoid broad markdown scans unless retrieval fails)

If this local file is missing, fall back to equivalent direct CLI workflow (`classify` → `lookup-endpoint` / `search-error` / `search-endpoints` / `search-pages` / `answer`) and state that fallback explicitly.

## Environment

- Python: **3.11+**
- Use `python3` (not `python`)
- Preferred shell for user-facing commands: `fish`

Quick setup:

```bash
python3 -m venv .venv
source .venv/bin/activate  # or: source .venv/bin/activate.fish
pip install -e ".[dev,semantic]"
uv run --extra dev python3 -m pytest
```

## Core Commands

```bash
# Initialize store
cex-api-docs init --docs-dir ./cex-docs

# Validate registry/base URLs
cex-api-docs validate-registry
cex-api-docs validate-base-urls

# Deterministic sync
cex-api-docs sync --docs-dir ./cex-docs
cex-api-docs sync --docs-dir ./cex-docs --resume --concurrency 4

# Search + answers
cex-api-docs search-pages "rate limit OR weight" --docs-dir ./cex-docs
cex-api-docs answer "..." --docs-dir ./cex-docs

# Endpoint import/search/lookup
cex-api-docs import-openapi --exchange <exchange> --section <section> --url <spec-url> --docs-dir ./cex-docs
cex-api-docs import-postman --exchange <exchange> --section <section> --url <collection-url> --docs-dir ./cex-docs
cex-api-docs search-endpoints "..." --docs-dir ./cex-docs
cex-api-docs lookup-endpoint /api/v5/account/balance --method GET --exchange okx --docs-dir ./cex-docs
cex-api-docs search-error -- -1002 --exchange binance --docs-dir ./cex-docs
cex-api-docs classify "POST /sapi/v1/convert/getQuote" --docs-dir ./cex-docs
cex-api-docs link-endpoints --docs-dir ./cex-docs

# Semantic retrieval (optional extras)
cex-api-docs build-index --docs-dir ./cex-docs
cex-api-docs compact-index --docs-dir ./cex-docs
cex-api-docs semantic-search "..." --docs-dir ./cex-docs --mode hybrid --rerank-policy auto
cex-api-docs validate-retrieval --qa-file tests/golden_qa.jsonl --limit 5 --docs-dir ./cex-docs

# Quality / coverage
cex-api-docs quality-check --docs-dir ./cex-docs
cex-api-docs coverage --docs-dir ./cex-docs
cex-api-docs detect-stale-citations --docs-dir ./cex-docs
cex-api-docs extract-changelogs --docs-dir ./cex-docs

# Crawl validation
cex-api-docs sanitize-check --docs-dir ./cex-docs
cex-api-docs validate-crawl-targets --exchange <exchange> --docs-dir ./cex-docs
cex-api-docs crawl-coverage --exchange <exchange> --docs-dir ./cex-docs
cex-api-docs check-links --sample 50 --docs-dir ./cex-docs

# Maintenance
cex-api-docs migrate-schema --docs-dir ./cex-docs
cex-api-docs fts-rebuild --docs-dir ./cex-docs
cex-api-docs fsck --docs-dir ./cex-docs
cex-api-docs store-report --docs-dir ./cex-docs

# CCXT cross-reference
cex-api-docs ccxt-xref --docs-dir ./cex-docs
```

## Code Areas

- `src/cex_api_docs/cli.py` — CLI entrypoint (51 subcommands)
- `src/cex_api_docs/sync.py` — inventory + fetch orchestration
- `src/cex_api_docs/endpoints.py` — endpoint CRUD, FTS search, review queue
- `src/cex_api_docs/openapi_import.py` — OpenAPI/Swagger spec import
- `src/cex_api_docs/postman_import.py` — Postman collection import
- `src/cex_api_docs/semantic.py` — semantic index/search
- `src/cex_api_docs/answer.py` — cite-only answer assembly
- `src/cex_api_docs/lookup.py` — endpoint path lookup + error code search
- `src/cex_api_docs/classify.py` — input classification
- `src/cex_api_docs/crawl_targets.py` — multi-method URL discovery
- `src/cex_api_docs/crawl_coverage.py` — coverage audit + gap backfill
- `src/cex_api_docs/ccxt_xref.py` — CCXT cross-reference validation
- `src/cex_api_docs/quality.py` — content quality gate
- `src/cex_api_docs/changelog.py` — changelog extraction for drift detection
- `src/cex_api_docs/validate.py` — golden QA retrieval validation
- `src/cex_api_docs/embeddings.py` — embedding backend selection (MLX/SentenceTransformers)
- `src/cex_api_docs/reranker.py` — cross-encoder reranking
- `schema/schema.sql` — canonical DB schema (v6)
- `data/exchanges.yaml` — exchange/section registry (46 exchanges, 78 sections)
- `.claude/skills/cex-api-docs/SKILL.md` — maintainer workflow skill
- `.claude/skills/cex-api-query/SKILL.md` — query/answer agent skill
- `.claude/skills/cex-discovery/SKILL.md` — exhaustive crawl target discovery skill

## Current Context (from latest handoff)

- Crawl validation pipeline implemented (10 phases, 25+ modules, 491 tests).
- Semantic index: jina-embeddings-v5-text-small (1024 dims, Jina MLX / sentence-transformers) with heading-context-injected mistune chunking.
- 10,724 pages in store across 46 exchanges (29 CEX, 16 DEX, 1 ref), 16.73M words, 4,872 endpoints, 78 sections.
- Crawl targets bible v3 (`docs/crawl-targets-bible.md`) — 46 registered exchanges, all 8 missing exchanges now registered.
- 11 new exchanges: MEXC (114ep), BingX, Deribit (173ep), Backpack (22ep), CoinEx, WOO X, Phemex, Gemini, Orderly (203ep), Bluefin, Nado.
- CCXT cross-reference: 33 exchanges mapped (korbit/orderly/bluefin/nado = None).
- Spec imports: KuCoin (250), WhiteBIT (137), BitMart (94), Coinbase Prime (97) + Exchange (45), Paradex (97), Lighter (58), dYdX (83), MEXC (114 Postman), Deribit (173), Backpack (22), Orderly (203).
- Multi-method crawl cascade: pipeline uses `--render auto` (requests + Playwright). Validation uses crawl4ai (primary), cloudscraper, headed browser, Agent Browser.

## Gotchas

- `cex-docs/` and derived local data are gitignored and should not be committed.
- Semantic features require optional extras (`[semantic]` / `[reranker]`).
- **Semantic search model**: jina-embeddings-v5-text-small (1024 dims). MLX path: `jinaai/jina-embeddings-v5-text-small-mlx`. Fallback: SentenceTransformers. Env overrides: `CEX_EMBEDDING_BACKEND`, `CEX_EMBEDDING_MODEL`, `CEX_JINA_MLX_REVISION`.
- **Reranker**: Backend-agnostic (CEX_RERANKER_BACKEND). macOS auto-selects jina-v3-mlx, Linux auto-selects cross-encoder then flashrank.
- `crawl` is legacy/deprecated; prefer `sync` (or `inventory` + `fetch-inventory`).
- **Write lock contention**: all DB writes acquire an exclusive file lock (`cex-docs/db/.write.lock`). `--lock-timeout-s` (default 10s) controls how long a command waits.
- **Single-page doc exchanges**: OKX, Gate.io, HTX, Crypto.com, Bitstamp, Korbit serve entire API reference from 1-4 HTML pages. Don't treat low page counts as errors.
- **Gate.io rate-limits aggressively**: After syncing, HTTP requests may return 403.

## Current Phase

Phase: API Assistant Tool v2. 46 exchanges (29 CEX, 16 DEX, 1 ref), 78 sections in registry. Synced: **10,724 pages, 16.73M words, 4,872 structured endpoints**. Store is at `cex-docs/`.

Next: Periodic CCXT docs refresh, changelog drift detection. Domain synonym/acronym expansion for query improvement.

## Non-Goals / Safety

- No hosted service.
- No real API key storage.
- No authenticated trading calls or trading logic.
