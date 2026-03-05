---
name: cex-api-docs
description: >
  Cite-only CEX API docs knowledge base. Sync official exchange documentation into a local
  SQLite FTS5 store via deterministic inventory+fetch pipeline, extract endpoint JSON with
  per-field provenance, and answer questions with claim-level citations only.
---

# CEX API Docs (Cite-Only)

## Core Rule: Cite-Only

- Never output unsupported claims.
- Every factual statement must include citations with mechanically verifiable excerpts.
- If a fact is not supported by stored sources, return:
  - `unknown` (sources not crawled/indexed)
  - `undocumented` (sources crawled but fact not stated)
  - `conflict` (sources disagree; return both)

## Local Store

Default store root: `./cex-docs/` (override via `--docs-dir` everywhere).

## Maintainer Workflow

### Setup (once)

```bash
bash scripts/bootstrap.sh [./cex-docs]
# Creates .venv, installs deps (+ semantic extras), inits store, runs tests
```

### Regular Sync (daily / cron)

`sync_and_report.sh` is the single entry point. It runs all four post-sync steps:

```bash
# Recommended: use the cron wrapper (sync + quality + changelogs + index)
bash scripts/sync_and_report.sh [./cex-docs]

# Or run the sync preset directly (sync only, no post-processing)
bash scripts/run_sync_preset.sh fast-daytime ./cex-docs     # incremental, concurrency 2
bash scripts/run_sync_preset.sh overnight-safe ./cex-docs   # force-refetch, slower
```

`sync_and_report.sh` writes timestamped artifacts to `cex-docs/reports/`:
- `TIMESTAMP-sync.json` — machine-readable sync result
- `TIMESTAMP-sync.md` — human-readable report
- `TIMESTAMP-quality.json` — empty/thin/tiny_html page flags
- `TIMESTAMP-changelogs.json` — new changelog entries (`entries_new > 0` = API changes)

### Post-Sync Steps (run by sync_and_report.sh automatically)

```bash
# 1. Quality gate — flags empty/thin/tiny_html pages
cex-api-docs quality-check --docs-dir ./cex-docs

# 2. Changelog extraction — new entries after sync = API drift detected
cex-api-docs extract-changelogs --docs-dir ./cex-docs
cex-api-docs list-changelogs --since YYYY-MM-DD --docs-dir ./cex-docs

# 3. Incremental semantic index — embeds only new/changed pages
cex-api-docs build-index --incremental --docs-dir ./cex-docs
cex-api-docs compact-index --docs-dir ./cex-docs   # merge fragments after large additions
```

### Periodic Maintenance

```bash
# CCXT wiki refresh (weekly) — re-fetches, reports changes, spot-checks links
bash scripts/refresh_ccxt_docs.sh [./cex-docs]

# Link reachability check (weekly or ad-hoc) — HEAD requests against stored URLs
bash scripts/check_links.sh [./cex-docs] [--exchange X] [--sample N]
```

### Pre-Publish Gate

Before pushing the runtime repo or sharing the store snapshot:

```bash
# Full pre-share gate: schema check, smoke syncs, tests, link spot-check
bash scripts/pre_share_check.sh [./cex-docs]

# Export query-only runtime (strips maintenance tables, writes manifest)
python3 scripts/sync_runtime_repo.py \
  --runtime-root ../cex-api-docs-runtime \
  --docs-dir ./cex-docs \
  --strip-maintenance \
  --clean
```

### Adding a New Exchange

1. Add entry to `data/exchanges.yaml` (exchange_id, sections, seed_urls, allowed_domains, scope_prefixes)
2. `cex-api-docs sync --exchange <id> --docs-dir ./cex-docs`
3. `cex-api-docs validate-crawl-targets --exchange <id> --enable-nav --docs-dir ./cex-docs`
4. `cex-api-docs build-index --incremental --docs-dir ./cex-docs`
5. Update section count in CLAUDE.md

### Registry Gotchas

- **Scope ownership**: sections sharing a sitemap need `scope_prefixes` + lower `scope_priority` (e.g. 50) to outrank broad sections (default 100). See binance/copy_trading.
- **URL migration**: when an exchange reorganises docs, update `seed_urls` and `scope_prefixes`; old orphaned pages stay in store but won't be re-fetched. See Coinbase 2026-03.
- **JS rendering**: set `render_mode: auto` for sites that require it (Coinbase, KuCoin, Aster, Paradex).
- **Binance sitemap 404**: expected — pipeline falls back to link-follow automatically.

---

## Quickstart (Query Only)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

cex-api-docs init --docs-dir ./cex-docs
```

## Sync Docs

```bash
# Full sync (inventory + fetch)
cex-api-docs sync --docs-dir ./cex-docs

# With JS rendering for sites that require it
cex-api-docs sync --docs-dir ./cex-docs --render auto

# Resume interrupted sync
cex-api-docs sync --docs-dir ./cex-docs --resume

# Parallel fetch
cex-api-docs sync --docs-dir ./cex-docs --concurrency 4
```

### Step-by-Step Alternative

```bash
cex-api-docs inventory --exchange binance --section spot --docs-dir ./cex-docs
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --resume --concurrency 4
```

> **Note:** The legacy `crawl` command still works but emits a deprecation warning. Use `sync` instead.

## Store Report

```bash
cex-api-docs store-report --docs-dir ./cex-docs
cex-api-docs store-report --exchange binance --section spot --output report.md
```

## Validate Registry (Domains/Seeds)

```bash
cex-api-docs validate-registry
cex-api-docs validate-base-urls
```

## Troubleshooting (403 / WAF / Seed Drift)

If `validate-registry` or `sync` fails due to UA-dependent 403s or doc host drift, see:

- `docs/solutions/integration-issues/ua-403-exchange-docs-crawler-tooling-20260210.md`

## Find Sources

```bash
cex-api-docs search-pages "rate limit" --docs-dir ./cex-docs
cex-api-docs get-page "https://..." --docs-dir ./cex-docs
```

## Store Integrity & Quality

```bash
cex-api-docs fsck --docs-dir ./cex-docs
cex-api-docs quality-check --docs-dir ./cex-docs
cex-api-docs coverage --docs-dir ./cex-docs
cex-api-docs coverage-gaps --docs-dir ./cex-docs
cex-api-docs detect-stale-citations --docs-dir ./cex-docs
cex-api-docs fts-optimize --docs-dir ./cex-docs
cex-api-docs check-links --docs-dir ./cex-docs
cex-api-docs check-links --exchange binance --sample 50 --docs-dir ./cex-docs
```

## Changelog Extraction

```bash
# Extract dated entries from stored changelog pages (idempotent)
cex-api-docs extract-changelogs --docs-dir ./cex-docs

# List entries; new entries after a sync = API drift
cex-api-docs list-changelogs --docs-dir ./cex-docs --exchange binance --since 2026-01-01
```

## Crawl Target Validation

```bash
# Quick (no network)
cex-api-docs sanitize-check --docs-dir ./cex-docs

# Sitemap health
cex-api-docs validate-sitemaps --docs-dir ./cex-docs

# Multi-method discovery
cex-api-docs validate-crawl-targets --exchange binance --docs-dir ./cex-docs
cex-api-docs validate-crawl-targets --exchange binance --enable-nav --enable-wayback --docs-dir ./cex-docs

# Coverage audit + backfill
cex-api-docs crawl-coverage --docs-dir ./cex-docs
cex-api-docs audit --docs-dir ./cex-docs --include-crawl-coverage
```

### When to Validate

- After sync: `sanitize-check`
- After adding exchange: `validate-crawl-targets --enable-nav`
- CCXT docs refresh: `bash scripts/refresh_ccxt_docs.sh`
- Monthly: `crawl-coverage`
- Gaps suspected: `--enable-live --enable-nav --enable-wayback`

### Interpreting Results

- `missing_from_store`: pages on live site not in store → sync needed
- `missing_from_live`: pages in store not on live site → potentially stale
- `completion_pct < 90%`: partial crawl (rate limiting / 403)

## Import Specs

```bash
cex-api-docs import-openapi spec.yaml --docs-dir ./cex-docs
cex-api-docs import-postman collection.json --docs-dir ./cex-docs
```

## Extract Endpoints (Agent Responsibility)

1. Read relevant stored pages (rate limits, auth/permissions, endpoint reference).
2. Produce endpoint JSON records matching `schemas/endpoint.schema.json`.
3. For high-risk fields (`required_permissions`, `rate_limit`, `error_codes`), include per-field citations:
   - `url`, `crawled_at`, `content_hash`, `path_hash`, `excerpt`, `excerpt_start`, `excerpt_end`
4. Record extraction metadata:
   - `temperature = 0`
   - `model`, `prompt_hash`, `input_content_hash`

## Ingest Endpoints (Deterministic)

```bash
cex-api-docs save-endpoint endpoint.json --docs-dir ./cex-docs
cex-api-docs search-endpoints "balance" --exchange binance --docs-dir ./cex-docs
```

## Review Queue

```bash
cex-api-docs review-list --docs-dir ./cex-docs
cex-api-docs review-show <id> --docs-dir ./cex-docs
cex-api-docs review-resolve <id> --docs-dir ./cex-docs
```

## Answer Questions

```bash
cex-api-docs answer "..." --docs-dir ./cex-docs
cex-api-docs answer "..." --clarification binance:portfolio_margin --docs-dir ./cex-docs
```

If a question is ambiguous, the tool returns `needs_clarification` with concrete section choices.

## Semantic Search

```bash
cex-api-docs semantic-search "check wallet balance" --docs-dir ./cex-docs
cex-api-docs semantic-search "funding rate" --exchange okx --mode vector --docs-dir ./cex-docs
```

## CCXT Cross-Reference

```bash
cex-api-docs ccxt-xref --docs-dir ./cex-docs
cex-api-docs ccxt-xref --exchange binance --docs-dir ./cex-docs
```
