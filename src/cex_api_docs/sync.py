from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import open_db
from .errors import CexApiDocsError
from .inventory import create_inventory
from .inventory_fetch import fetch_inventory
from .registry import load_registry
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


def _require_store_db(docs_dir: str) -> Path:
    db_path = Path(docs_dir) / "db" / "docs.db"
    if not db_path.exists():
        raise CexApiDocsError(code="ENOINIT", message="Store not initialized. Run `cex-api-docs init` first.", details={"docs_dir": docs_dir})
    return db_path


def _inventory_diff_counts(*, docs_dir: str, exchange_id: str, section_id: str, new_inventory_id: int) -> dict[str, int]:
    db_path = _require_store_db(docs_dir)
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
) -> dict[str, Any]:
    if render_mode not in ("http", "playwright", "auto"):
        raise CexApiDocsError(code="EBADARG", message="Invalid render_mode.", details={"render_mode": render_mode})

    started_at = now_iso_utc()
    reg = load_registry(registry_path)

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

            inv = create_inventory(
                docs_dir=docs_dir,
                lock_timeout_s=float(lock_timeout_s),
                exchange_id=ex.exchange_id,
                section_id=sec.section_id,
                allowed_domains=ex.allowed_domains,
                seed_urls=sec.seed_urls,
                timeout_s=float(timeout_s),
                max_bytes=max(50_000_000, int(max_bytes)),
                max_redirects=int(max_redirects),
                retries=int(retries),
                ignore_robots=bool(ignore_robots),
                include_urls=False,
            )

            inv_diff = _inventory_diff_counts(docs_dir=docs_dir, exchange_id=ex.exchange_id, section_id=sec.section_id, new_inventory_id=int(inv.inventory_id))

            fetch_res = fetch_inventory(
                docs_dir=docs_dir,
                lock_timeout_s=float(lock_timeout_s),
                exchange_id=ex.exchange_id,
                section_id=sec.section_id,
                inventory_id=int(inv.inventory_id),
                allowed_domains=ex.allowed_domains,
                delay_s=float(delay_s),
                timeout_s=float(timeout_s),
                max_bytes=int(max_bytes),
                max_redirects=int(max_redirects),
                retries=int(retries),
                ignore_robots=bool(ignore_robots),
                render_mode=str(render_mode),
                limit=cfg.limit,
            )

            totals["inventories"] += 1
            totals["inventory_urls"] += int(inv.url_count)
            totals["fetched"] += int(fetch_res["counts"]["fetched"])
            totals["stored"] += int(fetch_res["counts"]["stored"])
            totals["skipped"] += int(fetch_res["counts"]["skipped"])
            totals["new_pages"] += int(fetch_res["counts"].get("new_pages") or 0)
            totals["updated_pages"] += int(fetch_res["counts"].get("updated_pages") or 0)
            totals["unchanged_pages"] += int(fetch_res["counts"].get("unchanged_pages") or 0)
            totals["errors"] += int(fetch_res["counts"]["errors"]) + int(inv.counts["errors"])

            sections_run.append(
                {
                    "exchange_id": ex.exchange_id,
                    "section_id": sec.section_id,
                    "inventory": {
                        "inventory_id": int(inv.inventory_id),
                        "generated_at": inv.generated_at,
                        "url_count": int(inv.url_count),
                        "inventory_hash": inv.inventory_hash,
                        "diff": inv_diff,
                        "counts": inv.counts,
                        "errors": inv.errors,
                        "samples": inv.samples,
                    },
                    "fetch": fetch_res,
                }
            )

    ended_at = now_iso_utc()
    return {
        "cmd": "sync",
        "schema_version": "v1",
        "docs_dir": str(Path(docs_dir)),
        "started_at": started_at,
        "ended_at": ended_at,
        "config": asdict(cfg),
        "totals": totals,
        "sections": sections_run,
    }
