# Crawl + HTML Conversion Hardening Plan (Tool + Skill)
Date: 2026-02-26
Status: Proposed

## Goal
Make crawling/scraping and HTML→markdown conversion production-ready for team use, while keeping query skill behavior reliable and token-efficient.

## Scope
- Tooling: `sync`, `inventory`, `fetch-inventory`, `httpfetch`, `page_store`, `markdown`, quality checks.
- Skill: `.claude/skills/cex-api-query/SKILL.md` routing/output rules.
- Non-goals: hosted service, auth’d exchange API calls, trading execution.

---

## Research Verification (summary)

### Verified standards / primary sources
1. **Robots semantics + caching guidance**
   - RFC 9309: 4xx robots unavailable => crawler may proceed; 5xx/network unreachable => assume disallow; cache guidance includes 24h recommendation.
2. **Conditional revalidation**
   - RFC 9110/9111: `If-None-Match`, `If-Modified-Since`, and `304 Not Modified` are standard for efficient refresh.
3. **Rate-limit backoff semantics**
   - RFC 6585 defines `429` and optional `Retry-After`.
   - RFC 9110 defines `Retry-After` formats (seconds or HTTP-date).
   - urllib3 exposes `respect_retry_after_header` and retry controls.
4. **Headless/headed reliability context**
   - Chrome docs: modern headless is unified with Chrome codepath (not old separate implementation).
   - Playwright docs: headless defaults true; headed primarily for debugging/interactive flows.
5. **Extraction/chunking best practice**
   - Unstructured docs: element-aware chunking and dedicated `Table`/`TableChunk` treatment.
   - Pandoc docs: conversion from richer formats to markdown can be lossy.
   - MarkItDown/Trafilatura docs: LLM-focused markdown output and configurable structural preservation.

### Local evidence (repo/store)
- Store report baseline: ~3,819 pages, ~3,428 endpoints.
- Latest inventory entries: 7,133 with large overlap (~42% duplicate entries by canonical URL).
- High overlap in some exchange sections (notably Binance family and KuCoin sections).
- Markdown currently preserves many code blocks as `[code]...[/code]` markers, which is workable but suboptimal for downstream retrieval/chunking.

---

## Priority Plan (phased)

## Phase 0 — Measurement Harness (1 day)

### Deliverables
1. Add `scripts/bench_crawl_refresh.py` to benchmark:
   - full sync latency
   - resume latency
   - bytes transferred
   - per-domain error/429 rates
2. Add `scripts/bench_extraction_quality.py` on a fixed gold page set:
   - code-block preservation score
   - table preservation score
   - link preservation score
   - chunk quality signals (avg chunk length, heading integrity)
3. Save baseline artifact under `reports/` and `logs/`.

### Acceptance
- Reproducible benchmark command with JSON output checked into docs.

---

## Phase 1 — De-duping inventory/scope (2–3 days)

### Problem
Heavy cross-section overlap causes redundant crawling, higher block risk, and wasted indexing time.

### Changes
1. Registry policy extension in `data/exchanges.yaml`:
   - add explicit section `scope_prefixes` where missing
   - optional `scope_group` and `scope_priority`
2. Inventory filter hardening in `src/xdocs/inventory.py`:
   - apply strict scope filtering before queue expansion
   - add diagnostics (`dropped_out_of_scope`, `dropped_owned_by_other_section`)
3. Introduce ownership cache table (SQLite) for cross-section URL claims:
   - `inventory_scope_ownership(canonical_url, exchange_id, section_id, scope_group, inventory_id, owned_at)`
4. Sync/report updates to surface dedupe metrics.

### Tests
- New/updated inventory tests for overlap scenarios and deterministic ownership behavior.

### Acceptance
- Duplicate-entry ratio drops materially (target: from ~42% to <=15% on latest inventories).
- No regression in fetched unique pages.

---

## Phase 2 — Conditional revalidation + 304 flow (2 days)

### Problem
Refresh runs re-download too much content even when unchanged.

### Changes
1. `src/xdocs/httpfetch.py`
   - accept optional conditional headers (`If-None-Match`, `If-Modified-Since`)
   - pass through 304 status cleanly
2. `src/xdocs/inventory_fetch.py`
   - load stored ETag/Last-Modified for each URL
   - on 304: mark revalidated unchanged, skip markdown rewrite
3. DB schema additions in `schema/schema.sql` + migration:
   - `inventory_entries.last_etag`, `last_last_modified`, `last_cache_control`
4. CLI/report metrics:
   - `revalidated_unchanged` count
   - percentage revalidated per section/domain

### Tests
- integration test with local test server supporting ETag/Last-Modified and 304.

### Acceptance
- Resume refresh bandwidth/time reduction on unchanged corpus.
- Stable correctness: no false updates on 304.

---

## Phase 3 — Retry-After-aware throttling (2 days)

### Problem
Static delay is too rigid under dynamic server load/ratelimiting.

### Changes
1. `httpfetch.py`
   - capture `Retry-After` response header
2. `inventory_fetch.py`
   - extend domain limiter to maintain `next_allowed_at` per domain
   - parse both Retry-After formats (seconds/date)
   - adaptive delay escalation/de-escalation
3. CLI flags
   - `--adaptive-delay` (default on)
   - `--max-domain-delay`
4. logs/reporting
   - per-domain delay snapshots and `retry_after_applied` counters

### Tests
- unit tests for Retry-After parsing and limiter behavior.
- integration test with synthetic 429+Retry-After responses.

### Acceptance
- Fewer transient errors under aggressive domains.
- Reduced retries/timeouts in repeated runs.

---

## Phase 4 — HTML→Markdown fidelity upgrade (3–4 days)

### Problem
Code/table structures are preserved inconsistently for retrieval and citations.

### Changes
1. `src/xdocs/markdown.py`
   - add normalization pass to convert `[code]...[/code]` to fenced blocks
   - preserve table structure better (markdown tables or structured fallback blocks)
2. `src/xdocs/page_store.py`
   - persist optional sidecar metadata for blocks (heading/code/table offsets)
3. Optional extractor fallback path
   - configurable secondary extractor for pages failing quality thresholds
4. Add extraction config version bump and store metadata hash update.

### Tests
- new `tests/test_markdown.py` and fixtures for code/table heavy docs.
- verify no regression on existing page extraction corpus.

### Acceptance
- measurable gains on extraction benchmark:
  - code-block preservation +20% target
  - table preservation +20% target

---

## Phase 5 — Skill hardening (1–2 days)

### Goal
Ensure fresh sessions consistently use high-quality retrieval path with clear evidence links.

### Changes
1. Update `.claude/skills/cex-api-query/SKILL.md`:
   - explicit semantic-first route with bounded fallback budget
   - mandatory retrieval audit fields
   - mandatory source link policy
2. Add startup guard snippet for new sessions:
   - “use cex-api-query skill for CEX API doc questions”
3. Add skill eval cases in `EVALUATIONS.md`:
   - ambiguous multi-exchange query
   - permission/rate-limit comparison table
   - error-code remediation path

### Acceptance
- stress prompts stay within target context budget and include audit.
- session logs show semantic route used by default for NL queries.

---

## Phase 6 — Demo workspace + ops (1 day)

### Changes
1. Align demo workspace skill files with main repo (single source of truth).
2. Add launchd-runner docs + sample plist for background sync.
3. Add “overnight safe” and “fast daytime” presets.

### Acceptance
- teammate can clone/open demo and run one query with expected skill/tool routing.

---

## Rollout / Risk Control

1. Keep all major behavior behind flags for one release cycle.
2. Run A/B on same corpus before defaults flip.
3. Keep raw HTML as source-of-truth to allow re-extraction.
4. Add migration dry-run command and backup note before schema upgrade.

---

## Concrete File Touch Map

- `src/xdocs/inventory.py`
- `src/xdocs/inventory_fetch.py`
- `src/xdocs/httpfetch.py`
- `src/xdocs/markdown.py`
- `src/xdocs/page_store.py`
- `src/xdocs/sync.py`
- `src/xdocs/report.py`
- `schema/schema.sql`
- `data/exchanges.yaml`
- `.claude/skills/cex-api-query/SKILL.md`
- `.claude/skills/cex-api-query/EVALUATIONS.md`
- tests: inventory/fetch/markdown/rate-limiter integrations

---

## Sequencing Recommendation

Implement in this order:
1) Phase 0 baseline harness
2) Phase 1 dedupe
3) Phase 2 conditional revalidation
4) Phase 3 Retry-After/adaptive delay
5) Phase 4 conversion fidelity
6) Phase 5 skill hardening
7) Phase 6 demo/ops

Reason: biggest infra/runtime wins first, then fidelity, then skill polish.

