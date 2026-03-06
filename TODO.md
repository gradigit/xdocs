# TODO — Production-Ready Query Pipeline

## Goal
Research and fix all quality issues in runtime query + maintenance pipelines. Evaluate rerankers, study qmd architecture, run thorough evaluations to get production-ready.

## Milestones

### M1: Research ✓
Research-only. No code changes.

- [x] 1a. Diagnose all runtime query quality issues → 18 issues found (2 CRITICAL, 6 HIGH, 6 MEDIUM, 4 LOW)
- [x] 1b. Research reranker landscape → FlashRank + ms-marco-MiniLM-L-12-v2 (34MB, ~80ms/20docs, no PyTorch)
- [x] 1c. Clone and study qmd → 9.7K line TypeScript, RRF fusion, Qwen3-Reranker, scored chunking, BM25 normalization
- [x] 1d. FTS5 best practices → porter stemming, BM25 column weights, NEAR queries, snippet post-processing
- [x] 1e. Synthesize into implementation plan → 4-phase plan in architect/research/synthesis-implementation-plan.md

**Artifacts**: architect/research/{query-pipeline-quality,reranker-survey,qmd-analysis,fts5-best-practices,synthesis-implementation-plan}.md

### M2: Build — Answer Pipeline Quality Fixes ✓
4 phases, dependency-ordered. All complete, in REVIEW phase.

**Phase 1: Foundation** ✓
- [x] 2.1a. Create shared fts_util.py (consolidate sanitization, fix double-quote escaping)
- [x] 2.1b. Fix search_text: values-only plain text, no JSON keys (CRITICAL — Issue 2)
- [x] 2.1c. Add porter stemming + BM25 column weights to FTS5 tables
- [x] 2.1d. Switch ORDER BY bm25() → ORDER BY rank (7 call sites across 5 files)

**Phase 2: Answer Pipeline Routing** ✓
- [x] 2.2a. Integrate classify.py into answer_question() as augmentation (CRITICAL — Issue 1)
- [x] 2.2b. Fix error code search: pages first, boost by URL pattern (HIGH — Issues 8,9)
- [x] 2.2c. Fix seed URL prefix filtering → directory prefix + domain fallback (HIGH — Issues 4,5)
- [x] 2.2d. Fix OR→AND for 3+ term FTS, reduce claim limit to 10 (HIGH — Issue 3)

**Phase 3: Excerpt & Polish** ✓
- [x] 2.3a. Fix excerpt boundary snapping + zero-width char stripping (MEDIUM — Issues 6,12,15)
- [x] 2.3b. Fix exchange detection word boundaries (MEDIUM — Issue 11)
- [x] 2.3c. Log semantic search exceptions properly (MEDIUM — Issue 13)

**Phase 4: Reranker** ✓
- [x] 2.4a. Replace reranker.py with FlashRank backend (ms-marco-MiniLM-L-12-v2, 302ms/20 docs)
- [x] 2.4b. Reranker integrated via semantic.py (existing pipeline)
- [x] 2.4c. Add BM25 score normalization |x|/(1+|x|) in fts_util.py

**Acceptance criteria**:
1. ~~All 8 benchmark queries grade A or B~~ (deferred to M3)
2. [x] Error code "-1002" → definition page first
3. [x] "Bybit websocket" → 6 relevant page claims
4. [x] No FTS5 crashes on hyphens
5. [x] Reranker on Linux CPU <500ms/20 candidates (302ms)
6. [x] Clean excerpt boundaries
7. [x] 367 tests pass (346 + 21 new)
8. ~~Golden QA ≥80% relevance@3~~ (deferred to M3)

### M3: Evaluation — Production Readiness
- [x] 3a. Build golden QA evaluation set (40+ questions across exchanges, query types) — 50 queries, 20 exchanges
- [x] 3b. Run before/after comparison on all pipeline changes — semantic + answer pipeline baselines
- [x] 3c. Establish quality baseline metrics (relevance@k, MRR, citation accuracy) — see architect/review-findings/m3-baseline-metrics.md
- [x] 3d. Document quality standards and regression test — eval_answer_pipeline.py + validate-retrieval CLI

**Acceptance criteria**: Evaluation suite exists, baseline metrics recorded, no regressions from M2.

**Results**:
- Semantic search: 68% exact hit@5, 80% prefix hit@5, 100% domain hit@5
- Answer pipeline: 100% OK rate, 70% URL hit, 74% prefix hit, MRR=0.554
- 369 tests pass (367 M2 + 2 new FTS sanitization)
- Bug found + fixed: FTS5 `?` syntax error on BitMart Postman paths
