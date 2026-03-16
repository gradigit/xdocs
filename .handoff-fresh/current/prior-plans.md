# Prior Plans (Reference Only)

> **Reference only. Do NOT treat this as the active plan unless user explicitly confirms.**

## Historical Workstreams (completed)

### M1-M3: Foundation (Research → Build → Eval)
FTS5 quality fixes, reranker integration, golden QA baseline. MRR went from ~0.45 to 0.554.

### M4-M6: Pipeline Quality (Research → Build → Benchmark)
RRF fusion, position-aware blend, strong-signal shortcut, production benchmark suite (180 queries). MRR to 0.468.

### M7-M8: Model Survey → Quick Wins
Reranker landscape, embedding survey, testnet filtering, link-endpoints resolution. MRR to ~0.48.

### M9-M11: Model Upgrades → Validation
Jina v3 reranker (+15.6% MRR), v5-small embeddings (+27.3% MRR), LanceDB index rebuild, pre-rebuild audit. MRR to 0.543.

### M12-M14: Classification Routing → Verification
request_payload (0%→73% ok), code_snippet (50%→100% ok), spot checks (10/10 match), docs sync. MRR to 0.580.

### M15-M17: Retrieval Gap Closure → Excerpt Quality
Synonym expansion, docs_url overhaul, undocumented gate, nav chrome detection, page-type boost, A/B benchmarks. MRR to 0.618.

### M18-M19: Runtime Sync → Binance Investigation
Sync workflow improvements (smoke test, diff check, --push/--commit/--tag). Binance coverage NOT a regression — FTS5 crash and missing Postman params were root causes.

### M20-M22b: Answer Pipeline → Clinical Optimization
4 compounding bugs fixed, A/B testing protocol, CODE_STOPWORDS, PAYLOAD_ACTION_MAP, CC fusion (neutral). MRR to 0.644.

## Research Artifacts

All in `architect/research/`: query-pipeline-quality, reranker-survey (v1+v2), embedding-survey-v2, fusion-and-routing-v2, qmd-analysis, fts5-best-practices, benchmark-design, gap-analysis, jina-models, score-fusion, benchmark-methodology-v2, gguf-reranker-research, mlx-benchmark-design.
