"""Answer pipeline evaluation — tests the full answer_question flow.

Checks that answer claims contain expected URLs or endpoint paths, and
measures relevance@k, MRR, and citation accuracy across the golden QA set.

Usage:
    python -m tests.eval_answer_pipeline --docs-dir ./cex-docs [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class AnswerEvalResult:
    query: str
    expected_exchange: str | None
    expected_urls: list[str]
    status: str
    num_claims: int
    claim_urls: list[str]
    claim_endpoints: list[str]
    has_relevant_claim: bool
    url_hit: bool  # At least one expected URL found in claims
    prefix_hit: bool
    domain_hit: bool
    mrr: float  # Reciprocal rank of first relevant claim
    latency_s: float


@dataclass
class AnswerEvalSummary:
    total: int
    ok_rate: float
    url_hit_rate: float
    prefix_hit_rate: float
    domain_hit_rate: float
    mean_mrr: float
    mean_claims: float
    mean_latency_s: float
    per_query: list[AnswerEvalResult] = field(default_factory=list)


def _norm(url: str) -> str:
    return url.split("#")[0].rstrip("/").lower()


def _domain(url: str) -> str:
    return urlparse(url).hostname or ""


def _prefix_match(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    return na.startswith(nb) or nb.startswith(na)


def evaluate_answer_pipeline(
    docs_dir: str,
    qa_path: str,
    limit: int | None = None,
) -> AnswerEvalSummary:
    from cex_api_docs.answer import answer_question

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
    total_claims = 0
    total_latency = 0.0

    for pair in pairs:
        query = pair["query"]
        expected_urls = pair.get("expected_urls", [])
        expected_exchange = pair.get("expected_exchange")

        t0 = time.time()
        answer = answer_question(docs_dir=docs_dir, question=query)
        latency = time.time() - t0

        status = answer.get("status", "unknown")
        claims = answer.get("claims", [])

        # Extract all URLs from claims
        claim_urls = []
        claim_endpoints = []
        for c in claims:
            for cit in c.get("citations", []):
                if cit.get("url"):
                    claim_urls.append(cit["url"])
            if c.get("endpoint_id"):
                claim_endpoints.append(c["endpoint_id"])

        # Check hits
        expected_normed = {_norm(u) for u in expected_urls}
        expected_domains = {_domain(u) for u in expected_urls}

        url_hit = any(_norm(cu) in expected_normed for cu in claim_urls)
        prefix_hit = any(
            _prefix_match(cu, eu)
            for cu in claim_urls
            for eu in expected_urls
        )
        domain_hit = any(_domain(cu) in expected_domains for cu in claim_urls)

        # MRR: find reciprocal rank of first relevant claim
        mrr = 0.0
        for i, c in enumerate(claims, 1):
            c_urls = [cit.get("url", "") for cit in c.get("citations", [])]
            if any(_norm(cu) in expected_normed for cu in c_urls):
                mrr = 1.0 / i
                break
            if any(
                _prefix_match(cu, eu) for cu in c_urls for eu in expected_urls
            ):
                mrr = 1.0 / i
                break

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
        total_claims += len(claims)
        total_latency += latency

        results.append(AnswerEvalResult(
            query=query,
            expected_exchange=expected_exchange,
            expected_urls=expected_urls,
            status=status,
            num_claims=len(claims),
            claim_urls=claim_urls[:10],
            claim_endpoints=claim_endpoints[:5],
            has_relevant_claim=url_hit or prefix_hit,
            url_hit=url_hit,
            prefix_hit=prefix_hit,
            domain_hit=domain_hit,
            mrr=mrr,
            latency_s=latency,
        ))

    n = len(results) or 1
    return AnswerEvalSummary(
        total=len(results),
        ok_rate=total_ok / n,
        url_hit_rate=total_url_hit / n,
        prefix_hit_rate=total_prefix_hit / n,
        domain_hit_rate=total_domain_hit / n,
        mean_mrr=total_mrr / n,
        mean_claims=total_claims / n,
        mean_latency_s=total_latency / n,
        per_query=results,
    )


def main():
    parser = argparse.ArgumentParser(description="Answer pipeline evaluation")
    parser.add_argument("--docs-dir", default="./cex-docs")
    parser.add_argument("--qa-file", default="tests/golden_qa.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    summary = evaluate_answer_pipeline(
        docs_dir=args.docs_dir,
        qa_path=args.qa_file,
        limit=args.limit,
    )

    if args.json:
        out = {
            "total": summary.total,
            "ok_rate": summary.ok_rate,
            "url_hit_rate": summary.url_hit_rate,
            "prefix_hit_rate": summary.prefix_hit_rate,
            "domain_hit_rate": summary.domain_hit_rate,
            "mean_mrr": summary.mean_mrr,
            "mean_claims": summary.mean_claims,
            "mean_latency_s": summary.mean_latency_s,
        }
        json.dump(out, sys.stdout, indent=2)
        print()
    else:
        print(f"=== Answer Pipeline Evaluation (n={summary.total}) ===")
        print(f"OK rate:          {summary.ok_rate:.2%}")
        print(f"URL hit@all:      {summary.url_hit_rate:.2%}")
        print(f"Prefix hit@all:   {summary.prefix_hit_rate:.2%}")
        print(f"Domain hit@all:   {summary.domain_hit_rate:.2%}")
        print(f"Mean MRR:         {summary.mean_mrr:.3f}")
        print(f"Mean claims:      {summary.mean_claims:.1f}")
        print(f"Mean latency:     {summary.mean_latency_s:.2f}s")
        print()

        misses = [r for r in summary.per_query if not r.prefix_hit]
        if misses:
            print(f"Prefix misses ({len(misses)}):")
            for r in misses:
                print(f"  Q: {r.query}")
                print(f"    Status: {r.status}, Claims: {r.num_claims}")
                print(f"    Expected: {r.expected_urls[:2]}")
                print(f"    Got URLs: {r.claim_urls[:3]}")


if __name__ == "__main__":
    main()
