# Reports Snapshot

**Generated**: 2026-03-12

## Pipeline Metrics (206 queries, post-M22)

| Metric | Value |
|--------|-------|
| MRR | 0.644 |
| nDCG@5 | 1.343 |
| Prefix hit | 78% |
| URL hit | 65% |
| Domain hit | 97% |
| OK rate | 92% |

### Per-Path Breakdown

| Path | OK | URL | PFX | MRR | nDCG@5 |
|------|-----|-----|-----|-----|--------|
| question | 92% | 60% | 75% | 0.649 | 1.292 |
| error_message | 100% | 66% | 84% | 0.652 | 1.258 |
| endpoint_path | 86% | 55% | 55% | 0.506 | 0.974 |
| request_payload | 73% | 47% | 53% | 0.322 | 0.993 |
| code_snippet | 100% | 64% | 64% | 0.434 | 1.473 |

## QA Run History (Runtime Repo)

| Run | Date | Version | Tests | Pass Rate | Findings |
|-----|------|---------|-------|-----------|----------|
| v1 | 2026-03-12 | gapfinder v1 | 46 | 67.4% | 7 (0C/3H/3M/1L) |
| v2 (blind) | 2026-03-12 | gapfinder v2 | 108 | 67.6% | 10 (0C/4H/5M/1L) |
| 10-run batch | 2026-03-12 | gapfinder v2 | 340 | 61.1% | 10 (1C/4H/5M/0L) |
| Gate.io scoped | 2026-03-12 | manual | 1 | — | 3 (0C/0H/2M/1L) |

### 10-Run Batch Key Findings

| Finding | Severity | Frequency | Status |
|---------|----------|-----------|--------|
| FTS5 crash on `'` | Critical | 7/10 | **FIXED** (BUG-21) |
| Exchange detection misses | High | 10/10 | BUG (registry gap) |
| Numeric literal misclass | High | 10/10 | BUG-15 |
| Nav chrome in excerpts | High | 9/10 | BUG-16 |
| Bare endpoint → unknown | Medium | 8/10 | BUG-17 |
| Multi-exchange collapse | Medium | 7/10 | BUG-19 |
| URL-only direct citations | High | 5/10 | BUG-18 |

## Test Suite

- **559 tests** (557 unit + 2 canary)
- Key test files: `test_init.py`, `test_fts_util.py`, `test_answer_enhanced.py`, `test_canary_qa.py`
- Run: `pytest tests/ -x -q` (~90s)

## Benchmark Scripts

- `tests/eval_answer_pipeline.py` — full pipeline eval (MRR, nDCG@5, per-path)
- `scripts/benchmark_embeddings.py` — embedding model comparison
- `scripts/benchmark_rerankers.py` — reranker model comparison
- `scripts/benchmark_mlx.py` — macOS MLX benchmark
