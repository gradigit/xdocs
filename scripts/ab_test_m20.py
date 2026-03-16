"""Post-hoc A/B test for M20 answer pipeline fixes.

Reverts each fix one at a time from the current baseline, runs the
eval pipeline, and measures the isolated impact of each change.

Usage:
    python scripts/ab_test_m20.py --docs-dir ./cex-docs [--limit N]
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ANSWER_PY = Path("src/xdocs/answer.py")
SEMANTIC_PY = Path("src/xdocs/semantic.py")


def _backup(paths: list[Path], tmpdir: Path) -> dict[Path, Path]:
    """Backup files to a temp directory."""
    backups = {}
    for p in paths:
        dst = tmpdir / p.name
        shutil.copy2(p, dst)
        backups[p] = dst
    return backups


def _restore(backups: dict[Path, Path]) -> None:
    """Restore files from backups."""
    for src, bak in backups.items():
        shutil.copy2(bak, src)


def _apply_revert(name: str) -> None:
    """Apply a single revert to the source files."""
    if name == "bug1_augmentation":
        # Revert: url_prefix=_url_prefix -> exchange=exchange.exchange_id
        # Also remove the _url_prefix computation lines
        text = ANSWER_PY.read_text()
        # First occurrence (request_payload augmentation)
        text = text.replace(
            '                    _url_prefix = f"https://{exchange.allowed_domains[0]}" if exchange.allowed_domains else ""\n'
            '                    page_results = _search_pages(\n'
            '                        conn,\n'
            '                        query=trading_terms,\n'
            '                        url_prefix=_url_prefix,\n'
            '                        limit=3,\n'
            '                    )',
            '                    page_results = _search_pages(\n'
            '                        conn,\n'
            '                        query=trading_terms,\n'
            '                        exchange=exchange.exchange_id,\n'
            '                        limit=3,\n'
            '                    )',
            1
        )
        # Second occurrence (code_snippet augmentation)
        text = text.replace(
            '                _url_prefix = f"https://{exchange.allowed_domains[0]}" if exchange.allowed_domains else ""\n'
            '                page_results = _search_pages(\n'
            '                    conn,\n'
            '                    query=search_term,\n'
            '                    url_prefix=_url_prefix,\n'
            '                    limit=5,\n'
            '                )',
            '                page_results = _search_pages(\n'
            '                    conn,\n'
            '                    query=search_term,\n'
            '                    exchange=exchange.exchange_id,\n'
            '                    limit=5,\n'
            '                )',
            1
        )
        ANSWER_PY.write_text(text)

    elif name == "bug2_query_type_hint":
        # Revert: query_type_hint parameter -> hardcoded "question"
        text = ANSWER_PY.read_text()
        # Remove the parameter from _generic_search_answer signature
        text = text.replace(
            '    detected_section_override: str | None = None,\n'
            '    query_type_hint: str | None = None,\n'
            ') -> dict[str, Any]:',
            '    detected_section_override: str | None = None,\n'
            ') -> dict[str, Any]:'
        )
        # Revert query_type_hint usage in section search
        text = text.replace(
            'query_type_hint=query_type_hint)',
            'query_type_hint="question")'
        )
        # Revert the caller
        text = text.replace(
            'result = _generic_search_answer(conn, exchange=exchange, question=question, norm=norm, docs_dir=docs_dir, query_type_hint=classification.input_type)',
            'result = _generic_search_answer(conn, exchange=exchange, question=question, norm=norm, docs_dir=docs_dir)'
        )
        ANSWER_PY.write_text(text)

    elif name == "bug3_bm25_shortcut":
        # Revert: add "question" back to BM25 shortcut set
        text = ANSWER_PY.read_text()
        text = text.replace(
            'if query_type_hint in ("code_snippet", "error_message") and should_skip_vector_search(fts_results):',
            'if query_type_hint in ("question", "code_snippet", "error_message") and should_skip_vector_search(fts_results):'
        )
        ANSWER_PY.write_text(text)

    elif name == "bug4_blend_key":
        # Revert: remove retrieval_score_key="score" from position_aware_blend
        text = SEMANTIC_PY.read_text()
        text = text.replace(
            'raw_results = position_aware_blend(raw_results, retrieval_score_key="score")',
            'raw_results = position_aware_blend(raw_results)'
        )
        SEMANTIC_PY.write_text(text)

    elif name == "weight_request_payload":
        # Revert: request_payload weights [1.3, 0.7] -> [1.0, 1.0]
        text = ANSWER_PY.read_text()
        text = text.replace(
            '"request_payload": [1.3, 0.7],   # keyword-favoring',
            '"request_payload": [1.0, 1.0],   # balanced'
        )
        ANSWER_PY.write_text(text)

    else:
        raise ValueError(f"Unknown revert: {name}")


def _run_eval(docs_dir: str, limit: int | None = None) -> dict:
    """Run eval_answer_pipeline and return JSON metrics."""
    cmd = [
        sys.executable, "-m", "tests.eval_answer_pipeline",
        "--docs-dir", docs_dir,
        "--json",
    ]
    if limit:
        cmd.extend(["--limit", str(limit)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        print(f"  EVAL FAILED: {result.stderr[:500]}", file=sys.stderr)
        return {}
    return json.loads(result.stdout)


REVERTS = [
    ("bug1_augmentation", "Bug 1: augmentation exchange= fix (url_prefix)"),
    ("bug2_query_type_hint", "Bug 2: query_type_hint threading (was always 'question')"),
    ("bug3_bm25_shortcut", "Bug 3: BM25 shortcut excluded 'question'"),
    ("bug4_blend_key", "Bug 4: position_aware_blend key fix"),
    ("weight_request_payload", "Weight: request_payload [1.3,0.7] vs [1.0,1.0]"),
]


def main():
    parser = argparse.ArgumentParser(description="A/B test M20 fixes")
    parser.add_argument("--docs-dir", default="./cex-docs")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        backups = _backup([ANSWER_PY, SEMANTIC_PY], tmpdir)

        # Run baseline (all fixes applied)
        print("=" * 70)
        print("BASELINE (all M20 fixes applied)")
        print("=" * 70)
        baseline = _run_eval(args.docs_dir, args.limit)
        if not baseline:
            print("Baseline eval failed!", file=sys.stderr)
            return 1
        print(f"  MRR={baseline['mean_mrr']:.4f}  nDCG@5={baseline['mean_ndcg5']:.4f}  "
              f"URL={baseline['url_hit_rate']:.2%}  PFX={baseline['prefix_hit_rate']:.2%}")

        results = {"baseline": baseline}

        # Run each revert
        for revert_name, description in REVERTS:
            print()
            print("=" * 70)
            print(f"REVERT: {description}")
            print("=" * 70)

            _apply_revert(revert_name)
            metrics = _run_eval(args.docs_dir, args.limit)
            _restore(backups)  # Always restore immediately

            if not metrics:
                print(f"  EVAL FAILED for {revert_name}")
                results[revert_name] = {"error": "eval failed"}
                continue

            results[revert_name] = metrics
            mrr_delta = baseline["mean_mrr"] - metrics["mean_mrr"]
            ndcg_delta = baseline["mean_ndcg5"] - metrics["mean_ndcg5"]
            print(f"  MRR={metrics['mean_mrr']:.4f} (fix contribution: {mrr_delta:+.4f})")
            print(f"  nDCG@5={metrics['mean_ndcg5']:.4f} (fix contribution: {ndcg_delta:+.4f})")
            print(f"  URL={metrics['url_hit_rate']:.2%}  PFX={metrics['prefix_hit_rate']:.2%}")

            # Per-path breakdown
            for path, pm in sorted(metrics.get("by_path", {}).items()):
                base_pm = baseline.get("by_path", {}).get(path, {})
                pm_mrr = pm.get("mean_mrr", 0)
                base_mrr = base_pm.get("mean_mrr", 0)
                delta = base_mrr - pm_mrr
                if abs(delta) > 0.001:
                    print(f"    {path:20s} MRR={pm_mrr:.3f} (fix: {delta:+.3f})")

    # Summary table
    print()
    print("=" * 70)
    print("SUMMARY: Individual fix contributions (baseline - reverted)")
    print("=" * 70)
    print(f"{'Fix':<50s} {'MRR Δ':>8s} {'nDCG Δ':>8s} {'URL Δ':>8s} {'PFX Δ':>8s}")
    print("-" * 82)

    for revert_name, description in REVERTS:
        m = results.get(revert_name, {})
        if "error" in m:
            print(f"{description:<50s} {'ERROR':>8s}")
            continue
        mrr_d = baseline["mean_mrr"] - m["mean_mrr"]
        ndcg_d = baseline["mean_ndcg5"] - m["mean_ndcg5"]
        url_d = baseline["url_hit_rate"] - m["url_hit_rate"]
        pfx_d = baseline["prefix_hit_rate"] - m["prefix_hit_rate"]
        print(f"{description:<50s} {mrr_d:+.4f} {ndcg_d:+.4f} {url_d:+.2%} {pfx_d:+.2%}")

    # Save full results
    out_path = Path("reports/m20-ab-test.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nFull results saved to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
