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

Follow the template in `docs/crawl-targets-bible.md` Section 8. Summary:

1. Check the bible for existing research on the exchange (Section 6: Missing Exchanges)
2. Add entry to `data/exchanges.yaml` (exchange_id, sections, seed_urls, allowed_domains, scope_prefixes)
3. `cex-api-docs sync --exchange <id> --docs-dir ./cex-docs`
4. Multi-method crawl validation (see below)
5. `cex-api-docs validate-crawl-targets --exchange <id> --enable-nav --docs-dir ./cex-docs`
6. Import any available specs (OpenAPI, Postman)
7. `cex-api-docs build-index --incremental --docs-dir ./cex-docs`
8. Update exchange counts in CLAUDE.md and the bible

### Sync Pipeline Render Modes

The `sync` command supports three render modes via `--render`:

- **`http`** (default) — `requests` library, fast, works for static HTML
- **`auto`** — tries `requests` first, falls back to Playwright for thin/failed pages
- **`playwright`** — headless Chromium for JS-rendered SPAs

Use `--render auto` for most exchanges. Use `--render playwright` for sites like Bithumb EN and MercadoBitcoin.

### Post-Sync Validation (Multi-Method)

`requests` fails on ~40% of exchanges (SPAs, Cloudflare, WAF). After sync, validate output:

1. **`crawl4ai`** (primary validation) — works on ~95% of sites, returns LLM-ready markdown, handles JS + anti-bot
2. **`cloudscraper`** (alternative) — when crawl4ai is unavailable or rate-limited
3. **Headed browser** (`headless=False`) — CAPTCHA solving, headless detection bypass
4. **Agent Browser** — login-gated, infinite scroll, complex interaction

```bash
# Quick test with cloudscraper
python3 -c "import cloudscraper; s=cloudscraper.create_scraper(); r=s.get('URL'); print(r.status_code, len(r.text))"

# Test with crawl4ai
python3 -c "
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
async def test():
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as c:
        r = await c.arun(url='URL', config=CrawlerRunConfig())
        print(f'Success: {r.success}, Length: {len(r.markdown or \"\")}')
asyncio.run(test())
"
```

After sync, spot-check 5% of pages with an alternate method. If content differs >20%, re-crawl the entire exchange with the browser method.

### Source Trust & Drift

Official API docs pages are the closest thing to ground truth. Specs, Postman collections, and CCXT metadata all drift independently. See `docs/crawl-targets-bible.md` Section 10 for the full trust hierarchy and drift detection strategy.

Key rule: **crawl all sources, import all specs, then cross-reference**. Flag discrepancies for manual review. Never treat any single source as 100% accurate.

### Registry Gotchas

- **Scope ownership**: sections sharing a sitemap need `scope_prefixes` + lower `scope_priority` (e.g. 50) to outrank broad sections (default 100). See binance/copy_trading.
- **URL migration**: when an exchange reorganises docs, update `seed_urls` and `scope_prefixes`; old orphaned pages stay in store but won't be re-fetched. See Coinbase 2026-03.
- **JS rendering**: set `render_mode: auto` for sites that require it (Coinbase, KuCoin, Aster, Paradex).
- **Binance sitemap 404**: expected — pipeline falls back to link-follow automatically.
- **Sitemaps are hints, not truth**: always cross-validate with link-follow and nav extraction. Kraken's sitemap has 48 REST pages our crawler missed.
- **Coinbase scope gap**: FIX docs at `/exchange/fix-api/` etc. are outside current `/api-reference/` scope_prefixes.

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

If `validate-registry` or `sync` fails due to UA-dependent 403s or doc host drift:

1. Try `crawl4ai` (default — handles JS rendering, anti-bot, returns clean markdown)
2. Try `cloudscraper` if crawl4ai is unavailable (handles Cloudflare challenges)
3. Try headed browser (`headless=False`) for CAPTCHA or headless detection
4. Use Agent Browser for login-gated or interactive sites
5. See `docs/solutions/integration-issues/ua-403-exchange-docs-crawler-tooling-20260210.md`

### Crawl Tool Availability

| Tool | Install | Use Case |
|------|---------|----------|
| `cloudscraper` | `pip install cloudscraper` | Cloudflare bypass |
| `crawl4ai` | `pip install crawl4ai && crawl4ai-setup` | Browser + AI markdown, best all-around |
| Playwright | `pip install playwright && playwright install chromium` | JS rendering |
| Agent Browser | `.claude/skills/agent-browser/` | Interactive crawling |

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
