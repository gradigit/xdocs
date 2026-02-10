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

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

cex-api-docs init --docs-dir ./cex-docs
```

## Sync Docs (Primary Workflow)

Deterministic pipeline: inventory (enumerate URLs) then fetch (download + store).
Use `sync` for the combined orchestration, or run each step separately.

```bash
# Full sync (inventory + fetch); cron-friendly JSON output
cex-api-docs sync --docs-dir ./cex-docs

# With JS rendering for sites that require it
cex-api-docs sync --docs-dir ./cex-docs --render auto

# Resume interrupted sync (reuse inventories, fetch only pending/error entries)
cex-api-docs sync --docs-dir ./cex-docs --resume

# Parallel fetch (N concurrent workers with per-domain rate limiting)
cex-api-docs sync --docs-dir ./cex-docs --concurrency 4
```

### Step-by-Step Alternative

```bash
# Step 1: Build inventory for a specific exchange section
cex-api-docs inventory --exchange binance --section spot --docs-dir ./cex-docs

# Step 2: Fetch all inventory URLs into the store
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs

# Both steps support --resume and --concurrency
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --resume --concurrency 4
```

> **Note:** The legacy `crawl` command still works but emits a deprecation warning. Use `sync` instead.

## Store Report

```bash
# Full store overview (pages, inventories, endpoints, review queue)
cex-api-docs store-report --docs-dir ./cex-docs

# Scoped to one exchange section, output to file
cex-api-docs store-report --exchange binance --section spot --output report.md
```

## Validate Registry (Domains/Seeds)

Quick health-check for all 16 exchanges in `data/exchanges.yaml` (networked):

```bash
cex-api-docs validate-registry
```

## Validate Base URLs (API Endpoints)

Reachability check for `base_urls` in `data/exchanges.yaml` (networked; unauthenticated only).
For `wss://` base URLs, this is DNS-only (no websocket handshake).

```bash
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
# Detect DB/file inconsistencies (detection-only)
cex-api-docs fsck --docs-dir ./cex-docs

# Coverage gap analysis
cex-api-docs coverage --docs-dir ./cex-docs
cex-api-docs coverage-gaps --docs-dir ./cex-docs
cex-api-docs coverage-gaps-list --docs-dir ./cex-docs

# Detect stale endpoint citations vs current sources
cex-api-docs detect-stale-citations --docs-dir ./cex-docs

# FTS index maintenance
cex-api-docs fts-optimize --docs-dir ./cex-docs
cex-api-docs fts-rebuild --docs-dir ./cex-docs
```

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

Use `answer` for a cite-only assembled response (no new facts).

```bash
cex-api-docs answer "..." --docs-dir ./cex-docs
# If prompted for clarification, re-run with:
cex-api-docs answer "..." --clarification binance:portfolio_margin --docs-dir ./cex-docs
```

If a question is ambiguous (e.g., "Binance unified trading endpoint"), the tool must return `needs_clarification` with concrete section choices derived from what is present in the local store.
