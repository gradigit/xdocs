# cex-api-docs

Local-only, cite-only knowledge base for centralized exchange (CEX) API documentation.

This repository is for teams who keep getting tripped up by:
- which endpoint base URL to use (spot vs futures vs portfolio margin, etc.)
- differing rate-limit/weight models across endpoints
- API key permissions required for specific endpoints

It solves that by crawling *public* exchange documentation into a local store and enforcing a strict “cite-only” rule when answering questions.

## What It Does

- Crawl and store official exchange API docs locally (default `./cex-docs/`)
- Deterministically enumerate doc URLs via inventories (sitemaps + heuristics)
- Fall back to deterministic, bounded link-follow inventories for docs without usable sitemaps
- Sync docs in a cron-friendly way (`sync` + stable JSON output, optional Markdown report)
- Validate registry seeds/domains and API base URLs (reachability-only, unauthenticated)
- Full-text search crawled pages using SQLite FTS5
- Ingest structured endpoint JSON (agent-generated) with per-field provenance
- Ingest browser-captured pages back into the canonical store (`ingest-page`)
- Answer questions from the local store with claim-level citations only

## Non-Goals / Safety Rules

- No hosted service. Everything is local.
- No storage of real exchange API keys.
- No authenticated exchange API calls and no trading logic.
- No unsupported claims in answers:
  - If a fact is not backed by stored sources, return `unknown` / `undocumented` / `conflict`.

## Install (macOS)

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional (only needed for JS-heavy doc sites):

```bash
pip install -e ".[playwright]"
python3 -m playwright install
```

## Quickstart

Initialize a fresh store:

```bash
cex-api-docs init --docs-dir ./cex-docs
```

Sanity-check the built-in registry (networked):

```bash
cex-api-docs validate-registry
cex-api-docs validate-base-urls
```

Sync docs for a section (deterministic inventory -> fetch):

```bash
cex-api-docs sync --exchange binance --section spot --docs-dir ./cex-docs
```

Resume a partially completed inventory fetch (after interruption):

```bash
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --resume
```

Sync all configured exchanges/sections (debug-friendly caps):

```bash
cex-api-docs sync --docs-dir ./cex-docs --limit 1 --inventory-max-pages 10 --render auto
```

Render a sync JSON artifact into Markdown:

```bash
cex-api-docs sync --exchange binance --section spot --docs-dir ./cex-docs > /tmp/sync.json
cex-api-docs report --input /tmp/sync.json --output /tmp/sync.md
```

Legacy crawl (link-follow) using registry seeds:

```bash
cex-api-docs crawl --exchange binance --section spot --docs-dir ./cex-docs
```

Search the local docs:

```bash
cex-api-docs search-pages "rate limit OR weight" --docs-dir ./cex-docs
```

Answer a question (cite-only; answers come only from stored sources):

```bash
cex-api-docs answer "What API key permissions are required to query Binance Portfolio Margin subaccount balances?" --docs-dir ./cex-docs
```

Validate store integrity (detection-only by default):

```bash
cex-api-docs fsck --docs-dir ./cex-docs
```

## Registry (16 Exchanges)

The registry is `data/exchanges.yaml`. It defines:
- `allowed_domains`: host allowlist for crawling
- `sections[].seed_urls`: canonical doc roots to crawl
- `sections[].base_urls`: API base URLs for reachability checks (and for endpoint records)
- `sections[].doc_sources[]` (optional): additional enumeration sources (sitemap/spec URLs)
- `sections[].inventory_policy` (optional): per-section inventory mode + caps
  - `mode`: `inventory` (sitemap-based) or `link_follow` (deterministic link extraction)
  - `max_pages`: cap for link-follow inventories
  - `render_mode`: `http|playwright|auto`
  - `scope_prefixes`: optional explicit URL prefixes (override derived scope)

Current registry contains exactly these 16 exchanges:
`binance`, `okx`, `bybit`, `bitget`, `gateio`, `kucoin`, `htx`, `cryptocom`, `bitstamp`, `bitfinex`, `dydx`, `hyperliquid`, `upbit`, `bithumb`, `coinone`, `korbit`.

### Reconfirm Seeds/Domains

`validate-registry` fetches each seed URL and asserts:
- the seed is reachable (HTTP 2xx), and
- markdown extraction produced non-empty content (word_count > 0)

```bash
cex-api-docs validate-registry
cex-api-docs validate-registry --exchange binance
cex-api-docs validate-registry --exchange binance --section portfolio_margin
```

If a doc site is JS-rendered or doing UA-based blocking, try:

```bash
cex-api-docs validate-registry --render auto
```

### Reconfirm API Base URLs (Endpoints)

`validate-base-urls` is *reachability only* and **unauthenticated**:
- `https://...` / `http://...`: does a basic GET; any HTTP response counts as “reachable”
- `wss://...` / `ws://...`: DNS-only check (no websocket handshake)

```bash
cex-api-docs validate-base-urls
```

## CLI (JSON-First)

All commands print machine-readable JSON with a stable `schema_version` (currently `v1`).

Key commands:
- `init`: initialize directories + SQLite schema
- `crawl`: crawl docs and store pages + metadata
- `discover-sources`: mine registry seed pages for sitemap/spec URLs (best-effort bootstrap)
- `inventory`: enumerate doc URLs for a section (best-effort, deterministic)
- `fetch-inventory`: fetch every URL from an inventory (use `--resume` to continue pending/error after interruption)
- `sync`: inventory + fetch orchestration (cron-friendly JSON output)
- `report`: convert sync JSON into a human-readable Markdown report
- `ingest-page`: ingest browser-captured HTML/markdown into the canonical store
- `search-pages`, `get-page`: query stored sources
- `validate-registry`, `validate-base-urls`: reconfirm registry truth
- `import-openapi`, `import-postman`: deterministically import endpoint skeletons from machine-readable specs (recommended when available)
- `import-asyncapi`: AsyncAPI import (currently a stub; will return `ENOTIMPL`)
- `coverage-gaps`, `coverage-gaps-list`: compute and persist aggregated endpoint completeness gaps
- `detect-stale-citations`: enqueue review items when cited sources drift
- `save-endpoint`, `search-endpoints`: ingest/search structured endpoint records
- `coverage`: aggregate endpoint `field_status` coverage (unknown/undocumented/documented counts)
- `review-list`, `review-show`, `review-resolve`: manage review queue
- `answer`: assemble cite-only answers from the local store
- `fsck`: detect store inconsistencies

See `cex-api-docs --help` and `src/cex_api_docs/cli.py` for exact flags.

## Cite-Only Answers

`cex-api-docs answer ...` returns one of:
- `status: "ok"`: claims with citations
- `status: "needs_clarification"`: you must re-run with `--clarification <id>`
- `status: "unknown"`: not supported or not backed by stored sources

Notes:
- v1 MVP supports `answer` only for Binance. Other exchanges are crawlable/searchable, but not yet assembled into structured answers.
- Some questions are intentionally treated as ambiguous (for example “unified trading”) and require clarification.

Example clarification loop:

```bash
cex-api-docs answer "What's the rate limit difference between Binance unified trading endpoint and Binance spot endpoint?" --docs-dir ./cex-docs
# => status=needs_clarification with options like "binance:portfolio_margin"
cex-api-docs answer "..." --clarification binance:portfolio_margin --docs-dir ./cex-docs
```

## Endpoint JSON Ingestion (Deterministic)

This project supports ingesting agent-generated endpoint records into SQLite for fast search and review.

- Schema: `schemas/endpoint.schema.json`
- Ingest: `cex-api-docs save-endpoint path/to/endpoint.json`
- Search: `cex-api-docs search-endpoints "subaccount balance" --exchange binance`
- Coverage: `cex-api-docs coverage --exchange binance`

The expectation is that endpoint JSON includes per-field provenance for high-risk fields (permissions, rate limits, etc.): URL, crawl hashes, and a mechanically-verifiable excerpt.

### Machine-Readable Spec Imports (Preferred)

When an exchange publishes an OpenAPI/Swagger spec or a Postman collection, you can import it deterministically into the endpoint DB:

```bash
cex-api-docs import-openapi --exchange binance --section spot --url "https://example.com/openapi.yaml" --base-url "https://api.binance.com"
cex-api-docs import-postman --exchange binance --section spot --url "https://example.com/collection.json" --base-url "https://api.binance.com"
```

These imports:
- ingest the spec into the canonical store (so citations are verifiable)
- create one endpoint record per operation/request
- set `field_status` for a standard required field set
- mark only fields with verifiable citations as `documented` (everything else defaults to `unknown`)

## Store Layout

Default store root: `./cex-docs/` (override via `--docs-dir` everywhere).

Important paths:
- `cex-docs/db/docs.db`: SQLite database (pages, FTS, endpoints, review queue)
- `cex-docs/raw/`: raw HTML responses
- `cex-docs/pages/`: extracted markdown files
- `cex-docs/meta/`: per-page crawl metadata (JSON)
- `cex-docs/endpoints/`: ingested endpoint JSON blobs (as files, plus DB rows)
- `cex-docs/review/queue.jsonl`: review queue log (append-only)
- `cex-docs/crawl-log.jsonl`: crawl run log (append-only)

## How It Works (Tech Overview)

- Crawler
  - Fetches pages with `requests`
  - Extracts links + text, converts HTML to markdown (`beautifulsoup4`, `html2text`)
  - Respects `robots.txt` by default (override with `--ignore-robots`)
  - Handles UA-dependent 403s via multi-UA retry logic (some doc sites block “bot-like” UAs)
- Canonicalization + content addressing
  - Canonical URL normalization keeps storage deterministic
  - Content hashes and path hashes make it cheap to detect changes and build citations
- SQLite + FTS5
  - `pages` and `pages_fts` power full-text search over crawled markdown
  - `endpoints` and `endpoints_fts` power endpoint search
  - `endpoint_sources` records per-field provenance links back to specific crawled pages/hashes
- Rendering modes
  - `--render http` (default): fast, requests-based fetching
  - `--render playwright`: browser rendering for JS-heavy docs (optional dependency)
  - `--render auto`: uses HTTP first, falls back to Playwright when extraction is empty/non-2xx

## Development

Run tests:

```bash
.venv/bin/python -m pytest -q
```

## Docs / References

- Authoritative plan: `docs/plans/2026-02-09-feat-cex-api-docs-cite-only-knowledge-base-plan.md`
- Smoke report example: `docs/reports/2026-02-10-cex-api-docs-smoke-report.md`
- Runbook (Binance wow query): `docs/runbooks/binance-wow-query.md`
- Runbook (browser capture ingestion): `docs/runbooks/ingest-page.md`
- Troubleshooting (UA 403 + seed drift): `docs/solutions/integration-issues/ua-403-exchange-docs-crawler-tooling-20260210.md`
- “Critical patterns” required reading: `docs/solutions/patterns/critical-patterns.md`
- Agent skill: `skills/cex-api-docs/SKILL.md`

## License

MIT
