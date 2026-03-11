# CEX Docs Copilot Runtime

This repository is the **team runtime** for querying exchange API documentation.

It includes:

- query CLI/tooling (`cex-api-docs`)
- query skill (`cex-api-query`)

Data snapshots (`cex-docs/`) are distributed via GitHub Releases, not git.

## Quick start

```bash
git clone https://github.com/henryaxis/cex-api-docs-runtime.git
cd cex-api-docs-runtime
uv venv .venv
source .venv/bin/activate
uv pip install -e .
./scripts/bootstrap-data.sh
```

All query dependencies (including semantic search) are included by default.

Then in a fresh agent session:

```text
Use cex-api-query skill.
```

and ask your natural-language CEX API docs question.

## Update

Code updates:

```bash
git pull
```

Data updates (published separately):

```bash
./scripts/bootstrap-data.sh
```

Or download a specific version:

```bash
./scripts/bootstrap-data.sh data-2026.03.11
```

## Smoke check

```bash
python scripts/runtime_query_smoke.py
```
