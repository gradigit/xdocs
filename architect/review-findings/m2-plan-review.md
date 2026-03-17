# M2 Plan Review — Adversarial Findings

## CRITICAL Findings (must fix before build)

### F1: FTS5 tokenizer change requires DROP+CREATE
- `CREATE VIRTUAL TABLE IF NOT EXISTS` preserves old tokenizer on existing DBs
- `fts_rebuild` only deletes/re-inserts rows, never drops table
- **Resolution**: Migration (4,5) must DROP + CREATE both FTS tables with new tokenizer, then rebuild

### F2: Schema version bump needs explicit migration entry
- Missing (4,5) entry in db.py MIGRATIONS dict will crash on existing stores
- **Resolution**: Add _migrate_4_to_5() callable that: DROP FTS tables → CREATE with porter → INSERT rank config → mark for rebuild

## WARNING Findings (incorporated into plan)

### F3: fts_rebuild in pages.py uses raw JSON, not subset
- pages.py:224 uses `er["json"] or ""` — the entire endpoint JSON blob
- Also: method/path extraction reads wrong dict level (top-level vs record["http"])
- **Resolution**: Extract search_text generation into shared function, fix method/path extraction

### F4: classify integration should augment, not replace
- Single classification misses multi-type inputs (error code + endpoint path + question)
- Existing _wants_rate_limit / _wants_permissions logic is independent of classify
- **Resolution**: Use classification as AUGMENTATION: if error_message, prepend error search results; if endpoint_path, prepend path lookup; always run generic path too

### F5: OR→AND needs guard for <3 terms
- Single term after stopword filtering = no operator = fine
- 2 terms with AND = overly restrictive
- BM25 threshold must be calibrated AFTER porter stemming
- **Resolution**: AND only for 3+ terms, OR for 2 terms, no operator for 1 term. Calibrate threshold after Phase 1.

### F6: BM25 normalization integration point
- Should be at FTS5 search layer (answer.py:146-228), not reranker layer
- Enables score-based merging of FTS5 + semantic results
- **Resolution**: Move from Phase 4 to Phase 2, apply in _search_pages_with_semantic interleaving

### F7: FlashRank API returns different structure
- FlashRank returns RerankResult objects (.id, .text, .score), not dicts
- Need text_key extraction before calling, index mapping after
- **Resolution**: Add explicit implementation notes and unit test for contract
