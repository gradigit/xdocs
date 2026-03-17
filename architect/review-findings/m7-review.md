# M7 Adversarial Review — March 2026

## Summary
8 findings: 2 CRITICAL (already in plan), 6 WARNING. Key refinements:
- Weighted RRF weights must be validated via golden QA sweep, not guessed
- Section boosting needs confidence threshold + cross-section regression tests
- Reranker benchmark comparison (MTEB-R vs BEIR) is invalid — head-to-head eval on golden QA required
- ColBERT needs 1% sample storage validation before full investigation
- Jina v3 CC-BY-NC license noted but user explicitly says licensing is not a factor

## Findings Applied to Plan
1. Postman variable fix → M8 8.1c (already planned)
2. FTS5 sanitization → M8 8.1b (already planned)
3. Incomparable benchmarks → M9 9.1e: head-to-head eval as acceptance gate
4. CC-BY-NC license → No action (user directive)
5. Arbitrary weights → M8 8.2b-c: baseline + weight sweep instead of guessing
6. Cross-section harm → M8 8.2d-e: confidence threshold + cross-section test queries
7. Query string stripping → M8 8.1d (already planned)
8. ColBERT storage → M9 9.3a-b: 1% sample + RaBitQ compatibility check first
