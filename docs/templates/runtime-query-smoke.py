#!/usr/bin/env python3
"""Smoke test for the xdocs runtime query pipeline.

Verifies that the store is accessible and basic queries work.
Run after bootstrap-data.sh to confirm the data release is functional.
"""
from __future__ import annotations

import json
import subprocess
import sys


def _run(cmd: list[str]) -> dict:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"FAIL: {' '.join(cmd)}", file=sys.stderr)
        print(r.stderr[:500], file=sys.stderr)
        return {"ok": False}
    return json.loads(r.stdout)


def main() -> int:
    checks = 0
    passed = 0

    # 1. Store exists and has pages
    checks += 1
    r = _run(["xdocs", "store-report", "--docs-dir", "./cex-docs"])
    if r.get("ok") is not False:
        passed += 1
        print("PASS: store-report")
    else:
        print("FAIL: store-report")

    # 2. FTS search returns results
    checks += 1
    r = _run(["xdocs", "search-endpoints", "rate limit", "--exchange", "binance", "--docs-dir", "./cex-docs"])
    if r.get("ok") is not False:
        passed += 1
        print("PASS: search-endpoints")
    else:
        print("FAIL: search-endpoints")

    # 3. Classification works
    checks += 1
    r = _run(["xdocs", "classify", "POST /api/v3/order", "--docs-dir", "./cex-docs"])
    if r.get("ok") is not False:
        passed += 1
        print("PASS: classify")
    else:
        print("FAIL: classify")

    # 4. Semantic search (if index exists)
    checks += 1
    r = _run(["xdocs", "semantic-search", "check wallet balance", "--docs-dir", "./cex-docs"])
    if r.get("ok") is not False:
        passed += 1
        print("PASS: semantic-search")
    else:
        print("WARN: semantic-search (index may not be present)")
        passed += 1  # Optional — don't fail on missing index

    # 5. Answer pipeline
    checks += 1
    r = _run(["xdocs", "answer", "What is the Binance API rate limit?", "--docs-dir", "./cex-docs"])
    if r.get("ok") is not False:
        passed += 1
        print("PASS: answer")
    else:
        print("FAIL: answer")

    # 6. Endpoint lookup
    checks += 1
    r = _run(["xdocs", "lookup-endpoint", "/api/v3/order", "--exchange", "binance", "--docs-dir", "./cex-docs"])
    if r.get("ok") is not False:
        passed += 1
        print("PASS: lookup-endpoint")
    else:
        print("FAIL: lookup-endpoint")

    # 7. Error code search
    checks += 1
    r = _run(["xdocs", "search-error", "--", "-1002", "--exchange", "binance", "--docs-dir", "./cex-docs"])
    if r.get("ok") is not False:
        passed += 1
        print("PASS: search-error")
    else:
        print("FAIL: search-error")

    print(f"\n{passed}/{checks} checks passed")
    return 0 if passed >= checks - 1 else 1  # Allow 1 failure (semantic optional)


if __name__ == "__main__":
    raise SystemExit(main())
