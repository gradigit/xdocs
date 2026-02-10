from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import open_db
from .endpoints import REQUIRED_HTTP_FIELD_STATUS_KEYS
from .errors import CexApiDocsError


def _require_store_db(docs_dir: str) -> Path:
    db_path = Path(docs_dir) / "db" / "docs.db"
    if not db_path.exists():
        raise CexApiDocsError(code="ENOINIT", message="Store not initialized. Run `cex-api-docs init` first.", details={"docs_dir": docs_dir})
    return db_path


def endpoint_coverage(
    *,
    docs_dir: str,
    exchange: str | None = None,
    section: str | None = None,
    limit_samples: int = 5,
) -> dict[str, Any]:
    db_path = _require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
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

        rows = conn.execute(sql, tuple(params)).fetchall()

        totals = {"endpoints": 0}
        by_field: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        samples: dict[tuple[str, str], list[str]] = defaultdict(list)  # (field, status) -> endpoint_ids

        for r in rows:
            totals["endpoints"] += 1
            try:
                rec = json.loads(r["json"])
            except Exception:
                continue
            proto = str(rec.get("protocol") or r["protocol"] or "")
            fs = rec.get("field_status")
            if not isinstance(fs, dict):
                continue

            required: tuple[str, ...] = REQUIRED_HTTP_FIELD_STATUS_KEYS if proto == "http" else tuple(fs.keys())

            for k in required:
                st = str(fs.get(k, "missing"))
                by_field[k][st] += 1
                if st in ("unknown", "undocumented", "conflict", "missing"):
                    key = (k, st)
                    if len(samples[key]) < int(limit_samples):
                        samples[key].append(str(r["endpoint_id"]))

        gaps: list[dict[str, Any]] = []
        for (field, st), ids in sorted(samples.items(), key=lambda x: (x[0][0], x[0][1])):
            gaps.append({"field": field, "status": st, "sample_endpoint_ids": ids})

        # Convert defaultdicts to plain dicts.
        by_field_out: dict[str, dict[str, int]] = {k: dict(v) for k, v in by_field.items()}

        return {
            "cmd": "coverage",
            "schema_version": "v1",
            "filters": {"exchange": exchange, "section": section},
            "totals": totals,
            "by_field": by_field_out,
            "gaps": gaps,
        }
    finally:
        conn.close()

