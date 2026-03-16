"""Answer pipeline evaluation — tests the full answer_question flow.

Checks that answer claims contain expected URLs or endpoint paths, and
measures relevance@k, MRR, nDCG@5, and citation accuracy across the golden QA set.
Supports graded relevance, per-classification-path breakdown, and pre/post comparison.

Usage:
    python -m tests.eval_answer_pipeline --docs-dir ./cex-docs [--limit N]
    python -m tests.eval_answer_pipeline --docs-dir ./cex-docs --json
    python -m tests.eval_answer_pipeline --docs-dir ./cex-docs --compare baseline.json
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


@dataclass
class AnswerEvalResult:
    query: str
    expected_exchange: str | None
    expected_urls: list[str]
    classification: str
    relevance: int  # Graded: 0-3
    status: str
    num_claims: int
    claim_urls: list[str]
    claim_endpoints: list[str]
    has_relevant_claim: bool
    url_hit: bool
    prefix_hit: bool
    domain_hit: bool
    mrr: float
    dcg_at_5: float
    latency_s: float
    is_negative: bool
    expected_status: str | None


@dataclass
class PathMetrics:
    total: int = 0
    ok_rate: float = 0.0
    url_hit_rate: float = 0.0
    prefix_hit_rate: float = 0.0
    mean_mrr: float = 0.0
    mean_ndcg5: float = 0.0


@dataclass
class AnswerEvalSummary:
    total: int
    ok_rate: float
    url_hit_rate: float
    prefix_hit_rate: float
    domain_hit_rate: float
    mean_mrr: float
    mean_ndcg5: float
    mean_claims: float
    mean_latency_s: float
    negative_fp_rate: float
    by_path: dict[str, PathMetrics] = field(default_factory=dict)
    per_query: list[AnswerEvalResult] = field(default_factory=list)


def _norm(url: str) -> str:
    return unquote(url).split("#")[0].rstrip("/").lower()


def _domain(url: str) -> str:
    return urlparse(url).hostname or ""


def _prefix_match(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    return na.startswith(nb) or nb.startswith(na)


def _dcg_at_k(gains: list[float], k: int = 5) -> float:
    """Compute Discounted Cumulative Gain at rank k."""
    dcg = 0.0
    for i, g in enumerate(gains[:k]):
        dcg += g / math.log2(i + 2)  # rank 1-based: log2(1+1), log2(2+1), ...
    return dcg


def _ndcg_at_k(gains: list[float], ideal_gains: list[float], k: int = 5) -> float:
    """Compute nDCG@k."""
    dcg = _dcg_at_k(gains, k)
    ideal_dcg = _dcg_at_k(sorted(ideal_gains, reverse=True), k)
    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg


def evaluate_answer_pipeline(
    docs_dir: str,
    qa_path: str,
    limit: int | None = None,
) -> AnswerEvalSummary:
    from xdocs.answer import answer_question

    qa_file = Path(qa_path)
    pairs = []
    for line in qa_file.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pairs.append(json.loads(line))

    if limit:
        pairs = pairs[:limit]

    results: list[AnswerEvalResult] = []
    total_ok = 0
    total_url_hit = total_prefix_hit = total_domain_hit = 0
    total_mrr = 0.0
    total_ndcg5 = 0.0
    total_claims = 0
    total_latency = 0.0
    negative_count = 0
    negative_fp = 0

    # Per-path accumulators.
    path_counts: dict[str, dict[str, float]] = {}

    for pair in pairs:
        query = pair["query"]
        expected_urls = pair.get("expected_urls", [])
        expected_exchange = pair.get("expected_exchange")
        classification = pair.get("classification", "question")
        relevance = pair.get("relevance", 2)
        expected_status = pair.get("expected_status")
        is_negative = "negative" in pair.get("tags", [])

        t0 = time.time()
        answer = answer_question(docs_dir=docs_dir, question=query)
        latency = time.time() - t0

        status = answer.get("status", "unknown")
        claims = answer.get("claims", [])

        # Extract all URLs from claims.
        claim_urls = []
        claim_endpoints = []
        for c in claims:
            for cit in c.get("citations", []):
                if cit.get("url"):
                    claim_urls.append(cit["url"])
            if c.get("endpoint_id"):
                claim_endpoints.append(c["endpoint_id"])

        # Negative test scoring.
        if is_negative:
            negative_count += 1
            if status == "ok" and len(claims) > 0:
                negative_fp += 1

        # Check hits.
        expected_normed = {_norm(u) for u in expected_urls}
        expected_domains = {_domain(u) for u in expected_urls}

        url_hit = any(_norm(cu) in expected_normed for cu in claim_urls)
        prefix_hit = any(
            _prefix_match(cu, eu) for cu in claim_urls for eu in expected_urls
        )
        domain_hit = any(_domain(cu) in expected_domains for cu in claim_urls)

        # MRR.
        mrr = 0.0
        for i, c in enumerate(claims, 1):
            c_urls = [cit.get("url", "") for cit in c.get("citations", [])]
            if any(_norm(cu) in expected_normed for cu in c_urls):
                mrr = 1.0 / i
                break
            if any(_prefix_match(cu, eu) for cu in c_urls for eu in expected_urls):
                mrr = 1.0 / i
                break

        # Graded nDCG@5.
        gains: list[float] = []
        for c in claims[:5]:
            c_urls = [cit.get("url", "") for cit in c.get("citations", [])]
            if any(_norm(cu) in expected_normed for cu in c_urls):
                gains.append(float(relevance))
            elif any(_prefix_match(cu, eu) for cu in c_urls for eu in expected_urls):
                gains.append(float(max(1, relevance - 1)))
            elif any(_domain(cu) in expected_domains for cu in c_urls):
                gains.append(1.0)
            else:
                gains.append(0.0)
        ideal = [float(relevance)] * min(len(expected_urls), 5) if expected_urls else [0.0]
        ndcg5 = _ndcg_at_k(gains, ideal, k=5)

        is_ok = status == "ok"
        if is_ok:
            total_ok += 1
        if url_hit:
            total_url_hit += 1
        if prefix_hit:
            total_prefix_hit += 1
        if domain_hit:
            total_domain_hit += 1
        total_mrr += mrr
        total_ndcg5 += ndcg5
        total_claims += len(claims)
        total_latency += latency

        # Per-path accumulators.
        if classification not in path_counts:
            path_counts[classification] = {"total": 0, "ok": 0, "url_hit": 0, "prefix_hit": 0, "mrr": 0.0, "ndcg5": 0.0}
        pc = path_counts[classification]
        pc["total"] += 1
        if is_ok:
            pc["ok"] += 1
        if url_hit:
            pc["url_hit"] += 1
        if prefix_hit:
            pc["prefix_hit"] += 1
        pc["mrr"] += mrr
        pc["ndcg5"] += ndcg5

        results.append(AnswerEvalResult(
            query=query,
            expected_exchange=expected_exchange,
            expected_urls=expected_urls,
            classification=classification,
            relevance=relevance,
            status=status,
            num_claims=len(claims),
            claim_urls=claim_urls[:10],
            claim_endpoints=claim_endpoints[:5],
            has_relevant_claim=url_hit or prefix_hit,
            url_hit=url_hit,
            prefix_hit=prefix_hit,
            domain_hit=domain_hit,
            mrr=mrr,
            dcg_at_5=ndcg5,
            latency_s=latency,
            is_negative=is_negative,
            expected_status=expected_status,
        ))

    n = len(results) or 1
    positive_n = max(n - negative_count, 1)

    by_path: dict[str, PathMetrics] = {}
    for path, pc in path_counts.items():
        pt = max(pc["total"], 1)
        by_path[path] = PathMetrics(
            total=int(pc["total"]),
            ok_rate=pc["ok"] / pt,
            url_hit_rate=pc["url_hit"] / pt,
            prefix_hit_rate=pc["prefix_hit"] / pt,
            mean_mrr=pc["mrr"] / pt,
            mean_ndcg5=pc["ndcg5"] / pt,
        )

    # Use positive_n for retrieval quality metrics (MRR, nDCG, Hit rates).
    # Negatives have no expected URLs and always score 0, so dividing by
    # total n artificially depresses these metrics by ~9.4% (17/180 negatives).
    return AnswerEvalSummary(
        total=len(results),
        ok_rate=total_ok / n,
        url_hit_rate=total_url_hit / positive_n,
        prefix_hit_rate=total_prefix_hit / positive_n,
        domain_hit_rate=total_domain_hit / positive_n,
        mean_mrr=total_mrr / positive_n,
        mean_ndcg5=total_ndcg5 / positive_n,
        mean_claims=total_claims / n,
        mean_latency_s=total_latency / n,
        negative_fp_rate=negative_fp / max(negative_count, 1),
        by_path=by_path,
        per_query=results,
    )


def _compare_baselines(current: dict, baseline_path: str) -> list[str]:
    """Compare current metrics against a baseline JSON file.

    Checks both aggregate metrics AND per-classification-path metrics.
    A change that improves overall MRR but regresses a specific type will
    be flagged as a REGRESSION.
    """
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    alerts: list[str] = []

    # --- Aggregate metrics ---
    for key in ("url_hit_rate", "prefix_hit_rate", "mean_mrr", "mean_ndcg5"):
        cur_val = current.get(key, 0.0)
        base_val = baseline.get(key, 0.0)
        if base_val > 0:
            pct_change = (cur_val - base_val) / base_val * 100
            if pct_change < -10:
                alerts.append(f"HARD FAIL: {key} dropped {pct_change:.1f}% ({base_val:.3f} -> {cur_val:.3f})")
            elif pct_change < -5:
                alerts.append(f"WARNING: {key} dropped {pct_change:.1f}% ({base_val:.3f} -> {cur_val:.3f})")
            elif pct_change > 5:
                alerts.append(f"IMPROVED: {key} +{pct_change:.1f}% ({base_val:.3f} -> {cur_val:.3f})")

    # --- Per-classification-path regression detection ---
    cur_by_path = current.get("by_path", {})
    base_by_path = baseline.get("by_path", {})
    for path_name in sorted(set(cur_by_path) | set(base_by_path)):
        cur_pm = cur_by_path.get(path_name, {})
        base_pm = base_by_path.get(path_name, {})
        for metric in ("mean_mrr", "prefix_hit_rate"):
            cur_val = cur_pm.get(metric, 0.0)
            base_val = base_pm.get(metric, 0.0)
            if base_val > 0:
                pct_change = (cur_val - base_val) / base_val * 100
                if pct_change < -10:
                    alerts.append(
                        f"REGRESSION: {path_name}.{metric} dropped {pct_change:.1f}% "
                        f"({base_val:.3f} -> {cur_val:.3f})"
                    )
                elif pct_change < -3:
                    alerts.append(
                        f"REGRESS-WARN: {path_name}.{metric} dropped {pct_change:.1f}% "
                        f"({base_val:.3f} -> {cur_val:.3f})"
                    )
                elif pct_change > 10:
                    alerts.append(
                        f"PATH-IMPROVED: {path_name}.{metric} +{pct_change:.1f}% "
                        f"({base_val:.3f} -> {cur_val:.3f})"
                    )

    return alerts


def main():
    parser = argparse.ArgumentParser(description="Answer pipeline evaluation")
    parser.add_argument("--docs-dir", default="./cex-docs")
    parser.add_argument("--qa-file", default="tests/golden_qa.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--save", type=str, default=None, help="Save metrics to JSON file")
    parser.add_argument("--compare", type=str, default=None, help="Baseline JSON file for comparison")
    args = parser.parse_args()

    summary = evaluate_answer_pipeline(
        docs_dir=args.docs_dir,
        qa_path=args.qa_file,
        limit=args.limit,
    )

    metrics = {
        "total": summary.total,
        "ok_rate": summary.ok_rate,
        "url_hit_rate": summary.url_hit_rate,
        "prefix_hit_rate": summary.prefix_hit_rate,
        "domain_hit_rate": summary.domain_hit_rate,
        "mean_mrr": summary.mean_mrr,
        "mean_ndcg5": summary.mean_ndcg5,
        "mean_claims": summary.mean_claims,
        "mean_latency_s": summary.mean_latency_s,
        "negative_fp_rate": summary.negative_fp_rate,
        "by_path": {
            path: {
                "total": pm.total,
                "ok_rate": pm.ok_rate,
                "url_hit_rate": pm.url_hit_rate,
                "prefix_hit_rate": pm.prefix_hit_rate,
                "mean_mrr": pm.mean_mrr,
                "mean_ndcg5": pm.mean_ndcg5,
            }
            for path, pm in summary.by_path.items()
        },
    }

    if args.json:
        json.dump(metrics, sys.stdout, indent=2)
        print()
    else:
        print(f"=== Answer Pipeline Evaluation (n={summary.total}) ===")
        print(f"OK rate:          {summary.ok_rate:.2%}")
        print(f"URL hit@all:      {summary.url_hit_rate:.2%}")
        print(f"Prefix hit@all:   {summary.prefix_hit_rate:.2%}")
        print(f"Domain hit@all:   {summary.domain_hit_rate:.2%}")
        print(f"Mean MRR:         {summary.mean_mrr:.3f}")
        print(f"Mean nDCG@5:      {summary.mean_ndcg5:.3f}")
        print(f"Mean claims:      {summary.mean_claims:.1f}")
        print(f"Mean latency:     {summary.mean_latency_s:.2f}s")
        print(f"Negative FP rate: {summary.negative_fp_rate:.2%}")
        print()

        print("=== Per-Classification-Path Breakdown ===")
        for path, pm in sorted(summary.by_path.items()):
            print(f"  {path:20s}  n={pm.total:3d}  ok={pm.ok_rate:.0%}  url={pm.url_hit_rate:.0%}  pfx={pm.prefix_hit_rate:.0%}  MRR={pm.mean_mrr:.3f}  nDCG@5={pm.mean_ndcg5:.3f}")
        print()

        misses = [r for r in summary.per_query if not r.prefix_hit and not r.is_negative and r.expected_urls]
        if misses:
            print(f"Prefix misses ({len(misses)}):")
            for r in misses[:20]:
                print(f"  [{r.classification}] Q: {r.query[:80]}")
                print(f"    Status: {r.status}, Claims: {r.num_claims}")
                print(f"    Expected: {r.expected_urls[:2]}")
                print(f"    Got URLs: {r.claim_urls[:3]}")

    if args.save:
        Path(args.save).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"\nMetrics saved to {args.save}")

    if args.compare:
        alerts = _compare_baselines(metrics, args.compare)
        if alerts:
            print("\n=== Comparison vs Baseline ===")
            for a in alerts:
                print(f"  {a}")
            if any("HARD FAIL" in a or "REGRESSION:" in a for a in alerts):
                sys.exit(1)


if __name__ == "__main__":
    main()
