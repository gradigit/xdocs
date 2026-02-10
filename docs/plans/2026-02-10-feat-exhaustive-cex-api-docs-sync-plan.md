---
title: "feat: Exhaustive CEX API Docs Sync + Field-Complete Endpoint DB"
type: feat
date: 2026-02-10
---

# feat: Exhaustive CEX API Docs Sync + Field-Complete Endpoint DB

## Executive Summary

Turn `cex-api-docs` into an agent-first, local-only system that can:

- deterministically **enumerate and download** *all publicly documented* “production sections” for all configured exchanges
- keep a **diffable history** of documentation changes (cron-friendly)
- maintain a **field-complete endpoint database** where every required field is either:
  - `documented` with mechanically verifiable citations, or
  - `undocumented` and flagged for human review
- support an escalation path: deterministic fetch first, then **browser-assisted capture** (Playwright/agent-browser/manual) when deterministic fetch fails

This plan explicitly ignores truly undocumented endpoints. “Exhaustive” means: exhaustive relative to *public official documentation sources we can enumerate*.

## Goals (Non-Negotiable)

1. **Exhaustive docs acquisition**
   - For every exchange and every production section, download all docs pages into the local store.
   - Persist provenance and enable deterministic diffs between runs.

2. **Field-complete endpoint DB**
   - For every endpoint, required fields are always present as one of:
     - `documented` (value + per-field citation excerpt),
     - `undocumented` (explicit, with review flag), or
     - `unknown` (sources not yet acquired; also flagged).

3. **Agent-first interface**
   - CLI remains JSON-first, stable output.
   - Agents can drive the CLI; if deterministic fetch fails, the agent falls back to browser tooling.

4. **Local-only**
   - All docs, indexes, endpoint DB, and reports are local.
   - No hosted service required.

## Non-Goals (For This Phase)

- Perfect “chat UI” or hosted query experience. (We will lay the data foundation so it’s easy to add later.)
- Calling authenticated exchange APIs or storing API keys.
- Guaranteeing anything about endpoints not present in official public docs.

## Definitions

- **Exchange**: an entry in `data/exchanges.yaml`.
- **Production section**: a publicly documented product area for that exchange (spot, wallet, futures, etc). We treat “production section” as a *discovered + curated* list per exchange, not a guess.
- **Doc source**: an authoritative way to enumerate pages and/or endpoints for a section (sitemap, OpenAPI, Postman, nav index).
- **URL inventory**: the full list of doc URLs we believe belong to a section, derived deterministically from doc sources.
- **Field-complete**: for a configured required field set, every endpoint has either a cited value or an explicit `undocumented`/`unknown` status.
- **Variant (parameter-level variation)**: one `METHOD + PATH` whose documented behavior differs under specific conditions (accountType/marginMode/orderType/etc). Variants are modeled explicitly, not silently merged.

## Architecture (Agent Boundary)

### Deterministic core (code)

Code is responsible for deterministic I/O:

- inventory generation (deterministic enumeration of URLs and endpoint lists)
- fetching/downloading + storing pages
- hashing + versioning + diffing
- schema validation and deterministic ingestion of endpoint JSON
- mechanical citation verification against local store
- generating coverage and drift reports

### Agent/human responsibilities

- resolving “fetch failures” that require interactive browser steps (captcha/WAF/JS edge cases)
- extracting endpoint fields from local docs when no machine-readable spec exists (or specs omit fields)
- marking fields `undocumented` when not stated, and triaging human review flags

## Data Model Changes

### 1) Registry: expand from “seed URLs” to “section sources”

Extend `data/exchanges.yaml` to support multiple sources per section:

- `sections[].doc_sources[]` (new)
  - `kind`: `sitemap|openapi|postman|asyncapi|nav_index|other`
  - `url`: canonical source URL
  - `scope`: optional path prefix constraint
  - `notes`: optional
- `sections[].inventory_policy` (new)
  - `mode`: `inventory` (default) or `link_follow` (fallback only)
  - `max_pages`: optional override
  - `render_mode`: `http|playwright|auto`

Keep `seed_urls[]` as human-friendly entry points, but do not rely on them for “exhaustive”.

### 2) Store DB: add inventory + sync metadata

Add tables (or JSONL logs if we choose minimal DB changes) to persist:

- `inventories` (exchange, section, generated_at, sources_json, counts)
- `inventory_entries` (inventory_id, canonical_url, status, last_fetch_http_status, last_content_hash)
- `sync_runs` (started_at, ended_at, config_json)

Minimum requirement: inventories must be reproducible and diffable. DB tables are preferred over ad-hoc files.

### 3) Endpoint record schema: field status + variants

Extend `schemas/endpoint.schema.json` to add:

- `field_status`: object mapping required field names to:
  - `documented|undocumented|unknown|conflict`
- `variants`: optional array
  - each variant has:
    - `when`: human/agent-readable condition (string or structured)
    - field overrides with their own citations/status

Update `save-endpoint` ingestion rules:

- If a field is `documented`: require a per-field citation (`field_name` in `sources[]`) and verify excerpts.
- If a field is `undocumented`/`unknown`: do not require citations, but do emit a review/coverage signal.

### 4) Review/flags: scale-aware

Avoid creating millions of per-endpoint review items.

- Keep `review_queue` for actionable, specific issues (stale citation, schema failure, conflicting citations).
- Add coverage-gap aggregation:
  - one review item per `(exchange, section, field_name)` summarizing counts and samples, OR
  - a dedicated `coverage_gaps` table/report.

## New/Changed CLI Commands (JSON-First)

### Source acquisition

- `discover-sources` (new)
  - input: `--exchange`, optional `--section`
  - output: proposed `doc_sources` candidates (sitemap/spec URLs) + confidence + evidence
  - purpose: bootstrap registry expansion without manual guessing

- `inventory` (new)
  - input: `--exchange`, `--section`
  - output: deterministic URL list + counts + source provenance

- `fetch-inventory` (new)
  - input: `--exchange`, `--section`, `--inventory-id` optional
  - behavior: fetch every URL in the inventory into the store, respecting allowlists and throttling
  - output: counts + failures list

- `sync` (new, orchestration)
  - runs: inventory -> fetch -> diff -> fsck -> stale-source detection -> coverage report
  - output: a single stable JSON report (for cron)

### Browser-assisted capture path

- `ingest-page` (new)
  - input: `--url`, plus one of:
    - `--html-path` (preferred)
    - `--markdown-path` (fallback)
  - behavior:
    - canonicalize URL, compute hashes, run the same extractor pipeline, write to `raw/`, `pages/`, `meta/`, and DB
    - mark `render_mode=ingest` + capture tool metadata (agent-browser/manual)
  - purpose: unify “AI browser fallback” artifacts into the same store with normal hashes/versions

### Endpoint enumeration/import

- `import-openapi` (new)
- `import-postman` (new)
- `import-asyncapi` (new)

These produce endpoint skeleton records for every operation, setting:
- method/path/base_url/api_version/description/params/req/resp schema when available
- `field_status` for missing fields (permissions/rate limits/errors often missing)
- citations for any fields sourced from docs pages (when possible)

### Drift / completeness

- `coverage` (new)
  - per exchange/section: endpoints count, documented vs undocumented per field, review backlog pointers

- `detect-stale-citations` (new)
  - find endpoint fields whose cited `page_content_hash` no longer matches the current page hash for that URL
  - create targeted review items for re-extraction

- `report` (new; optional)
  - convert the JSON sync output into a Markdown report suitable for humans

## Operational Workflow (Cron-Friendly)

### Daily sync run (deterministic first)

1. `sync --all` (or per exchange) generates inventories and fetches them.
2. Produces:
   - page-level diff (new/updated/stale)
   - base URL reachability drift
   - stale citations detection
   - coverage metrics and aggregated gaps
3. Emits stable JSON for automation and optionally a Markdown report.

### When deterministic fetching fails

1. `sync` returns failures with reasons (403/captcha/timeout/empty extraction).
2. Agent picks failures and uses:
   - `--render playwright|auto` retries first
   - if still blocked, uses AI browser tooling to reach the final content
3. Agent exports HTML (or text) and runs `ingest-page` so the store remains canonical.
4. Re-run inventory fetch for that section; failures should shrink over time.

### Human review loop for completeness

1. Coverage report highlights fields/endpoints with `undocumented`/`unknown`.
2. Humans (or extraction agents) fill missing fields by:
   - locating authoritative pages via `search-pages`
   - adding cited values to endpoint JSON
   - ingesting via `save-endpoint`
3. Over time, coverage approaches 100% “field complete” (where fields are either documented or explicitly undocumented).

## Implementation Plan (Phased, Decision-Complete)

### Phase 0: Lock the “Exhaustive” Contract

- [ ] Define the required field set per protocol:
  - HTTP: `method`, `path`, `base_url`, `description`, `request_schema`, `response_schema`, `required_permissions`, `rate_limit`, `error_codes`
  - WS: `base_url`, `topics/channels`, `auth_requirements`, `rate_limit`, `error_codes` (as applicable)
- [ ] Define “field complete” as “documented OR explicitly undocumented/unknown”.
- [ ] Add a policy doc: what “undocumented” and “unknown” mean operationally (not a claim about reality).

Acceptance:
- A single endpoint record can be declared “complete” even when docs omit a field, as long as status is explicit and flagged.

### Phase 1: Inventory-Based Exhaustive Fetch

- [ ] Implement `discover-sources` (bootstrap)
- [x] Implement `inventory` with at least:
  - sitemap parsing (`sitemap.xml`, `sitemap-index.xml`)
  - doc-site heuristics for common stacks (GitBook/Docusaurus/ReadMe/SwaggerUI) to find sitemap/spec URLs
- [x] Implement `fetch-inventory`
- [x] Add inventory persistence (DB tables) and diffing between inventories
- [ ] Update `crawl` behavior: keep link-follow as fallback only; inventory fetch is the default path to “exhaustive”

Acceptance:
- For at least 3 heterogeneous exchanges (one GitBook, one Docusaurus-like, one custom), `inventory` returns a stable URL list and `fetch-inventory` can fetch >95% without manual intervention.

### Phase 2: Browser-Assisted Ingestion Bridge

- [x] Implement `ingest-page` that writes into the normal store + DB
- [x] Add `render_mode=ingest` metadata and include tool provenance
- [x] Document a runbook: “When a URL can’t be fetched deterministically, capture HTML and ingest it”

Acceptance:
- A page captured via a browser can be ingested and then appears in `search-pages`/`get-page` with stable hashes and FTS indexing.

### Phase 3: Endpoint Enumeration (Skeleton DB for “Everything Exists”)

- [ ] Implement `import-openapi` (JSON/YAML)
- [ ] Implement `import-postman`
- [ ] Implement `import-asyncapi` (or defer if too heavy; keep as stub + plan)
- [ ] Store endpoint skeletons as endpoint JSON with `field_status` defaults:
  - if spec provides field, mark `documented` with spec citation if available
  - else mark `undocumented` or `unknown` with a flag for review
- [ ] Add `coverage` reporting for endpoint counts per exchange/section

Acceptance:
- For at least 1 exchange with OpenAPI/Postman available, import yields 100% endpoint inventory into `endpoints` and `endpoints_fts`.

### Phase 4: Field Completion Framework + Review Scaling

- [ ] Extend `schemas/endpoint.schema.json` with `field_status` + `variants`
- [ ] Update `save-endpoint` validation rules accordingly
- [ ] Implement aggregated coverage gaps:
  - create one review item per `(exchange, section, field)` summarizing missing/undocumented counts
  - provide a drill-down command to list sample endpoint_ids
- [ ] Implement `detect-stale-citations` and create targeted review items

Acceptance:
- A full sync run can output:
  - coverage numbers
  - aggregated gaps
  - stale-citation review items when docs change

### Phase 5: Sync Orchestration + Reports + Cron

- [x] Implement `sync` command (one JSON artifact per run)
- [x] Implement `report` (JSON -> Markdown) for human summaries
- [ ] Add a `scripts/` runner for macOS cron/launchd that:
  - runs `sync`
  - writes a timestamped report file
  - exits non-zero only for true failures (not for “undocumented fields”)

Acceptance:
- Cron-friendly output is stable.
- Drift signals are actionable: “these pages changed”, “these endpoints are impacted”.

## Test Plan

- Unit tests for:
  - sitemap parsing and URL canonicalization stability
  - inventory determinism (same inputs -> same outputs ordering)
  - ingest-page produces identical hashes to normal crawl when given identical HTML
  - endpoint schema validation with `field_status` and `variants`
  - stale-citation detection logic
- Integration tests (optional, quarantined):
  - a small set of real doc URLs behind a `RUN_NETWORK_TESTS=1` gate

## Risks and Mitigations

- **Docs volume is huge**: inventories can be tens of thousands of URLs.
  - Mitigate with incremental fetch (ETag/Last-Modified), per-domain throttles, and resumable sync runs.
- **WAF/captcha breaks automation**:
  - deterministic retries first; then ingest-page bridge for manual/agent-browser capture.
  - cron can alert on persistent failure counts without blocking the whole run.
- **Review backlog explosion**:
  - aggregate coverage gaps; avoid per-endpoint-per-field noise.
- **Field completeness is sometimes impossible**:
  - explicit `undocumented` is allowed and flagged; the system must never guess.

## Open Questions (Defaults Proposed)

1. **Robots policy**: default respect robots; allow `--ignore-robots` explicitly for local runs.
2. **Retention**: keep all page versions by default; add optional retention policy later (keep last N per URL).
3. **What qualifies as “production section”**: start with all public doc categories discovered from nav + sitemaps; humans can mark `section.status=deprecated|internal|ignore`.
