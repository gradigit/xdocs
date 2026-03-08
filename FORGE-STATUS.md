---
milestone: 11
phase: compound
updated: 2026-03-08T10:00:00Z
run_id: pre-rebuild-confidence-validation
---
## Current State
M11 COMPOUND complete. Pre-rebuild confidence validated. Ready for M10 Phase 5 (v5-small index rebuild).

## Milestones
- [x] M1-M9: Pipeline fixes, score fusion, routing, benchmark suite, model upgrades
- [x] M10 Phase 1-4: Benchmark harnesses, reranker eval, embedding baseline, MLX script
- [x] M11: Pre-rebuild confidence validation — 2 CRITICAL + 2 HIGH bugs fixed, benchmarks audited, data validated
- [ ] M10 Phase 5: v5-small index rebuild + full pipeline eval (next)

## Key Results (preserved)
- **Reranker (163 queries)**: Jina v3 winner (MRR=0.556, +15.6% over MiniLM, p=0.0014)
- **Embedding v5-nano baseline**: MRR=0.465, Hit@5=0.577 (163 queries)
- **Auto cascade**: Linux: jina-v3 → cross-encoder → flashrank

## M11 Fixes Applied
- embeddings.py defaults reverted to v5-nano (was crashing semantic search)
- _DOMAIN_MAP: 11 exchanges added (1,960 pages were invisible)
- Incremental build: exchange filter scoped to prevent cross-exchange deletion
- Vector memory: row.pop("vector") prevents 10 GB heap accumulation
- eval_answer_pipeline: negative dilution fixed (use positive_n)
- benchmark_rerankers: per_query_details length mismatch fixed
- Golden QA: 8 URL mismatches fixed (86.7% → 90.0%)
- Schema migrated v5 → v6

## Build Readiness (confirmed)
- GPU: RTX 4070 Ti SUPER, 16 GB VRAM, v5-small uses 1.27 GB
- Memory fix: vector pop + torch.cuda.empty_cache() every 50 batches
- Estimated time: ~36 min (v5-small, batch_size=16)
- Rollback: v5-nano baseline report preserved

## Pending
- M10 Phase 5: Change defaults → rebuild → compact → benchmark → eval → update docs

## Last Update: 2026-03-08T10:00:00Z
