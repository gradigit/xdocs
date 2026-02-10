# CEX API Docs

## What This Is

A local-only, cite-only CEX API documentation knowledge base (library + CLI + agent skill) that crawls official exchange docs, stores and indexes them via SQLite FTS5, and enables agents to answer endpoint, rate limit, and permission questions with strict provenance.

## Build Commands

Quick setup (macOS):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
cex-api-docs --help
```

## Commands

```bash
# Initialize a local store (idempotent)
cex-api-docs init --docs-dir ./cex-docs

# Deterministic sync (inventory -> fetch); use --render auto for JS-heavy docs
cex-api-docs sync --docs-dir ./cex-docs --render auto

# Resume an interrupted inventory fetch
cex-api-docs fetch-inventory --exchange binance --section spot --docs-dir ./cex-docs --resume
```

## Project Structure

- `docs/plans/` Authoritative plans and design decisions.
- `docs/runbooks/` Demo/run instructions.
- `data/` Machine-readable configuration, including `data/exchanges.yaml`.
- `skills/` Claude Code skill definitions (for agent usage).
- `todos/` File-based work tracking (source of truth for follow-ups).

## Conventions

- Cite-only outputs: no unsupported claims. If not backed by sources, return `unknown` / `undocumented` / `conflict`.
- Deterministic code: crawling, storage, indexing, querying, diffing.
- Agent boundary: agent does interpretation and extraction; code does deterministic I/O and validation.
- JSON-first CLI: machine-readable output to stdout; logs to stderr.

## Key Files

- `data/exchanges.yaml` Registry of exchanges/sections, doc seeds, allowlists, and base URLs
- `schema/schema.sql` SQLite schema (pages + endpoint DB + review queue)
- `src/cex_api_docs/cli.py` CLI entrypoint
- `src/cex_api_docs/inventory.py` Inventory generation (sitemaps + deterministic link-follow fallback)
- `src/cex_api_docs/inventory_fetch.py` Fetch + persist inventory entries
- `src/cex_api_docs/playwrightfetch.py` Playwright fetch wrapper (JS-rendered docs fallback)
- `src/cex_api_docs/sync.py` Cron-friendly orchestration (inventory + fetch)
- `src/cex_api_docs/report.py` Markdown report rendering for sync JSON artifacts

## Gotchas

- `cex-docs/` is a local store and must never be committed (gitignored).
- CLI JSON is printed at the end of a command; if you redirect stdout to a file, it may stay empty until completion.
- Prefer deterministic fetch first; use `--render auto` when a docs site requires JS rendering.

## Current Phase

Phase: MVP implemented (inventory+fetch, local store+search, endpoint ingest, cite-only answer assembly, tests)

Next steps live in `todos/` (prioritized), and the “wow query” demo runbook is at:
- `docs/runbooks/binance-wow-query.md`
