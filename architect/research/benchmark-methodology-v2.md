# IR Benchmark Methodology v2 — March 2026

## Key Findings

### Statistical Tests
- **Paired permutation test** is the gold standard (Smucker et al. CIKM 2007)
- t-test, bootstrap, and permutation agree closely at n>=50 (Urbano et al. SIGIR 2019)
- Wilcoxon and sign tests should be discontinued for IR eval
- Use `scipy.stats.bootstrap` (BCa, 10,000 resamples) for confidence intervals
- Use `scipy.stats.permutation_test` for significance testing

### Sample Size
- 180 queries exceeds TREC standard (43-50 judged queries per task)
- At n=180, α=0.05, power=0.80: MDE ≈ Cohen's d=0.21 → ~0.03 MRR/nDCG points
- At n=30 (our M9 eval): MDE ≈ 0.077 — the 0.028 MRR difference was NOT reliably detectable
- Sub-groups: code_snippet (n=14) and request_payload (n=15) are underpowered

### Evaluation Design
- **Embedding eval**: Each model retrieves independently, compare nDCG@5/MRR
- **Reranker eval**: Fixed candidate set (top-30 from base embedder), vary only reranker
- **Metrics**: nDCG@5 (primary), MRR, Hit@5, nDCG@10, Recall@20
- **TREC graded relevance**: 0-3 scale (already matching our golden QA)

### Bootstrap CI Code
```python
from scipy.stats import bootstrap
import numpy as np

def bootstrap_ci(scores, n_resamples=10000, confidence=0.95, seed=42):
    res = bootstrap(
        (np.array(scores),), statistic=np.mean,
        n_resamples=n_resamples, confidence_level=confidence,
        method='BCa', rng=np.random.default_rng(seed),
    )
    return {
        'mean': float(np.mean(scores)),
        'ci_low': float(res.confidence_interval.low),
        'ci_high': float(res.confidence_interval.high),
    }

def paired_ci(scores_a, scores_b, n_resamples=10000, confidence=0.95, seed=42):
    def mean_diff(x, y, axis=-1):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)
    res = bootstrap(
        (np.array(scores_a), np.array(scores_b)),
        statistic=mean_diff, n_resamples=n_resamples,
        confidence_level=confidence, method='BCa',
        paired=True, rng=np.random.default_rng(seed),
    )
    return {
        'mean_diff': float(np.mean(scores_a) - np.mean(scores_b)),
        'ci_low': float(res.confidence_interval.low),
        'ci_high': float(res.confidence_interval.high),
        'significant': bool(res.confidence_interval.low > 0 or res.confidence_interval.high < 0),
    }
```

## Sources
- Smucker, Allan, Carterette. CIKM 2007 (significance test comparison)
- Urbano, Lima, Hanjalic. SIGIR 2019 (topic set sizes, test agreement)
- TREC DL 2019 Overview (43 judged queries, graded relevance)
- SciPy v1.17 bootstrap docs (BCa method)
- ranx library (Fisher's randomization test, Tukey HSD)
