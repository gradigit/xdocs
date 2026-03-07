# Production-Grade Benchmark Suite Design

## Summary

Expand from 50 to 200 queries with graded relevance (0-3 TREC scale), stratified across 5 classification paths and 3 exchange tiers. Use `ranx` for metrics (nDCG, ERR, MRR) with Fisher's randomization test. Two-tier CI: FTS5-only canary (20-30 queries, <10s) + nightly full eval.

## Graded Relevance Scale

| Grade | Label | API Docs Definition | Example |
|-------|-------|---------------------|---------|
| 3 | Perfect | Exact answer page with specific endpoint/error code/parameter | "Binance error -1002" -> Error codes page |
| 2 | Highly relevant | Correct topic area, relevant info but not precise answer | "Binance rate limits" -> General API info |
| 1 | Related | Same exchange/version but different endpoint/section | "Binance order" -> Account endpoint page |
| 0 | Irrelevant | Wrong exchange, wrong version, or unrelated | Binance query -> OKX page |

Binary cutoff: grades 2-3 = relevant, 0-1 = irrelevant (for MAP).

## Query Set Design (200 queries)

### By Classification Path
| Path | Count | Rationale |
|------|-------|-----------|
| question | 80 (40%) | Primary use case |
| endpoint_path | 40 (20%) | Deterministic lookup |
| error_message | 40 (20%) | Exchange-specific routing |
| code_snippet | 20 (10%) | Library context |
| request_payload | 20 (10%) | Parameter identification |

### By Exchange Tier
- **Tier 1** (Binance, Bybit, OKX, KuCoin, Bitget): 15-20 queries each
- **Tier 2** (Kraken, Coinbase, Gate.io, HTX, etc.): 5-10 queries each
- **Tier 3** (single-page sites, DEXes): 2-5 queries each

### By Difficulty
- Exact match: 30%
- Fuzzy match: 40%
- Multi-hop: 20%
- Ambiguous: 10%

## Negative Test Cases (30-40 of 200)

| Type | Count | Expected Response |
|------|-------|-------------------|
| Out-of-scope exchange | 8 | `unknown` |
| Non-existent endpoint | 8 | `undocumented` |
| Deprecated feature | 5 | `undocumented`/`conflict` |
| Cross-exchange confusion | 5 | Wrong-exchange detection |
| Nonsensical | 4 | `unknown` |

Target False Positive Rate: < 5%.

## CI Strategy

### Tier 1: CI-Fast (<10 seconds, every commit)
- 20-30 "canary queries" covering all classification paths + top-10 exchanges
- FTS5-only (0.19s/query) — no semantic search, no model loading
- Compare against pre-computed expected results
- Hard fail on any canary regression

### Tier 2: Nightly Full (5-15 minutes)
- Full 200 queries through all search modes
- nDCG@5, nDCG@10, ERR@10 with graded relevance
- Per-classification-path breakdowns
- Bootstrap significance test vs baseline

## Regression Detection

### Threshold Alerts
- Hard fail: nDCG@5 < 0.50 or hit_rate@5 < 0.60
- Warning: any metric drops > 5% from baseline
- Hard fail: any metric drops > 10% from baseline

### Statistical Tests (nightly)
- Paired bootstrap test (B=1000, BCa intervals)
- Fisher's randomization test via ranx
- Threshold: p < 0.01 for automated alerts

## Recommended Tools

- **ranx**: nDCG, MAP, MRR, ERR, RBP with Numba acceleration + Fisher's test
- **ir-measures**: 40+ metrics, wraps pytrec_eval (alternative if ranx insufficient)
- Add as `[eval]` optional dependency in pyproject.toml

## Answer Quality Scoring

1. **Citation accuracy** (deterministic): URL exists in store + excerpt byte-matches
2. **Completeness** (heuristic): Expected term overlap ratio
3. **Faithfulness** (optional, NLI): DeBERTa-v3 MNLI entailment score (~300ms/claim, r=0.64 with human)

Start with (1) and (2). Add (3) as optional nightly metric.

## Sources

- TREC Deep Learning Track (2019, 2021)
- BEIR Benchmark (NeurIPS 2021)
- Sakai SIGIR 2016 (statistical power)
- ranx, ir-measures, pytrec_eval
- Adaptive bootstrap testing (BCa)
