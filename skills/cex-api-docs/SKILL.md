---
name: cex-api-docs
description: >
  Cite-only CEX API docs knowledge base. Crawl official exchange documentation into a local store,
  extract endpoint JSON with per-field provenance, ingest deterministically into SQLite FTS5, and
  answer questions with claim-level citations only.
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

## Crawl Docs

Use registry seeds from `data/exchanges.yaml`, or provide a direct URL + domain scope.

```bash
cex-api-docs crawl --exchange binance --section spot --docs-dir ./cex-docs
cex-api-docs crawl --url "https://example.com/docs" --domain-scope "example.com" --docs-dir ./cex-docs
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

If `validate-registry` or `crawl` fails due to UA-dependent 403s or doc host drift, see:

- `docs/solutions/integration-issues/ua-403-exchange-docs-crawler-tooling-20260210.md`

## Find Sources

```bash
cex-api-docs search-pages "rate limit" --docs-dir ./cex-docs
cex-api-docs get-page "https://..." --docs-dir ./cex-docs
```

## Store Integrity Check

Detect DB/file inconsistencies (detection-only):

```bash
cex-api-docs fsck --docs-dir ./cex-docs
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

## Answer Questions

Use `answer` for a cite-only assembled response (no new facts).

```bash
cex-api-docs answer "..." --docs-dir ./cex-docs
# If prompted for clarification, re-run with:
cex-api-docs answer "..." --clarification binance:portfolio_margin --docs-dir ./cex-docs
```

If a question is ambiguous (e.g., “Binance unified trading endpoint”), the tool must return `needs_clarification` with concrete section choices derived from what is present in the local store.
