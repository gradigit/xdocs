# M2 Build Review Findings

Compiled from adversarial reviewer and feature-presence reviewer agents (fresh-context).

## Finding R1: `_augment_with_classification` uses PRAGMA instead of `docs_dir` param
- **Severity**: MEDIUM (code smell, fragile)
- **File**: `src/xdocs/answer.py:803,845`
- **Issue**: `_augment_with_classification` receives `docs_dir` as a parameter but ignores it, deriving docs_dir from `conn.execute("PRAGMA database_list").fetchone()[2]` via `.parent.parent`. This is fragile (breaks with in-memory DBs, relative paths, or layout changes) and redundant.
- **Fix**: Use the `docs_dir` parameter directly.

## Finding R2: `_snap_end_forward` can exceed `hard_max` by up to 80 chars
- **Severity**: LOW (cosmetic, not a correctness bug)
- **File**: `src/xdocs/answer.py:74-76`
- **Issue**: After enforcing `hard_max` on line 75, line 76 calls `_snap_end_forward` again which can extend `end` by up to 80 chars. Excerpt could be up to `hard_max + 80` = 680 chars. This only affects answer excerpts (not endpoint citations), so no EBADCITE risk.
- **Fix**: Don't call `_snap_end_forward` after the hard_max enforcement, or accept the +80 overshoot as intentional for readability.

## Finding R3: LanceDB exchange filter uses f-string interpolation
- **Severity**: LOW (local CLI tool, not network-facing)
- **File**: `src/xdocs/semantic.py:477`
- **Issue**: `search_obj.where(f"exchange = '{exchange}'")` interpolates user input directly. While LanceDB is local-only, this is still a SQL injection pattern.
- **Fix**: LanceDB doesn't support parameterized queries in `.where()`, so sanitize the exchange value (alphanumeric + underscore only).

## Finding R4: `changelog_entries_fts` missing porter tokenizer
- **Severity**: LOW (inconsistency, not a regression)
- **File**: `schema/schema.sql`, `src/xdocs/db.py:119`
- **Issue**: `pages_fts` and `endpoints_fts` use `porter unicode61` after v4→v5 migration, but `changelog_entries_fts` (created in v3→v4) still uses default `unicode61`. Inconsistent stemming behavior.
- **Fix**: Not in M2 scope (changelog FTS was pre-existing). Note for future: add porter to changelog_entries_fts in a v5→v6 migration.

## Finding R5: FTS tables empty after v4→v5 migration until manual `fts-rebuild`
- **Severity**: HIGH (silent degradation)
- **File**: `src/xdocs/db.py:15-55`
- **Issue**: The v4→v5 migration drops and recreates FTS tables but does NOT rebuild content. Users upgrading from v4 will have empty FTS tables (0 search results) until they manually run `xdocs fts-rebuild`. The docstring says "FTS content is rebuilt by running fts-rebuild after migration" but there's no enforcement or warning.
- **Fix**: Add a post-migration warning log, or better: auto-trigger fts-rebuild after v4→v5 migration in `ensure_store_schema`.

## Finding R6: Misleading comment in reranker.py
- **Severity**: LOW (documentation only)
- **File**: `src/xdocs/reranker.py:73`
- **Issue**: Comment says "FlashRank returns RerankResult objects with .id, .text, .score attributes" but they're actually dicts with `["id"]`, `["text"]`, `["score"]` keys. The code correctly uses dict access, so no bug.
- **Fix**: Update comment.

## Finding R7: `_binance_answer` uses raw seed URLs vs `_generic_search_answer` uses `_directory_prefix`
- **Severity**: LOW (Binance seeds already end with `/`)
- **File**: `src/xdocs/answer.py`
- **Issue**: `_binance_answer` uses `sec.seed_urls[0]` directly as LIKE prefix, while `_generic_search_answer` uses `_directory_prefix()`. For Binance, seeds end with `/` so the behavior is equivalent. But if a Binance seed URL ever changed to not end with `/`, the LIKE match would be overly restrictive.
- **Fix**: Not critical. Binance-specific code is legacy and works correctly with current seeds.

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| HIGH | 1 | R5: Fix (auto-rebuild or warning) |
| MEDIUM | 1 | R1: Fix (use docs_dir param) |
| LOW | 5 | R2,R3,R4,R6,R7: Fix R6 (trivial), note others |

## Finding R8: BM25 rank weights never applied to fresh databases
- **Severity**: CRITICAL (from adversarial reviewer)
- **File**: `src/xdocs/db.py:195`
- **Issue**: Fresh databases (user_version=0) skip all migrations including `_migrate_4_to_5`, so BM25 column weights are never configured. Title matches get equal weight to body matches, degrading search quality.
- **Fix**: Added `_configure_fts_rank_weights()` function called both for fresh DBs in `apply_schema` and in `_migrate_4_to_5`. Verified with test: title match now ranks above body-only match on fresh DB.

## Summary (updated)

| Severity | Count | Action |
|----------|-------|--------|
| CRITICAL | 1 | R8: Fixed (BM25 weights on fresh DBs) |
| HIGH | 1 | R5: Fixed (auto-rebuild warning) |
| MEDIUM | 1 | R1: Fixed (use docs_dir param) |
| LOW | 5 | R2,R3,R4,R6,R7: Fix R6 (trivial), note others |

**Recommendation**: All CRITICAL/HIGH/MEDIUM findings fixed. R2/R3/R4/R7 acceptable as-is.
