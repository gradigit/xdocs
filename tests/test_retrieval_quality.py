"""Retrieval quality gate using golden QA test set.

Wraps ``scripts/bench_retrieval_quality.py`` logic into a pytest test.
Requires the ``[semantic]`` extras and a built LanceDB index at ``cex-docs/``.
Skipped automatically if either dependency is missing.

Mark: ``@pytest.mark.slow`` — excluded from default runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_DIR / "cex-docs"
GOLDEN_QA = PROJECT_DIR / "tests" / "golden_qa.jsonl"
LANCE_INDEX = DOCS_DIR / "lancedb-index"

# Skip conditions
_skip_no_index = pytest.mark.skipif(
    not LANCE_INDEX.exists(),
    reason="LanceDB index not built (run: xdocs build-index --docs-dir ./cex-docs)",
)
_skip_no_semantic = pytest.importorskip  # used inline below


def _load_golden_qa() -> list[dict]:
    cases = []
    with open(GOLDEN_QA) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def _url_matches(result_url: str, expected_urls: list[str]) -> bool:
    for exp in expected_urls:
        if result_url == exp or result_url.startswith(exp) or exp.startswith(result_url):
            return True
    return False


def _find_rank(results: list[dict], expected_urls: list[str]) -> int | None:
    for i, r in enumerate(results):
        if _url_matches(r.get("url", ""), expected_urls):
            return i + 1
    return None


def _compute_recall(ranks: list[int | None], k: int) -> float:
    hits = sum(1 for r in ranks if r is not None and r <= k)
    return hits / len(ranks) if ranks else 0.0


@pytest.mark.slow
@_skip_no_index
def test_retrieval_recall_at_10():
    """Assert Recall@10 >= 0.70 on the golden QA set (filtered, hybrid mode)."""
    _skip_no_semantic("lancedb", reason="lancedb not installed (pip install -e '.[semantic]')")

    from xdocs.semantic import semantic_search

    cases = _load_golden_qa()
    assert len(cases) >= 20, f"Expected >= 20 golden QA cases, got {len(cases)}"

    ranks: list[int | None] = []
    failures: list[str] = []

    for case in cases:
        query = case["query"]
        expected_urls = case["expected_urls"]
        exchange = case.get("expected_exchange")

        try:
            results = semantic_search(
                docs_dir=str(DOCS_DIR),
                query=query,
                exchange=exchange,
                limit=10,
                query_type="hybrid",
                rerank="auto",
                include_meta=False,
            )
        except Exception as e:
            results = []
            failures.append(f"{query}: ERROR - {e}")

        rank = _find_rank(results, expected_urls)
        ranks.append(rank)
        if rank is None:
            top = results[0]["url"] if results else "(no results)"
            failures.append(f"{query}: MISS (top: {top})")

    recall_at_10 = _compute_recall(ranks, 10)
    recall_at_1 = _compute_recall(ranks, 1)

    # Print diagnostic info regardless of pass/fail
    print(f"\nRecall@1:  {recall_at_1:.1%}")
    print(f"Recall@10: {recall_at_10:.1%}")
    print(f"Hits: {sum(1 for r in ranks if r is not None)}/{len(ranks)}")
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for f in failures:
            print(f"  {f}")

    assert recall_at_10 >= 0.70, (
        f"Recall@10 = {recall_at_10:.1%} (target >= 70%). "
        f"{len(failures)} queries missed. See output above for details."
    )
