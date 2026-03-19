---
name: xdocs-maintain
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

## Exhaustive Coverage Mandate

The store must be 100% exhaustive. No pages missing, no content missing, no endpoints missing, no partial data. If a crawl method fails, escalate through the cascade until content is captured. A 0-page section or 0-endpoint exchange with known specs is a bug, not an acceptable state. See CLAUDE.md for the full mandate.

## Local Store

Default store root: `./cex-docs/` (override via `--docs-dir` everywhere).

## Maintainer Workflow

### Fresh Agent: Start Here

If you are starting a new session with no prior context, follow these steps before doing anything:

1. **Read CLAUDE.md** — project overview, conventions, exhaustive coverage mandate, current phase, gotchas
2. **Read this skill** (you're reading it) — the end-to-end maintainer workflow
3. **Read the registry** (`data/exchanges.yaml`) — all 46 exchanges, 78 sections, seed URLs, render modes, scope settings
4. **Read the bible** (`docs/crawl-targets-bible.md`) — all 11 sections; per-exchange crawl notes, spec URLs, failure modes, missing exchanges, import priorities
5. **Assess current store state**:

```bash
xdocs store-report --docs-dir ./cex-docs
```

6. **Determine what phase to start from**:
   - Store empty or missing → Phase 0 (full workflow from scratch)
   - Store exists but outdated → Phase 0 (readiness check) then Phase 2 (sync)
   - Store current but specs not imported → Phase 3 (spec imports)
   - Store current and complete → Phase 4 (validation) then Phase 5 (doc update)
   - Adding new exchange → "Adding a New Exchange" section below

7. **Check for pending inventory entries** (decides `--resume` vs fresh sync):

```bash
python3 -c "
import sqlite3; conn = sqlite3.connect('cex-docs/db/docs.db')
for r in conn.execute('''
    SELECT i.exchange_id, i.section_id, ie.status, COUNT(*)
    FROM inventories i JOIN inventory_entries ie ON ie.inventory_id = i.id
    WHERE ie.status IN (\"pending\", \"error\")
    GROUP BY i.exchange_id, i.section_id, ie.status
    ORDER BY i.exchange_id'''):
    print(f'{r[0]:20s} {r[1]:20s} {r[2]:10s} {r[3]:5d}')
"
```

If pending/error entries exist, use `--resume` for sync. If store is empty, proceed with full sync.

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
xdocs quality-check --docs-dir ./cex-docs

# 2. Changelog extraction — new entries after sync = API drift detected
xdocs extract-changelogs --docs-dir ./cex-docs
xdocs list-changelogs --since YYYY-MM-DD --docs-dir ./cex-docs

# 3. Incremental semantic index — embeds only new/changed pages
xdocs build-index --incremental --docs-dir ./cex-docs
xdocs compact-index --docs-dir ./cex-docs   # merge fragments after large additions
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

# Publish data release
python3 scripts/sync_runtime_repo.py \
  --runtime-root . --docs-dir ./cex-docs --publish
```

### Adding a New Exchange

**Use the `xdocs-discovery` skill** (`.claude/skills/xdocs-discovery/SKILL.md`) to run exhaustive discovery before registering. The discovery skill produces a bible entry and a ready-to-paste `exchanges.yaml` config block.

Summary after discovery is complete:

1. Run the `xdocs-discovery` skill for the target exchange — produces bible entry + registry YAML
2. Add the bible entry to `docs/crawl-targets-bible.md` (Section 3-5 per exchange type)
3. Add the registry entry to `data/exchanges.yaml`
4. `xdocs sync --exchange <id> --docs-dir ./cex-docs --render auto`
5. Multi-method crawl validation (see "Post-Sync Validation" below)
6. `xdocs validate-crawl-targets --exchange <id> --enable-nav --docs-dir ./cex-docs`
7. Import any discovered specs (OpenAPI, Postman, AsyncAPI)
8. `xdocs build-index --incremental --docs-dir ./cex-docs`
9. Follow "Updating Skills & Documentation" checklist (all 7 files)

### Updating Skills & Documentation

After any significant store change (new exchange, spec import, crawl gap fix, new CLI command), update these files:

1. **CLAUDE.md** — Commands section, Key Files, Current Phase stats
2. **xdocs-query SKILL.md** (`.claude/skills/xdocs-query/SKILL.md`) — "What's In The Store" section: endpoint counts per exchange/section, DEX page counts, CCXT stats. Bump `version` in metadata when changing content.
3. **xdocs SKILL.md** (this file) — CLI command reference, workflow steps
4. **xdocs-discovery SKILL.md** (`.claude/skills/xdocs-discovery/SKILL.md`) — exchange list, spec patterns, platform detection (update when new exchange types or doc platforms are encountered)
5. **README.md** — Exchange counts, project structure, command examples
6. **AGENTS.md** — Current context stats, command reference
7. **Bible** (`docs/crawl-targets-bible.md`) — Coverage table (Section 2a), spec status, section counts

**How to verify:**

```bash
# Get current numbers
xdocs store-report --docs-dir ./cex-docs

# Cross-check endpoints in query skill against DB
python3 -c "
import sqlite3; conn = sqlite3.connect('cex-docs/db/docs.db')
for r in conn.execute('SELECT exchange, section, COUNT(*) FROM endpoints GROUP BY exchange, section ORDER BY exchange, section'):
    print(f'{r[0]:20s} {r[1]:25s} {r[2]:5d}')
print(f\"Total: {conn.execute('SELECT COUNT(*) FROM endpoints').fetchone()[0]}\")"
```

### Full Exhaustive Sync Workflow

When executing a complete sync (all exchanges, all specs, all validation), follow this end-to-end workflow. **Every phase has mandatory pre-checks.**

#### Phase 0: Pre-Crawl Readiness (mandatory before any sync)

1. **Read the registry** (`data/exchanges.yaml`) — verify all sections, seed URLs, render modes, scope settings. Cross-reference against the bible for correctness.
2. **Read the full bible** (`docs/crawl-targets-bible.md`, all 11 sections) — note per-exchange crawl notes, known failure modes, spec URLs, pending additions, and import commands.
3. **Baseline snapshot** — record current counts to measure delta after sync:

```bash
xdocs store-report --docs-dir ./cex-docs
```

4. **Inventory state check** — identify pending/error entries (decides `--resume` vs fresh):

```bash
python3 -c "
import sqlite3; conn = sqlite3.connect('cex-docs/db/docs.db')
for r in conn.execute('''
    SELECT i.exchange_id, i.section_id, ie.status, COUNT(*)
    FROM inventories i JOIN inventory_entries ie ON ie.inventory_id = i.id
    WHERE ie.status IN (\"pending\", \"error\")
    GROUP BY i.exchange_id, i.section_id, ie.status
    ORDER BY i.exchange_id'''):
    print(f'{r[0]:20s} {r[1]:20s} {r[2]:10s} {r[3]:5d}')
"
```

5. **Render mode review** — cross-check `render_mode` in exchanges.yaml against bible Section 1c failure modes. Sites that MUST have `render_mode: auto` or `playwright`:
   - `auto`: Gate.io, OKX, HTX, Crypto.com, KuCoin, Bitstamp, Bitfinex, Coinbase, Aevo, dYdX, Drift, Gains, Kwenta, Lighter, Aster, ApeX, Paradex, Korbit, Coinone, BitMart
   - `playwright`: Bithumb EN, MercadoBitcoin

6. **Spec URL liveness** — verify all import URLs are reachable before starting imports:

```bash
for url in \
  "https://raw.githubusercontent.com/Kucoin/kucoin-universal-sdk/main/spec/rest/entry/openapi-spot.json" \
  "https://docs.whitebit.com/openapi/public/http-v4.yaml" \
  "https://raw.githubusercontent.com/bitmartexchange/bitmart-postman-api/master/collections/Spot.postman_collection.json" \
  "https://api.prime.coinbase.com/v1/openapi.yaml" \
  "https://api.prod.paradex.trade/swagger/doc.json" \
  "https://raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json" \
  "https://raw.githubusercontent.com/dydxprotocol/v4-chain/main/indexer/services/comlink/public/swagger.json" \
  "https://raw.githubusercontent.com/metalocal/coinbase-exchange-api/main/api.oas3.json"; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "$url")
  echo "$code $url"
done
```

If any URL returns non-200, check the bible for alternatives before proceeding.

#### Phase 1: Registry Alignment

Before syncing, ensure `data/exchanges.yaml` matches the bible:

1. **Verify existing sections** — seed URLs, allowed_domains, scope_prefixes, render_mode all match bible Section 3-5 per-exchange entries
2. **Fix known gaps** documented in the bible:
   - Kraken: seed URL only discovered guide pages, not `/rest-api/` pages (sitemap has 48 REST pages)
   - Coinbase: FIX docs at `/exchange/fix-api/`, `/international-exchange/fix-api/`, `/prime/fix-api/`, `/derivatives/fix/` outside current scope_prefixes
   - Bithumb EN: `render_mode: playwright` required (Localize.js)
3. **Add new exchanges** from bible Section 6 (MEXC, BingX = CRITICAL; Deribit, Backpack = HIGH)
4. **Add new sections** from bible Section 2k (FIX docs) and Section 5 (new priorities)

#### Phase 2: Sync Execution

```bash
# Full sync with JS fallback (1-4 hours for all 46 exchanges)
xdocs sync --docs-dir ./cex-docs --render auto --concurrency 2

# If interrupted, resume (reuses inventories, fetches only pending/error)
xdocs sync --docs-dir ./cex-docs --resume --concurrency 2

# Re-sync specific exchange (e.g., after fixing registry entry)
xdocs sync --exchange kraken --docs-dir ./cex-docs --render auto
```

**Timeout handling**: Full sync takes 1-4 hours. Use `--concurrency 2` to balance speed vs rate limits. If running agentically, use background execution for the sync and check progress via `store-report`. If an exchange fails (403, timeout), re-sync it individually. Gate.io rate-limits aggressively — may need `--concurrency 1` or longer delays.

#### Phase 3: Spec Imports

Import all verified specs. See bible Section 9 for the full priority list with exact commands.

```bash
# KuCoin (9 files, all need --base-url since specs lack servers[])
for spec in openapi-spot openapi-futures openapi-account openapi-margin openapi-broker openapi-earn openapi-copytrading openapi-viplending openapi-affiliate; do
  base_url="https://api.kucoin.com"
  [[ "$spec" == *futures* || "$spec" == *copytrading* ]] && base_url="https://api-futures.kucoin.com"
  xdocs import-openapi --exchange kucoin --section spot \
    --url "https://raw.githubusercontent.com/Kucoin/kucoin-universal-sdk/main/spec/rest/entry/${spec}.json" \
    --base-url "$base_url" --docs-dir ./cex-docs --continue-on-error
done

# WhiteBIT (7 OpenAPI specs)
for spec in public/http-v4.yaml public/http-v2.yaml public/http-v1.yaml \
  private/main_api_v4.yaml private/http-trade-v4.yaml private/http-trade-v1.yaml oauth2.yaml; do
  xdocs import-openapi --exchange whitebit --section v4 \
    --url "https://docs.whitebit.com/openapi/${spec}" --docs-dir ./cex-docs --continue-on-error
done

# BitMart (2 Postman collections: Spot 54 + Futures 57 = 111 endpoints)
xdocs import-postman --exchange bitmart --section spot \
  --url "https://raw.githubusercontent.com/bitmartexchange/bitmart-postman-api/master/collections/Spot.postman_collection.json" \
  --docs-dir ./cex-docs --continue-on-error
xdocs import-postman --exchange bitmart --section futures \
  --url "https://raw.githubusercontent.com/bitmartexchange/bitmart-postman-api/master/collections/Futures.postman_collection.json" \
  --docs-dir ./cex-docs --continue-on-error

# Coinbase Prime (351KB, ~95 endpoints)
xdocs import-openapi --exchange coinbase --section prime \
  --url "https://api.prime.coinbase.com/v1/openapi.yaml" --docs-dir ./cex-docs --continue-on-error

# Paradex (380KB, 67 paths — spec lacks servers[], needs --base-url)
xdocs import-openapi --exchange paradex --section api \
  --url "https://api.prod.paradex.trade/swagger/doc.json" \
  --base-url "https://api.prod.paradex.trade/v1" --docs-dir ./cex-docs --continue-on-error

# Lighter (225KB, 72 paths — spec lacks servers[], needs --base-url)
xdocs import-openapi --exchange lighter --section docs \
  --url "https://raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json" \
  --base-url "https://api.lighter.xyz" --docs-dir ./cex-docs --continue-on-error

# dYdX (115KB, 43 paths — spec lacks servers[], needs --base-url)
xdocs import-openapi --exchange dydx --section docs \
  --url "https://raw.githubusercontent.com/dydxprotocol/v4-chain/main/indexer/services/comlink/public/swagger.json" \
  --base-url "https://indexer.dydx.trade/v4" --docs-dir ./cex-docs --continue-on-error

# Coinbase Exchange (community spec, 157KB, 38 paths)
xdocs import-openapi --exchange coinbase --section exchange \
  --url "https://raw.githubusercontent.com/metalocal/coinbase-exchange-api/main/api.oas3.json" \
  --docs-dir ./cex-docs --continue-on-error

# Link imported endpoints to doc pages
xdocs link-endpoints --docs-dir ./cex-docs
```

After each import, verify endpoint count matches bible expectations. If count is significantly lower, check for `--continue-on-error` output for parsing failures.

#### Phase 4: Post-Sync Validation

```bash
# Quality gate (empty/thin/tiny_html pages)
xdocs quality-check --docs-dir ./cex-docs

# Store consistency (DB/file mismatches)
xdocs fsck --docs-dir ./cex-docs

# CCXT cross-reference (gap detection)
xdocs ccxt-xref --docs-dir ./cex-docs

# Changelog extraction (API drift detection)
xdocs extract-changelogs --docs-dir ./cex-docs

# Stale citation detection
xdocs detect-stale-citations --docs-dir ./cex-docs

# Semantic index rebuild
xdocs build-index --incremental --docs-dir ./cex-docs
xdocs compact-index --docs-dir ./cex-docs

# Coverage gaps
xdocs coverage-gaps --docs-dir ./cex-docs

# Final report — compare against Phase 0 baseline
xdocs store-report --docs-dir ./cex-docs
```

Spot-check 5% of pages with `crawl4ai`. If content differs >20% from stored markdown, flag the exchange for re-crawl with `--render auto`.

#### Phase 5: Update Documentation

Follow the "Updating Skills & Documentation" checklist above. This is NOT optional — every sync that changes page/endpoint counts must update all 6 doc files.

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
uv venv .venv
source .venv/bin/activate
uv pip install -e .

xdocs init --docs-dir ./cex-docs
```

## Sync Docs

```bash
# Full sync (inventory + fetch)
xdocs sync --docs-dir ./cex-docs

# With JS rendering for sites that require it
xdocs sync --docs-dir ./cex-docs --render auto

# Resume interrupted sync
xdocs sync --docs-dir ./cex-docs --resume

# Parallel fetch
xdocs sync --docs-dir ./cex-docs --concurrency 4
```

### Step-by-Step Alternative

```bash
xdocs inventory --exchange binance --section spot --docs-dir ./cex-docs
xdocs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --resume --concurrency 4
```

> **Note:** The legacy `crawl` command still works but emits a deprecation warning. Use `sync` instead.

## Store Report

```bash
xdocs store-report --docs-dir ./cex-docs
xdocs store-report --exchange binance --section spot --output report.md
```

## Validate Registry (Domains/Seeds)

```bash
xdocs validate-registry
xdocs validate-base-urls
```

## Troubleshooting (403 / WAF / Seed Drift)

If `validate-registry` or `sync` fails due to UA-dependent 403s or doc host drift:

1. Try `crawl4ai` (default — handles JS rendering, anti-bot, returns clean markdown)
2. Try `cloudscraper` if crawl4ai is unavailable (handles Cloudflare challenges)
3. Try headed browser (`headless=False`) for CAPTCHA or headless detection
4. Use Agent Browser for login-gated or interactive sites
5. Check `docs/ops/` for operational guides on handling blocked crawls

### Crawl Tool Availability

| Tool | Install | Use Case |
|------|---------|----------|
| `cloudscraper` | `uv pip install cloudscraper` | Cloudflare bypass |
| `crawl4ai` | `uv pip install crawl4ai && crawl4ai-setup` | Browser + AI markdown, best all-around |
| Playwright | `uv pip install playwright && playwright install chromium` | JS rendering |
| Agent Browser | `.claude/skills/agent-browser/` | Interactive crawling |

## Find Sources

```bash
xdocs search-pages "rate limit" --docs-dir ./cex-docs
xdocs get-page "https://..." --docs-dir ./cex-docs
```

## Store Integrity & Quality

```bash
xdocs fsck --docs-dir ./cex-docs
xdocs quality-check --docs-dir ./cex-docs
xdocs coverage --docs-dir ./cex-docs
xdocs coverage-gaps --docs-dir ./cex-docs
xdocs detect-stale-citations --docs-dir ./cex-docs
xdocs fts-optimize --docs-dir ./cex-docs
xdocs check-links --docs-dir ./cex-docs
xdocs check-links --exchange binance --sample 50 --docs-dir ./cex-docs
```

## Changelog Extraction

```bash
# Extract dated entries from stored changelog pages (idempotent)
xdocs extract-changelogs --docs-dir ./cex-docs

# List entries; new entries after a sync = API drift
xdocs list-changelogs --docs-dir ./cex-docs --exchange binance --since 2026-01-01
```

## Crawl Target Validation

```bash
# Quick (no network)
xdocs sanitize-check --docs-dir ./cex-docs

# Sitemap health
xdocs validate-sitemaps --docs-dir ./cex-docs

# Multi-method discovery
xdocs validate-crawl-targets --exchange binance --docs-dir ./cex-docs
xdocs validate-crawl-targets --exchange binance --enable-nav --enable-wayback --docs-dir ./cex-docs

# Coverage audit + backfill
xdocs crawl-coverage --docs-dir ./cex-docs
xdocs audit --docs-dir ./cex-docs --include-crawl-coverage
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
xdocs import-openapi spec.yaml --docs-dir ./cex-docs
xdocs import-postman collection.json --docs-dir ./cex-docs
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
xdocs save-endpoint endpoint.json --docs-dir ./cex-docs
xdocs search-endpoints "balance" --exchange binance --docs-dir ./cex-docs
```

## Review Queue

```bash
xdocs review-list --docs-dir ./cex-docs
xdocs review-show <id> --docs-dir ./cex-docs
xdocs review-resolve <id> --docs-dir ./cex-docs
```

## Answer Questions

```bash
xdocs answer "..." --docs-dir ./cex-docs
xdocs answer "..." --clarification binance:portfolio_margin --docs-dir ./cex-docs
```

If a question is ambiguous, the tool returns `needs_clarification` with concrete section choices.

## Semantic Search

```bash
xdocs semantic-search "check wallet balance" --docs-dir ./cex-docs
xdocs semantic-search "funding rate" --exchange okx --mode vector --docs-dir ./cex-docs
```

## CCXT Cross-Reference

```bash
xdocs ccxt-xref --docs-dir ./cex-docs
xdocs ccxt-xref --exchange binance --docs-dir ./cex-docs
```
