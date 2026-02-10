# CEX API Docs Sync Report

- **Started:** `2026-02-10T10:57:28+00:00`
- **Ended:** `2026-02-10T10:57:35+00:00`
- **Totals:** inventories=1, inventory_urls=93, fetched=10, stored=10, new_pages=0, updated_pages=0, unchanged_pages=10, skipped=0, errors=0

## Per Exchange/Section

| Exchange | Section | Inventory URLs | +Added | -Removed | Fetched | Stored | New | Updated | Unchanged | Skipped | Errors | Inventory ID | Crawl Run |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| binance | spot | 93 | 0 | 0 | 10 | 10 | 0 | 0 | 10 | 0 | 0 | 5 | 11 |

## Errors (Sample)

No errors recorded.

## Endpoint Coverage Gaps (Aggregated)

- **Coverage rows:** endpoints=0, rows=0, rows_with_gaps=0
- Use `cex-api-docs coverage-gaps-list` to drill into field-level samples.

## Stale Citations (Sweep)

- **Findings:** total=0, stale=0, missing_source=0, review_items_created=0
- Use `cex-api-docs review-list --status open` to triage.

## Notes

- This report is generated from the deterministic `sync` JSON output.
- Inventory enumeration uses sitemaps when available and can fall back to deterministic link-follow inventories when configured in the registry.
- For JS-heavy docs or WAF edge cases, use `--render auto` (Playwright optional) or browser capture + `ingest-page`.
