# Benchmark / Test / Evaluation Summary — 2026-02-26

## 1) Test status

- Full suite: **82 passed**
- Runtime: **~53s** (second full run)
- Notes:
  - One flaky lock timing failure observed once in `tests/test_init.py::TestInit::test_lockfile_blocks_other_process`, then passed in 3/3 targeted reruns and on full rerun.
  - Warnings include `joblib` serial fallback due temp-space issue and swig deprecation notices.

## 2) Crawl/sync benchmark

### Full-store resume benchmark
- Artifact: `reports/2026-02-26T175032Z-crawl-refresh-benchmark.json`
- Mode: `resume`, all exchanges/sections
- Inventories enumerated: **37**
- URLs enumerated: **7,133**
- Fetched/stored pages: **0 / 0** (expected for warm resume)
- Errors: **0**
- 429s: **0**

### Bitfinex v2 resume vs force-refetch
- Artifact: `reports/2026-02-26T174042Z-crawl-refresh-benchmark.json`
- Resume:
  - inventory URLs: **118**
  - fetched/stored: **0 / 0**
  - duration: effectively near-zero CLI-reported
- Force-refetch:
  - fetched/stored: **118 / 118**
  - unchanged pages: **118**
  - raw bytes fetched: **38,852,360**
  - duration: **128s**
  - errors/429s: **0 / 0**

## 3) Extraction quality benchmark

- Artifact: `reports/2026-02-26T174308Z-extraction-quality-benchmark.json`
- Store totals:
  - pages: **3,819**
  - words: **4,610,108**
- Quality counts:
  - empty pages: **3**
  - thin (<50 words): **146**
  - ok (>=50 words): **3,670**
- Sample (500 pages):
  - avg words/page: **1,408**
  - pages with code tags `[code]`: **324**
  - pages with fenced code blocks: **11**
  - pages with headings: **492**

## 4) Retrieval evaluation (golden QA)

### No rerank (k=5)
- Artifact: `reports/2026-02-26T1744-validate-retrieval-no-rerank.json`
- hit_rate: **0.35**
- mean_recall: **0.35**
- total_queries: **20**

### With rerank (k=5)
- Artifact: `reports/2026-02-26T1745-validate-retrieval-rerank.json`
- hit_rate: **0.35**
- mean_recall: **0.35**
- total_queries: **20**

### Rerank latency sample (8-query subset)
- no-rerank: **9.6s**
- rerank: **44.47s**
- relative overhead: **~4.6x**
- hit-rate delta on sample: **none**

## 5) Readiness assessment

- Core correctness: **good** (tests green)
- Incremental sync stability: **good** (resume path fast, no 429/errors in sampled runs)
- Extraction fidelity: **improved but mixed** (high `[code]` residue still present in sampled pages)
- Retrieval quality vs golden set: **needs work** (35% exact-URL hit rate; reranker not improving this metric currently)

## 6) Priority follow-ups

1. Deflake lock timing test by making contention deterministic (barrier/handshake before assertion).
2. Re-baseline `tests/golden_qa.jsonl` to match current canonical URLs and add alias/near-match scoring.
3. Add a “semantic correctness” eval metric in addition to exact URL hit.
4. Expand markdown normalization rollout with targeted refetch on high `[code]` domains.
5. Keep reranker on conditional path until eval shows clear gain at acceptable latency.
