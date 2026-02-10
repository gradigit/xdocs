# Context Handoff — 2026-02-10

Session summary for context continuity after clearing.

## First Steps (Read in Order)

1. Read `CLAUDE.md` — project context, conventions, current phase, key files
2. Read `docs/plans/2026-02-10-feat-exhaustive-cex-api-docs-sync-plan.md` — the “exhaustive fetch/store” plan (and what’s already checked off)
3. Read `data/exchanges.yaml` — canonical list of exchanges/sections + seeds/domains/base URLs
4. Read `todos/` — completed + follow-up work items (especially the remaining missing sections)

After reading these files, you’ll have full context to continue.

## Session Summary

### What Was Done

- Implemented `fetch-inventory --resume` so long-running fetches can be resumed (pending/error only; includes skipped when `--ignore-robots`).
- Improved link-follow inventories to include all discovered queued URLs (not only visited URLs) to better approximate “all reachable” without requiring huge `max_pages`.
- Fixed/improved registry entries (notably `gateio/v4` seed URL) and tuned `max_pages` caps for ReadMe-heavy docs to keep inventories bounded.
- Added/updated deterministic tooling for coverage gaps + stale citation detection, plus security hardening for Playwright fetch (tests included).
- Updated `README.md` and `CLAUDE.md` to document the resume workflow and key operational gotchas.
- Created `.doc-manifest.yaml` (doc inventory + best-effort code reference tracking).

### Current State

- Branch: `feat/exhaustive-sync`
- Local store lives under `./cex-docs/` (gitignored; never commit).
- Local DB (`./cex-docs/db/docs.db`) contains many completed inventories/fetches, but **not yet all exchanges/sections** are fully inventoried and fetched (notably dYdX and a few remaining sections).
- Tests: `./.venv/bin/pytest -q` passes (20 tests).
- Last commit: `690bc9b` — WIP: harden inventory sync + docs manifest

### What's Next

1. Finish “inventory + fetch-inventory” for remaining missing sections in `data/exchanges.yaml`:
   - `kucoin/spot`, `kucoin/futures`, `upbit/rest_en`, `upbit/rest_ko`, `bitfinex/v2`, `dydx/docs`
2. For JS-heavy/slow sections (especially `dydx/docs`), lower inventory caps and rely on “queued URL capture” plus `fetch-inventory --resume` batching.
3. Run a full `sync` pass and generate a fresh Markdown report under `docs/reports/` once all 23 sections are fetched.
4. Add a cron-friendly wrapper that runs nightly and diffs inventories/pages, then writes “what changed” into reports and queues review tasks.

### Failed Approaches

- dYdX inventory with high `max_pages` was too slow and repeatedly interrupted; JSON redirected to a file stays empty until the command completes.
- Treating link-follow inventories as “visited only” undercounted reachable URLs for sidebar-heavy docs; capturing queued links is a better approximation.

### Open Questions / Blockers

- dYdX docs: pick an inventory strategy that finishes reliably (likely smaller `max_pages` + Playwright `--render auto` where needed).
- Define “exhaustive” acceptance criteria precisely:
  - Per section: all production docs pages reachable from seeds/sitemaps, within domain allowlist, stored with non-empty extracted markdown.
  - Coverage reporting: how to measure “missing fields” for endpoints when endpoint extraction is not yet run for all exchanges.

### Key Context

- Deterministic-first:
  - prefer inventory sources (sitemaps/spec URLs) and deterministic fetch
  - fallback to deterministic link-follow inventories (robots-aware, throttled, bounded)
  - if docs require JS rendering or block non-browser fetch, use `--render auto` (Playwright) or ingest via `ingest-page`
- Operational gotcha:
  - CLI prints JSON to stdout at command end; for long runs, prefer smaller batches + `fetch-inventory --resume`.

## Reference Files

| File | Purpose |
|------|---------|
| `data/exchanges.yaml` | Registry of exchanges/sections, seeds, allowed domains, base URLs |
| `src/cex_api_docs/inventory.py` | Inventory generation (sitemaps + link-follow fallback) |
| `src/cex_api_docs/inventory_fetch.py` | Fetch inventory entries into the store (supports `--resume`) |
| `src/cex_api_docs/sync.py` | Orchestrates inventory + fetch; cron-friendly JSON output |
| `src/cex_api_docs/playwrightfetch.py` | JS-rendered docs fallback fetch |
| `docs/plans/2026-02-10-feat-exhaustive-cex-api-docs-sync-plan.md` | “Exhaustive sync” plan and acceptance criteria |
| `docs/runbooks/binance-wow-query.md` | Example “wow query” workflow (Binance) |
| `docs/runbooks/ingest-page.md` | How to ingest a browser-captured page into the store |
| `.doc-manifest.yaml` | Documentation inventory + references |
