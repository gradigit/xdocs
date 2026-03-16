#!/usr/bin/env python3
"""Reranker model benchmark with statistical significance testing.

Evaluates reranker models head-to-head on the golden QA set using a fixed
candidate set design (isolates reranking quality from retrieval quality).

Design:
  1. For each query, retrieve top-K candidates via semantic_search (no reranking).
  2. Rerank candidates with each model under test.
  3. Compute per-query MRR, nDCG@5, Hit@5 with bootstrap 95% CI.
  4. Run paired permutation test between models.

Usage:
    python scripts/benchmark_rerankers.py --docs-dir ./cex-docs
    python scripts/benchmark_rerankers.py --docs-dir ./cex-docs --json
    python scripts/benchmark_rerankers.py --docs-dir ./cex-docs --models cross-encoder,qwen3,flashrank
    python scripts/benchmark_rerankers.py --docs-dir ./cex-docs --candidate-pool 30 --limit 20
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np
from scipy.stats import bootstrap, permutation_test


# ── Metrics ──

def _norm(url: str) -> str:
    return unquote(url).split("#")[0].rstrip("/").lower()


def _prefix_match(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    return na.startswith(nb) or nb.startswith(na)


def _domain(url: str) -> str:
    return urlparse(url).hostname or ""


def _dcg_at_k(gains: list[float], k: int = 5) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains[:k]))


def _ndcg_at_k(gains: list[float], ideal: list[float], k: int = 5) -> float:
    dcg = _dcg_at_k(gains, k)
    idcg = _dcg_at_k(sorted(ideal, reverse=True), k)
    return dcg / idcg if idcg > 0 else 0.0


def _compute_gains(
    result_urls: list[str],
    expected_urls: list[str],
    relevance: int,
    k: int = 5,
) -> list[float]:
    expected_normed = {_norm(u) for u in expected_urls}
    expected_domains = {_domain(u) for u in expected_urls}
    gains: list[float] = []
    for url in result_urls[:k]:
        if _norm(url) in expected_normed:
            gains.append(float(relevance))
        elif any(_prefix_match(url, eu) for eu in expected_urls):
            gains.append(float(max(1, relevance - 1)))
        elif _domain(url) in expected_domains:
            gains.append(1.0)
        else:
            gains.append(0.0)
    return gains


def _mrr(result_urls: list[str], expected_urls: list[str]) -> float:
    expected_normed = {_norm(u) for u in expected_urls}
    for i, url in enumerate(result_urls, 1):
        if _norm(url) in expected_normed:
            return 1.0 / i
        if any(_prefix_match(url, eu) for eu in expected_urls):
            return 1.0 / i
    return 0.0


# ── Bootstrap CI ──

def bootstrap_ci(scores: np.ndarray, n_resamples: int = 10000, confidence: float = 0.95):
    res = bootstrap(
        (scores,), statistic=np.mean,
        n_resamples=n_resamples, confidence_level=confidence,
        method="BCa", rng=np.random.default_rng(42),
    )
    return {
        "mean": float(np.mean(scores)),
        "ci_low": float(res.confidence_interval.low),
        "ci_high": float(res.confidence_interval.high),
    }


def paired_significance(scores_a: np.ndarray, scores_b: np.ndarray):
    def stat_func(x, y, axis):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)
    res = permutation_test(
        (scores_a, scores_b), statistic=stat_func,
        permutation_type="samples", n_resamples=9999,
        alternative="two-sided", rng=np.random.default_rng(42),
    )
    return {"p_value": float(res.pvalue), "significant_005": bool(res.pvalue < 0.05)}


# ── Candidate retrieval ──

def retrieve_candidates(docs_dir: str, qa_pairs: list[dict], pool_size: int = 30):
    """Retrieve fixed candidate sets for all queries (no reranking)."""
    from xdocs.semantic import semantic_search

    print(f"Retrieving top-{pool_size} candidates for {len(qa_pairs)} queries...", file=sys.stderr)

    # Warm up
    semantic_search(docs_dir=docs_dir, query="test", limit=1, query_type="vector",
                    rerank=False, include_meta=False)

    candidates = []
    for i, pair in enumerate(qa_pairs):
        try:
            results = semantic_search(
                docs_dir=docs_dir,
                query=pair["query"],
                exchange=pair.get("expected_exchange"),
                limit=pool_size,
                query_type="vector",
                rerank=False,
                include_meta=False,
                keep_text=True,
            )
        except Exception as e:
            print(f"  [{i+1}] FAILED: {pair['query'][:50]}... — {e}", file=sys.stderr)
            results = []
        candidates.append(results)
        if (i + 1) % 30 == 0:
            print(f"  [{i+1}/{len(qa_pairs)}] retrieved", file=sys.stderr)

    print(f"  Done. {sum(len(c) for c in candidates)} total candidates.", file=sys.stderr)
    return candidates


# ── Reranker evaluation ──

@dataclass
class ModelResult:
    model: str
    backend: str
    mrr: dict
    ndcg5: dict
    hit5: dict
    mean_latency_s: float
    per_query: list[dict] = field(default_factory=list)


def evaluate_reranker(
    model_name: str,
    backend: str,
    qa_pairs: list[dict],
    candidates: list[list[dict]],
    top_n: int = 5,
) -> ModelResult:
    """Evaluate a single reranker on fixed candidate sets."""
    import xdocs.reranker as mod

    # Save and set backend
    orig_backend = mod._BACKEND
    orig_model = mod._MODEL
    mod._BACKEND = backend

    if backend == "cross-encoder" and model_name != "default":
        mod._MODEL = model_name

    per_query_mrr = []
    per_query_ndcg = []
    per_query_hit = []
    latencies = []
    per_query_details = []

    try:
        for pair, cands in zip(qa_pairs, candidates):
            if not cands:
                per_query_mrr.append(0.0)
                per_query_ndcg.append(0.0)
                per_query_hit.append(0.0)
                per_query_details.append({
                    "query": pair["query"],
                    "mrr": 0.0, "ndcg5": 0.0, "hit5": 0.0, "latency_s": 0.0,
                })
                continue

            expected_urls = pair.get("expected_urls", [])
            relevance = pair.get("relevance", 2)

            t0 = time.perf_counter()
            try:
                reranked = mod.rerank(pair["query"], cands, top_n=top_n, text_key="text")
            except Exception as e:
                print(f"  Rerank failed for {backend}/{model_name}: {e}", file=sys.stderr)
                reranked = cands[:top_n]
            latency = time.perf_counter() - t0
            latencies.append(latency)

            result_urls = [r.get("url", "") for r in reranked]
            mrr_val = _mrr(result_urls, expected_urls)
            gains = _compute_gains(result_urls, expected_urls, relevance)
            ideal = [float(relevance)] * min(len(expected_urls), 5) if expected_urls else [0.0]
            ndcg_val = _ndcg_at_k(gains, ideal)
            hit_val = 1.0 if any(_norm(u) in {_norm(e) for e in expected_urls}
                                 or any(_prefix_match(u, e) for e in expected_urls)
                                 for u in result_urls) else 0.0

            per_query_mrr.append(mrr_val)
            per_query_ndcg.append(ndcg_val)
            per_query_hit.append(hit_val)

            per_query_details.append({
                "query": pair["query"],
                "mrr": mrr_val,
                "ndcg5": ndcg_val,
                "hit5": hit_val,
                "latency_s": latency,
            })
    finally:
        mod._BACKEND = orig_backend
        mod._MODEL = orig_model

    arr_mrr = np.array(per_query_mrr)
    arr_ndcg = np.array(per_query_ndcg)
    arr_hit = np.array(per_query_hit)

    return ModelResult(
        model=model_name,
        backend=backend,
        mrr=bootstrap_ci(arr_mrr),
        ndcg5=bootstrap_ci(arr_ndcg),
        hit5=bootstrap_ci(arr_hit),
        mean_latency_s=float(np.mean(latencies)) if latencies else 0.0,
        per_query=per_query_details,
    )


# ── Main ──

MODELS = {
    "minilm-l12": ("cross-encoder/ms-marco-MiniLM-L-12-v2", "cross-encoder"),
    "qwen3": ("tomaarsen/Qwen3-Reranker-0.6B-seq-cls", "qwen3"),
    "flashrank": ("ms-marco-MiniLM-L-12-v2", "flashrank"),
    "jina-v3": ("jinaai/jina-reranker-v3", "jina-v3"),
    "bge-v2-m3": ("BAAI/bge-reranker-v2-m3", "cross-encoder"),
}


def main():
    parser = argparse.ArgumentParser(description="Reranker model benchmark")
    parser.add_argument("--docs-dir", default="./cex-docs")
    parser.add_argument("--qa-file", default="tests/golden_qa.jsonl")
    parser.add_argument("--models", default="minilm-l12,qwen3,flashrank",
                        help="Comma-separated model keys")
    parser.add_argument("--candidate-pool", type=int, default=30)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    # Load golden QA
    qa_file = Path(args.qa_file)
    pairs = []
    for line in qa_file.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pair = json.loads(line)
        # Skip negatives (no expected URLs)
        if "negative" in pair.get("tags", []):
            continue
        pairs.append(pair)

    if args.limit:
        pairs = pairs[:args.limit]

    print(f"Benchmark: {len(pairs)} queries, pool={args.candidate_pool}, top_n={args.top_n}",
          file=sys.stderr)

    # Retrieve fixed candidate sets
    candidates = retrieve_candidates(args.docs_dir, pairs, args.candidate_pool)

    # Evaluate each model
    model_keys = [k.strip() for k in args.models.split(",")]
    results: list[ModelResult] = []

    for key in model_keys:
        if key not in MODELS:
            print(f"Unknown model key: {key}. Available: {list(MODELS.keys())}", file=sys.stderr)
            continue
        model_name, backend = MODELS[key]
        print(f"\nEvaluating {key} ({backend}: {model_name})...", file=sys.stderr)
        t0 = time.perf_counter()
        result = evaluate_reranker(model_name, backend, pairs, candidates, args.top_n)
        elapsed = time.perf_counter() - t0
        print(f"  MRR: {result.mrr['mean']:.3f} [{result.mrr['ci_low']:.3f}, {result.mrr['ci_high']:.3f}]",
              file=sys.stderr)
        print(f"  nDCG@5: {result.ndcg5['mean']:.3f} [{result.ndcg5['ci_low']:.3f}, {result.ndcg5['ci_high']:.3f}]",
              file=sys.stderr)
        print(f"  Hit@5: {result.hit5['mean']:.3f} [{result.hit5['ci_low']:.3f}, {result.hit5['ci_high']:.3f}]",
              file=sys.stderr)
        print(f"  Latency: {result.mean_latency_s*1000:.0f}ms/query, Total: {elapsed:.1f}s",
              file=sys.stderr)
        results.append(result)

    # Paired significance tests
    comparisons = []
    if len(results) >= 2:
        baseline = results[0]
        for challenger in results[1:]:
            bl_mrr = np.array([q["mrr"] for q in baseline.per_query])
            ch_mrr = np.array([q["mrr"] for q in challenger.per_query])
            sig = paired_significance(ch_mrr, bl_mrr)
            diff = float(np.mean(ch_mrr) - np.mean(bl_mrr))
            comparisons.append({
                "baseline": baseline.model,
                "challenger": challenger.model,
                "mrr_diff": diff,
                "p_value": sig["p_value"],
                "significant": sig["significant_005"],
            })
            print(f"\n{challenger.model} vs {baseline.model}: "
                  f"MRR diff={diff:+.4f}, p={sig['p_value']:.4f} "
                  f"{'(significant)' if sig['significant_005'] else '(not significant)'}",
                  file=sys.stderr)

    # Output
    report = {
        "benchmark": "reranker",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "queries": len(pairs),
            "candidate_pool": args.candidate_pool,
            "top_n": args.top_n,
        },
        "results": [
            {
                "model": r.model,
                "backend": r.backend,
                "mrr": r.mrr,
                "ndcg5": r.ndcg5,
                "hit5": r.hit5,
                "mean_latency_ms": r.mean_latency_s * 1000,
            }
            for r in results
        ],
        "comparisons": comparisons,
    }

    output_str = json.dumps(report, indent=2)

    if args.output:
        Path(args.output).write_text(output_str + "\n", encoding="utf-8")
        print(f"\nReport written to {args.output}", file=sys.stderr)
    elif args.json:
        print(output_str)
    else:
        # Human-readable summary
        print("\n" + "=" * 70)
        print("RERANKER BENCHMARK RESULTS")
        print("=" * 70)
        print(f"Queries: {len(pairs)}, Candidate pool: {args.candidate_pool}, Top-N: {args.top_n}\n")
        print(f"{'Model':<45} {'MRR':>8} {'nDCG@5':>8} {'Hit@5':>8} {'Latency':>8}")
        print("-" * 70)
        for r in results:
            print(f"{r.model:<45} {r.mrr['mean']:>8.3f} {r.ndcg5['mean']:>8.3f} "
                  f"{r.hit5['mean']:>8.3f} {r.mean_latency_s*1000:>6.0f}ms")
        if comparisons:
            print(f"\n{'Comparison':<50} {'MRR diff':>10} {'p-value':>10} {'Sig?':>6}")
            print("-" * 70)
            for c in comparisons:
                sig_str = "YES" if c["significant"] else "no"
                print(f"{c['challenger']:<25} vs {c['baseline']:<22} "
                      f"{c['mrr_diff']:>+10.4f} {c['p_value']:>10.4f} {sig_str:>6}")


if __name__ == "__main__":
    main()
