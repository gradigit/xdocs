# CEX Docs Copilot Runtime

This repository is the **team runtime** for querying exchange API documentation.

It includes:

- query CLI/tooling (`cex-api-docs`)
- query skill (`cex-api-query`)
- prebuilt local data snapshot (`cex-docs/`)

It intentionally excludes crawling/maintainer operations from day-to-day team use.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,semantic]"
```

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
scripts/runtime_query_smoke.sh
```
