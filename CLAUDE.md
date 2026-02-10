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

## Current Phase

Phase: MVP implemented (crawler + search + endpoint ingest + answer + tests)

Next steps live in `todos/` (prioritized), and the “wow query” demo runbook is at:
- `docs/runbooks/binance-wow-query.md`
