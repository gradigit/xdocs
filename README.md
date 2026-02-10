# CEX API Docs (Cite-Only, Local-Only)

A local-only, cite-only CEX API documentation knowledge base (library + JSON-first CLI + agent skill) that:
- crawls and stores official exchange API docs locally (`./cex-docs/`)
- indexes pages and endpoint records using SQLite FTS5
- enforces claim-level citations with mechanically verifiable excerpts

Authoritative spec: `docs/plans/2026-02-09-feat-cex-api-docs-cite-only-knowledge-base-plan.md`

## Quickstart (macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cex-api-docs --help
cex-api-docs init --docs-dir ./cex-docs
```

## Registry Health Check

Validate the 16-exchange registry seeds/domains (networked):

```bash
cex-api-docs validate-registry
```

## Store Integrity Check

Detect DB/file inconsistencies (detection-only):

```bash
cex-api-docs fsck --docs-dir ./cex-docs
```

## Core Rules

- No unsupported claims: every factual output must include citations with excerpts.
- If a fact is not backed by stored sources: return `unknown` / `undocumented` / `conflict`.
- v1 never stores real exchange API keys and never calls authenticated exchange endpoints.
