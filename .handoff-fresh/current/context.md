# Context — CEX API Docs

**Generated**: 2026-03-12

## Project Purpose

Local-only, cite-only CEX API documentation knowledge base. Crawls official exchange docs, stores/indexes via SQLite FTS5 + LanceDB vectors, and enables agents to answer endpoint, rate limit, and permission questions with strict provenance. No unsupported claims — returns `unknown`/`undocumented`/`conflict` when sources are insufficient.

## Two-Repo Architecture

| | Maintainer | Runtime |
|---|---|---|
| Path | `/home/lechat/Projects/cex-api-docs` | `/home/lechat/Projects/cex-api-docs-runtime` |
| Remote | `github.com/henryaxis/cex-api-docs` | `github.com/henryaxis/cex-api-docs-runtime` |
| Platform | Linux (CUDA, full dev) | macOS (MLX, query-only) |
| Install | `uv pip install -e ".[dev,semantic]"` | `uv pip install -e .` |
| Purpose | Crawl, sync, index, test, benchmark | Query CLI + prebuilt snapshot |

**Every push to maintainer MUST be followed by runtime sync + push.**

## Data Pipeline

Registry (`exchanges.yaml`) → Inventory (sitemaps/link-follow) → Fetch (HTTP/Playwright) → Store (SQLite WAL + FTS5) → Endpoint Ingest (OpenAPI/Postman) → Semantic Index (LanceDB vectors) → Query/Answer (classify → search → cite)

## Key Technical Decisions

1. **Embedding**: jina-v5-text-small (1024d) over v5-nano (768d) — +27.3% MRR, +22.3% Hit@5
2. **Reranker**: Jina v3 over CrossEncoder MiniLM — +15.6% MRR (p=0.0014), 41% faster
3. **Fusion**: RRF k=60 default. CC tested neutral, kept opt-in (`CEX_FUSION_MODE=cc`)
4. **FTS5**: Porter stemming, BM25 column weights, AND-first with OR fallback
5. **Direct routing**: High-confidence (>=0.7) endpoint_path/error_message bypass generic search
6. **Position-aware blend**: 75/25→60/40→40/60 retrieval/reranker weights by rank position

## QA Infrastructure

- **Golden QA**: 206 queries across 37 exchanges (tests/golden_qa.jsonl)
- **Eval script**: `tests/eval_answer_pipeline.py` — MRR, nDCG@5, per-path breakdown
- **Canary tests**: `tests/test_canary_qa.py` — 17 FTS-only queries for CI-fast
- **Gapfinder skill**: `skills/cex-qa-gapfinder/SKILL.md` v2.2.0 — blind mode, adversarial, golden QA cross-check
- **10-run batch QA**: Ran on runtime repo, 340 tests, validated all known bugs

## Skills (3 active)

| Skill | Purpose | Version |
|-------|---------|---------|
| `cex-api-docs` | Maintainer workflow (sync, import, validate) | in SKILL.md |
| `cex-api-query` | Query/answer (classify → search → cite) | v2.11.0 |
| `cex-qa-gapfinder` | QA discovery (blind mode, adversarial, regression) | v2.2.0 |

Skills are canonical in `skills/`, symlinked to `.claude/skills/` and `.agents/skills/`. Real copies in runtime repo via `sync_runtime_repo.py`.

## Known Limitations

- 11 store-backed exchanges unreachable through `answer()` exchange detection (registry has 24 IDs, store has 28)
- Code snippets with numeric literals misclassified as error_message
- Direct-routed answers lack excerpts (BUG-18)
- Nav chrome bleeds into excerpts on some exchanges (Binance, Gate.io, Bithumb)
- Single-page sites (OKX 224K words, Gate.io 256K, HTX 325K) are correct — not bugs
