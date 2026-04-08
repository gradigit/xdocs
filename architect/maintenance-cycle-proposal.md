# Maintenance Cycle Proposal

## Problem

47 sections use link-follow inventory. New pages added by exchanges after our last inventory are invisible until a fresh inventory is generated. `sync --force-refetch` re-fetches existing entries but does NOT discover new pages. This caused the Bitget gap (182 → 568 pages, 386 missing).

## Current State

- Inventories are generated once (during initial onboarding) and reused forever
- `sync --resume` and `sync --force-refetch` both reuse existing inventories
- No mechanism to detect that an exchange added new pages
- No scheduled re-inventory

## Proposed: Three-Tier Maintenance Cycle

### Tier 1: Weekly — Fresh Inventory Discovery (automated)

```bash
# For all link-follow exchanges: generate fresh inventory, compare to existing, fetch delta
xdocs sync --docs-dir ./cex-docs --fresh-inventory --concurrency 4
```

New `--fresh-inventory` flag on `sync`:
- Generates a new inventory (link-follow or sitemap) for each section
- Compares new inventory URLs to existing inventory URLs
- Only fetches URLs that are NEW (not in any previous inventory)
- Reports: `new_urls_discovered: N, removed_urls: M`

This is the missing piece. It's the equivalent of `git fetch` — discover what's new without re-downloading everything.

**Implementation:** Add a `fresh_inventory` flag to `sync.py` that always calls `create_inventory()` instead of reusing existing ones, then passes the new inventory to `fetch_inventory()` with `resume=True` (only fetch pending entries = newly discovered URLs).

### Tier 2: Monthly — Full Re-fetch (automated)

```bash
# Re-download all pages to detect content changes (not just new pages)
xdocs sync --docs-dir ./cex-docs --force-refetch --render auto --concurrency 4
```

This already works. Catches content updates on existing pages.

### Tier 3: Quarterly — Coverage Audit (manual)

```bash
# Full crawl-target validation with nav extraction
xdocs validate-crawl-targets --enable-nav --enable-wayback --docs-dir ./cex-docs
xdocs crawl-coverage --enable-live --docs-dir ./cex-docs
xdocs ccxt-xref --docs-dir ./cex-docs
```

Catches structural changes: new API versions, renamed sections, new exchange platforms.

## Quick Win: `sync --fresh-inventory`

The simplest fix is a one-line change in `sync.py`: when `--fresh-inventory` is passed, skip the "reuse existing inventory" logic and always generate a new one.

```python
# sync.py, line 227
if cfg.resume or cfg.force_refetch:
    # Currently: reuse existing inventory
    # With --fresh-inventory: skip this block
    if not cfg.fresh_inventory:
        existing_id = latest_inventory_id(...)
```

Then the weekly cron job is just:
```bash
xdocs sync --docs-dir ./cex-docs --fresh-inventory --render auto --concurrency 4
```

## Cron Schedule

| Frequency | Command | Purpose |
|-----------|---------|---------|
| Weekly (Sun 02:00) | `sync --fresh-inventory --concurrency 4` | Discover new pages |
| Weekly (Sun 06:00) | `backfill-params` | Fill params for new endpoints |
| Monthly (1st, 02:00) | `sync --force-refetch --concurrency 4` | Detect content changes |
| Monthly (1st, 08:00) | `build-index --incremental && compact-index` | Update semantic index |
| Quarterly | Manual coverage audit | Structural validation |
