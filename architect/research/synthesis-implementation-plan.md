# M2 Implementation Plan — Synthesis of All Research

## Sources
- query-pipeline-quality.md (18 issues, 2 CRITICAL, 6 HIGH, 6 MEDIUM, 4 LOW)
- reranker-survey.md (FlashRank primary recommendation)
- qmd-analysis.md (architectural patterns to adopt)
- fts5-best-practices.md (tokenizer, ranking, excerpt improvements)

## Implementation Order (dependency-aware)

### Phase 1: Foundation (no behavior change, enables everything else)

**1a. Create shared `fts_util.py`**
- Move `_sanitize_fts_query` to shared module
- Improve: escape internal double-quotes, handle FTS operators
- Import from answer.py, endpoints.py, lookup.py, resolve_docs_urls.py, semantic.py, pages.py
- Fixes: Issue 14 (duplicate), Issue 7 (fragile hyphen handling)

**1b. Fix `search_text` in endpoints_fts — values only, no JSON keys**
- endpoints.py:514-524: change from `json.dumps({...})` to plain text values
- pages.py fts_rebuild: same change for rebuild path
- Run `fts-rebuild` after
- Fixes: Issue 2 (CRITICAL — JSON key pollution)

**1c. Add porter stemming + BM25 column weights**
- schema.sql: `tokenize = 'porter unicode61'` for both FTS tables
- After table creation: configure rank with column weights
- pages_fts: title 10x, markdown 1x
- endpoints_fts: path 5x, search_text 1x
- Bump SCHEMA_USER_VERSION
- Run `fts-rebuild`
- Fixes: FTS5 findings 2, 3

**1d. Switch ORDER BY bm25() → ORDER BY rank**
- answer.py:58, answer.py:138, resolve_docs_urls.py:97
- Fixes: FTS5 finding 2

### Phase 2: Answer Pipeline Routing (the big quality win)

**2a. Integrate classify.py into answer_question()**
- At top of answer_question(): call classify_input(question)
- Route by type:
  - error_message → _error_code_answer() [new]
  - endpoint_path → _endpoint_path_answer() [new]
  - question → existing _generic_search_answer / _binance_answer
  - request_payload, code_snippet → existing generic path
- Fixes: Issue 1 (CRITICAL)

**2b. Fix error code search: pages first, then endpoints**
- New _error_code_answer(): search pages first (definitions), then endpoints (affected)
- Boost pages with "error" in URL path
- Use phrase matching for numeric codes
- Fixes: Issues 8, 9

**2c. Fix seed URL prefix filtering**
- Extract directory prefix (strip trailing path segment)
- Always include domain-level fallback regardless of claim count
- Use scope_prefixes from InventoryPolicy when available
- Fixes: Issues 4, 5

**2d. Fix OR→AND for multi-term FTS queries**
- Use AND instead of OR when 2+ terms present
- Add BM25 score threshold (discard rank > -1.0)
- Reduce hard claim limit from 20 to 10
- Fixes: Issues 3, 16

### Phase 3: Excerpt Quality

**3a. Fix excerpt boundary snapping**
- Snap start backward to nearest \n or whitespace
- Snap end forward to nearest sentence end or \n\n
- Strip zero-width characters
- Add page title + nearest heading as structural context
- Fixes: Issues 6, 12, 15

**3b. Fix exchange detection word boundaries**
- `re.search(rf"\b{re.escape(ex_id)}\b", norm)` instead of `ex_id in norm`
- Fixes: Issue 11

**3c. Log semantic search exceptions**
- Replace `except (ImportError, Exception): pass` with proper logging
- Fixes: Issue 13

### Phase 4: Reranker Integration

**4a. Replace reranker.py with FlashRank backend**
- New reranker.py using `flashrank` with `ms-marco-MiniLM-L-12-v2`
- Same `rerank()` function signature
- Update pyproject.toml [reranker] extra
- Lazy loading with module-level cache (same pattern as embeddings.py)

**4b. Integrate reranker into answer pipeline**
- After FTS/semantic search, before claim assembly
- Rerank candidates, take top N by rerank score
- Position-aware blending (adopt from qmd): top 1-3 use more retrieval weight, lower ranks use more reranker weight

**4c. BM25 score normalization (adopt from qmd)**
- `score = |x| / (1 + |x|)` for combining BM25 with vector scores
- Enables meaningful score thresholds across different query types

## Acceptance Criteria for M2

1. All 8 benchmark queries return grade A or B (no F or C grades)
2. Error code "-1002" returns the error definition page as first result
3. "Bybit websocket" returns relevant page claims (not 0 results)
4. No FTS5 crashes on hyphenated queries
5. Reranker works on Linux CPU (<500ms for 20 candidates)
6. Excerpts have clean boundaries (no mid-word breaks)
7. 346+ tests pass (no regressions)
8. Golden QA set scores ≥80% relevance@3

## Estimated Complexity

- Phase 1: Standard (4 files, schema change, clear spec)
- Phase 2: Complex (answer.py rewrite, new routing, multiple search paths)
- Phase 3: Simple (targeted fixes in answer.py)
- Phase 4: Standard (reranker.py rewrite, integration in answer.py/semantic.py)
