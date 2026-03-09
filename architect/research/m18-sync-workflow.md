# M18 Research: Runtime Repo Sync Workflow

## Summary
5 friction points confirmed. Key findings from codebase analysis + web research.

## FP1: No Automated Smoke Test
- Template smoke test (`runtime-query-smoke.sh`) only runs 1 classify call
- A comprehensive E2E test (13 cases) exists at runtime repo `scripts/test_runtime_e2e.sh` but NOT in template system
- `pre_share_check.sh` uses --no-data for runtime check, missing actual data validation
- **Fix**: Expand smoke test template, run it after sync, gate commit on pass

## FP2: No Diff Check
- Manifest has SHA256 hashes per component but never read/compared
- Script unconditionally overwrites previous manifest
- **Fix**: Read previous manifest before sync, compare hashes, print human-readable delta

## FP3: Manual Push
- Script exits after writing manifest. All git ops are manual per CLAUDE.md
- Reflog confirms every commit is immediately pushed manually
- **Fix**: Add --commit and --push flags with safety checks (clean tree, no upstream divergence)

## FP4: No Version Tag
- Zero git tags in runtime repo. data_version is timestamp in manifest only
- pyproject.toml stuck at 0.1.0 across 16 commits
- **Fix**: CalVer data tags (data-YYYY.MM.DD), annotated with manifest summary

## FP5: Large LFS Push
- LFS has NO delta compression — full file upload every time
- DB: 486 MB (irreducible per-sync cost for any data change)
- Pages/meta: per-file tracking (only changed files upload)
- LanceDB: 2.2 GB (only on index rebuild)
- Typical data sync: ~500 MB. Full rebuild: ~3.1 GB
- **Fix**: DB preparation (VACUUM + wal_checkpoint + optimize), document expected sizes, LFS prune
- Current code only VACUUMs when --strip-maintenance set, never runs wal_checkpoint(TRUNCATE)
- sqlite3_rsync could reduce to ~20KB (future consideration, not for M18)
