---
status: complete
priority: p1
issue_id: "001"
tags: [python, packaging, cli, repo]
dependencies: []
---

# Project Bootstrap (Python Package + CLI Skeleton)

## Problem Statement

We need a greenfield, reproducible project skeleton for the cite-only CEX API docs tool: Python package, JSON-first CLI entrypoint, baseline repo structure, and guardrails (gitignore, docs layout).

## Findings

- Repo is greenfield; reference-only drafts live under `cex-api-docs-plan-handoff/`.
- Authoritative plan/spec:
  - `docs/plans/2026-02-09-feat-cex-api-docs-cite-only-knowledge-base-plan.md`
  - `architect/prompt.md`

## Proposed Solutions

### Option 1: Minimal Python + argparse (recommended)

**Approach:** Use `pyproject.toml` + `src/` layout and `argparse` for CLI. Keep dependencies minimal.

**Pros:**
- Low dependency surface
- Easy to keep deterministic contracts

**Cons:**
- Slightly more boilerplate vs Typer/Rich

**Effort:** 2-4 hours

**Risk:** Low

## Recommended Action

Implement a minimal package skeleton with:
- `pyproject.toml` defining console script `cex-api-docs`
- `src/cex_api_docs/` with CLI entrypoint and shared JSON output helpers
- `.gitignore` (ignore `cex-docs/`, `.venv/`, caches, `.DS_Store`)
- Create baseline directories: `schema/`, `schemas/`, `data/`, `skills/`, `docs/runbooks/`

## Acceptance Criteria

- [x] Repo has a `.gitignore` that prevents committing `./cex-docs/`
- [x] CLI help works via `PYTHONPATH=src python -m cex_api_docs --help`
- [x] Core scaffold files exist (`pyproject.toml`, `schema/schema.sql`, `data/exchanges.yaml`, `schemas/*.json`, `skills/cex-api-docs/SKILL.md`, `docs/runbooks/binance-wow-query.md`)

## Work Log

### 2026-02-10 - Created

**By:** Codex

**Actions:**
- Created initial todo to bootstrap the repo

### 2026-02-10 - Completed Bootstrap

**By:** Codex

**Actions:**
- Added `.gitignore` with `cex-docs/` ignore and Python ignores
- Added Python package scaffold under `src/cex_api_docs/`
- Added initial config/docs:
  - `schema/schema.sql`
  - `schemas/page_meta.schema.json`
  - `schemas/endpoint.schema.json`
  - `data/exchanges.yaml` (16 exchanges, Binance split)
  - `skills/cex-api-docs/SKILL.md`
  - `docs/runbooks/binance-wow-query.md`
- Verified CLI help runs via `PYTHONPATH=src python -m cex_api_docs --help`
