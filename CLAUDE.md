# CEX API Docs

## What This Is

A local-only, cite-only CEX API documentation knowledge base (library + CLI + agent skill) that crawls official exchange docs, stores and indexes them via SQLite FTS5, and enables agents to answer endpoint, rate limit, and permission questions with strict provenance.

## Build Commands

Greenfield. The implementation should provide a simple macOS setup path. Expected commands (subject to change once code exists):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
cex-api-docs --help
```

## Project Structure

- `architect/` Planning artifacts. `architect/prompt.md` is the current specification.
- `data/` Machine-readable configuration, including `data/exchanges.yaml`.
- `skills/` Claude Code skill definitions (for agent usage).
- `docs/` Plans, runbooks, and other documentation.

## Conventions

- Cite-only outputs: no unsupported claims. If not backed by sources, return `unknown` / `undocumented` / `conflict`.
- Deterministic code: crawling, storage, indexing, querying, diffing.
- Agent boundary: agent does interpretation and extraction; code does deterministic I/O and validation.
- JSON-first CLI: machine-readable output to stdout; logs to stderr.

## architect/ Directory

Read `architect/prompt.md` for the current build specification.

Notes:
- `architect/plan.md` does not exist yet. It will be created during forging-plans Mode 2 (plan iteration).
- `architect/transcript.md` contains Q&A, research, and challenge results.
- `architect/STATE.md` tracks where the forging workflow left off.

## Current Phase

Phase: not started (planning complete, execution not started)
Next step: create an execution plan (forging-plans Mode 2) from `architect/prompt.md`

## Phase Progress

- Phase 1: Plan iteration (pending)
- Phase 2: Implementation (pending)
- Phase 3: Demo wow query (pending)
