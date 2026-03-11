# CEX Docs Copilot Runtime

This repository is the **team runtime** for querying exchange API documentation.

It includes:

- query CLI/tooling (`cex-api-docs`)
- query skill (`cex-api-query`)
- prebuilt local data snapshot (`cex-docs/`)

It intentionally excludes crawling/maintainer operations from day-to-day team use.

## Quick start

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .
```

All query dependencies (including semantic search) are included by default.

Then in a fresh agent session:

```text
Use cex-api-query skill.
```

and ask your natural-language CEX API docs question.

## Update model

Maintainers publish refreshed snapshots and query-skill updates.
Team members only need:

```bash
git pull
```

## Smoke check

```bash
python scripts/runtime_query_smoke.py
```
