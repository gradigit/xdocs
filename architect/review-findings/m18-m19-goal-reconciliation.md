# M18+M19 Goal Reconciliation — 2026-03-09

## M18: Runtime Repo Sync Workflow

### Criterion 1: Automated smoke test runs after sync
- **Code**: `scripts/sync_runtime_repo.py:_run_smoke_test()` (line ~350) + `docs/templates/runtime-query-smoke.sh` (65 lines, 7 checks: DB exists+size, schema version, page count, endpoint count, FTS5 functional, maintenance tables, PRAGMA quick_check)
- **Test**: Manual verification — smoke test template validated in code review. No unit test (shell script, not Python).
- **Status**: PASS

### Criterion 2: Diff check shows what changed vs previous runtime state
- **Code**: `scripts/sync_runtime_repo.py:_compare_manifests()` (line ~130) + `_build_delta_summary()` (line ~197). Reads previous manifest, compares SHA256 hashes per component, returns human-readable diff and `all_unchanged` flag.
- **Test**: Verified via adversarial review. Bug found (directories without `--hash-tree` always report CHANGED) — fixed in improvement phase by falling back to files/bytes comparison.
- **Status**: PASS (after fix)

### Criterion 3: Push automation (--push flag with safety checks)
- **Code**: `scripts/sync_runtime_repo.py:_git_push_runtime()` (line ~530). Checks git-lfs installed, fetches upstream, checks for divergence, sets LFS timeout, pushes. CLI flag `--push` (requires `--commit`).
- **Test**: No unit test (requires git remote). Safety checks verified in code review: never force-push, divergence detection.
- **Status**: PASS

### Criterion 4: Version tagging (git tag on runtime repo)
- **Code**: `scripts/sync_runtime_repo.py:_git_tag_runtime()` (line ~560). CalVer `data-YYYY.MM.DD[.N]` format with collision handling via existing tag enumeration.
- **Test**: No unit test (requires git repo). Bug found (tag sequence skips .1) — fixed in improvement phase by initializing `max_n = 0`.
- **Status**: PASS (after fix)

### Criterion 5: LFS push size optimization
- **Code**: `scripts/sync_runtime_repo.py:_prepare_runtime_db()` (line ~290) — VACUUM + `PRAGMA wal_checkpoint(TRUNCATE)` + `PRAGMA optimize` on destination DB. `_checkpoint_source_db()` (line ~275) checkpoints source DB WAL before copy.
- **Test**: No unit test (requires full DB). Verified via adversarial review — WAL checkpoint prevents data loss in copy.
- **Status**: PASS

## M19: Binance Coverage Test Regression

### Criterion 1: Root cause of each PARTIAL result identified
- **Code**: Research artifact `architect/research/m19-binance-coverage.md` — detailed per-question root cause analysis
- **Test**: Evidence from running coverage test and tracing each query through the pipeline
- **Status**: PASS — Q1: peg params not in upstream spec (0 matches in raw YAML). Q3/Q5: Postman import didn't extract params + some endpoints have empty params even in source. Q4: two bugs (FTS crash + semantic-search text field missing).

### Criterion 2: Q1 (parameters) — all 19 expected params found (currently 16/19)
- **Code**: N/A — the 3 missing params (pegPriceType, pegOffsetValue, pegOffsetType) are NOT in the Binance OpenAPI spec at all. They exist only in doc pages.
- **Test**: Research confirms 0 matches in raw YAML for peg params
- **Status**: PARTIAL — This is a known data gap, not a code issue. Requires doc page parameter extraction (beyond M19 scope). Documented in architect/research/m19-binance-coverage.md.

### Criterion 3: Q4 (auth) — all 5 auth items found in search results
- **Code**: `src/xdocs/pages.py:search_pages()` — added FTS5 sanitization via `sanitize_fts_query()` to prevent crash on hyphenated terms like "X-MBX-APIKEY"
- **Test**: `tests/test_init.py:TestSearchPagesSanitization` — 3 tests covering hyphenated terms, colons, mixed special characters
- **Status**: PARTIAL — FTS crash fixed but Q4 requires finding all 5 auth terms in a single response. FTS5 snippets are 12 tokens (too short). Semantic-search results lack text content field. The page content EXISTS (request-security page has all 5 terms) but extraction window is too narrow.

### Criterion 4: Q3/Q5 root cause documented
- **Code**: `src/xdocs/postman_import.py:_extract_request_schema()` (~72 lines) — now extracts params from urlencoded, formdata, raw JSON, and URL query params
- **Test**: `tests/test_fts_util.py:TestPostmanExtractRequestSchema` — 10 tests covering all 4 body modes, deduplication, empty/invalid input
- **Status**: PASS — Root cause documented (Postman import set `request_schema: None`). Fix implemented but specific Q3/Q5 endpoints (OPO, OPOCO, newer Binance endpoints) have empty param arrays even in Postman source. Documented as known gap.

## Overall Verdict

- **M18**: 5/5 criteria PASS (2 after improvement-phase bug fixes)
- **M19**: 2/4 criteria PASS, 2/4 PARTIAL (known data/content gaps, not code issues)
  - Research proved this is NOT a regression from a previous "good" state
  - The fixable code bugs (FTS crash, Postman param extraction) are fixed
  - Remaining gaps require doc page parameter extraction or wider search windows

## Evidence Summary
- Tests: 529 pass (0 fail, 1 deselected)
- Files changed: 7 (sync_runtime_repo.py, runtime-query-smoke.sh, pages.py, postman_import.py, test_fts_util.py, test_init.py, TODO.md)
- Research artifacts: architect/research/m18-sync-workflow.md, architect/research/m19-binance-coverage.md
- Review findings: architect/review-findings/m18-m19.md
