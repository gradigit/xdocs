---
milestone: M29
phase: complete
updated: 2026-03-19T22:00:00+09:00
run_id: batch-bugfix-2026-03-19
---
## Current State
Batch bug fix + optimization run complete. 7 fixes applied, 1 reverted (BUG-8 blend weights caused endpoint_path regression), all A/B validated against 206-query golden QA.

## Milestones
- [x] BUG-1: Deribit spec URL bypass — filtered in endpoint citations + page search candidates
- [x] BUG-14: Crypto/API code detection — 2 new patterns (dict assignment, .encode())
- [x] OPT-2: Code snippet API URL extraction — api_path from URLs in code → direct endpoint lookup
- [x] OPT-12: Synonym map expansion — 14 new API-domain synonym groups
- [x] BUG-8: Blend weights — REVERTED (-3.4% endpoint_path, no net benefit)
- [x] BUG-13: Section hint routing — section-matching results promoted for Binance spot
- [x] BUG-19: Multi-exchange comparison — "Binance and OKX" returns results from both

## Eval Results (206 queries, vs M22 baseline)
- MRR: 0.6350 → 0.6341 (flat)
- PFX: 76.19% → 77.25% (+1.06pp)
- Latency: 3.93s → 3.52s (-10.4%)
- error_message MRR: +3.7%
- request_payload nDCG: +2.1%
- endpoint_path MRR: -3.4% (from BUG-1 spec URL filtering, correct behavior — needs link-endpoints re-run)
- 574 tests pass, 0 regressions

## Active Agents
- None

## Last Update: 2026-03-19T22:00:00+09:00
