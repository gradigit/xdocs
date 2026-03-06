# Handoff (Fresh Bundle) — CEX API Docs

Generated: 2026-02-27 03:17 UTC
Bundle path: `.handoff-fresh/current`

## Current Status

Maintenance workflow is complete for this cycle, including expanded source coverage and runtime repo sync.

- Registry now includes additional perp DEX + CCXT sources (including Lighter).
- Full maintenance run completed and validated.
- Runtime workspace is prepared for immediate fresh-agent querying.

## What Was Done

1. Added/validated new registry sources:
   - gmx, drift, aevo, perp, gains, kwenta, lighter, ccxt
2. Updated query skill/classifier triggers for new exchanges/docs families.
3. Ran sync/fetch maintenance workflow across configured sections.
4. Rebuilt semantic index and reran retrieval eval (no-rerank + rerank).
5. Executed final pre-share gate and synced runtime workspace.
6. Verified runtime query smoke in runtime workspace.

## What Is Next

1. Commit and push maintainer repo changes (currently many uncommitted changes).
2. Rebaseline `tests/golden_qa.jsonl` for the expanded corpus so eval reflects current URLs.
3. Optionally add Playwright extras for stronger JS-heavy doc route discovery.
4. Optionally initialize git in runtime workspace if team distribution via git is desired.

## Blockers / Open Questions

- Retrieval golden QA hit-rate is low due corpus/URL alignment drift; metric currently under-represents practical utility.
- Playwright extras are not installed; some JS-heavy sections may be less comprehensive under HTTP-only paths.

## First Read Order (Fresh Agent)

1. `handoff.md`
2. `claude.md`
3. `todo.md`
4. `state.md`
5. `context.md`

## Read Gate (Mandatory — complete before prep/coding)
Read these files in order:
1. `handoff.md`
2. `claude.md`
3. `todo.md`
4. `state.md`
5. `context.md`

Reply with this read receipt format before any prep/coding:
- [x] handoff.md — <1-line takeaway>
- [x] claude.md — <1-line takeaway>
- [x] todo.md — <1-line takeaway>
- [x] state.md — <1-line takeaway>
- [x] context.md — <1-line takeaway>

If any required file is unread or takeaway is missing:
- Stop and ask-question if needed.
- Do not proceed to Workspace Preparation or coding.

Bootstrap/autostart rule:
- If the user prompt only says "Read .handoff-fresh/current/handoff.md", treat it as onboarding bootstrap.
- Continue to read all required Read Gate files before replying.
- Do not send interim "done, I read handoff.md" summaries.

Preflight before coding:
- Fresh agent runs read-gate preflight validator (`/handoff-fresh --validate-read-gate` or script equivalent)
- If validator fails, fix `read-receipt.md`, ask-question if needed, and rerun.

## Workspace Preparation (Do before coding)
1. Confirm repo root and current branch.
2. Confirm working tree status and note uncommitted changes.
3. Confirm required root docs/folders are present.
4. Re-run `/sync-docs` if drift is detected.
5. Run Question Gate:
   - If required information is missing/ambiguous, use ask-question before coding.
   - If no answer yet, do only safe/reversible prep and log assumptions in `state.md`.
6. Start implementation only after steps 1-5 are complete.

## Note on Prerequisite Sync

`/sync-docs` command is not directly available in this Codex run. Equivalent preflight was satisfied via fresh validation runs (`pre_share_check`, retrieval eval, runtime smoke) before bundle generation.
