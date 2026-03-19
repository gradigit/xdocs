#!/usr/bin/env python3
"""Sweep CC fusion alpha values per query type on golden QA.

Usage:
    source .venv/bin/activate
    python3 scripts/sweep_cc_alpha.py --qa-file tests/golden_qa.jsonl

Outputs per-alpha metrics to stdout for analysis.
"""
import argparse
import json
import os
import subprocess
import sys


def run_eval(qa_file: str, alpha_override: float | None = None) -> dict:
    """Run eval with CEX_FUSION_MODE=cc and optional alpha override."""
    env = os.environ.copy()
    env["CEX_FUSION_MODE"] = "cc"
    if alpha_override is not None:
        env["CEX_CC_ALPHA_OVERRIDE"] = str(alpha_override)

    result = subprocess.run(
        [sys.executable, "tests/eval_answer_pipeline.py", "--qa-file", qa_file],
        capture_output=True, text=True, env=env, timeout=900,
    )
    # Parse the JSON output from the last line or from --save
    # The eval script prints metrics to stderr, saves JSON to file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = f.name

    result2 = subprocess.run(
        [sys.executable, "tests/eval_answer_pipeline.py", "--qa-file", qa_file, "--save", tmp],
        capture_output=True, text=True, env=env, timeout=900,
    )
    with open(tmp) as f:
        metrics = json.load(f)
    os.unlink(tmp)
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-file", required=True)
    args = parser.parse_args()

    alphas = [0.2, 0.3, 0.35, 0.4, 0.5, 0.6, 0.65, 0.7, 0.8]

    print(f"{'alpha':>6} | {'MRR':>6} | {'PFX':>6} | {'nDCG@5':>7} | {'q_MRR':>6} | {'ep_MRR':>6} | {'err_MRR':>7} | {'code_MRR':>8} | {'pay_MRR':>7}")
    print("-" * 85)

    for alpha in alphas:
        try:
            m = run_eval(args.qa_file, alpha_override=alpha)
            bp = m.get("by_path", {})
            print(f"{alpha:>6.2f} | {m['mean_mrr']:>6.3f} | {m['prefix_hit_rate']:>6.3f} | {m['mean_ndcg5']:>7.3f} | "
                  f"{bp.get('question', {}).get('mean_mrr', 0):>6.3f} | "
                  f"{bp.get('endpoint_path', {}).get('mean_mrr', 0):>6.3f} | "
                  f"{bp.get('error_message', {}).get('mean_mrr', 0):>7.3f} | "
                  f"{bp.get('code_snippet', {}).get('mean_mrr', 0):>8.3f} | "
                  f"{bp.get('request_payload', {}).get('mean_mrr', 0):>7.3f}")
        except Exception as e:
            print(f"{alpha:>6.2f} | ERROR: {e}")


if __name__ == "__main__":
    main()
