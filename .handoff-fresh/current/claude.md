# Claude Onboarding — CEX API Docs

**Generated**: 2026-03-12

<!-- BEGIN SHARED-ONBOARDING-CONTEXT -->

## What This Is

Local-only, cite-only CEX API documentation knowledge base (library + CLI + agent skill). 46 exchanges, 10,727 pages, 4,963 endpoints, SQLite FTS5 + LanceDB vector search.

## Two-Repo Architecture

- **Maintainer** (`/home/lechat/Projects/xdocs`): Linux, full dev. `uv pip install -e ".[dev,semantic]"`
- **Runtime** (`/home/lechat/Projects/xdocs-runtime`): macOS, query-only. `uv pip install -e .`
- **Every push to maintainer MUST be followed by runtime sync + push** via `scripts/sync_runtime_repo.py`

## Quick Start

```bash
source /home/lechat/Projects/.venv/bin/activate  # shared venv
pytest tests/ -x -q                               # 559 tests, ~90s
xdocs --help                                # 51 subcommands
```

## Key Files

- `CLAUDE.md` — full project instructions (symlink to AGENTS.md)
- `TODO.md` — all milestones (M1-M22b done) + open bugs (BUG-15 through BUG-21)
- `data/exchanges.yaml` — registry of 46 exchanges, 78 sections
- `schema/schema.sql` — SQLite DDL (schema v6)
- `src/xdocs/answer.py` — cite-only answer assembly (main query pipeline)
- `src/xdocs/classify.py` — input classification (error/endpoint/payload/code/question)
- `src/xdocs/fts_util.py` — FTS5 utilities (sanitize, BM25, RRF, blend)
- `src/xdocs/semantic.py` — LanceDB vector/hybrid search
- `tests/golden_qa.jsonl` — 206-query benchmark across 37 exchanges
- `tests/eval_answer_pipeline.py` — pipeline evaluation (MRR, nDCG@5)

## Current Metrics

MRR=0.644, nDCG@5=1.343, PFX=78%, URL=65%, domain=97%, OK=92%. 559 tests.

## Open Bugs (High Priority)

- **BUG-18**: Direct-route citations missing excerpts (answer.py ~L1223/1258/1266)
- **BUG-15**: Numeric literals → error_message (classify.py `\d{5,6}`)
- **BUG-16**: Nav chrome in excerpts (`_is_nav_region` threshold)

## Conventions

- Cite-only: no unsupported claims. Return `unknown`/`undocumented`/`conflict` when uncertain.
- JSON-first CLI: stdout for data, stderr for logs.
- A/B test every pipeline change independently before merging.
- Skills stay in sync with store — update docs after any significant change.

<!-- END SHARED-ONBOARDING-CONTEXT -->
