# State — 2026-03-12T22:00:00+09:00

## Git

- **Branch**: `main`
- **Remote**: `origin https://github.com/henryaxis/cex-api-docs.git`
- **Last commit**: `5687003 fix: FTS5 crash on single quotes in search_pages (BUG-21)`
- **Working tree**: Clean (only git-excluded handoff artifacts)
- **Up to date**: Yes

## Runtime Repo

- **Path**: `/home/lechat/Projects/cex-api-docs-runtime`
- **Remote**: `origin https://github.com/henryaxis/cex-api-docs-runtime`
- **Last commit**: `390fbfc3 sync: fix FTS5 crash on single quotes (BUG-21)`
- **In sync**: Yes

## Active Phase

No active milestone. Last completed: **M22b** (Score Fusion & BUG-14 Fix).
This session was QA evaluation + bug cataloguing (not a forge milestone).

## Pipeline Metrics (post-M22)

| Metric | Value |
|--------|-------|
| MRR | 0.644 |
| nDCG@5 | 1.343 |
| URL hit | 65% |
| Prefix hit | 78% |
| Domain hit | 97% |
| OK rate | 92% |
| Tests | 559 |

## Store

| Metric | Value |
|--------|-------|
| Pages | 10,727 |
| Words | 16.75M |
| Endpoints | 4,963 |
| Exchanges | 46 |
| Sections | 78 |
| Schema | v6 |
| LanceDB | 334,935 rows, 2.3 GB |

## Environment

- **Platform**: Linux WSL2 (Ubuntu)
- **Python**: 3.12
- **venv**: `/home/lechat/Projects/.venv/bin/activate`
- **DB**: `./cex-docs/db/docs.db`
- **Embedding**: jina-embeddings-v5-text-small (1024d, SentenceTransformers on Linux)
- **Reranker**: Jina v3 auto cascade (jina-v3 → cross-encoder → flashrank)
- **Fusion**: RRF k=60 (CC opt-in via `CEX_FUSION_MODE=cc`)

## Blockers

None.
