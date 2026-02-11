#!/usr/bin/env python3
"""POC: Compare LanceDB semantic search vs SQLite FTS5 on 20 test queries.

Usage:
    source .venv/bin/activate
    python scripts/poc_lancedb_eval.py --docs-dir ./cex-docs

Requires: pip install -e ".[semantic]"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cex_api_docs.semantic import build_index, fts5_search, semantic_search

# 20 test queries spanning different query types:
# - Natural language questions (semantic search should shine)
# - Exact API path lookups (FTS should shine)
# - Conceptual/synonym queries (semantic should shine)
# - Cross-exchange queries (semantic should help)
TEST_QUERIES = [
    # Natural language questions
    {"q": "How do I check my account balance on Binance?", "exchange": "binance", "type": "natural"},
    {"q": "What permissions does the API key need?", "exchange": None, "type": "natural"},
    {"q": "How to place a limit order", "exchange": None, "type": "natural"},
    {"q": "How to withdraw funds from my account", "exchange": None, "type": "natural"},
    {"q": "What are the rate limits for trading endpoints?", "exchange": None, "type": "natural"},
    # Exact API lookups
    {"q": "GET /api/v3/account", "exchange": "binance", "type": "exact"},
    {"q": "POST /api/v3/order", "exchange": "binance", "type": "exact"},
    {"q": "/v5/market/tickers", "exchange": "bybit", "type": "exact"},
    {"q": "GET /api/v1/market/orderbook/level2_20", "exchange": "kucoin", "type": "exact"},
    {"q": "/api/v5/account/balance", "exchange": "okx", "type": "exact"},
    # Conceptual / synonym queries (semantic should bridge the gap)
    {"q": "authentication HMAC signature", "exchange": None, "type": "concept"},
    {"q": "websocket real-time order updates", "exchange": None, "type": "concept"},
    {"q": "transfer assets between accounts", "exchange": None, "type": "concept"},
    {"q": "candlestick chart data klines", "exchange": None, "type": "concept"},
    {"q": "IP whitelist security restrictions", "exchange": None, "type": "concept"},
    # Cross-exchange queries
    {"q": "margin trading leverage API", "exchange": None, "type": "cross"},
    {"q": "copy trading follower endpoints", "exchange": None, "type": "cross"},
    {"q": "earn staking savings products", "exchange": None, "type": "cross"},
    {"q": "broker sub-account management", "exchange": None, "type": "cross"},
    {"q": "futures perpetual swap funding rate", "exchange": None, "type": "cross"},
]


def run_eval(docs_dir: str, limit: int, top_k: int = 5) -> dict:
    print(f"=== LanceDB POC Evaluation ===")
    print(f"Store: {docs_dir}")
    print(f"Embedding limit: {limit} pages")
    print(f"Top-K: {top_k} results per query")
    print()

    # Step 1: Build index.
    print("Building LanceDB index...")
    t0 = time.time()
    build_result = build_index(docs_dir=docs_dir, limit=limit)
    build_time = time.time() - t0
    print(f"  Embedded {build_result['pages_embedded']} pages in {build_time:.1f}s")
    print(f"  Skipped {build_result.get('skipped', 0)} pages (no content)")
    print(f"  Index at: {build_result.get('lance_dir', 'N/A')}")
    print()

    # Step 2: Run queries.
    results = []
    fts5_total_ms = 0
    vector_total_ms = 0
    hybrid_total_ms = 0

    for i, tq in enumerate(TEST_QUERIES):
        q = tq["q"]
        exchange = tq.get("exchange")
        qtype = tq["type"]

        # FTS5 baseline.
        t0 = time.time()
        try:
            fts5_results = fts5_search(docs_dir=docs_dir, query=q, exchange=exchange, limit=top_k)
        except Exception as e:
            fts5_results = [{"error": str(e)}]
        fts5_ms = (time.time() - t0) * 1000
        fts5_total_ms += fts5_ms

        # LanceDB vector search.
        t0 = time.time()
        try:
            vec_results = semantic_search(docs_dir=docs_dir, query=q, exchange=exchange, limit=top_k, query_type="vector")
        except Exception as e:
            vec_results = [{"error": str(e)}]
        vec_ms = (time.time() - t0) * 1000
        vector_total_ms += vec_ms

        # LanceDB hybrid search.
        t0 = time.time()
        try:
            hybrid_results = semantic_search(docs_dir=docs_dir, query=q, exchange=exchange, limit=top_k, query_type="hybrid")
        except Exception as e:
            hybrid_results = [{"error": str(e)}]
        hybrid_ms = (time.time() - t0) * 1000
        hybrid_total_ms += hybrid_ms

        # Compare top-1 results.
        fts5_top = fts5_results[0]["url"] if fts5_results and "url" in fts5_results[0] else None
        vec_top = vec_results[0]["url"] if vec_results and "url" in vec_results[0] else None
        hybrid_top = hybrid_results[0]["url"] if hybrid_results and "url" in hybrid_results[0] else None

        # URL overlap between FTS5 and hybrid top-K.
        fts5_urls = {r["url"] for r in fts5_results if "url" in r}
        vec_urls = {r["url"] for r in vec_results if "url" in r}
        hybrid_urls = {r["url"] for r in hybrid_results if "url" in r}
        overlap_fts_vec = len(fts5_urls & vec_urls)
        overlap_fts_hybrid = len(fts5_urls & hybrid_urls)

        result = {
            "query": q,
            "type": qtype,
            "exchange": exchange,
            "fts5": {"top1": fts5_top, "count": len(fts5_results), "ms": round(fts5_ms, 1)},
            "vector": {"top1": vec_top, "count": len(vec_results), "ms": round(vec_ms, 1)},
            "hybrid": {"top1": hybrid_top, "count": len(hybrid_results), "ms": round(hybrid_ms, 1)},
            "overlap_fts_vec": overlap_fts_vec,
            "overlap_fts_hybrid": overlap_fts_hybrid,
            "top1_match": fts5_top == hybrid_top,
            "fts5_results": fts5_results[:3],
            "vec_results": vec_results[:3],
            "hybrid_results": hybrid_results[:3],
        }
        results.append(result)

        # Print summary line.
        match_icon = "=" if fts5_top == hybrid_top else "!"
        print(f"  [{i+1:2d}/{len(TEST_QUERIES)}] {match_icon} [{qtype:8s}] {q[:60]}")
        print(f"         FTS5:   {_short_url(fts5_top)} ({fts5_ms:.0f}ms)")
        print(f"         Vector: {_short_url(vec_top)} ({vec_ms:.0f}ms)")
        print(f"         Hybrid: {_short_url(hybrid_top)} ({hybrid_ms:.0f}ms)")
        print(f"         Overlap: FTS∩Vec={overlap_fts_vec}/{top_k}  FTS∩Hyb={overlap_fts_hybrid}/{top_k}")
        print()

    # Summary stats.
    n = len(TEST_QUERIES)
    top1_matches = sum(1 for r in results if r["top1_match"])
    avg_overlap_vec = sum(r["overlap_fts_vec"] for r in results) / n
    avg_overlap_hybrid = sum(r["overlap_fts_hybrid"] for r in results) / n

    # Per-type breakdown.
    types = sorted(set(r["type"] for r in results))
    type_stats = {}
    for t in types:
        typed = [r for r in results if r["type"] == t]
        type_stats[t] = {
            "count": len(typed),
            "top1_match_rate": sum(1 for r in typed if r["top1_match"]) / len(typed),
            "avg_overlap_fts_vec": sum(r["overlap_fts_vec"] for r in typed) / len(typed),
            "avg_overlap_fts_hybrid": sum(r["overlap_fts_hybrid"] for r in typed) / len(typed),
        }

    summary = {
        "build_time_s": round(build_time, 1),
        "pages_embedded": build_result["pages_embedded"],
        "queries": n,
        "top_k": top_k,
        "top1_match_rate": round(top1_matches / n, 2),
        "avg_overlap_fts_vec": round(avg_overlap_vec, 2),
        "avg_overlap_fts_hybrid": round(avg_overlap_hybrid, 2),
        "avg_latency_ms": {
            "fts5": round(fts5_total_ms / n, 1),
            "vector": round(vector_total_ms / n, 1),
            "hybrid": round(hybrid_total_ms / n, 1),
        },
        "type_breakdown": type_stats,
    }

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Pages embedded:        {summary['pages_embedded']}")
    print(f"Build time:            {summary['build_time_s']}s")
    print(f"Queries:               {summary['queries']}")
    print(f"Top-1 match rate:      {summary['top1_match_rate']:.0%} (FTS5 == Hybrid)")
    print(f"Avg overlap FTS∩Vec:   {summary['avg_overlap_fts_vec']:.1f}/{top_k}")
    print(f"Avg overlap FTS∩Hyb:   {summary['avg_overlap_fts_hybrid']:.1f}/{top_k}")
    print(f"Avg latency FTS5:      {summary['avg_latency_ms']['fts5']:.1f}ms")
    print(f"Avg latency Vector:    {summary['avg_latency_ms']['vector']:.1f}ms")
    print(f"Avg latency Hybrid:    {summary['avg_latency_ms']['hybrid']:.1f}ms")
    print()
    print("Per-type breakdown:")
    for t, st in type_stats.items():
        print(f"  {t:10s}: top1_match={st['top1_match_rate']:.0%}  overlap_vec={st['avg_overlap_fts_vec']:.1f}  overlap_hybrid={st['avg_overlap_fts_hybrid']:.1f}")

    return {"summary": summary, "results": results}


def _short_url(url: str | None) -> str:
    if url is None:
        return "(none)"
    # Trim to last 60 chars.
    if len(url) > 70:
        return "..." + url[-67:]
    return url


def main():
    parser = argparse.ArgumentParser(description="LanceDB POC evaluation")
    parser.add_argument("--docs-dir", required=True, help="Path to cex-docs store")
    parser.add_argument("--limit", type=int, default=200, help="Max pages to embed (0=all)")
    parser.add_argument("--top-k", type=int, default=5, help="Results per query")
    parser.add_argument("--output", type=str, help="Write JSON report to file")
    args = parser.parse_args()

    report = run_eval(args.docs_dir, args.limit, args.top_k)

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nFull report saved to: {args.output}")


if __name__ == "__main__":
    main()
