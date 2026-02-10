from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .db import open_db
from .endpoints import REQUIRED_HTTP_FIELD_STATUS_KEYS
from .errors import CexApiDocsError
from .lock import acquire_write_lock
from .store import require_store_db
from .timeutil import now_iso_utc


def _ensure_table(conn) -> None:
    conn.execute(
        """
CREATE TABLE IF NOT EXISTS coverage_gaps (
  exchange TEXT NOT NULL,
  section TEXT NOT NULL,
  protocol TEXT NOT NULL,
  field_name TEXT NOT NULL,
  status_counts_json TEXT NOT NULL,
  sample_endpoint_ids_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (exchange, section, protocol, field_name)
);
"""
    )


@dataclass(frozen=True, slots=True)
class CoverageGapRow:
    exchange: str
    section: str
    protocol: str
    field_name: str
    status_counts: dict[str, int]
    sample_endpoint_ids: dict[str, list[str]]


def compute_and_persist_coverage_gaps(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    exchange: str | None = None,
    section: str | None = None,
    limit_samples: int = 5,
) -> dict[str, Any]:
    """
    Compute aggregated endpoint field_status gaps and persist them into `coverage_gaps`.

    This is a scale-safe "review backlog" for completeness without exploding review_queue.
    """
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"
    updated_at = now_iso_utc()

    # Compute outside the write lock (eventually consistent reporting),
    # then upsert under lock to minimize global lock duration.
    where: list[str] = []
    params: list[Any] = []
    if exchange:
        where.append("exchange = ?")
        params.append(str(exchange))
    if section:
        where.append("section = ?")
        params.append(str(section))

    sql = "SELECT endpoint_id, exchange, section, protocol, json FROM endpoints"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY exchange, section, endpoint_id;"

    # (exchange, section, protocol, field) -> counts, samples
    counts: dict[tuple[str, str, str, str], dict[str, int]] = {}
    samples: dict[tuple[str, str, str, str], dict[str, list[str]]] = {}

    def bump(key: tuple[str, str, str, str], status: str, endpoint_id: str) -> None:
        c = counts.setdefault(key, {})
        c[status] = int(c.get(status, 0)) + 1
        if status in ("unknown", "undocumented", "conflict", "missing"):
            s = samples.setdefault(key, {})
            arr = s.setdefault(status, [])
            if len(arr) < int(limit_samples):
                arr.append(endpoint_id)

    total_endpoints = 0
    conn_read = open_db(db_path)
    try:
        cur = conn_read.execute(sql, tuple(params))
        for r in cur:
            total_endpoints += 1
            endpoint_id = str(r["endpoint_id"])
            ex = str(r["exchange"])
            sec = str(r["section"])
            proto = str(r["protocol"] or "")
            try:
                rec = json.loads(r["json"])
            except Exception:
                continue

            fs = rec.get("field_status")
            if not isinstance(fs, dict):
                continue

            required: tuple[str, ...] = REQUIRED_HTTP_FIELD_STATUS_KEYS if proto == "http" else tuple(fs.keys())
            for field in required:
                st = str(fs.get(field, "missing"))
                bump((ex, sec, proto, str(field)), st, endpoint_id)
    finally:
        conn_read.close()

    gap_rows: list[CoverageGapRow] = []
    for (ex, sec, proto, field), c in sorted(counts.items(), key=lambda x: x[0]):
        s = samples.get((ex, sec, proto, field), {})
        gap_rows.append(
            CoverageGapRow(
                exchange=ex,
                section=sec,
                protocol=proto,
                field_name=field,
                status_counts=dict(sorted(c.items(), key=lambda x: x[0])),
                sample_endpoint_ids={k: list(v) for k, v in sorted(s.items(), key=lambda x: x[0])},
            )
        )

    with acquire_write_lock(lock_path, timeout_s=float(lock_timeout_s)):
        conn = open_db(db_path)
        try:
            _ensure_table(conn)
            with conn:
                for gr in gap_rows:
                    conn.execute(
                        """
INSERT INTO coverage_gaps (exchange, section, protocol, field_name, status_counts_json, sample_endpoint_ids_json, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(exchange, section, protocol, field_name) DO UPDATE SET
  status_counts_json = excluded.status_counts_json,
  sample_endpoint_ids_json = excluded.sample_endpoint_ids_json,
  updated_at = excluded.updated_at;
""",
                        (
                            gr.exchange,
                            gr.section,
                            gr.protocol,
                            gr.field_name,
                            json.dumps(gr.status_counts, sort_keys=True),
                            json.dumps(gr.sample_endpoint_ids, sort_keys=True),
                            updated_at,
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

    # Return a summary plus a small sample for debugging.
    total_rows = len(gap_rows)
    total_gaps = 0
    for gr in gap_rows:
        non_doc = sum(v for k, v in gr.status_counts.items() if k in ("unknown", "undocumented", "conflict", "missing"))
        if non_doc > 0:
            total_gaps += 1

    return {
        "cmd": "coverage-gaps",
        "schema_version": "v1",
        "filters": {"exchange": exchange, "section": section},
        "updated_at": updated_at,
        "counts": {"endpoints": total_endpoints, "rows": total_rows, "rows_with_gaps": total_gaps},
        "sample": [asdict(r) for r in gap_rows[:10]],
    }


def list_coverage_gaps(
    *,
    docs_dir: str,
    exchange: str | None = None,
    section: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        _ensure_table(conn)
        where: list[str] = []
        params: list[Any] = []
        if exchange:
            where.append("exchange = ?")
            params.append(str(exchange))
        if section:
            where.append("section = ?")
            params.append(str(section))
        sql = "SELECT exchange, section, protocol, field_name, status_counts_json, sample_endpoint_ids_json, updated_at FROM coverage_gaps"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY exchange, section, protocol, field_name LIMIT ?;"
        params.append(int(limit))

        rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "exchange": str(r["exchange"]),
                    "section": str(r["section"]),
                    "protocol": str(r["protocol"]),
                    "field_name": str(r["field_name"]),
                    "status_counts": json.loads(r["status_counts_json"] or "{}"),
                    "sample_endpoint_ids": json.loads(r["sample_endpoint_ids_json"] or "{}"),
                    "updated_at": str(r["updated_at"]),
                }
            )
        return {
            "cmd": "coverage-gaps-list",
            "schema_version": "v1",
            "filters": {"exchange": exchange, "section": section},
            "count": len(out),
            "items": out,
        }
    finally:
        conn.close()
