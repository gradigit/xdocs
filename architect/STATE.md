# Forge State

## Mode: 1
## Current Stage: ready_for_approval
## Depth: full (default)
## Categories Asked: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
## Categories Skipped: []
## Categories Remaining: []

## Key Decisions
- Greenfield build: treat `cex-api-docs-plan-handoff/` as reference-only design notes/pseudocode.
- Output shape: build both a library and CLI, optimized for internal team usage first.
- Local-only storage: all crawled docs and extracted structures are stored locally.
- Core value proposition: eliminate endpoint/rate-limit/permission confusion, accelerate debugging and onboarding via a unified queryable knowledge base.
- Binance-first complexity: must model Binance account modes (sub-accounts, unified trading, portfolio margin) and map endpoints/permissions/rate limits accordingly.
- Accuracy policy: cite-only; no inferred facts. All answers must be backed by stored sources and provenance.
- Consumption model: provide as a Claude Code skill (and ideally agent-agnostic tooling), not just a human CLI.
- Exchange scope: support all 16 exchanges in the current registry (Tier 1 global, DEX-like, and Korean exchanges).
- Extraction approach: agent-run parsing/extraction; scripts are deterministic persistence + indexing + retrieval only.
- Soft constraint: “prompt the agent and everything just works” (minimize setup and operational friction).
- Architecture defaults (approved): Python v1 on macOS, SQLite FTS5, optional Playwright, library+CLI, single unified local store, cite-only provenance, schema validation.
- Categories 7-12 defaults approved (security/privacy, dependencies, testing, ops, trade-offs, scope).
- Prior-art research, gap analysis, and challenge passes completed; prompt ready at `architect/prompt.md`.
