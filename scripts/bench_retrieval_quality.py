#!/usr/bin/env python3
"""Retrieval quality benchmark using golden QA test set.

Calls the semantic_search Python API directly (avoids repeated model loading).
"""

import json
import sys
import time
from pathlib import Path

# Ensure project is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PROJECT_DIR = Path(__file__).resolve().parents[1]
DOCS_DIR = str(PROJECT_DIR / "cex-docs")
GOLDEN_QA = str(PROJECT_DIR / "tests/golden_qa.jsonl")


def load_golden_qa():
    cases = []
    with open(GOLDEN_QA) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def url_matches(result_url: str, expected_urls: list[str]) -> bool:
    """Check if result_url matches any expected URL (startswith match)."""
    for exp in expected_urls:
        if result_url == exp or result_url.startswith(exp) or exp.startswith(result_url):
            return True
    return False


def find_rank(results: list[dict], expected_urls: list[str]) -> int | None:
    """Find the 1-based rank of the first matching result. None if not found."""
    for i, r in enumerate(results):
        if url_matches(r.get("url", ""), expected_urls):
            return i + 1
    return None


def compute_recall(ranks: list[int | None], k: int) -> float:
    """Compute Recall@K: fraction of queries where expected was in top K."""
    hits = sum(1 for r in ranks if r is not None and r <= k)
    return hits / len(ranks) if ranks else 0.0


def mrr(ranks: list[int | None]) -> float:
    """Mean Reciprocal Rank."""
    rrs = []
    for r in ranks:
        if r is not None:
            rrs.append(1.0 / r)
        else:
            rrs.append(0.0)
    return sum(rrs) / len(rrs) if rrs else 0.0


def run_benchmark():
    cases = load_golden_qa()
    print(f"Loaded {len(cases)} golden QA test cases", flush=True)

    # Lazy import — triggers model loading once
    print("Loading semantic search module and embedding model...", flush=True)
    t_load = time.time()
    from cex_api_docs.semantic import semantic_search
    # Warm up the model with a dummy query
    semantic_search(docs_dir=DOCS_DIR, query="test", limit=1, query_type="hybrid",
                    rerank=False, include_meta=False)
    print(f"Model loaded in {time.time() - t_load:.1f}s\n", flush=True)

    # ── Part 1: Filtered vs Unfiltered (all queries, hybrid mode) ──
    print("=" * 72, flush=True)
    print("PART 1: Filtered vs Unfiltered Recall (hybrid mode, all queries)", flush=True)
    print("=" * 72, flush=True)

    filtered_ranks = []
    unfiltered_ranks = []
    filtered_details = []
    unfiltered_details = []

    for i, case in enumerate(cases):
        query = case["query"]
        expected_urls = case["expected_urls"]
        exchange = case.get("expected_exchange")

        print(f"\n[{i+1}/{len(cases)}] {query}", flush=True)
        print(f"  Exchange: {exchange}, Expected: {expected_urls[0]}", flush=True)

        # Filtered search
        t0 = time.time()
        try:
            results_f = semantic_search(
                docs_dir=DOCS_DIR, query=query, exchange=exchange,
                limit=10, query_type="hybrid", rerank="auto", include_meta=False,
            )
        except Exception as e:
            results_f = []
            print(f"  Filtered:   ERROR - {e}", flush=True)
        t_f = time.time() - t0

        rank_f = find_rank(results_f, expected_urls)
        filtered_ranks.append(rank_f)
        top_urls_f = [r["url"] for r in results_f[:3]]
        filtered_details.append({
            "query": query, "exchange": exchange, "rank": rank_f,
            "top_urls": top_urls_f, "time": t_f, "n_results": len(results_f),
        })
        status_f = f"rank={rank_f}" if rank_f else "MISS"
        print(f"  Filtered:   {status_f} ({t_f:.1f}s, {len(results_f)} results)", flush=True)
        if rank_f is None and results_f:
            print(f"    Top result: {results_f[0]['url']}", flush=True)

        # Unfiltered search
        t0 = time.time()
        try:
            results_u = semantic_search(
                docs_dir=DOCS_DIR, query=query, exchange=None,
                limit=10, query_type="hybrid", rerank="auto", include_meta=False,
            )
        except Exception as e:
            results_u = []
            print(f"  Unfiltered: ERROR - {e}", flush=True)
        t_u = time.time() - t0

        rank_u = find_rank(results_u, expected_urls)
        unfiltered_ranks.append(rank_u)
        top_urls_u = [r["url"] for r in results_u[:3]]
        unfiltered_details.append({
            "query": query, "exchange": exchange, "rank": rank_u,
            "top_urls": top_urls_u, "time": t_u, "n_results": len(results_u),
        })
        status_u = f"rank={rank_u}" if rank_u else "MISS"
        print(f"  Unfiltered: {status_u} ({t_u:.1f}s, {len(results_u)} results)", flush=True)
        if rank_u is None and results_u:
            print(f"    Top result: {results_u[0]['url']}", flush=True)

    # Recall summary
    print("\n" + "=" * 72, flush=True)
    print("RECALL SUMMARY — Filtered vs Unfiltered", flush=True)
    print("=" * 72, flush=True)
    print(f"{'Metric':<20} {'Filtered':>12} {'Unfiltered':>12} {'Delta':>10}", flush=True)
    print("-" * 54, flush=True)
    for k in [1, 3, 5, 10]:
        r_f = compute_recall(filtered_ranks, k)
        r_u = compute_recall(unfiltered_ranks, k)
        delta = r_f - r_u
        sign = "+" if delta >= 0 else ""
        print(f"Recall@{k:<13} {r_f:>11.1%} {r_u:>11.1%} {sign}{delta:>9.1%}", flush=True)

    # Failed queries detail
    print("\n" + "=" * 72, flush=True)
    print("FAILED QUERIES (not in top 10)", flush=True)
    print("=" * 72, flush=True)

    print("\n-- Filtered --", flush=True)
    any_fail = False
    for d in filtered_details:
        if d.get("rank") is None:
            any_fail = True
            print(f"  Q: {d['query']}", flush=True)
            if d.get("top_urls"):
                for j, u in enumerate(d["top_urls"][:3]):
                    prefix = "    Got instead:" if j == 0 else "                "
                    print(f"{prefix} {u}", flush=True)
            else:
                print("    No results returned", flush=True)
    if not any_fail:
        print("  (none)", flush=True)

    print("\n-- Unfiltered --", flush=True)
    any_fail = False
    for d in unfiltered_details:
        if d.get("rank") is None:
            any_fail = True
            print(f"  Q: {d['query']}", flush=True)
            if d.get("top_urls"):
                for j, u in enumerate(d["top_urls"][:3]):
                    prefix = "    Got instead:" if j == 0 else "                "
                    print(f"{prefix} {u}", flush=True)
            else:
                print("    No results returned", flush=True)
    if not any_fail:
        print("  (none)", flush=True)

    # ── Part 2: Mode comparison (first 5 queries) ──
    print("\n" + "=" * 72, flush=True)
    print("PART 2: Search Mode Comparison (first 5 queries, filtered)", flush=True)
    print("=" * 72, flush=True)

    modes = ["vector", "fts", "hybrid"]
    mode_ranks = {m: [] for m in modes}
    mode_details = {m: [] for m in modes}

    for i, case in enumerate(cases[:5]):
        query = case["query"]
        expected_urls = case["expected_urls"]
        exchange = case.get("expected_exchange")

        print(f"\n[{i+1}/5] {query}", flush=True)

        for mode in modes:
            t0 = time.time()
            try:
                results = semantic_search(
                    docs_dir=DOCS_DIR, query=query, exchange=exchange,
                    limit=10, query_type=mode, rerank="auto", include_meta=False,
                )
            except Exception as e:
                results = []
                print(f"  {mode:>7}: ERROR - {e}", flush=True)
            t = time.time() - t0

            rank = find_rank(results, expected_urls)
            mode_ranks[mode].append(rank)
            mode_details[mode].append({
                "query": query, "rank": rank,
                "top_url": results[0]["url"] if results else None,
                "n_results": len(results), "time": t,
            })
            status = f"rank={rank}" if rank else "MISS"
            top = results[0]["url"][:60] if results else "(none)"
            print(f"  {mode:>7}: {status:>8} ({t:.1f}s, {len(results)} results) top={top}", flush=True)

    print("\n" + "=" * 72, flush=True)
    print("MODE COMPARISON SUMMARY (first 5 queries)", flush=True)
    print("=" * 72, flush=True)
    print(f"{'Metric':<20}", end="", flush=True)
    for m in modes:
        print(f" {m:>10}", end="")
    print(flush=True)
    print("-" * 50, flush=True)
    for k in [1, 3, 5, 10]:
        print(f"Recall@{k:<13}", end="")
        for m in modes:
            r = compute_recall(mode_ranks[m], k)
            print(f" {r:>9.1%}", end="")
        print(flush=True)
    print(f"{'MRR':<20}", end="")
    for m in modes:
        v = mrr(mode_ranks[m])
        print(f" {v:>9.3f}", end="")
    print(flush=True)

    # ── Part 3: Overall Analysis ──
    print("\n" + "=" * 72, flush=True)
    print("OVERALL ANALYSIS", flush=True)
    print("=" * 72, flush=True)

    mrr_f = mrr(filtered_ranks)
    mrr_u = mrr(unfiltered_ranks)
    print(f"MRR (filtered):   {mrr_f:.3f}", flush=True)
    print(f"MRR (unfiltered): {mrr_u:.3f}", flush=True)

    hits_f = sum(1 for r in filtered_ranks if r is not None)
    hits_u = sum(1 for r in unfiltered_ranks if r is not None)
    total = len(cases)
    print(f"\nHit rate (filtered):   {hits_f}/{total} ({hits_f/total:.1%})", flush=True)
    print(f"Hit rate (unfiltered): {hits_u}/{total} ({hits_u/total:.1%})", flush=True)

    # Per-exchange breakdown
    exchange_hits = {}
    for case, rank in zip(cases, filtered_ranks):
        ex = case.get("expected_exchange", "unknown")
        if ex not in exchange_hits:
            exchange_hits[ex] = {"total": 0, "hit": 0}
        exchange_hits[ex]["total"] += 1
        if rank is not None:
            exchange_hits[ex]["hit"] += 1

    print("\nPer-exchange hit rate (filtered, top 10):", flush=True)
    for ex, stats in sorted(exchange_hits.items()):
        rate = stats["hit"] / stats["total"]
        print(f"  {ex:<15} {stats['hit']}/{stats['total']} ({rate:.0%})", flush=True)

    # Rank distribution
    print("\nRank distribution (filtered):", flush=True)
    rank_counts = {}
    for r in filtered_ranks:
        if r is not None:
            bucket = f"rank {r}"
            rank_counts[bucket] = rank_counts.get(bucket, 0) + 1
        else:
            rank_counts["miss"] = rank_counts.get("miss", 0) + 1
    for k in sorted(rank_counts.keys(), key=lambda x: (x == "miss", x)):
        print(f"  {k}: {rank_counts[k]}", flush=True)

    print("\n" + "=" * 72, flush=True)
    print("BENCHMARK COMPLETE", flush=True)
    print("=" * 72, flush=True)


if __name__ == "__main__":
    run_benchmark()
