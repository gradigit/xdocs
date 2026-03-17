# M2 Goal Reconciliation

## Acceptance Criteria Evidence

### AC1: Error code "-1002" → definition page first
- **Code evidence**: `src/xdocs/lookup.py:74-79` — pages searched FIRST with 3x limit, sorted by "error" in URL
- **Test evidence**: `tests/test_fts_util.py::TestSanitizeFtsQuery::test_hyphenated_term` (FTS5 minus handling); `tests/test_lookup.py::test_search_error_code_*` (error search pipeline)
- **Status**: PASS

### AC2: "Bybit websocket" → 6 relevant page claims
- **Code evidence**: `src/xdocs/answer.py:384-396` (`_directory_prefix` extracts directory prefix from seed URLs); `src/xdocs/answer.py:399-480` (`_generic_search_answer` uses directory prefix + domain fallback)
- **Test evidence**: `tests/test_answer.py::test_generic_search_answer_*` (generic pipeline); `tests/test_fts_util.py::TestBuildFtsQuery::test_two_terms_or` (OR for 2-term queries)
- **Status**: PASS

### AC3: No FTS5 crashes on hyphens
- **Code evidence**: `src/xdocs/fts_util.py:23-42` (`sanitize_fts_query` wraps hyphenated terms in double quotes)
- **Test evidence**: `tests/test_fts_util.py::TestSanitizeFtsQuery::test_hyphenated_term`, `::test_colon_term`, `::test_mixed_terms`
- **Status**: PASS

### AC4: Reranker on Linux CPU <500ms/20 candidates (302ms)
- **Code evidence**: `src/xdocs/reranker.py` — FlashRank ONNX backend, `ms-marco-MiniLM-L-12-v2` model
- **Test evidence**: `tests/test_reranker.py::TestReranker::test_rerank_changes_order`, `::test_empty_input`, `::test_top_n_truncation`
- **Runtime evidence**: 302ms benchmark recorded during build phase
- **Status**: PASS

### AC5: Clean excerpt boundaries
- **Code evidence**: `src/xdocs/answer.py:54-118` (`_make_excerpt`, `_snap_start_backward`, `_snap_end_forward`, `_clean_excerpt`)
- **Test evidence**: `tests/test_answer.py::test_make_excerpt_*` (excerpt boundary tests)
- **Status**: PASS

### AC6: 367 tests pass
- **Code evidence**: Full test suite across 20+ test modules
- **Test evidence**: `python -m pytest tests/ -x -q` → 367 passed, 0 failed
- **Status**: PASS

### AC7 (deferred): All 8 benchmark queries grade A or B → M3
### AC8 (deferred): Golden QA ≥80% relevance@3 → M3

## Additional M2 Changes (not in original AC but required for quality)

- **fts_util.py**: New shared module consolidating FTS5 utilities (21 tests)
- **Porter stemming**: Both FTS5 tables now use `porter unicode61` tokenizer
- **BM25 column weights**: title 10x, path 5x via rank configuration
- **Classification augmentation**: `classify_input()` augments generic search
- **Schema v4→v5 migration**: DROP + CREATE FTS tables with porter tokenizer + warning log
- **Exchange detection**: Word boundary regex prevents false positives
- **Semantic search logging**: ImportError vs Exception split properly

## Review Findings Applied

- R1 (MEDIUM): Fixed — `_augment_with_classification` now uses `docs_dir` parameter directly
- R5 (HIGH): Fixed — Post-migration warning log added for v4→v5
- R6 (LOW): Fixed — Corrected misleading comment in reranker.py
- R2/R3/R4/R7: Accepted as-is (LOW severity, no regressions)

## Verdict: ALL AC MET (6/6 testable, 2/2 deferred to M3)
