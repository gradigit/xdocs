# Score Fusion Patterns for Hybrid Search

## Summary

RRF with k=60 is the industry standard for rank fusion. Replace the current interleaved merge in answer.py with RRF. Add position-aware reranker blending (75/25 at top, 40/60 at bottom). Strong-signal BM25 shortcut for endpoint_path and error_message queries.

## RRF Algorithm

```
RRF_score(d) = SUM over all ranked lists L:  1 / (k + rank(L, d))
```

- k=60 (default): Balances top-rank credit and cross-list consensus
- Lower k (30-50): More weight to top ranks
- Higher k (60+): Favors documents appearing across multiple lists
- Industry consensus: Elasticsearch, LanceDB, OpenSearch all default to k=60
- Zero-calibration: No annotated queries needed (vs linear combination which needs ~300)

**Failure modes**: Disjoint result lists degrade to interleaving. Rank inflation from low-quality results.

## Position-Aware Reranker Blending (from qmd)

| RRF Rank | Retrieval Weight | Reranker Weight | Rationale |
|----------|-----------------|-----------------|-----------|
| 1-3 | 75% | 25% | Top retrieval results are high-confidence |
| 4-10 | 60% | 40% | Balanced contribution |
| 11+ | 40% | 60% | Weak retrieval; trust cross-encoder |

Additional: Top-rank bonus +0.05 for rank 1, +0.02 for ranks 2-3 from original query.

## Strong-Signal BM25 Shortcut

Skip vector search when:
- Normalized BM25 top score >= 0.7
- Gap between #1 and #2 >= 0.3
- Query type is endpoint_path or error_message (NOT question)

Saves ~300ms vector search latency for obvious exact matches.

**Risk**: Only apply for keyword-matchable query types. Natural language questions should always use vector search.

## Top-K Pipeline

| Stage | K | Rationale |
|-------|---|-----------|
| Per-method retrieval (BM25, vector) | 20 each | 40 total candidates |
| Post-RRF fusion | Top 30 | Feed to cross-encoder reranker |
| Final output | 5-10 | User-facing results |

Current `limit * 3` fetch pattern already aligned.

## Score Normalization

Keep `|x|/(1+|x|)` for BM25. RRF eliminates need for cross-method normalization.
For reranker scores: sigmoid or divide by max observed score if blending.

**Key insight**: RRF operates on ranks only, so individual score normalization is unnecessary at the fusion stage.

## Implementation Plan

1. Replace `_search_pages_with_semantic` interleaved merge (answer.py:238-274) with RRF fusion
2. Add `rrf_fuse()` to fts_util.py (or new fusion.py)
3. Add `position_aware_blend()` for post-reranker blending
4. Add `should_skip_vector_search()` for strong-signal shortcut in answer_question()
5. Normalize FlashRank scores via sigmoid before blending

## Sources

- Cormack et al. 2009 SIGIR — RRF paper
- Elasticsearch RRF, Weighted RRF, BEIR benchmarks
- OpenSearch hybrid search best practices
- Weaviate fusion algorithms comparison
- LanceDB hybrid search (uses RRF k=60 internally)
- qmd implementation (position-aware blending, top-rank bonus)
- Adaptive-k (EMNLP 2025) — dynamic K selection
