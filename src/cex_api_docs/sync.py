from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .coverage_gaps import compute_and_persist_coverage_gaps
from .db import open_db
from .errors import CexApiDocsError
from .inventory import create_inventory, latest_inventory_id
from .inventory_fetch import fetch_inventory
from .quality import quality_check
from .registry import load_registry
from .stale_citations import detect_stale_citations
from .store import require_store_db
from .timeutil import now_iso_utc


@dataclass(frozen=True, slots=True)
class SyncConfig:
    exchange: str | None
    section: str | None
    render_mode: str
    ignore_robots: bool
    timeout_s: float
    max_bytes: int
    max_redirects: int
    retries: int
    delay_s: float
    limit: int | None
    inventory_max_pages: int | None
    resume: bool
    concurrency: int
    force_refetch: bool


def _inventory_diff_counts(*, docs_dir: str, exchange_id: str, section_id: str, new_inventory_id: int) -> dict[str, int]:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        prev = conn.execute(
            """
SELECT id
FROM inventories
WHERE exchange_id = ? AND section_id = ? AND id < ?
ORDER BY generated_at DESC, id DESC
LIMIT 1;
""",
            (exchange_id, section_id, int(new_inventory_id)),
        ).fetchone()
        if prev is None:
            return {"added": 0, "removed": 0}
        prev_id = int(prev["id"])

        added = conn.execute(
            """
SELECT COUNT(*) AS n FROM (
  SELECT canonical_url FROM inventory_entries WHERE inventory_id = ?
  EXCEPT
  SELECT canonical_url FROM inventory_entries WHERE inventory_id = ?
);
""",
            (int(new_inventory_id), prev_id),
        ).fetchone()
        removed = conn.execute(
            """
SELECT COUNT(*) AS n FROM (
  SELECT canonical_url FROM inventory_entries WHERE inventory_id = ?
  EXCEPT
  SELECT canonical_url FROM inventory_entries WHERE inventory_id = ?
);
""",
            (prev_id, int(new_inventory_id)),
        ).fetchone()
        return {"added": int(added["n"] or 0), "removed": int(removed["n"] or 0)}
    finally:
        conn.close()


def _load_inventory_from_db(
    docs_dir: str, inventory_id: int, exchange_id: str, section_id: str,
) -> dict[str, Any]:
    """Load an existing inventory row + entry status counts from DB."""
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        row = conn.execute(
            "SELECT generated_at, url_count, inventory_hash, sources_json FROM inventories WHERE id = ?;",
            (int(inventory_id),),
        ).fetchone()
        if row is None:
            raise CexApiDocsError(
                code="ENOINV",
                message="Inventory not found.",
                details={"inventory_id": inventory_id},
            )
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM inventory_entries WHERE inventory_id = ? GROUP BY status;",
            (int(inventory_id),),
        ).fetchall()
        status_counts = {str(r["status"]): int(r["n"]) for r in status_rows}
        return {
            "inventory_id": int(inventory_id),
            "generated_at": str(row["generated_at"]),
            "url_count": int(row["url_count"]),
            "inventory_hash": str(row["inventory_hash"]),
            "status_counts": status_counts,
        }
    finally:
        conn.close()


def run_sync(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    registry_path: Path,
    exchange: str | None = None,
    section: str | None = None,
    render_mode: str = "http",
    ignore_robots: bool = False,
    timeout_s: float = 20.0,
    max_bytes: int = 10_000_000,
    max_redirects: int = 5,
    retries: int = 2,
    delay_s: float = 0.25,
    limit: int | None = None,
    inventory_max_pages: int | None = None,
    resume: bool = False,
    concurrency: int = 1,
    force_refetch: bool = False,
) -> dict[str, Any]:
    if render_mode not in ("http", "playwright", "auto"):
        raise CexApiDocsError(code="EBADARG", message="Invalid render_mode.", details={"render_mode": render_mode})

    started_at = now_iso_utc()
    reg = load_registry(registry_path)

    if resume and force_refetch:
        raise CexApiDocsError(code="EBADARG", message="Cannot use both --resume and --force-refetch.", details={})

    cfg = SyncConfig(
        exchange=exchange,
        section=section,
        render_mode=str(render_mode),
        ignore_robots=bool(ignore_robots),
        timeout_s=float(timeout_s),
        max_bytes=int(max_bytes),
        max_redirects=int(max_redirects),
        retries=int(retries),
        delay_s=float(delay_s),
        limit=None if limit is None else int(limit),
        inventory_max_pages=None if inventory_max_pages is None else max(1, int(inventory_max_pages)),
        resume=bool(resume),
        concurrency=max(1, int(concurrency)),
        force_refetch=bool(force_refetch),
    )

    sections_run: list[dict[str, Any]] = []
    totals = {
        "inventories": 0,
        "inventory_urls": 0,
        "fetched": 0,
        "stored": 0,
        "skipped": 0,
        "errors": 0,
        "new_pages": 0,
        "updated_pages": 0,
        "unchanged_pages": 0,
    }

    for ex in reg.exchanges:
        if exchange and ex.exchange_id != exchange:
            continue
        for sec in ex.sections:
            if section and sec.section_id != section:
                continue

            # Resume/force-refetch mode: reuse the latest existing inventory instead of creating a new one.
            inv = None
            inv_resumed = False
            if cfg.resume or cfg.force_refetch:
                existing_id = latest_inventory_id(docs_dir=docs_dir, exchange_id=ex.exchange_id, section_id=sec.section_id)
                if existing_id is not None:
                    inv_resumed = True
                    inv_info = _load_inventory_from_db(docs_dir, existing_id, ex.exchange_id, sec.section_id)

            if not inv_resumed:
                inv = create_inventory(
                    docs_dir=docs_dir,
                    lock_timeout_s=float(lock_timeout_s),
                    exchange_id=ex.exchange_id,
                    section_id=sec.section_id,
                    allowed_domains=ex.allowed_domains,
                    seed_urls=sec.seed_urls,
                    doc_sources=getattr(sec, "doc_sources", None),
                    inventory_policy=getattr(sec, "inventory_policy", None),
                    link_follow_max_pages_override=cfg.inventory_max_pages,
                    timeout_s=float(timeout_s),
                    max_bytes=max(50_000_000, int(max_bytes)),
                    link_follow_max_bytes=int(max_bytes),
                    max_redirects=int(max_redirects),
                    retries=int(retries),
                    ignore_robots=bool(ignore_robots),
                    delay_s=float(delay_s),
                    default_render_mode=str(render_mode),
                    include_urls=False,
                )

            if inv_resumed:
                use_inv_id = int(inv_info["inventory_id"])
                inv_url_count = int(inv_info["url_count"])
                inv_generated_at = inv_info["generated_at"]
                inv_hash = inv_info["inventory_hash"]
                inv_diff = {"added": 0, "removed": 0}
                inv_counts = inv_info.get("status_counts", {})
                inv_errors: list[dict[str, Any]] = []
                inv_samples: dict[str, Any] = {}
            else:
                assert inv is not None
                use_inv_id = int(inv.inventory_id)
                inv_url_count = int(inv.url_count)
                inv_generated_at = inv.generated_at
                inv_hash = inv.inventory_hash
                inv_diff = _inventory_diff_counts(
                    docs_dir=docs_dir, exchange_id=ex.exchange_id,
                    section_id=sec.section_id, new_inventory_id=use_inv_id,
                )
                inv_counts = inv.counts
                inv_errors = inv.errors
                inv_samples = inv.samples

            fetch_res = fetch_inventory(
                docs_dir=docs_dir,
                lock_timeout_s=float(lock_timeout_s),
                exchange_id=ex.exchange_id,
                section_id=sec.section_id,
                inventory_id=use_inv_id,
                allowed_domains=ex.allowed_domains,
                delay_s=float(delay_s),
                timeout_s=float(timeout_s),
                max_bytes=int(max_bytes),
                max_redirects=int(max_redirects),
                retries=int(retries),
                ignore_robots=bool(ignore_robots),
                render_mode=str(render_mode),
                resume=cfg.resume,
                limit=cfg.limit,
                concurrency=cfg.concurrency,
                force_refetch=cfg.force_refetch,
            )

            totals["inventories"] += 1
            totals["inventory_urls"] += inv_url_count
            totals["fetched"] += int(fetch_res["counts"]["fetched"])
            totals["stored"] += int(fetch_res["counts"]["stored"])
            totals["skipped"] += int(fetch_res["counts"]["skipped"])
            totals["new_pages"] += int(fetch_res["counts"].get("new_pages") or 0)
            totals["updated_pages"] += int(fetch_res["counts"].get("updated_pages") or 0)
            totals["unchanged_pages"] += int(fetch_res["counts"].get("unchanged_pages") or 0)
            inv_error_count = int(inv_counts.get("errors", 0)) if isinstance(inv_counts, dict) else 0
            totals["errors"] += int(fetch_res["counts"]["errors"]) + inv_error_count

            sections_run.append(
                {
                    "exchange_id": ex.exchange_id,
                    "section_id": sec.section_id,
                    "resumed": inv_resumed,
                    "inventory": {
                        "inventory_id": use_inv_id,
                        "generated_at": inv_generated_at,
                        "url_count": inv_url_count,
                        "inventory_hash": inv_hash,
                        "diff": inv_diff,
                        "counts": inv_counts,
                        "errors": inv_errors,
                        "samples": inv_samples,
                    },
                    "fetch": fetch_res,
                }
            )

    ended_at = now_iso_utc()
    post: dict[str, Any] = {}
    # Post-processing: keep cron runs actionable (completeness + stale citation sweeps).
    # These are scale-safe and cheap when endpoint DB is empty.
    try:
        post["coverage_gaps"] = compute_and_persist_coverage_gaps(
            docs_dir=docs_dir,
            lock_timeout_s=float(lock_timeout_s),
            exchange=cfg.exchange,
            section=cfg.section,
            limit_samples=5,
        )
    except CexApiDocsError as e:
        post["coverage_gaps_error"] = e.to_json()

    try:
        post["stale_citations"] = detect_stale_citations(
            docs_dir=docs_dir,
            lock_timeout_s=float(lock_timeout_s),
            exchange=cfg.exchange,
            section=cfg.section,
            dry_run=False,
            limit=None,
        )
    except CexApiDocsError as e:
        post["stale_citations_error"] = e.to_json()

    try:
        post["quality_check"] = quality_check(docs_dir=docs_dir)
    except CexApiDocsError as e:
        post["quality_check_error"] = e.to_json()

    return {
        "cmd": "sync",
        "schema_version": "v1",
        "docs_dir": str(Path(docs_dir)),
        "started_at": started_at,
        "ended_at": ended_at,
        "config": asdict(cfg),
        "totals": totals,
        "sections": sections_run,
        "post": post,
    }
