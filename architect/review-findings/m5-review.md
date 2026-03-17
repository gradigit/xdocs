# M5 Review Findings

## Adversarial Review

| # | Severity | File | Description | Status |
|---|----------|------|-------------|--------|
| 1 | WARNING | answer.py:1003 | Spec URL suppression missing in `_augment_with_classification` endpoint_path branch | **FIXED** — added `_is_spec_url()` check |
| 2 | WARNING | fts_util.py:167 | ~9x scale mismatch between RRF scores and sigmoid-normalized reranker scores in `position_aware_blend` | **FIXED** — added max-normalization of RRF scores before blending |

## Positive Observations
- Double-RRF prevention correctly implemented (query_type="vector")
- SQL injection prevention uses strict allowlist regex
- Schema migration robust with porter stemming verification test
- BM25 normalization mathematically sound
- Strong-signal shortcut properly scoped to question type only

## Excluded (below 80% confidence)
- `\boptions?\b` false-positive on generic English (60%) — advisory routing, not blocking
- Mid-file `import math` (30%) — style only
- Top-rank bonus not implemented (40%) — deferred, not yet in production path

## Quality Gate
- All 413 tests pass
- Both CRITICAL/HIGH findings addressed (none found — 2 WARNINGs)
- No regressions
- **GATE C: PASS**
