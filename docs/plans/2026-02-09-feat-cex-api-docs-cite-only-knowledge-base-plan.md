---
title: "feat: Cite-Only CEX API Docs Knowledge Base"
type: feat
date: 2026-02-09
---

# feat: Cite-Only CEX API Docs Knowledge Base

## Executive Summary

Build a local-only, cite-only CEX API documentation knowledge base (Python library + JSON-first CLI + Claude Code skill) that crawls official exchange docs, stores raw + extracted content deterministically, indexes via SQLite FTS5, and enables agents to answer endpoint/rate-limit/permission questions with strict provenance.

This is greenfield. Everything under `docs/archive/cex-api-docs-plan-handoff/` is reference-only and must not be treated as implemented code or as a dependency baseline.

## Why This Exists

Exchange API documentation is fragmented across sections (spot/futures/portfolio margin/etc) and sometimes multiple doc sites per exchange. It is easy to misread:

- which endpoint families to use
- rate limit semantics (weights, per-IP vs per-UID, parameter-dependent costs, tiering)
- API key permissions/scopes required for an operation

This project eliminates that confusion by enabling provable answers backed by locally stored, cited official documentation.

## Non-Negotiable Requirements (Hard Constraints)

### Cite-Only Accuracy Policy

- No unsupported factual claims.
- Every factual statement returned must be backed by stored sources and provenance.
- Allowed output kinds:
  - `[SOURCE]` direct quotes/excerpts from stored pages.
  - `[SOURCE]` extracted structured facts with per-field citations/excerpts.
  - `[DERIVED]` deterministic computations/transforms over cited inputs (explicitly marked).
- If a requested fact cannot be backed by stored sources, return one of:
  - `unknown`: store lacks the needed sources (not crawled / not indexed).
  - `undocumented`: relevant docs were crawled, but the fact is not stated anywhere.
  - `conflict`: sources disagree; present both claims with citations, no resolution unless a source explicitly supersedes.

### Local-Only

- All crawled pages, extracted records, and search indexes stored locally (macOS).
- No hosted service. No cloud dependency for query serving.
- Using a remote LLM (Claude Code) for extraction is allowed, but retrieval must run purely from local artifacts.

### No Private Exchange API Calls

- Never require storing real API keys.
- Do not call authenticated exchange endpoints in v1.
- Crawl public docs only.

### Interfaces

- Python library API (importable).
- JSON-first CLI with stable output shape for agents/scripts.
- Primary consumption is via a Claude Code skill at `skills/cex-api-docs/SKILL.md`.

### Supported Exchanges (Registry Must Include These 16)

`binance`, `okx`, `bybit`, `bitget`, `gateio`, `kucoin`, `htx`, `cryptocom`, `bitstamp`, `bitfinex`, `dydx`, `hyperliquid`, `upbit`, `bithumb`, `coinone`, `korbit`

System must allow adding exchanges without schema changes.

## MVP Wow Query (Must Work End-to-End)

Answer cite-only:

> “What’s the rate limit difference between Binance unified trading endpoint and the Binance spot endpoint? And in order to look up the balance of our Binance subaccount in Portfolio Margin mode, what permissions does the API key need?”

Rules:
- “Unified trading” is ambiguous. The system must ask a clarifying question to resolve it to a specific Binance section unless explicitly specified.
- Binance Spot vs Futures vs Portfolio Margin must be treated as distinct sections with distinct doc sources.

## System Design (Decision-Complete)

### AI-Native Boundary

- Agent responsibilities:
  - interpret documentation
  - decide which pages matter
  - extract endpoint records into JSON that includes per-field provenance + excerpts
  - canonical mapping (optional v1)
- Code responsibilities (deterministic only):
  - crawl/fetch and store raw bytes + extracted markdown + metadata
  - compute hashes
  - write/read SQLite
  - query/diff
  - validate and ingest endpoint JSON
  - manage review queue
  - assemble cite-only answers strictly from stored artifacts (no new interpretation)

No heuristic endpoint parsers in code (no regex “guessing”).

### Store Root and Layout (Authoritative)

Default store root: `./cex-docs/` (override `--docs-dir`).

```
cex-docs/
  db/
    docs.db
  raw/
    {domain}/{path_hash}.bin
  pages/
    {domain}/{path_hash}.md
  meta/
    {domain}/{path_hash}.json
  endpoints/
    {exchange}/{section}/{endpoint_id}.json
  review/
    queue.jsonl
  crawl-log.jsonl
```

### Exchange Registry (Authoritative)

Path: `data/exchanges.yaml`.

Minimum fields per exchange:
- `exchange_id` (one of the 16 in v1)
- `display_name`
- `allowed_domains[]`
- `sections[]` each with:
  - `section_id`
  - `base_urls[]`
  - `seed_urls[]`
- Optional:
  - `playwright_ready_selectors[]`
  - `playwright_max_wait_s`
  - `robots_url`
  - `tos_url`

Binance requirement:
- Must have multiple `sections` (at least `spot` and `portfolio_margin`).
- Do not collapse sections unless docs explicitly state equivalence.

### Page Provenance Requirements

For every stored page:
- `url` (requested)
- `final_url` (after redirects)
- `redirect_chain[]`
- `crawled_at`
- `http_status`
- `content_type`
- `raw_hash` (sha256 of bytes)
- `content_hash` (sha256 of extracted markdown after deterministic normalization)
- `path_hash` (sha256 of canonicalized final_url)
- `render_mode` (`http` or `playwright`)
- selected headers (`etag`, `last-modified`, `cache-control`, `content-length` when present)

Raw is stored as `.bin` (bytes). Interpretation is via metadata.

### Deterministic Markdown Extraction (Defined)

Define one deterministic pipeline and lock it:
- Convert HTML -> markdown using `html2text` with a fixed config. Record the converter name+version+config in page metadata so changes are auditable.
- Normalize markdown before hashing:
  - newline normalization to `\n`
  - trim trailing whitespace per line
  - collapse runs of >2 blank lines to 2
  - do not remove content heuristically (no “strip last updated” rules) in v1

Required metadata for the converter:
- `extractor.name`: `html2text`
- `extractor.version`: installed version string
- `extractor.config`: JSON object (exact keys/values used)
- `extractor.config_hash`: sha256 of canonical JSON encoding of `extractor.config`

### URL Canonicalization (Defined)

To keep `path_hash` stable and prevent duplicates, define `canonical_url` as follows (apply to `final_url`):
- Parse as URL.
- Lowercase `scheme` and `host`.
- Remove default ports (`:80` for `http`, `:443` for `https`).
- Remove fragment (`#...`) entirely.
- Normalize path by removing dot-segments. Preserve a trailing slash if present in the original path (except root).
- Preserve the query string exactly as received (do not sort or drop parameters in v1).
- Recompose as `scheme://host[:port]/path[?query]`.

Compute:
- `path_hash = sha256(canonical_url)`

Store `canonical_url` in page metadata and the DB.

### SQLite Schema (Authoritative)

DB path: `cex-docs/db/docs.db`. FTS5 required; fail fast if unavailable.

Minimum tables:
- `crawl_runs`
- `pages`
- `page_versions`
- `links` (optional to populate in v1 but table exists)
- `pages_fts` (FTS5 over markdown)
- `endpoints`
- `endpoint_sources` (endpoint_id + field_name -> page_url + page_content_hash)
- `endpoints_fts` (FTS5 over endpoint text + key fields)
- `review_queue`

Schema contract:
- Check in `schema/schema.sql` as the source of truth.
- Tests must assert required tables/columns exist.

FTS operations:
- Provide `fts-optimize` and `fts-rebuild`.
- Do not use ad-hoc drop/recreate patterns.

### Crawling Requirements (Defined Behavior)

Safety defaults (override by flags):
- `timeout_s=20`
- `max_bytes=10_000_000`
- `max_redirects=5`
- `delay_s=1.0`
- `retries=2` with exponential backoff + jitter for 429/5xx

Domain scoping:
- Strict allowlist by `allowed_domains` and/or `--domain-scope`.
- Only `http`/`https` schemes.

Robots.txt (RFC9309-aligned semantics):
- 2xx: parse and apply rules for the crawler user-agent.
- 4xx: treat as allow.
- 5xx or network error/timeout: treat as disallow all until a later successful robots fetch.
- `--ignore-robots` override.

JS-rendered docs:
- `--render http|playwright|auto`
- Avoid `networkidle`; use `domcontentloaded` + explicit readiness checks:
  - selectors from registry when provided
  - otherwise, content length threshold + primary content container heuristic (documented)

Change detection:
- Store `prev_content_hash`.
- `diff` reports new/updated/stale pages.
- If a source page changes, endpoints citing that page+field must be queued for re-review via `endpoint_sources`.

Atomicity:
- Writes for a page update must be consistent: raw/meta/page/DB should not diverge.

### Excerpts and Citations (Defined)

To avoid “citation spray”, citations must be mechanically verifiable against stored markdown.

Rules:
- Every citation `excerpt` MUST be a verbatim substring of the stored markdown for the cited page content hash.
- Excerpts must be short and stable:
  - default target length 200-400 characters
  - hard max 600 characters
- Citations include offsets into the markdown string so audits can confirm exact provenance without re-running heuristics.

Citation object (used in CLI outputs and endpoint per-field sources):
- `url`
- `crawled_at`
- `content_hash`
- `path_hash`
- `excerpt`
- `excerpt_start` (0-based char offset into markdown)
- `excerpt_end` (exclusive)
- optional `field_name` (when citing extracted endpoint fields)

If an excerpt cannot be produced for an asserted high-risk field (`required_permissions`, `rate_limit`, `error_codes`), the field must be set to `undocumented` and a review item must be enqueued.

### Endpoint Extraction (Agent-Produced JSON)

Endpoint record schema requirements:
- `exchange`, `section`
- `protocol`: `http|ws|rpc|other`
- HTTP fields: `method`, `path`, `base_url`, `api_version` (nullable if docs unversioned)
- `description`
- `parameters`, `headers` (when documented)
- `required_permissions` (exchange-native strings + notes)
- `rate_limit` (weight/limit/type/conditions/notes)
- `error_codes` (when documented)
- `sources[]` (one or more)
- per-field sources for high-risk fields (`required_permissions`, `rate_limit`, `error_codes`), each requiring:
  - `url`, `crawled_at`, `content_hash`, `excerpt` (mandatory if field asserted as documented)
- extraction metadata:
  - `model`
  - `temperature=0`
  - `prompt_hash`
  - `input_content_hash`

Endpoint identity:
- `endpoint_id = sha256("{exchange}|{section}|{protocol}|{base_url}|{api_version}|{method}|{path}")`

Confidence/review rules:
- If not explicitly documented, mark field `undocumented`.
- If excerpt cannot be captured for an asserted high-risk field, set that field to `undocumented` and enqueue review item.
- Any `confidence != high` enqueues a review item.

Translation:
- Translations are `[DERIVED]`.
- Store original excerpt + language code.
- Never treat translation as sole source of truth.

### CLI (Decision-Complete Contracts)

CLI name: `cex-api-docs`. All commands accept `--docs-dir`.

Commands:
- `init`
- `crawl`
- `search-pages`
- `get-page`
- `diff`
- `save-endpoint`
- `search-endpoints`
- `review-list`, `review-show`, `review-resolve`
- `fts-optimize`, `fts-rebuild`
- `answer` (required for demo; assembler only)

Output contract (every command):
- stdout JSON:
  - `ok: true|false`
  - `schema_version: "v1"`
  - `result: {...}` on success
  - `error: { code, message, details }` on failure
- stderr: logs only
- any command returning facts must include claim-level citations:
  - per-claim/per-field `sources[]` with `excerpt`

### Single-Writer Enforcement (Defined)

SQLite is single-writer in practice for reliability. Enforce this at the CLI level with a lockfile.

Rules:
- Commands that mutate the store MUST acquire an exclusive lock:
  - `init`, `crawl`, `save-endpoint`, `review-resolve`, `fts-optimize`, `fts-rebuild`
- Lock path: `cex-docs/db/.write.lock` under the active `--docs-dir`.
- Lock behavior:
  - wait up to `--lock-timeout-s` (default 10)
  - if lock cannot be acquired, return `ok:false` with `error.code="ELOCKED"`
- Always release lock on exit (including exceptions).

Note: parallel agents may produce endpoint JSON files, but DB ingestion is serialized via this lock.

### Library API (Minimal)

Expose stable functions mirroring CLI:
- open/create store
- crawl
- search pages
- upsert endpoint record
- query endpoints
- compute diffs
- manage review queue
- assemble cite-only answer (same output as CLI `answer`)

## SpecFlow (Required Validation)

### User Flow Overview

1. `init` store
2. `crawl` one or more doc sections
3. `search-pages` to find relevant pages (rate limits, auth/permissions)
4. agent extracts endpoint JSON with provenance/excerpts
5. `save-endpoint` ingests endpoint JSON and updates DB/FTS + review queue
6. `search-endpoints` answers structured queries
7. `answer` assembles cite-only response (or clarifies ambiguity)
8. periodic `crawl` + `diff` triggers re-review for impacted endpoint fields

### Flow Permutations Matrix

| Dimension | Variants | Required system response |
|---|---|---|
| Query ambiguity | “unified trading” unclear | `needs_clarification` with choices drawn from sections present in local store |
| Missing sources | docs not crawled | `unknown` with suggestion of which exchange/section to crawl |
| Missing documentation | docs crawled but field absent | `undocumented` citing pages searched |
| Conflicting pages | docs disagree | `conflict` returning both claims with citations |
| JS-only docs | empty HTML | `--render auto` uses Playwright and records `render_mode` |
| Robots unreachable | 5xx/timeouts | disallow crawl for that domain until robots fetch succeeds |
| Multi-site exchanges | Binance spot vs PM | registry sections ensure no conflation |

### Missing Elements & Gaps (Closed Here)

- Clarification UX in `answer` is explicitly required and defined.
- Derived computations are explicitly constrained and labeled.
- Review queue triggers are explicitly defined.

## Implementation Plan (Phases, No Decisions Left)

## Progress Checklist

- [x] Phase 0: Repo bootstrap artifacts (`pyproject.toml`, `schema/schema.sql`, `schemas/*.json`, `data/exchanges.yaml`, `skills/cex-api-docs/SKILL.md`, `docs/runbooks/binance-wow-query.md`)
- [x] Phase 1: Store + DB + FTS (`init`, schema apply, FTS5 check, schema versioning, lockfile)
- [x] Phase 2: Crawl + Page Index (`crawl`, persistence, `search-pages`, `get-page`, `diff`, `fts-*`)
- [x] Phase 3: Endpoint Ingest + Query (`save-endpoint`, `search-endpoints`, review queue, endpoint_sources)
- [x] Phase 4: Answer + Binance demo (`answer` output schema + runbook reproducibility)
- [x] Phase 5: Tests and quality gates (unit + integration tests)

### Phase 0: Repo Bootstrap (1 day)

Deliverables:
- `pyproject.toml` with console script `cex-api-docs`
- `schema/schema.sql`
- `schemas/endpoint.schema.json` and `schemas/page_meta.schema.json`
- `data/exchanges.yaml` with 16 exchanges and Binance section split
- `skills/cex-api-docs/SKILL.md` with strict cite-only instructions
- `docs/runbooks/binance-wow-query.md`

Acceptance:
- teammate can run: venv -> install -> `cex-api-docs --help`

### Phase 1: Store + DB + FTS (1–2 days)

Implement:
- `init` creates directories + db + tables + fts
- FTS5 availability check
- versioning mechanism for schema

Acceptance:
- `init` is idempotent
- DB schema matches `schema/schema.sql`

### Phase 2: Crawl + Page Index (2–4 days)

Implement:
- deterministic crawler with domain allowlist, robots semantics, limits, retries, delay
- raw/meta/pages persistence
- `search-pages`, `get-page`
- `diff`
- `fts-optimize`, `fts-rebuild`

Acceptance:
- fixture crawl works offline in tests
- live crawl of one doc section works end-to-end on macOS

### Phase 3: Endpoint Ingest + Endpoint Query (2–4 days)

Implement:
- endpoint JSON schema validation
- `save-endpoint` writes endpoint JSON to disk + DB
- `endpoint_sources` mapping persisted
- `search-endpoints` supports filters: exchange, section, method, path, permission keyword, error-code keyword
- review queue commands

Acceptance:
- ingest rejects missing provenance
- review items created per confidence/excerpt rules
- page hash change triggers deterministic re-review entries for affected endpoint fields

### Phase 4: Answer Assembler + Binance Demo (2–3 days)

Implement:
- `answer` that is an assembler only: it may select and format stored facts, but MUST NOT invent or infer new facts.
- `answer` output schema is decision-complete and must be stable:

```json
{
  "ok": true,
  "schema_version": "v1",
  "status": "ok|needs_clarification|unknown|undocumented|conflict",
  "question": "string",
  "normalized_question": "string",
  "clarification": {
    "prompt": "string",
    "options": [
      {
        "id": "string",
        "label": "string",
        "exchange": "string",
        "section": "string"
      }
    ]
  },
  "claims": [
    {
      "id": "c1",
      "kind": "SOURCE|DERIVED",
      "text": "string",
      "citations": [
        {
          "url": "string",
          "crawled_at": "string",
          "content_hash": "string",
          "path_hash": "string",
          "excerpt": "string",
          "excerpt_start": 0,
          "excerpt_end": 123,
          "field_name": "string"
        }
      ],
      "derived": {
        "op": "string",
        "inputs": [
          { "claim_id": "c2" }
        ]
      }
    }
  ],
  "notes": [
    "string"
  ]
}
```

Assembler rules:
- If query references an ambiguous section (e.g., “unified trading”), return `needs_clarification` and populate `clarification.options` using Binance sections present in the local store.
- For comparisons like “rate limit difference”, only output a numeric “difference” if both input numbers are explicitly cited. Mark the difference claim as `kind:"DERIVED"` and link inputs via `derived.inputs`.
- If sources are missing: `status:"unknown"` and include notes describing which exchange/section to crawl.
- If docs were crawled but do not state the fact: `status:"undocumented"` and include citations showing what was searched.
- If sources disagree: `status:"conflict"` and include both claims with citations.

Binance demo runbook must demonstrate:
- clarification for “unified trading”
- cite-only answer after selection
- `[DERIVED]` numeric comparison only when both cited facts exist
- `undocumented` when permissions aren’t explicitly stated (with citations to searched sources)

## Testing Plan (Definition-Complete)

Unit tests:
- markdown normalization hashing determinism
- URL canonicalization and `path_hash` determinism
- robots semantics: 2xx/4xx/5xx/network failure behavior
- domain scoping enforcement (reject off-domain)
- schema validation for endpoint records including excerpt requirements

Integration tests:
- local fixture site crawl producing raw/meta/pages + FTS entries
- CLI golden JSON shape tests per command
- endpoint ingest -> query roundtrip

Non-goals for tests:
- relying on live exchange docs as the only test signal (too flaky)

## Operational Plan (Local-Only)

- Provide cron-friendly invocation patterns:
  - `crawl` + `diff` + “re-review required” reporting
- Keep logs JSONL for audit:
  - `crawl-log.jsonl`
- Document retention knobs (v1):
  - max pages per run (flag)
  - optional pruning of old `page_versions` (future; document as follow-up)

## Risks and Mitigations

- “100% accurate” expectation:
  - Mitigation: strict cite-only + explicit unknown/undocumented/conflict; never guess.
- Binance ambiguity:
  - Mitigation: clarify-first contract, no conflation of sections.
- JS-rendered docs:
  - Mitigation: optional Playwright with explicit selectors and stable readiness checks.
- SQLite single-writer realities:
  - Mitigation: v1 single writer; parallel agents may produce JSON but ingestion is serialized.
- Supply chain / reproducibility:
  - Mitigation: pinned deps in package; no runtime `pip install` in default paths.

## Final Acceptance Criteria (Project-Level)

- `data/exchanges.yaml` includes all 16 exchanges and supports multiple sections per exchange.
- A user can:
  - `init` a store
  - `crawl` at least one doc section
  - `search-pages` via FTS5
  - ingest endpoint JSON and query it back with citations
  - run the Binance wow query demo with clarification and cite-only output

## References (Internal)

- Spec: `docs/archive/architect/prompt.md`
- Rationale and gap analysis: `docs/archive/architect/transcript.md`
- Prior plan (superseded): `docs/plans/2026-02-09-feat-cex-api-docs-intelligence-layer-plan.md`
- Reference-only drafts: `docs/archive/cex-api-docs-plan-handoff/`
