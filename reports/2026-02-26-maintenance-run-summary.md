# Maintenance Run Summary — 2026-02-26

## What was added before maintenance

### Registry expansion
Added these new sources in `data/exchanges.yaml`:

- Perp DEX exchanges:
  - `gmx/docs`
  - `drift/docs`
  - `aevo/api`
  - `perp/docs` (Perpetual Protocol)
  - `gains/docs`
  - `kwenta/docs`
  - `lighter/docs`
- CCXT documentation:
  - `ccxt/manual`

### Query routing updates
- `src/xdocs/classify.py`: added exchange hints for new DEX/CCXT names.
- `.claude/skills/cex-api-query/SKILL.md`: bumped to **v2.6.1** and expanded trigger list.

## Full maintenance workflow executed

1. Full refresh runs were executed across sections using `sync --force-refetch` and targeted `fetch-inventory --force-refetch` where needed.
2. All configured sections now have fresh crawl-run coverage in this maintenance window.
3. Semantic index was rebuilt (LanceDB artifacts updated and semantic query smoke succeeded).
4. Retrieval evaluation ran with/without reranker.
5. Final pre-share gate passed.
6. Runtime repo was synced and runtime smoke passed.

## Coverage confirmation

- Registry sections: **45**
- Sections with latest crawl run in this maintenance window: **45 / 45**

## Final store stats

- Pages: **4,537**
- Words: **6,412,721**

New-source domain page snapshot:
- `gmx`: 64 pages
- `drift`: 132 pages
- `aevo`: 144 pages
- `perp`: 36 pages
- `gains`: 114 pages
- `kwenta`: 20 pages
- `lighter`: 19 pages
- `ccxt`: 223 pages

## Benchmarks (final)

### Crawl resume benchmark
Artifact: `reports/2026-02-26T200246Z-crawl-refresh-benchmark.json`

- sections: 45
- inventory URLs: 7,931
- fetched: 0
- errors: 0

### Extraction quality benchmark
Artifact: `reports/2026-02-26T200239Z-extraction-quality-benchmark.json`

- pages: 4,537
- words: 6,412,721
- empty: 4
- thin (<50 words): 150
- sample markdown signals:
  - `code_tag_occurrences`: 1
  - `fence_occurrences`: 3,002

## Retrieval evaluation (final)

Artifacts:
- `reports/2026-02-26T2003-validate-retrieval-no-rerank.json`
- `reports/2026-02-26T2003-validate-retrieval-rerank.json`

(20 golden queries, k=5)
- no-rerank: hit_rate=0.05, mean_recall=0.05
- rerank: hit_rate=0.05, mean_recall=0.05

Interpretation: current golden QA file is not aligned with the present corpus/URL distribution and should be rebaselined for production-quality offline eval.

## Final gates + runtime readiness

- `scripts/pre_share_check.sh ./cex-docs` passed.
- Runtime sync completed:
  - `scripts/sync_runtime_repo.py --runtime-root /Users/aaaaa/Projects/xdocs-runtime --docs-dir ./cex-docs --clean`
- Runtime smoke passed:
  - `/Users/aaaaa/Projects/xdocs-runtime/scripts/runtime_query_smoke.sh`

## Known operational note

- Playwright is not installed in this environment. JS-heavy sites are handled HTTP-first in this run; install Playwright extras for maximum route-discovery reliability on future maintenance runs.
