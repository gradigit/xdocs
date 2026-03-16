# Production Readiness + Team Rollout

Date: 2026-02-27

## 1) Current state snapshot

- Core crawler/retrieval hardening is implemented:
  - cross-section scope dedupe
  - conditional revalidation (`If-None-Match` / `If-Modified-Since`) with 304 handling
  - adaptive per-domain throttling with `Retry-After`
  - markdown fidelity improvements + block metadata sidecars
  - semantic-first query skill hardening + retrieval audit contract
  - demo workspace skill sync tooling
  - schema migration dry-run/apply command
- Current baseline validation:
  - test suite passing locally (`82 passed`)
  - benchmark scripts available under `scripts/bench_*`
  - demo workspace query flow validated

## 2) Naming recommendation (production-facing)

Current package name: `xdocs`.

Recommended product naming options:

1. **CEX Docs Copilot** (recommended)
   - simple, descriptive, team-friendly.
2. **CEX API Knowledge Base**
   - precise/neutral; good for internal platform naming.
3. **Exchange Docs Intelligence**
   - strongest “analysis” framing; less CLI-specific.

Suggested split:
- Repo/package (technical): keep `xdocs` for near-term stability.
- Product/internal rollout name: **CEX Docs Copilot**.

## 3) Pre-share checklist (must pass)

Run:

```bash
scripts/pre_share_check.sh ./cex-docs
```

This executes:
- schema migration dry-run
- base-url validation smoke
- classify/query smoke
- sync preset smoke
- full pytest suite
- demo skill sync verification
- runtime repo export smoke (`--no-data`)

## 4) Packaging/release checklist

1. Tag and release:
   - bump version in `pyproject.toml`
   - create changelog entry
   - tag release (`vX.Y.Z`)
2. Lock environment:
   - keep install docs pinned
3. CI required checks:
   - `.github/workflows/ci.yml` green on PRs
4. Data refresh ops:
   - daytime and overnight presets (`scripts/run_sync_preset.sh`)
   - optional launchd setup (`ops/launchd/*.plist`)
5. Runtime repo sync:
   - `python3 scripts/sync_runtime_repo.py --runtime-root <runtime-repo-path> --docs-dir ./cex-docs --clean`
   - commit/push runtime repo update with refreshed `runtime-manifest.json`

## 5) Team onboarding flow

1. Clone repo.
2. Setup env (`python3 -m venv .venv && pip install -e ".[dev,semantic]"`).
3. Copy/pull shared `cex-docs` snapshot (or run sync/index).
4. (Optional) run demo skill sync:
   - `python3 scripts/sync_demo_skills.py --demo-root <path>`
5. Start fresh agent session in demo workspace and prompt:
   - `Use xdocs-query skill.`
   - then ask the natural-language CEX API question.

## 6) Final gate before broad share

- [ ] `scripts/pre_share_check.sh` is green
- [ ] CI green on default branch
- [ ] demo workspace skill files synced
- [ ] release tag + short “What changed” note prepared
- [ ] owners assigned for:
  - sync/index operations
  - benchmark monitoring
  - skill/update governance
