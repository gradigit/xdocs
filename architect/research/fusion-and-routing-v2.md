# Fusion, Routing & Pipeline Research v2 — March 2026

## Summary

Weighted RRF (5-line change) + section-metadata boosting (10% nDCG lift in benchmarks) are the highest-impact improvements. Adaptive-K is single-retriever only but gap-detection could improve BM25 shortcut. CC (convex combination) outperforms RRF with ~40 labeled queries but is less robust zero-shot. Pipeline architecture is already state-of-the-art. HHEM-2.1-Open is the best non-LLM faithfulness metric.

## Weighted RRF

Formula: `weight * 1/(rank + k)` per retriever. Released in Elasticsearch Sept 2025.

Query-type-dependent weights:
- `question`: FTS5=0.8, vector=1.2 (favor semantic)
- `endpoint_path`: FTS5=1.5, vector=0.5 (favor exact keyword)
- `error_message`: FTS5=1.3, vector=0.7 (keyword with some semantic)
- `code_snippet`: FTS5=0.7, vector=1.3 (favor semantic)
- `request_payload`: FTS5=1.0, vector=1.0 (balanced)

## Section-Metadata Boosting

Post-fusion: if URL matches detected section prefix, apply 1.3-1.5x score multiplier.
WANDS benchmark: 10% nDCG lift (0.750 to 0.842) from field-specific boosting over plain RRF.

## Testnet URL Suppression

38 Binance testnet pages (115K words, 90.7% identical to mainnet).
BM25 scores differ by only 0.003-0.01 — testnet ranks tied with mainnet.
Fix: `_is_testnet_url(url)` filter in `_search_pages()`, suppress unless query contains "testnet".
Also affects: 95 Paradex testnet pages (different pattern — parallel environments).

## Adaptive-K

Single-retriever cutoff via gap detection in sorted cosine similarity scores.
Not applicable to multi-source fusion.
Adaptable idea: replace hardcoded BM25 shortcut thresholds (min_top_score=0.7, min_gap=0.3) with dynamic gap analysis on BM25 score distribution.

## Alternative Fusion Methods

| Method | Training Needed | Quality vs RRF | Notes |
|--------|----------------|----------------|-------|
| Weighted RRF | No (domain knowledge) | Better for typed queries | 5-line change |
| CC (Convex Combination) | ~40 labeled queries | +7% nDCG on WANDS | Less robust zero-shot |
| DBSF (Distribution-Based) | Population stats | Unknown vs RRF | 3-sigma normalization |
| SRRF (Scaled RRF) | No | Unknown | Sigmoid-approximated ranks |
| CombMNZ + ZMUV | No | Highest in XMTC study | Task-specific |

## link-endpoints Bugs

Three compounding bugs in resolve_docs_urls.py:
1. FTS5 sanitization: raw path segments → OperationalError for hyphens/underscores (2,192 eps)
2. Postman variable: only strips {{url}}, not {{host}}/{{api_url}} (186 eps)
3. Query strings: not stripped before literal matching (175 eps)

After all fixes + batch run: ~2,804 of 3,410 (82.2%) NULL endpoints resolvable.

## Answer Completeness Metrics

| Metric | Type | Speed | Quality | Notes |
|--------|------|-------|---------|-------|
| HHEM-2.1-Open | T5-based NLI | ~1.5s/2K tokens CPU | Best non-LLM | English only |
| DeBERTa-v3 MNLI | NLI classifier | ~300ms/claim | Good | Standard approach |
| BERTScore | Token similarity | Fast | 59% human alignment | Less accurate |
| ARES | Trained classifier | Fast after training | Good | Needs ~100 annotations |

## Sources

- Elastic Labs: weighted RRF, linear retriever, hybrid search benchmarks
- TOIS 2024: CC vs RRF analysis (arxiv 2210.11934)
- Doug Turnbull: Elasticsearch hybrid search strategies (WANDS benchmark)
- Vectara: HHEM-2.1 blog
- RAGAS docs, ARES GitHub (Stanford)
- ranx library: 24 fusion methods
- Pinecone, NVIDIA: multi-stage pipeline best practices
