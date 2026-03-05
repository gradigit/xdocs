# Maintainer vs Runtime Repo Split

Date: 2026-02-27

## Goal

Operate with two repos:

1. **Maintainer repo** (this repo): crawl/sync/index/validate/publish.
2. **Runtime repo** (team-facing): query CLI + query skill + prebuilt snapshot only.

This keeps teammate workflow fast (`git pull` + query) while centralizing crawler/index maintenance.

## Maintainer workflow

1. Refresh data/index in maintainer repo.
2. Validate:

```bash
scripts/pre_share_check.sh ./cex-docs
```

3. Sync runtime repo contents:

```bash
python3 scripts/sync_runtime_repo.py \
  --runtime-root /path/to/cex-api-docs-runtime \
  --docs-dir ./cex-docs \
  --clean
```

Optional:
- omit semantic index for smaller runtime repo:
  `--no-lancedb`
- copy metadata only (no snapshot data):
  `--no-data`

4. In runtime repo:
   - review `runtime-manifest.json`
   - commit + push

## Team workflow (runtime repo)

1. `git pull`
2. Ensure env is installed (`pip install -e ".[dev,semantic]"`)
3. Start fresh agent session
4. Prompt:

```text
Use cex-api-query skill.
```

Then ask natural-language exchange API questions.

## Notes

- Runtime snapshot excludes crawling duties by policy.
- Maintainers own snapshot freshness/versioning.
- `runtime-manifest.json` is the snapshot provenance/contents record.
