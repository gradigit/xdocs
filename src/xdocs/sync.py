from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .coverage_gaps import compute_and_persist_coverage_gaps
from .db import open_db
from .errors import XDocsError
from .inventory import create_inventory, latest_inventory_id
from .inventory_fetch import fetch_inventory
from .quality import quality_check
from .registry import load_registry
from .stale_citations import detect_stale_citations
from .store import require_store_db
from .timeutil import now_iso_utc

_log = logging.getLogger(__name__)


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
    conditional: bool
    adaptive_delay: bool
    max_domain_delay_s: float
    scope_dedupe: bool


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
            raise XDocsError(
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
    render_mode: str = "auto",
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
    conditional: bool = True,
    adaptive_delay: bool = True,
    max_domain_delay_s: float = 30.0,
    scope_dedupe: bool = True,
) -> dict[str, Any]:
    if render_mode not in ("http", "playwright", "auto"):
        raise XDocsError(code="EBADARG", message="Invalid render_mode.", details={"render_mode": render_mode})

    started_at = now_iso_utc()
    reg = load_registry(registry_path)

    if resume and force_refetch:
        raise XDocsError(code="EBADARG", message="Cannot use both --resume and --force-refetch.", details={})

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
        conditional=bool(conditional),
        adaptive_delay=bool(adaptive_delay),
        max_domain_delay_s=max(float(max_domain_delay_s), 0.0),
        scope_dedupe=bool(scope_dedupe),
    )

    sections_run: list[dict[str, Any]] = []
    totals = {
        "inventories": 0,
        "inventory_urls": 0,
        "fetched": 0,
        "stored": 0,
        "skipped": 0,
        "dedupe_skipped": 0,
        "errors": 0,
        "new_pages": 0,
        "updated_pages": 0,
        "unchanged_pages": 0,
        "revalidated_unchanged": 0,
        "retry_after_applied": 0,
    }

    # ── Build section task list ──
    section_tasks: list[dict[str, Any]] = []
    for ex in reg.exchanges:
        if exchange and ex.exchange_id != exchange:
            continue
        sections_sorted = sorted(
            ex.sections,
            key=lambda s: (
                int(getattr(s.inventory_policy, "scope_priority", 100)),
            ),
        )
        for sec in sections_sorted:
            if section and sec.section_id != section:
                continue
            section_tasks.append({"exchange": ex, "section": sec})

    _log.info("Sync: %d sections to process", len(section_tasks))

    # ── Full pipeline per section (inventory + fetch) ──
    # Runs in parallel across exchanges. Each exchange's sections still run
    # in priority order (scope dedup), but different exchanges run concurrently.
    # Per-domain rate limiting inside fetch_inventory prevents hammering.
    def _process_section(task: dict[str, Any]) -> dict[str, Any]:
        ex = task["exchange"]
        sec = task["section"]
        label = f"{ex.exchange_id}/{sec.section_id}"
        # Scale lock timeout with parallelism — more concurrent writers need
        # longer waits. Each 3-phase lock hold is ~1-5s, so N writers need
        # ~N*5s worst case.
        parallel_lock_timeout = max(float(lock_timeout_s), float(parallel_exchanges) * 10.0)
        try:
            # Inventory phase
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
                    lock_timeout_s=parallel_lock_timeout,
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

            _log.info("  %s: inventory ready (%d URLs, resumed=%s)", label, inv_url_count, inv_resumed)

            # Fetch phase
            fetch_res = fetch_inventory(
                docs_dir=docs_dir,
                lock_timeout_s=parallel_lock_timeout,
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
                conditional=cfg.conditional,
                adaptive_delay=cfg.adaptive_delay,
                max_domain_delay_s=cfg.max_domain_delay_s,
                scope_dedupe=cfg.scope_dedupe,
                scope_group=(sec.inventory_policy.scope_group or ex.exchange_id),
                scope_priority=int(sec.inventory_policy.scope_priority),
            )

            fc = fetch_res["counts"]
            _log.info("  %s: done — %d fetched, %d stored, %d skipped, %d errors",
                      label, fc["fetched"], fc["stored"], fc["skipped"], fc["errors"])

            return {
                "exchange": ex, "section": sec,
                "inv_resumed": inv_resumed,
                "inv_id": use_inv_id, "inv_url_count": inv_url_count,
                "inv_generated_at": inv_generated_at, "inv_hash": inv_hash,
                "inv_diff": inv_diff, "inv_counts": inv_counts,
                "inv_errors": inv_errors, "inv_samples": inv_samples,
                "fetch_res": fetch_res, "error": None,
            }
        except Exception as e:
            _log.error("  %s: FAILED — %s", label, e)
            return {
                "exchange": ex, "section": sec,
                "inv_resumed": False,
                "inv_id": 0, "inv_url_count": 0,
                "inv_generated_at": "", "inv_hash": "",
                "inv_diff": {}, "inv_counts": {},
                "inv_errors": [], "inv_samples": {},
                "fetch_res": None, "error": str(e),
            }

    # Group sections by exchange so same-exchange sections run sequentially
    # (preserves scope dedup order) while different exchanges run in parallel.
    from collections import defaultdict
    by_exchange: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in section_tasks:
        by_exchange[task["exchange"].exchange_id].append(task)

    def _process_exchange_sections(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run all sections for one exchange sequentially."""
        return [_process_section(t) for t in tasks]

    # Parallelism is limited by memory (each exchange holds HTTP responses +
    # sitemap parsing in memory) and SQLite write contention. OOM observed at
    # 12 parallel (65GB VM, 3.6GB RSS) due to OKX's 5M-entry sitemap.
    # 4 concurrent exchanges balances speed vs memory safety.
    parallel_exchanges = min(len(by_exchange), 4)
    _log.info("Running %d exchanges in parallel (up to %d slots, %d workers each)",
              len(by_exchange), parallel_exchanges, cfg.concurrency)

    completed_tasks: list[dict[str, Any]] = []
    if parallel_exchanges > 1 and len(by_exchange) > 1:
        with ThreadPoolExecutor(max_workers=parallel_exchanges) as pool:
            futures = {
                pool.submit(_process_exchange_sections, tasks): ex_id
                for ex_id, tasks in by_exchange.items()
            }
            for future in as_completed(futures):
                completed_tasks.extend(future.result())
    else:
        for tasks in by_exchange.values():
            completed_tasks.extend(_process_exchange_sections(tasks))

    # ── Aggregate results ──
    for task in completed_tasks:
        fetch_res = task.get("fetch_res")
        if fetch_res is None:
            totals["inventories"] += 1
            totals["errors"] += 1
            sections_run.append({
                "exchange_id": task["exchange"].exchange_id,
                "section_id": task["section"].section_id,
                "resumed": task["inv_resumed"],
                "error": task["error"],
            })
            continue

        totals["inventories"] += 1
        totals["inventory_urls"] += task["inv_url_count"]
        totals["fetched"] += int(fetch_res["counts"]["fetched"])
        totals["stored"] += int(fetch_res["counts"]["stored"])
        totals["skipped"] += int(fetch_res["counts"]["skipped"])
        totals["dedupe_skipped"] += int(fetch_res["counts"].get("dedupe_skipped") or 0)
        totals["new_pages"] += int(fetch_res["counts"].get("new_pages") or 0)
        totals["updated_pages"] += int(fetch_res["counts"].get("updated_pages") or 0)
        totals["unchanged_pages"] += int(fetch_res["counts"].get("unchanged_pages") or 0)
        totals["revalidated_unchanged"] += int(fetch_res["counts"].get("revalidated_unchanged") or 0)
        totals["retry_after_applied"] += int(fetch_res["counts"].get("retry_after_applied") or 0)
        inv_counts = task["inv_counts"]
        inv_error_count = int(inv_counts.get("errors", 0)) if isinstance(inv_counts, dict) else 0
        totals["errors"] += int(fetch_res["counts"]["errors"]) + inv_error_count

        sections_run.append({
            "exchange_id": task["exchange"].exchange_id,
            "section_id": task["section"].section_id,
            "resumed": task["inv_resumed"],
            "inventory": {
                "inventory_id": task["inv_id"],
                "generated_at": task["inv_generated_at"],
                "url_count": task["inv_url_count"],
                "inventory_hash": task["inv_hash"],
                "diff": task["inv_diff"],
                "counts": inv_counts,
                "errors": task["inv_errors"],
                "samples": task["inv_samples"],
            },
            "fetch": fetch_res,
        })

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
    except XDocsError as e:
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
    except XDocsError as e:
        post["stale_citations_error"] = e.to_json()

    try:
        post["quality_check"] = quality_check(docs_dir=docs_dir)
    except XDocsError as e:
        post["quality_check_error"] = e.to_json()

    # Changelog extraction — detect new changelog entries from crawled pages.
    try:
        from .changelog import extract_changelogs
        cl_result = extract_changelogs(docs_dir=docs_dir, exchange=cfg.exchange)
        post["changelog_extraction"] = {
            "entries_new": cl_result.get("entries_new", 0),
            "pages_processed": cl_result.get("pages_processed", 0),
        }
    except Exception as e:
        post["changelog_extraction_error"] = str(e)

    # Incremental semantic index build — index new/changed pages.
    # Only runs if the [semantic] extra is installed (lancedb available).
    if totals.get("new_pages", 0) > 0 or totals.get("updated_pages", 0) > 0:
        try:
            from .semantic import build_index
            idx_result = build_index(
                docs_dir=docs_dir,
                incremental=True,
                exchange=cfg.exchange,
            )
            post["build_index"] = {
                "chunks_added": idx_result.get("chunks_added", 0),
                "pages_processed": idx_result.get("pages_processed", 0),
            }
            _log.info("Post-sync index build: %d chunks from %d pages",
                      idx_result.get("chunks_added", 0), idx_result.get("pages_processed", 0))
        except ImportError:
            post["build_index"] = {"skipped": "semantic extras not installed"}
        except Exception as e:
            post["build_index_error"] = str(e)
            _log.warning("Post-sync index build failed: %s", e)

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
