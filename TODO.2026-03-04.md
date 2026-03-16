# TODO — Semantic Search Retrieval Quality Fix

## Goal
Achieve near-100% hit rate on golden QA for API documentation retrieval. Current: 64-70% (both 4B and 0.6B models). Root cause: retrieval returns right exchange but wrong page for ~32% of queries. Golden QA validation methodology also masks true quality with overly strict URL matching.

## Milestones

## Milestone 1: Fix Golden QA Evaluation
- **Goal**: Make validation metrics accurately reflect retrieval quality by adding prefix/domain matching and fixing overly specific expected URLs
- **Dependencies**: none
- **Files in scope**: `tests/golden_qa.jsonl`, `src/xdocs/validate.py`
- **Quality criteria**: Validation reports exact, prefix, and domain hit rates. Golden QA URLs updated where current entries are wrong/overly-specific. All 50 queries have verified expected URLs.
- **Research needed**: none (data from benchmark already available)
- **Steps**:
  1. Add prefix-match and domain-match metrics to validate.py
     - Success criteria: `ValidationResult` includes `prefix_hit_rate` and `domain_hit_rate` fields. CLI output shows all three metrics.
     - Artifacts: `src/xdocs/validate.py`
  2. Audit and fix golden QA expected URLs
     - Success criteria: Each of the 50 queries has verified expected URLs that match actual pages in the store. Re-run validation shows exact hit rate improvement.
     - Artifacts: `tests/golden_qa.jsonl`
  3. Run updated validation and establish baseline
     - Success criteria: Baseline numbers recorded for all three match levels (exact, prefix, domain)
     - Artifacts: `/tmp/cex-bench-embedding/baseline-after-qa-fix.json`

## Milestone 2: Diagnose and Fix Retrieval Quality
- **Goal**: Fix the retrieval pipeline so correct pages rank in top-5 for all golden QA queries
- **Dependencies**: Milestone 1 (need accurate metrics to measure improvement)
- **Files in scope**: `src/xdocs/semantic.py`, `src/xdocs/chunker.py`, `src/xdocs/embeddings.py`
- **Quality criteria**: Exact hit rate >= 90% on updated golden QA. All remaining misses are edge cases with documented reasons.
- **Research needed**: Why do correct pages rank below incorrect ones? Chunk content analysis, heading context loss, hybrid search weight tuning.
- **Steps**:
  1. Research: Analyze the top miss patterns (what chunks are returned vs expected)
     - Success criteria: Root cause analysis document with specific findings per miss category
     - Artifacts: `architect/research/retrieval-misses.md`
  2. Fix chunking to preserve page-level context (heading hierarchy in chunk text)
     - Success criteria: Chunks include page title and heading path. Re-embedding a sample shows improved similarity to golden QA queries.
     - Artifacts: `src/xdocs/chunker.py`
  3. Tune hybrid search (FTS5 weight, top-K candidates, rerank parameters)
     - Success criteria: Validation hit rate improves measurably over baseline
     - Artifacts: `src/xdocs/semantic.py`
  4. Run validation and compare against Milestone 1 baseline
     - Success criteria: Exact hit rate >= 90%, documented reasons for any remaining misses
     - Artifacts: Validation results

## Milestone 3: Model Swap + Clean Rebuild
- **Goal**: Switch to Qwen3-Embedding-0.6B with batch_size=128, complete a full clean index build, validate quality
- **Dependencies**: Milestone 2 (need retrieval fixes in place before final build)
- **Files in scope**: `src/xdocs/embeddings.py`, `src/xdocs/semantic.py`, CLAUDE.md, AGENTS.md
- **Quality criteria**: Full index built, validation hit rate matches or exceeds Milestone 2 results, build completes in <4 hours
- **Research needed**: none (benchmark data already confirms 0.6B parity)
- **Steps**:
  1. Update embedder defaults to 0.6B model, batch_size to 128
     - Success criteria: `DEFAULT_MLX_MODEL` points to 0.6B, `build_index` default batch_size is 128
     - Artifacts: `src/xdocs/embeddings.py`, `src/xdocs/semantic.py`
  2. Full clean index build
     - Success criteria: Index complete with all pages, no errors. Build time < 4 hours.
     - Artifacts: `cex-docs/lancedb-index/`
  3. Final validation
     - Success criteria: Hit rate >= 90% on golden QA, matching Milestone 2 results
     - Artifacts: Validation results
  4. Update documentation
     - Success criteria: CLAUDE.md and AGENTS.md reflect 0.6B model, 1024 dims, correct chunk count
     - Artifacts: CLAUDE.md, AGENTS.md
