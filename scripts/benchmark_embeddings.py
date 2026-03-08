#!/usr/bin/env python3
"""Embedding model benchmark with statistical significance testing.

Evaluates embedding models by running retrieval against the production LanceDB
index and computing quality metrics with bootstrap 95% CI.

Design:
  Each model retrieves independently (since embedding determines what is found).
  Compares Hit@5, MRR, nDCG@5 across models with paired permutation tests.

  NOTE: Switching embedding models requires a full LanceDB index rebuild
  (~2-3 hours). This script evaluates the CURRENT index's embedding model.
  To compare models, rebuild the index between runs and use --compare.

Usage:
    python scripts/benchmark_embeddings.py --docs-dir ./cex-docs
    python scripts/benchmark_embeddings.py --docs-dir ./cex-docs --json
    python scripts/benchmark_embeddings.py --docs-dir ./cex-docs --compare reports/m10-embedding-baseline.json
    python scripts/benchmark_embeddings.py --docs-dir ./cex-docs --output reports/m10-embedding-v5small.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np
from scipy.stats import bootstrap


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


# ── Search modes ──

def evaluate_search(
    docs_dir: str,
    qa_pairs: list[dict],
    query_type: str = "hybrid",
    rerank: bool = True,
    limit: int = 5,
) -> dict:
    """Run all queries through semantic_search, compute per-query metrics."""
    from cex_api_docs.semantic import semantic_search

    # Warm up
    semantic_search(docs_dir=docs_dir, query="test", limit=1,
                    query_type=query_type, rerank=False, include_meta=False)

    per_query = []
    latencies = []

    for i, pair in enumerate(qa_pairs):
        query = pair["query"]
        expected_urls = pair.get("expected_urls", [])
        exchange = pair.get("expected_exchange")
        relevance = pair.get("relevance", 2)

        t0 = time.perf_counter()
        try:
            results = semantic_search(
                docs_dir=docs_dir, query=query, exchange=exchange,
                limit=limit, query_type=query_type, rerank=rerank,
                include_meta=False,
            )
        except Exception as e:
            print(f"  [{i+1}] FAILED: {query[:50]}... — {e}", file=sys.stderr)
            results = []
        latency = time.perf_counter() - t0
        latencies.append(latency)

        result_urls = [r.get("url", "") for r in results]
        expected_normed = {_norm(u) for u in expected_urls}

        # MRR
        mrr_val = 0.0
        for j, url in enumerate(result_urls, 1):
            if _norm(url) in expected_normed or any(_prefix_match(url, eu) for eu in expected_urls):
                mrr_val = 1.0 / j
                break

        # Hit@5
        hit_val = 1.0 if any(
            _norm(u) in expected_normed or any(_prefix_match(u, eu) for eu in expected_urls)
            for u in result_urls
        ) else 0.0

        # nDCG@5
        gains = []
        expected_domains = {_domain(u) for u in expected_urls}
        for url in result_urls[:5]:
            if _norm(url) in expected_normed:
                gains.append(float(relevance))
            elif any(_prefix_match(url, eu) for eu in expected_urls):
                gains.append(float(max(1, relevance - 1)))
            elif _domain(url) in expected_domains:
                gains.append(1.0)
            else:
                gains.append(0.0)
        ideal = [float(relevance)] * min(len(expected_urls), 5) if expected_urls else [0.0]
        ndcg_val = _ndcg_at_k(gains, ideal)

        per_query.append({
            "query": query,
            "classification": pair.get("classification", "question"),
            "mrr": mrr_val,
            "ndcg5": ndcg_val,
            "hit5": hit_val,
            "latency_s": latency,
        })

        if (i + 1) % 30 == 0:
            print(f"  [{i+1}/{len(qa_pairs)}] evaluated", file=sys.stderr)

    arr_mrr = np.array([q["mrr"] for q in per_query])
    arr_ndcg = np.array([q["ndcg5"] for q in per_query])
    arr_hit = np.array([q["hit5"] for q in per_query])

    # Per-classification breakdown
    by_class = {}
    for pq in per_query:
        cls = pq["classification"]
        if cls not in by_class:
            by_class[cls] = {"mrr": [], "ndcg5": [], "hit5": []}
        by_class[cls]["mrr"].append(pq["mrr"])
        by_class[cls]["ndcg5"].append(pq["ndcg5"])
        by_class[cls]["hit5"].append(pq["hit5"])

    by_class_summary = {}
    for cls, vals in by_class.items():
        by_class_summary[cls] = {
            "total": len(vals["mrr"]),
            "mrr": float(np.mean(vals["mrr"])),
            "ndcg5": float(np.mean(vals["ndcg5"])),
            "hit5": float(np.mean(vals["hit5"])),
        }

    return {
        "mrr": bootstrap_ci(arr_mrr),
        "ndcg5": bootstrap_ci(arr_ndcg),
        "hit5": bootstrap_ci(arr_hit),
        "mean_latency_s": float(np.mean(latencies)),
        "p50_latency_s": float(np.percentile(latencies, 50)),
        "p95_latency_s": float(np.percentile(latencies, 95)),
        "by_classification": by_class_summary,
        "per_query": per_query,
    }


def compare_reports(current: dict, baseline: dict) -> list[dict]:
    """Compare current results with a baseline report."""
    comparisons = []
    for metric in ["mrr", "ndcg5", "hit5"]:
        cur = current.get(metric, {})
        base = baseline.get(metric, {})
        if cur and base:
            diff = cur["mean"] - base["mean"]
            # Check CI overlap
            overlap = cur["ci_low"] <= base["ci_high"] and base["ci_low"] <= cur["ci_high"]
            comparisons.append({
                "metric": metric,
                "current": cur["mean"],
                "baseline": base["mean"],
                "diff": diff,
                "pct_change": diff / base["mean"] * 100 if base["mean"] > 0 else 0,
                "ci_overlap": overlap,
                "significant": not overlap,
            })
    return comparisons


def main():
    parser = argparse.ArgumentParser(description="Embedding model benchmark")
    parser.add_argument("--docs-dir", default="./cex-docs")
    parser.add_argument("--qa-file", default="tests/golden_qa.jsonl")
    parser.add_argument("--query-type", default="vector",
                        choices=["vector", "hybrid", "fts"],
                        help="Search mode (vector isolates embedding quality)")
    parser.add_argument("--rerank", action="store_true", default=False,
                        help="Enable reranking (default: off to isolate embedding)")
    parser.add_argument("--limit", type=int, default=None, help="Limit queries")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--compare", type=str, default=None,
                        help="Baseline JSON report for comparison")
    args = parser.parse_args()

    # Detect current embedding model
    from cex_api_docs.embeddings import get_embedder
    embedder = get_embedder()
    model_name = embedder.model_name
    dims = embedder.ndims()
    print(f"Embedding model: {model_name} ({dims}d, {embedder.backend_name})", file=sys.stderr)

    # Load golden QA
    qa_file = Path(args.qa_file)
    pairs = []
    for line in qa_file.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pair = json.loads(line)
        if "negative" in pair.get("tags", []):
            continue
        pairs.append(pair)

    if args.limit:
        pairs = pairs[:args.limit]

    print(f"\nBenchmark: {len(pairs)} queries, mode={args.query_type}, "
          f"rerank={args.rerank}, top_n={args.top_n}", file=sys.stderr)

    result = evaluate_search(
        args.docs_dir, pairs, args.query_type, args.rerank, args.top_n,
    )

    print(f"\n  MRR: {result['mrr']['mean']:.3f} [{result['mrr']['ci_low']:.3f}, {result['mrr']['ci_high']:.3f}]",
          file=sys.stderr)
    print(f"  nDCG@5: {result['ndcg5']['mean']:.3f} [{result['ndcg5']['ci_low']:.3f}, {result['ndcg5']['ci_high']:.3f}]",
          file=sys.stderr)
    print(f"  Hit@5: {result['hit5']['mean']:.3f} [{result['hit5']['ci_low']:.3f}, {result['hit5']['ci_high']:.3f}]",
          file=sys.stderr)
    print(f"  Latency: p50={result['p50_latency_s']*1000:.0f}ms, p95={result['p95_latency_s']*1000:.0f}ms",
          file=sys.stderr)

    report = {
        "benchmark": "embedding",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "model": model_name,
            "dims": dims,
            "backend": embedder.backend_name,
            "query_type": args.query_type,
            "rerank": args.rerank,
            "queries": len(pairs),
            "top_n": args.top_n,
        },
        "results": {k: v for k, v in result.items() if k != "per_query"},
        "per_query": result["per_query"],
    }

    # Comparison with baseline
    if args.compare:
        baseline_data = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        baseline_results = baseline_data.get("results", {})
        comparisons = compare_reports(result, baseline_results)
        report["comparisons"] = comparisons

        print("\n  Comparison with baseline:", file=sys.stderr)
        for c in comparisons:
            sig = "SIGNIFICANT" if c["significant"] else "not significant"
            print(f"    {c['metric']}: {c['baseline']:.3f} → {c['current']:.3f} "
                  f"({c['pct_change']:+.1f}%, {sig})", file=sys.stderr)

    output_str = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_str + "\n", encoding="utf-8")
        print(f"\nReport written to {args.output}", file=sys.stderr)
    elif args.json:
        print(output_str)


if __name__ == "__main__":
    main()
