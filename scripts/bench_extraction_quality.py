#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _sample_rows(conn: sqlite3.Connection, sample_size: int) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
SELECT canonical_url, domain, markdown_path, word_count
FROM pages
WHERE markdown_path IS NOT NULL
ORDER BY canonical_url ASC;
"""
    ).fetchall()
    if len(rows) <= sample_size:
        return rows
    rng = random.Random(42)
    idx = sorted(rng.sample(range(len(rows)), sample_size))
    return [rows[i] for i in idx]


def _line_count_with_prefix(text: str, prefix: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.lstrip().startswith(prefix))


def _evaluate_markdown_sample(rows: list[sqlite3.Row]) -> dict[str, Any]:
    domains: Counter[str] = Counter()
    pages = 0
    words = 0
    code_tag_pages = 0
    fenced_code_pages = 0
    table_like_pages = 0
    html_table_pages = 0
    link_pages = 0
    heading_pages = 0
    metric_sums: Counter[str] = Counter()

    for r in rows:
        pages += 1
        domains[str(r["domain"] or "")] += 1
        words += int(r["word_count"] or 0)

        md_path = Path(str(r["markdown_path"]))
        md = _read_text(md_path)
        if not md:
            continue

        code_tag_n = md.count("[code]")
        fence_n = md.count("```")
        table_pipe_n = sum(1 for ln in md.splitlines() if "|" in ln and len(ln.strip()) > 2)
        html_table_n = len(re.findall(r"<table\b", md, flags=re.IGNORECASE))
        link_n = len(re.findall(r"\[[^\]]+\]\([^)]+\)", md))
        heading_n = _line_count_with_prefix(md, "#")

        metric_sums["code_tag_occurrences"] += code_tag_n
        metric_sums["fence_occurrences"] += fence_n
        metric_sums["table_like_line_occurrences"] += table_pipe_n
        metric_sums["html_table_occurrences"] += html_table_n
        metric_sums["link_occurrences"] += link_n
        metric_sums["heading_line_occurrences"] += heading_n

        if code_tag_n > 0:
            code_tag_pages += 1
        if fence_n > 0:
            fenced_code_pages += 1
        if table_pipe_n > 0:
            table_like_pages += 1
        if html_table_n > 0:
            html_table_pages += 1
        if link_n > 0:
            link_pages += 1
        if heading_n > 0:
            heading_pages += 1

    avg_word_count = (words / pages) if pages else 0.0
    return {
        "sample_pages": pages,
        "avg_word_count": avg_word_count,
        "domain_distribution_top20": dict(domains.most_common(20)),
        "pages_with_code_tags": code_tag_pages,
        "pages_with_fenced_code": fenced_code_pages,
        "pages_with_table_like_lines": table_like_pages,
        "pages_with_html_table_markup": html_table_pages,
        "pages_with_links": link_pages,
        "pages_with_headings": heading_pages,
        **{k: int(v) for k, v in metric_sums.items()},
    }


def _quality_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT word_count FROM pages;").fetchall()
    total = len(rows)
    empty = 0
    thin = 0
    for r in rows:
        wc = int(r["word_count"] or 0)
        if wc == 0:
            empty += 1
        elif wc < 50:
            thin += 1
    return {
        "total": total,
        "empty": empty,
        "thin_lt_50": thin,
        "ok_ge_50": max(0, total - empty - thin),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark extraction quality signals from stored markdown."
    )
    parser.add_argument(
        "--docs-dir",
        default="./cex-docs",
        help="Store root (default: ./cex-docs)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=500,
        help="Max number of markdown pages sampled for detailed metrics (default: 500)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: reports/<timestamp>-extraction-quality-benchmark.json)",
    )
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    db_path = docs_dir / "db" / "docs.db"
    if not db_path.exists():
        raise SystemExit(f"Missing DB: {db_path}")

    out = (
        Path(args.output).resolve()
        if args.output
        else (Path.cwd() / "reports" / f"{_iso_now().replace(':', '')}-extraction-quality-benchmark.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sampled = _sample_rows(conn, max(1, int(args.sample_size)))
        quality = _quality_counts(conn)
        details = _evaluate_markdown_sample(sampled)
        total_pages = int(
            conn.execute("SELECT COUNT(*) AS n FROM pages;").fetchone()["n"]  # type: ignore[index]
        )
        total_words = int(
            conn.execute("SELECT COALESCE(SUM(word_count), 0) AS n FROM pages;").fetchone()["n"]  # type: ignore[index]
        )
    finally:
        conn.close()

    payload = {
        "cmd": "bench-extraction-quality",
        "generated_at": _iso_now(),
        "docs_dir": str(docs_dir),
        "sample_size_requested": int(args.sample_size),
        "store_totals": {
            "pages": total_pages,
            "words": total_words,
        },
        "quality_counts": quality,
        "sample_metrics": details,
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
