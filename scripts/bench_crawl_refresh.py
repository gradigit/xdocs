#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime:
    # Handles offsets like +00:00 and zulu-ish strings.
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.fromisoformat(value)


def _run_sync(
    *,
    cli: Path,
    docs_dir: Path,
    render: str,
    concurrency: int,
    delay_s: float,
    retries: int,
    timeout_s: float,
    mode: str,
    exchange: str | None,
    section: str | None,
    module: str | None,
) -> dict[str, Any]:
    if module:
        cmd = [
            sys.executable,
            "-m",
            module,
            "sync",
            "--docs-dir",
            str(docs_dir),
            "--render",
            render,
            "--concurrency",
            str(concurrency),
            "--delay-s",
            str(delay_s),
            "--retries",
            str(retries),
            "--timeout-s",
            str(timeout_s),
        ]
    else:
        cmd = [
            str(cli),
            "sync",
            "--docs-dir",
            str(docs_dir),
            "--render",
            render,
            "--concurrency",
            str(concurrency),
            "--delay-s",
            str(delay_s),
            "--retries",
            str(retries),
            "--timeout-s",
            str(timeout_s),
        ]
    if exchange:
        cmd += ["--exchange", exchange]
    if section:
        cmd += ["--section", section]
    if mode == "resume":
        cmd.append("--resume")
    elif mode == "force-refetch":
        cmd.append("--force-refetch")
    elif mode != "full":
        raise ValueError(f"Unsupported mode: {mode}")

    env = dict(os.environ)
    if module:
        repo_root = Path(__file__).resolve().parents[1]
        src_dir = str(repo_root / "src")
        env["PYTHONPATH"] = src_dir + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    p = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if p.returncode != 0:
        raise RuntimeError(
            f"sync failed (mode={mode}, rc={p.returncode}):\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    try:
        payload = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Unable to parse sync JSON output for mode={mode}: {e}") from e
    if not bool(payload.get("ok")):
        raise RuntimeError(f"sync returned ok=false for mode={mode}: {payload}")
    return payload["result"]


def _collect_run_metrics(db_path: Path, crawl_run_ids: list[int]) -> dict[str, Any]:
    if not crawl_run_ids:
        return {
            "raw_bytes_sum": 0,
            "http_status_counts": {},
            "status_429_count": 0,
            "domains_with_429": {},
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ", ".join("?" for _ in crawl_run_ids)
        rows = conn.execute(
            f"""
SELECT pv.http_status, p.domain, pv.raw_path
FROM page_versions pv
JOIN pages p ON p.id = pv.page_id
WHERE pv.crawl_run_id IN ({placeholders});
""",
            tuple(crawl_run_ids),
        ).fetchall()
    finally:
        conn.close()

    raw_bytes_sum = 0
    status_counts: Counter[int] = Counter()
    domain_429: Counter[str] = Counter()
    for r in rows:
        status = int(r["http_status"] or 0)
        status_counts[status] += 1
        if status == 429:
            domain_429[str(r["domain"] or "")] += 1
        raw_path = str(r["raw_path"] or "")
        if raw_path:
            p = Path(raw_path)
            try:
                raw_bytes_sum += int(p.stat().st_size)
            except OSError:
                pass

    return {
        "raw_bytes_sum": raw_bytes_sum,
        "http_status_counts": {str(k): v for k, v in sorted(status_counts.items())},
        "status_429_count": int(status_counts.get(429, 0)),
        "domains_with_429": dict(domain_429),
    }


def _collect_fetch_error_domains(sync_result: dict[str, Any]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for sec in sync_result.get("sections", []):
        fetch = sec.get("fetch") or {}
        for item in fetch.get("errors", []) or []:
            url = str(item.get("url") or "")
            host = urlsplit(url).netloc or "(unknown)"
            c[host] += 1
    return dict(c)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark sync refresh modes and persist JSON metrics."
    )
    parser.add_argument(
        "--docs-dir",
        default="./cex-docs",
        help="Store root (default: ./cex-docs)",
    )
    parser.add_argument(
        "--cli-path",
        default="./.venv/bin/cex-api-docs",
        help="Path to cex-api-docs executable (default: ./.venv/bin/cex-api-docs)",
    )
    parser.add_argument(
        "--module",
        default=None,
        help="Run via `python -m <module>` (recommended for local dev, e.g. cex_api_docs.cli).",
    )
    parser.add_argument(
        "--modes",
        default="resume",
        help="Comma-separated modes: full,resume,force-refetch (default: resume)",
    )
    parser.add_argument("--render", default="auto", choices=["http", "playwright", "auto"])
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--delay-s", type=float, default=0.25)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout-s", type=float, default=20.0)
    parser.add_argument("--exchange", default=None)
    parser.add_argument("--section", default=None)
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: reports/<timestamp>-crawl-refresh-benchmark.json)",
    )

    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    cli = Path(args.cli_path).resolve()
    if args.module is None and not cli.exists():
        raise SystemExit(f"Missing CLI executable: {cli}")

    modes = [m.strip() for m in str(args.modes).split(",") if m.strip()]
    if not modes:
        raise SystemExit("No benchmark modes requested.")

    out = (
        Path(args.output).resolve()
        if args.output
        else (Path.cwd() / "reports" / f"{_iso_now().replace(':', '')}-crawl-refresh-benchmark.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    run_results: list[dict[str, Any]] = []
    for mode in modes:
        started = _iso_now()
        result = _run_sync(
            cli=cli,
            docs_dir=docs_dir,
            render=args.render,
            concurrency=int(args.concurrency),
            delay_s=float(args.delay_s),
            retries=int(args.retries),
            timeout_s=float(args.timeout_s),
            mode=mode,
            exchange=args.exchange,
            section=args.section,
            module=args.module,
        )
        ended = _iso_now()
        start_dt = _parse_iso(result["started_at"])
        end_dt = _parse_iso(result["ended_at"])
        duration_s = (end_dt - start_dt).total_seconds()

        crawl_run_ids = []
        for sec in result.get("sections", []):
            fetch = sec.get("fetch") or {}
            run_id = fetch.get("crawl_run_id")
            if run_id is not None:
                crawl_run_ids.append(int(run_id))

        db_path = docs_dir / "db" / "docs.db"
        db_metrics = _collect_run_metrics(db_path, crawl_run_ids)
        run_results.append(
            {
                "mode": mode,
                "started_at_cli": started,
                "ended_at_cli": ended,
                "sync_started_at": result.get("started_at"),
                "sync_ended_at": result.get("ended_at"),
                "duration_s": duration_s,
                "config": result.get("config") or {},
                "totals": result.get("totals") or {},
                "sections_count": len(result.get("sections") or []),
                "crawl_run_ids": crawl_run_ids,
                "fetch_error_domains": _collect_fetch_error_domains(result),
                "db_metrics": db_metrics,
            }
        )

    payload = {
        "cmd": "bench-crawl-refresh",
        "generated_at": _iso_now(),
        "cwd": str(Path.cwd()),
        "docs_dir": str(docs_dir),
        "modes": modes,
        "runs": run_results,
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
