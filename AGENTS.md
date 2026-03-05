# CEX API Docs — AGENTS Guide

## Project Summary

`cex-api-docs` is a local-only, cite-only CEX API documentation knowledge base.
It crawls official exchange docs, stores/indexes them (SQLite FTS5 + optional LanceDB), and answers endpoint/rate-limit/permission questions with strict provenance.

## Agent Rules

- **Cite-only**: never assert unsupported facts.
- If sources are insufficient, return `unknown`, `undocumented`, or `conflict`.
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

# Endpoint import/search
cex-api-docs import-openapi --exchange <exchange> --section <section> --url <spec-url> --docs-dir ./cex-docs
cex-api-docs import-postman --exchange <exchange> --section <section> --url <collection-url> --docs-dir ./cex-docs
cex-api-docs search-endpoints "..." --docs-dir ./cex-docs

# Semantic retrieval (optional extras)
cex-api-docs build-index --docs-dir ./cex-docs
cex-api-docs semantic-search "..." --docs-dir ./cex-docs --mode hybrid --rerank-policy auto
cex-api-docs validate-retrieval --qa-file tests/golden_qa.jsonl --limit 5 --docs-dir ./cex-docs

# Crawl validation
cex-api-docs sanitize-check --docs-dir ./cex-docs
cex-api-docs validate-crawl-targets --exchange <exchange> --docs-dir ./cex-docs
cex-api-docs crawl-coverage --exchange <exchange> --docs-dir ./cex-docs
cex-api-docs check-links --sample 50 --docs-dir ./cex-docs

# CCXT cross-reference
cex-api-docs ccxt-xref --docs-dir ./cex-docs
```

## Code Areas

- `src/cex_api_docs/semantic.py` — semantic index/search
- `src/cex_api_docs/chunker.py` — heading-aware chunking (mistune AST)
- `src/cex_api_docs/validate.py` — golden QA retrieval validation
- `src/cex_api_docs/reranker.py` — cross-encoder reranking
- `src/cex_api_docs/answer.py` — cite-only answer assembly
- `src/cex_api_docs/cli.py` — CLI entrypoint
- `schema/schema.sql` — canonical DB schema
- `data/exchanges.yaml` — exchange/section registry
- `src/cex_api_docs/crawl_targets.py` — multi-method URL discovery
- `src/cex_api_docs/crawl_coverage.py` — coverage audit + gap backfill
- `src/cex_api_docs/extraction_verify.py` — HTML→markdown quality scoring
- `src/cex_api_docs/link_check.py` — stored page reachability checks
- `src/cex_api_docs/ccxt_xref.py` — CCXT cross-reference validation
- `src/cex_api_docs/embeddings.py` — embedding backend selection (MLX/SentenceTransformers)

## Current Context (from latest handoff)

- Crawl validation pipeline implemented (10 phases, 25+ modules, 319 tests).
- Semantic index: Qwen3-Embedding-0.6B (1024 dims, MLX 4-bit) with heading-context-injected mistune chunking.
- 5,716+ pages in store across 35 exchanges (21 CEX, 13 DEX, 1 ref).
- Golden QA validation: three-level matching (exact/prefix/domain). Baseline: 68% exact, 82% prefix, 98% domain.
- Optional reranking with `jina-reranker-v3-mlx`.

## Gotchas

- `cex-docs/` and derived local data are gitignored and should not be committed.
- Semantic features require optional extras (`[semantic]` / `[reranker]`).
- **Semantic search model**: Qwen3-Embedding-0.6B (1024 dims) via MLX 4-bit on Apple Silicon. Fallback: SentenceTransformers. Env override: `CEX_EMBEDDING_BACKEND`, `CEX_EMBEDDING_MODEL`.
- `crawl` is legacy/deprecated; prefer `sync` (or `inventory` + `fetch-inventory`).
- **Write lock contention**: all DB writes acquire an exclusive file lock (`cex-docs/db/.write.lock`). `--lock-timeout-s` (default 10s) controls how long a command waits.
- **Single-page doc exchanges**: OKX, Gate.io, HTX, Crypto.com, Bitstamp, Korbit serve entire API reference from 1-4 HTML pages. Don't treat low page counts as errors.
- **Gate.io rate-limits aggressively**: After syncing, HTTP requests may return 403.

## Current Phase

Phase: API Assistant Tool v2. 35 exchanges (21 CEX, 13 DEX, 1 ref), 62 sections in registry. Synced: **5,716+ pages, 7.6M words, ~3,600 structured endpoints**. Store is at `cex-docs/`.

Next: Rebuild semantic index (incremental). Add link validation to maintainer workflow. Periodic CCXT docs refresh. Add Tier 2 DEXes.

## Non-Goals / Safety

- No hosted service.
- No real API key storage.
- No authenticated trading calls or trading logic.
