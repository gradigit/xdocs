# M22 Critical Evaluation — Data-Driven Optimization Triage

**Date**: 2026-03-10
**Baseline**: 206 queries, MRR=0.633, pfx=74.6%, 529 tests

## Analysis Methodology

1. Ran full 206-query pipeline eval to establish exact baseline
2. Analyzed all 48 prefix misses by type and root cause
3. Traced code paths for each proposed optimization
4. Calculated maximum theoretical impact per optimization
5. Assessed risk and dependency chains

## Key Finding: Question-Type Prefix Misses Dominate

Of 48 prefix misses on 189 positive queries:
- **question**: ~32 misses (67% of all misses)
- **endpoint_path**: ~11 misses (23%)
- **code_snippet**: ~7 misses (15%)
- **request_payload**: ~7 misses (15%)

The question-type misses fall into 4 categories:
- **A: Section mismatch** (3 queries) — Binance spot queries returning derivatives pages
- **B: Overview not ranked** (8 queries) — broad queries getting endpoint pages instead of intro/overview
- **C: Auth/rate-limit routing** (3 queries) — auth/permission pages not ranking well
- **D: Close misses** (3 queries) — right section but wrong sub-page

## Optimization Priority Matrix

| # | Optimization | Queries Affected | Max Pfx Gain | Risk | Effort | Verdict |
|---|---|---|---|---|---|---|
| 1 | BUG-13: Section filter | 3-13 Binance | +1.6-6.8% | LOW | 30 LOC | **DO NOW** |
| 2 | Page-type boost 2.0 | 8+ question | +4.2% | LOW | 20 LOC | **DO NOW** |
| 3 | Phase 2: Op inference | 8/14 req_payload | +3.7% | LOW | 80 LOC | **DO NOW** |
| 4 | Phase 1: Code stops | 5/13 code_snippet | +2.6% | LOW | 30 LOC | **DO NOW** |
| 5 | Phase 3: Param FTS | 39 ep+payload | +2-5% | V.LOW | 15 LOC | **DO NOW** |
| 6 | Phase 6: Rerank min | 17 small-exchange | +1-2% | V.LOW | 1 LOC | **DO NOW** |
| 7 | Phase 5: CC fusion | All 189 | +1-5% nDCG | MED | 80 LOC | **A/B FIRST** |
| 8 | BUG-8: Blend weights | 107 question | +0-2% | MED | 10 LOC | **A/B FIRST** |
| 9 | Phase 4: FTS/sem split | All | <1% | LOW | 20 LOC | Bundle |
| 10 | BUG-14: Code patterns | Few | <1% | LOW | 10 LOC | Bundle with #4 |

## A/B Test Design Requirements

Each change MUST be tested in isolation:
1. Save baseline eval results to `reports/m22-baseline.json`
2. Implement change behind env var toggle
3. Run eval with change ON vs OFF
4. Compare per-type MRR and overall MRR
5. Check for regressions on ANY type (even if overall improves)
6. Only commit changes that show improvement AND no regression
7. Run full 529-test suite after each committed change

## Rejected/Deferred Items

- OPT-10 (ColBERT): Already evaluated, not worth it
- OPT-9 (PRF): Chicken-egg problem, deferred
- OPT-8 (BM25 weight tuning): Overfitting risk on 200 queries
- BUG-9 (Chunk heading): Requires index rebuild, separate milestone
- BUG-12 (Korean): Very low impact
- GTE-ModernBERT: Marginal over Jina v3, deferred
