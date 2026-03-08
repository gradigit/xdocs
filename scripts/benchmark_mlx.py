#!/usr/bin/env python3
"""MLX benchmark for embedding and reranker models on Apple Silicon.

Measures retrieval quality (Hit@5, MRR, nDCG@5), embedding throughput,
reranker quality lift, and MLX memory usage.

Requirements:
    pip install -e ".[semantic]"
    # macOS Apple Silicon only. Requires mlx, lancedb, huggingface_hub.
    # Models download on first run (~2.5GB total for embedder + reranker).

Usage:
    python scripts/benchmark_mlx.py --docs-dir ./cex-docs
    python scripts/benchmark_mlx.py --docs-dir ./cex-docs --json
    python scripts/benchmark_mlx.py --docs-dir ./cex-docs --skip-reranker
    python scripts/benchmark_mlx.py --docs-dir ./cex-docs --output reports/m10-mlx.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse


def _check_mlx():
    if platform.system() != "Darwin":
        print("ERROR: This benchmark requires macOS with Apple Silicon.", file=sys.stderr)
        print(f"  Current platform: {platform.system()}", file=sys.stderr)
        sys.exit(1)
    try:
        import mlx.core as mx
        if not mx.metal.is_available():
            print("ERROR: Metal GPU not available.", file=sys.stderr)
            sys.exit(1)
        return mx
    except ImportError:
        print("ERROR: mlx not installed. Run: pip install -e '.[semantic]'", file=sys.stderr)
        sys.exit(1)


# ── Metrics (same as benchmark_embeddings.py) ──

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


def _memory_snapshot(mx, label: str = "") -> dict:
    return {
        "label": label,
        "active_mb": round(mx.metal.get_active_memory() / (1024**2), 1),
        "peak_mb": round(mx.metal.get_peak_memory() / (1024**2), 1),
        "cache_mb": round(mx.metal.get_cache_memory() / (1024**2), 1),
    }


def _get_platform_info(mx) -> dict:
    import subprocess
    ram_gb = None
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True
        )
        ram_gb = round(int(result.stdout.strip()) / (1024**3), 1)
    except Exception:
        pass

    chip = "unknown"
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        )
        chip = result.stdout.strip()
    except Exception:
        pass

    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "chip": chip,
        "ram_gb": ram_gb,
        "python": platform.python_version(),
        "mlx_version": mx.__version__,
    }


def benchmark_embedding_quality(docs_dir: str, qa_pairs: list[dict], limit: int = 5):
    """Measure retrieval quality using vector-only search."""
    from cex_api_docs.semantic import semantic_search

    # Warm up (3 calls for shader compilation)
    for _ in range(3):
        semantic_search(docs_dir=docs_dir, query="test", limit=1,
                        query_type="vector", rerank=False, include_meta=False)

    per_query = []
    for pair in qa_pairs:
        expected_urls = pair.get("expected_urls", [])
        relevance = pair.get("relevance", 2)

        t0 = time.perf_counter()
        try:
            results = semantic_search(
                docs_dir=docs_dir, query=pair["query"],
                exchange=pair.get("expected_exchange"),
                limit=limit, query_type="vector",
                rerank=False, include_meta=False,
            )
        except Exception:
            results = []
        latency = time.perf_counter() - t0

        result_urls = [r.get("url", "") for r in results]
        expected_normed = {_norm(u) for u in expected_urls}
        expected_doms = {_domain(u) for u in expected_urls}

        mrr = 0.0
        for j, url in enumerate(result_urls, 1):
            if _norm(url) in expected_normed or any(_prefix_match(url, eu) for eu in expected_urls):
                mrr = 1.0 / j
                break

        hit5 = 1.0 if any(
            _norm(u) in expected_normed or any(_prefix_match(u, eu) for eu in expected_urls)
            for u in result_urls
        ) else 0.0

        gains = []
        for url in result_urls[:5]:
            if _norm(url) in expected_normed:
                gains.append(float(relevance))
            elif any(_prefix_match(url, eu) for eu in expected_urls):
                gains.append(float(max(1, relevance - 1)))
            elif _domain(url) in expected_doms:
                gains.append(1.0)
            else:
                gains.append(0.0)
        ideal = [float(relevance)] * min(len(expected_urls), 5) if expected_urls else [0.0]
        ndcg5 = _ndcg_at_k(gains, ideal)

        per_query.append({
            "query": pair["query"],
            "classification": pair.get("classification", "question"),
            "mrr": mrr, "ndcg5": ndcg5, "hit5": hit5, "latency_s": latency,
        })

    import numpy as np
    latencies = [q["latency_s"] for q in per_query]
    return {
        "total": len(per_query),
        "mrr": float(np.mean([q["mrr"] for q in per_query])),
        "ndcg5": float(np.mean([q["ndcg5"] for q in per_query])),
        "hit5": float(np.mean([q["hit5"] for q in per_query])),
        "mean_latency_s": float(np.mean(latencies)),
        "p50_latency_s": float(np.percentile(latencies, 50)),
        "p95_latency_s": float(np.percentile(latencies, 95)),
        "per_query": per_query,
    }


def benchmark_embedding_throughput(mx, texts: list[str], batch_sizes=(1, 16, 32, 64)):
    """Measure embedding throughput at different batch sizes."""
    from cex_api_docs.embeddings import get_embedder
    embedder = get_embedder()

    results = {}
    for bs in batch_sizes:
        # Warm up
        for _ in range(10):
            embedder.embed_texts(texts[:min(bs, len(texts))])

        mx.metal.reset_peak_memory()
        mx.clear_cache()

        t0 = time.perf_counter()
        total = 0
        for i in range(0, len(texts), bs):
            batch = texts[i:i+bs]
            embedder.embed_texts(batch)
            total += len(batch)
        elapsed = time.perf_counter() - t0

        results[f"batch_{bs}"] = {
            "batch_size": bs,
            "total_texts": total,
            "total_time_s": round(elapsed, 2),
            "texts_per_second": round(total / elapsed, 1),
            "peak_memory_mb": round(mx.metal.get_peak_memory() / (1024**2), 1),
        }
        mx.clear_cache()
        print(f"  Batch {bs}: {total/elapsed:.1f} texts/sec", file=sys.stderr)

    return results


def benchmark_reranker(docs_dir: str, qa_pairs: list[dict], candidate_pool: int = 30, top_n: int = 5):
    """Measure reranker quality lift: unreranked vs reranked nDCG@5."""
    os.environ["CEX_RERANKER_BACKEND"] = "jina-v3-mlx"
    from cex_api_docs.semantic import semantic_search

    # Warm up
    semantic_search(docs_dir=docs_dir, query="test", limit=1,
                    query_type="vector", rerank=True, include_meta=False)

    per_query = []
    for pair in qa_pairs:
        expected_urls = pair.get("expected_urls", [])
        relevance = pair.get("relevance", 2)
        expected_normed = {_norm(u) for u in expected_urls}

        # Unreranked baseline
        baseline = semantic_search(
            docs_dir=docs_dir, query=pair["query"],
            exchange=pair.get("expected_exchange"),
            limit=top_n, query_type="vector", rerank=False, include_meta=False,
        )
        baseline_urls = [r.get("url", "") for r in baseline]

        # Reranked
        t0 = time.perf_counter()
        reranked = semantic_search(
            docs_dir=docs_dir, query=pair["query"],
            exchange=pair.get("expected_exchange"),
            limit=top_n, query_type="vector", rerank=True, include_meta=False,
        )
        rerank_latency = time.perf_counter() - t0
        reranked_urls = [r.get("url", "") for r in reranked]

        def quick_ndcg(urls):
            gains = []
            for url in urls[:5]:
                if _norm(url) in expected_normed:
                    gains.append(float(relevance))
                elif any(_prefix_match(url, eu) for eu in expected_urls):
                    gains.append(float(max(1, relevance - 1)))
                else:
                    gains.append(0.0)
            ideal = [float(relevance)] * min(len(expected_urls), 5) if expected_urls else [0.0]
            return _ndcg_at_k(gains, ideal)

        b_ndcg = quick_ndcg(baseline_urls)
        r_ndcg = quick_ndcg(reranked_urls)

        per_query.append({
            "query": pair["query"],
            "baseline_ndcg5": b_ndcg,
            "reranked_ndcg5": r_ndcg,
            "ndcg_lift": r_ndcg - b_ndcg,
            "rerank_latency_s": rerank_latency,
        })

    import numpy as np
    lifts = [q["ndcg_lift"] for q in per_query]
    lats = [q["rerank_latency_s"] for q in per_query]
    return {
        "total_queries": len(per_query),
        "baseline_mean_ndcg5": float(np.mean([q["baseline_ndcg5"] for q in per_query])),
        "reranked_mean_ndcg5": float(np.mean([q["reranked_ndcg5"] for q in per_query])),
        "ndcg_lift": float(np.mean(lifts)),
        "mean_rerank_latency_s": float(np.mean(lats)),
        "p95_rerank_latency_s": float(np.percentile(lats, 95)),
        "queries_improved": sum(1 for l in lifts if l > 0),
        "queries_unchanged": sum(1 for l in lifts if l == 0),
        "queries_worsened": sum(1 for l in lifts if l < 0),
    }


def main():
    parser = argparse.ArgumentParser(description="MLX benchmark for cex-api-docs")
    parser.add_argument("--docs-dir", default="./cex-docs")
    parser.add_argument("--qa-file", default="tests/golden_qa.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skip-reranker", action="store_true")
    parser.add_argument("--skip-throughput", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--batch-sizes", type=str, default="1,16,32,64")
    args = parser.parse_args()

    mx = _check_mlx()

    # Platform info
    plat = _get_platform_info(mx)
    print(f"Platform: {plat['chip']}, {plat['ram_gb']}GB RAM, MLX {plat['mlx_version']}",
          file=sys.stderr)

    # Detect embedding model
    os.environ.setdefault("CEX_EMBEDDING_BACKEND", "jina-mlx")
    from cex_api_docs.embeddings import get_embedder
    embedder = get_embedder()
    print(f"Embedder: {embedder.model_name} ({embedder.ndims()}d, {embedder.backend_name})",
          file=sys.stderr)

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

    print(f"\nBenchmark: {len(pairs)} queries\n", file=sys.stderr)

    # Phase 1: Embedding quality
    print("Phase 1: Embedding quality (vector-only search)...", file=sys.stderr)
    mx.metal.reset_peak_memory()
    mx.clear_cache()
    emb_quality = benchmark_embedding_quality(args.docs_dir, pairs)
    emb_memory = _memory_snapshot(mx, "post_embedding_quality")
    print(f"  MRR: {emb_quality['mrr']:.3f}, nDCG@5: {emb_quality['ndcg5']:.3f}, "
          f"Hit@5: {emb_quality['hit5']:.3f}", file=sys.stderr)

    # Phase 2: Embedding throughput
    emb_throughput = {}
    if not args.skip_throughput:
        print("\nPhase 2: Embedding throughput...", file=sys.stderr)
        sample_texts = [pair["query"] for pair in pairs[:100]]
        batch_sizes = tuple(int(b) for b in args.batch_sizes.split(","))
        emb_throughput = benchmark_embedding_throughput(mx, sample_texts, batch_sizes)

    # Phase 3: Reranker quality
    reranker_quality = None
    if not args.skip_reranker:
        print("\nPhase 3: Reranker quality lift (jina-v3-mlx)...", file=sys.stderr)
        mx.metal.reset_peak_memory()
        mx.clear_cache()
        reranker_quality = benchmark_reranker(args.docs_dir, pairs)
        print(f"  Baseline nDCG@5: {reranker_quality['baseline_mean_ndcg5']:.3f}",
              file=sys.stderr)
        print(f"  Reranked nDCG@5: {reranker_quality['reranked_mean_ndcg5']:.3f} "
              f"(lift: {reranker_quality['ndcg_lift']:+.3f})", file=sys.stderr)
        print(f"  Improved: {reranker_quality['queries_improved']}, "
              f"Worsened: {reranker_quality['queries_worsened']}", file=sys.stderr)

    final_memory = _memory_snapshot(mx, "final")

    report = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "platform": plat,
            "models": {
                "embedder": embedder.model_name,
                "embedder_dims": embedder.ndims(),
                "reranker": "jinaai/jina-reranker-v3-mlx" if not args.skip_reranker else None,
            },
        },
        "embedding_quality": {k: v for k, v in emb_quality.items() if k != "per_query"},
        "embedding_throughput": emb_throughput,
        "reranker_quality": reranker_quality,
        "memory_profile": {
            "embedding_peak_mb": emb_memory["peak_mb"],
            "final_active_mb": final_memory["active_mb"],
            "final_cache_mb": final_memory["cache_mb"],
        },
    }

    output_str = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_str + "\n", encoding="utf-8")
        print(f"\nReport written to {args.output}", file=sys.stderr)
    elif args.json:
        print(output_str)
    else:
        print(f"\n{'='*50}")
        print("MLX BENCHMARK RESULTS")
        print(f"{'='*50}")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
