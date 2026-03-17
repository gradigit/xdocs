# M5 Plan Adversarial Review

## Critical Findings (addressed in plan update)

1. **Double-RRF** (CRITICAL): LanceDB hybrid search already uses RRF k=60 internally. Proposed outer RRF would double-fuse. Fix: Switch semantic_search to `query_type="vector"` when outer RRF is applied.

2. **BM25 scores unavailable** (CRITICAL): `_search_pages` doesn't SELECT rank column. RRF and BM25 shortcut can't access scores. Fix: Add `rank` to SELECT, propagate through pipeline.

## Warning Findings (addressed in plan update)

3. **Redundant shortcut/routing**: BM25 shortcut and direct routing both target endpoint_path/error_message. Fix: BM25 shortcut only for `question` type; direct routing handles typed queries.

4. **schema.sql gap**: Plan mentioned migration but not schema.sql update. Fix: Include schema.sql + test_init.py updates.

5. **FlashRank normalization**: Position-aware blending needs bounded scores. Fix: Sigmoid normalization `1/(1+exp(-score))`.

6. **Spec URL suppression risk**: Blanket suppression → zero citations. Fix: Selective suppression + citation_status field.

7. **Routing insertion point**: Undefined relative to Binance/generic branch. Fix: Before branch for generic; in fallthrough path for Binance.

## Plan Status
All CRITICAL findings addressed. GATE B passed.
