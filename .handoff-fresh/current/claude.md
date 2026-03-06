# Claude Onboarding — CEX API Docs

Generated: 2026-02-27 03:17 UTC

<!-- BEGIN SHARED-ONBOARDING-CONTEXT -->
# Shared Onboarding Context

## Project Snapshot
- Project: `cex-api-docs` (local, cite-only exchange docs knowledge base)
- Primary flow: inventory → fetch → SQLite/FTS5 + LanceDB semantic index → cite-only query answers
- Current expansion now includes additional perp DEX + CCXT docs coverage.

## Current Working State
- Branch: `main`
- Working tree entries (tracked+untracked): `49`
- Last commit: `729b106 feat: API Assistant v2 — input classification, endpoint lookup, error search, enhanced answers`
- Latest maintenance summary: `reports/2026-02-26-maintenance-run-summary.md`

## Key Outcomes in This Handoff Window
1. Added registry coverage for: GMX, Drift, Aevo, Perpetual Protocol, Gains, Kwenta, Lighter, and CCXT manual docs.
2. Ran maintenance workflow (sync, benchmark, retrieval eval, final gate).
3. Synced runtime workspace at `/Users/aaaaa/Projects/cex-api-docs-runtime` with fresh snapshot + manifest.
4. Runtime smoke check passes in runtime workspace with local `.venv` installed.

## Build/Test Commands
```bash
# Main repo checks
bash scripts/pre_share_check.sh ./cex-docs

# Retrieval eval
PYTHONPATH=src .venv/bin/python -m cex_api_docs.cli validate-retrieval --docs-dir ./cex-docs --qa-file tests/golden_qa.jsonl --limit 5 --no-rerank
PYTHONPATH=src .venv/bin/python -m cex_api_docs.cli validate-retrieval --docs-dir ./cex-docs --qa-file tests/golden_qa.jsonl --limit 5 --rerank

# Runtime smoke
cd /Users/aaaaa/Projects/cex-api-docs-runtime
bash scripts/runtime_query_smoke.sh
```

## Key Files and Rules
- `data/exchanges.yaml`: registry source-of-truth.
- `.claude/skills/cex-api-query/SKILL.md`: query workflow contract (v2.6.1).
- `scripts/run_sync_preset.sh`: sync presets.
- `scripts/sync_runtime_repo.py`: maintainer→runtime publish path.
- `reports/`: latest benchmark/eval artifacts.
- Cite-only policy is mandatory: unsupported facts must be `unknown` / `undocumented` / `conflict`.
<!-- END SHARED-ONBOARDING-CONTEXT -->


## Claude-Specific Appendix

- Preferred user-facing shell is fish.
- Use `python3` in commands.
- Use OSC-8 hyperlinks in responses where required by workspace policy.
- Never guess facts outside citations from local store.
