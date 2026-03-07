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
4 phases, dependency-ordered. All complete.

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

### M3: Evaluation — Production Readiness ✓
- [x] 3a. Build golden QA evaluation set (50 queries, 20 exchanges)
- [x] 3b. Run before/after comparison
- [x] 3c. Establish baselines (semantic: 68% hit@5, answer: 70% URL hit, MRR=0.554)
- [x] 3d. Document quality standards + eval_answer_pipeline.py

---

### M4: Research — Advanced Pipeline & Benchmarks ✓
Research-only. No code changes.

- [x] 4a. Jina HuggingFace model cards → FlashRank confirmed optimal, no Jina model better under constraints
- [x] 4b. Score fusion patterns → RRF k=60, position-aware blending (75/25→40/60), strong-signal shortcut
- [x] 4c. Benchmark suite design → 200 queries, graded relevance (0-3), ranx, two-tier CI
- [x] 4d. Gap analysis → 6 gaps found, Binance disambiguation highest (54% of misses)

**Artifacts**: architect/research/{jina-models,score-fusion,benchmark-design,gap-analysis}.md

### M5: Build — Pipeline Quality Fixes & Score Fusion ✓
Dependency: M4 research complete.

**Phase 1: Gap Fixes (highest impact first)** ✓
- [x] 5.1a. Binance section disambiguation — `_detect_binance_section()` keyword mapping, `_detect_section_keywords()` for generic multi-section, `_directory_prefix()` consistency
- [x] 5.1b. LanceDB exchange filter sanitization — regex validation `r'^[a-z0-9_]+$'` in semantic.py
- [x] 5.1c. Changelog FTS v5→v6 migration — DROP + CREATE changelog_entries_fts with porter stemming
- [x] 5.1d. Spec URL suppression — `_is_spec_url()` check in `_resolve_endpoint_citation_url()`

**Phase 2: Score Fusion** ✓
- [x] 5.2a. Add `rank`/`bm25_score` to `_search_pages` SELECT, normalize with `|x|/(1+|x|)`
- [x] 5.2b. RRF fusion — `rrf_fuse()` in fts_util.py, k=60. Switched to `query_type="vector"` to avoid double-RRF
- [x] 5.2c. Strong-signal BM25 shortcut — `should_skip_vector_search()`, only for `question` query_type_hint
- [x] 5.2d. Position-aware reranker blending — `sigmoid()` + `position_aware_blend()` with 75/25→60/40→40/60 weights

**Phase 3: Query Routing** ✓
- [x] 5.3a. Direct routing for high-confidence endpoint_path (>= 0.7) — `_direct_route()` before Binance/generic branch
- [x] 5.3b. Direct routing for high-confidence error_message (>= 0.7) — same `_direct_route()`
- [x] 5.3c. Selective spec URL suppression — done in Phase 1 (5.1d)
- [x] 5.3d. Eval script — URL `unquote()` normalization in `_norm()`

**Acceptance criteria**:
1. RRF fusion produces better ordering than interleave (A/B on golden QA, nDCG improvement)
2. Strong-signal shortcut saves latency on clear FTS5 matches (endpoint_path, error_message)
3. Prefix hit rate improves from 74% baseline to >= 85%
4. All FTS tables use porter stemming (schema version 6)
5. No raw spec URLs in answer pipeline claims
6. LanceDB exchange filter validates input
7. 369+ tests pass (no regressions)

### M6: Build — Production Benchmark Suite ✓
Dependency: M5 pipeline improvements.

- [x] 6a. Expanded golden QA to 175 queries across 36 exchanges (88 question, 28 endpoint_path, 30 error_message, 14 code_snippet, 15 request_payload)
- [x] 6b. Added graded relevance labels (0/1/2/3 TREC scale) — 70 grade-3, 88 grade-2, 17 grade-0
- [x] 6c. Added 17 negative test cases (defunct exchange, out-of-scope, nonsensical, nonexistent, cross-exchange confusion)
- [x] 6d. Added all 5 classification paths — endpoint_path (28), error_message (30), code_snippet (14), request_payload (15)
- [x] 6e. CI-fast canary: 17 canary queries (test_canary_qa.py), FTS-only capable, covers question + endpoint_path + error_message + negatives
- [x] 6f. Eval script with nDCG@5, per-classification-path breakdown, negative FP rate
- [x] 6g. Pre/post comparison with --compare flag, threshold alerts (5% warning, 10% hard fail)
- [ ] 6h. Citation accuracy scoring (deferred — needs `excerpt` validation infrastructure)

**Acceptance criteria**:
1. 150+ queries across 30+ exchanges with proportionate coverage
2. All 5 classification paths represented (15+ queries each)
3. CI-fast eval runs in <10 seconds with canary regression detection
4. nDCG@5 computed with graded relevance shows improvement from M5
5. Negative test cases achieve <5% false positive rate
6. Per-path metrics identify weakest classification routes
7. Pre/post comparison detects 10%+ regressions with statistical significance
