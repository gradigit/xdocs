# M3 Baseline Metrics — 2026-03-06

## Evaluation Setup
- Golden QA set: `tests/golden_qa.jsonl` (50 queries across 20 exchanges)
- Tags: keyword, auth, trading, rate-limit, websocket, error-codes, margin, futures, overview, market-data, withdrawal, position, options, copy-trading, spot, perpetual
- Store: 10,718 pages, 16.72M words, 4,872 endpoints, 46 exchanges
- Schema: v5 (porter stemming + BM25 column weights)

## Semantic Search Baseline (validate-retrieval, k=5)

### With reranking (FlashRank)
| Metric | Value |
|--------|-------|
| Exact hit@5 | 68.00% |
| Exact recall@5 | 64.33% |
| Prefix hit@5 | 80.00% |
| Prefix recall@5 | 77.67% |
| Domain hit@5 | 100.00% |
| Domain recall@5 | 100.00% |

### Without reranking
| Metric | Value |
|--------|-------|
| Exact hit@5 | 70.00% |
| Prefix hit@5 | 82.00% |
| Domain hit@5 | 100.00% |

Note: Reranking slightly *decreases* hit rate (70%→68%) because it sometimes reorders good FTS hits below vector results. The reranker is more valuable for natural language queries where FTS keyword matching is weak.

## Answer Pipeline Baseline (eval_answer_pipeline, full pipeline)
| Metric | Value |
|--------|-------|
| OK rate | 100.00% |
| URL hit@all | 70.00% |
| Prefix hit@all | 74.00% |
| Domain hit@all | 100.00% |
| Mean MRR | 0.554 |
| Mean claims | 6.9 |
| Mean latency | 3.26s |

### Prefix Misses (13/50 = 26%)
1. **Binance spot queries (5)**: "account balance", "rate limits", "place order", "API key permissions", "websocket streams" — FTS returns testnet/websocket-api variants instead of the REST API page. Root cause: Binance has many similar pages across REST/WebSocket/Testnet.
2. **Binance cross-section (2)**: "margin account", "options trading" — queries match derivatives sections instead of margin_trading section. Root cause: section routing uses seed URL prefix which doesn't span cross-section topics.
3. **KuCoin account balance (1)**: Returns OpenAPI spec URLs instead of docs pages. Root cause: spec-imported endpoints cite the raw spec JSON URL.
4. **Bitget copy trading (1)**: Returns sub-pages instead of intro page. Root cause: intro page not in FTS results; sub-pages rank higher.
5. **Upbit market info (1)**: Returns changelog/global-docs instead of reference. Root cause: `docs.upbit.com/reference` is Korean, query is English.
6. **Coinbase (2)**: Returns spec URLs or derivative docs instead of exchange docs. Root cause: multiple Coinbase sections with overlapping content.
7. **Bithumb auth (1)**: Actually a near-match — URLs are percent-encoded Korean vs UTF-8 in golden QA. Would pass with URL normalization.
8. **Bitget broker errors (1)**: Returns common docs instead of broker error codes. Root cause: "error" in query doesn't route to broker-specific error page.

### Quality Issues Identified
1. **Percent-encoding mismatch**: Bithumb URLs in store are percent-encoded, golden QA has UTF-8. The `_norm()` function in `validate.py` does `unquote()` but the answer pipeline doesn't normalize URLs the same way.
2. **Spec URL citations**: KuCoin/Coinbase endpoints cite raw GitHub spec URLs instead of official docs pages.
3. **Binance section disambiguation**: Queries about "Binance spot" often return results from derivatives, testnet, or websocket-api sections.
4. **Reranker diminishing returns**: FlashRank reranking provides marginal value for keyword-heavy queries. Its value is higher for natural language queries not in the current QA set.

## Test Count
369 tests (367 from M2 + 2 new FTS sanitization tests for `?` and URL query params).

## Bug Found During Evaluation
- **FTS5 `?` syntax error**: `sanitize_fts_query` didn't quote `?`, `=`, `&` characters. BitMart Postman endpoints have `?symbol=BTCUSDT` in paths, causing crashes when those paths are used in FTS queries. Fixed by extending the special character regex.
