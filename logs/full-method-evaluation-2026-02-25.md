# Full Retrieval Method Evaluation

## 1) Golden QA retrieval benchmark (20 queries, top-5)

| Method | Hit@5 | Mean Recall@5 | Mean latency/query |
|---|---:|---:|---:|
| vector_no_rerank | 0.40 | 0.40 | 0.739s |
| hybrid_no_rerank | 0.35 | 0.35 | 0.204s |
| fts_no_rerank | 0.30 | 0.30 | 0.170s |
| sqlite_fts5_pages | 0.20 | 0.20 | 0.011s |

## 2) Reranker impact (hybrid mode)

- no-rerank: hit=0.35, recall=0.35, runtime=7.19s
- rerank: hit=0.35, recall=0.35, runtime=68.25s
- runtime multiplier (rerank/no-rerank): 9.49x
- ranking changed on 16/20 queries, but hard-hit improved on 0 and regressed on 0.

## 3) Agent stress-turn telemetry (A/B real runs)

See dedicated A/B report:

- A/B file: logs/ab-retrieval-benchmark-focused-2026-02-24.md

Key takeaways from that file:

- Both runs used cex-api-query skill, but neither executed semantic-search/rerank.
- Post-update run had lower context pressure (65.1%/70.9% vs 89.2%/94.5%).
- Retrieval remained FTS/raw-scan heavy.

## 4) Staged retrieval smoke checks for the 6-exchange incident prompt

| Exchange | Semantic hits | Endpoint-template hits |
|---|---:|---:|
| binance | 2 | 5 |
| okx | 1 | 5 |
| bybit | 0 | 2 |
| bitget | 0 | 5 |
| upbit | 0 | 1 |
| bithumb | 0 | 1 |

Observation: semantic alone missed several exchanges; exchange-specific endpoint keyword templates recovered them.

## 5) Decision

Best method for this project is a staged hybrid: semantic-first candidate gathering (hybrid, no-rerank default), then deterministic endpoint/page verification with exchange-specific fallback templates.
