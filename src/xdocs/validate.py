"""Golden QA validation for semantic search retrieval quality.

Loads a JSONL file of (query, expected_urls) pairs, runs each query through
semantic search, and computes Hit Rate@K and Recall@K metrics at three
match levels: exact, prefix, and domain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


def _norm(url: str) -> str:
    """Strip trailing slash, fragment, and decode percent-encoding."""
    return unquote(url.split("#")[0].rstrip("/"))


def _prefix_match(expected: str, retrieved: str) -> bool:
    """True if either URL is a prefix of the other (after normalisation)."""
    a, b = _norm(expected), _norm(retrieved)
    return a.startswith(b) or b.startswith(a)


def _domain(url: str) -> str:
    """Extract hostname from URL."""
    return urlparse(url).hostname or ""


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Result for a single validation query."""

    query: str
    expected_urls: list[str]
    retrieved_urls: list[str]
    hit: bool  # Exact: at least one expected URL in top-K
    recall: float  # Exact: fraction of expected URLs found
    prefix_hit: bool  # At least one prefix match
    prefix_recall: float  # Fraction with prefix match
    domain_hit: bool  # At least one same-domain match
    domain_recall: float  # Fraction with domain match


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Aggregate validation metrics."""

    total_queries: int
    hit_rate: float
    mean_recall: float
    prefix_hit_rate: float
    prefix_mean_recall: float
    domain_hit_rate: float
    domain_mean_recall: float
    per_query: list[QueryResult]
    k: int


def _match_counts(
    expected_urls: list[str], retrieved_urls: list[str]
) -> tuple[int, int, int]:
    """Return (exact, prefix, domain) match counts for expected URLs."""
    exact = 0
    prefix = 0
    domain = 0
    retrieved_normed = [_norm(u) for u in retrieved_urls]
    retrieved_normed_set = set(retrieved_normed)
    retrieved_domains = {_domain(u) for u in retrieved_urls}

    for exp in expected_urls:
        exp_n = _norm(exp)
        if exp_n in retrieved_normed_set:
            exact += 1
        if any(
            exp_n.startswith(rn) or rn.startswith(exp_n)
            for rn in retrieved_normed
        ):
            prefix += 1
        if _domain(exp) in retrieved_domains:
            domain += 1

    return exact, prefix, domain


def validate_retrieval(
    *,
    docs_dir: str,
    qa_path: str,
    limit: int = 5,
    rerank: bool = True,
) -> ValidationResult:
    """Run golden QA validation against the semantic search index.

    Args:
        docs_dir: Path to the cex-docs store directory.
        qa_path: Path to JSONL file with golden QA pairs.
            Each line: ``{"query": "...", "expected_urls": ["..."], ...}``
        limit: Top-K results to check (default: 5).
        rerank: Enable cross-encoder reranking during semantic retrieval.

    Returns:
        ValidationResult with hit rate, mean recall, and per-query details
        at exact, prefix, and domain match levels.
    """
    from .semantic import semantic_search

    qa_file = Path(qa_path)
    if not qa_file.exists():
        raise FileNotFoundError(f"Golden QA file not found: {qa_path}")

    pairs: list[dict[str, Any]] = []
    for line in qa_file.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pairs.append(json.loads(line))

    if not pairs:
        return ValidationResult(
            total_queries=0,
            hit_rate=0.0,
            mean_recall=0.0,
            prefix_hit_rate=0.0,
            prefix_mean_recall=0.0,
            domain_hit_rate=0.0,
            domain_mean_recall=0.0,
            per_query=[],
            k=limit,
        )

    per_query: list[QueryResult] = []
    hits = prefix_hits = domain_hits = 0
    total_recall = total_prefix_recall = total_domain_recall = 0.0

    for pair in pairs:
        query = pair["query"]
        expected_urls = pair["expected_urls"]
        exchange = pair.get("expected_exchange")

        try:
            results = semantic_search(
                docs_dir=docs_dir,
                query=query,
                exchange=exchange,
                limit=limit,
                query_type="hybrid",
                rerank=rerank,
            )
            retrieved_urls = [r["url"] for r in results]
        except Exception as e:
            logger.warning("Search failed for query %r: %s", query, e)
            retrieved_urls = []

        n_exp = len(expected_urls) or 1
        exact, prefix, domain = _match_counts(expected_urls, retrieved_urls)

        exact_hit = exact > 0
        prefix_hit = prefix > 0
        domain_hit = domain > 0

        if exact_hit:
            hits += 1
        if prefix_hit:
            prefix_hits += 1
        if domain_hit:
            domain_hits += 1

        exact_recall = exact / n_exp
        prefix_recall = prefix / n_exp
        domain_recall = domain / n_exp

        total_recall += exact_recall
        total_prefix_recall += prefix_recall
        total_domain_recall += domain_recall

        per_query.append(QueryResult(
            query=query,
            expected_urls=expected_urls,
            retrieved_urls=retrieved_urls,
            hit=exact_hit,
            recall=exact_recall,
            prefix_hit=prefix_hit,
            prefix_recall=prefix_recall,
            domain_hit=domain_hit,
            domain_recall=domain_recall,
        ))

    n = len(pairs)
    return ValidationResult(
        total_queries=n,
        hit_rate=hits / n,
        mean_recall=total_recall / n,
        prefix_hit_rate=prefix_hits / n,
        prefix_mean_recall=total_prefix_recall / n,
        domain_hit_rate=domain_hits / n,
        domain_mean_recall=total_domain_recall / n,
        per_query=per_query,
        k=limit,
    )
