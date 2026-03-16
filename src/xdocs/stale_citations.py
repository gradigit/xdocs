from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .db import open_db
from .errors import XDocsError
from .lock import acquire_write_lock
from .store import require_store_db
from .timeutil import now_iso_utc


@dataclass(frozen=True, slots=True)
class StaleCitationFinding:
    kind: str  # stale_citation|missing_source
    endpoint_id: str
    field_name: str
    page_canonical_url: str
    cited_hash: str | None
    current_hash: str | None


def detect_stale_citations(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    exchange: str | None = None,
    section: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Scan endpoint citations for staleness:
    - citations to a page hash that no longer matches the latest stored page hash
    - citations to a page that is missing from the store

    This is complementary to the proactive enqueue in page_store.py:
    - if a page changes during a crawl/fetch, page_store enqueues `source_changed`
    - this command is a deterministic "sweep" to ensure no stale citations are missed
    """
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"

    created_at = now_iso_utc()
    created = 0

    # Phase 1: Read findings without holding the write lock.
    base_predicates: list[str] = []
    params: list[Any] = []
    if exchange:
        base_predicates.append("e.exchange = ?")
        params.append(str(exchange))
    if section:
        base_predicates.append("e.section = ?")
        params.append(str(section))

    missing_predicates = list(base_predicates) + ["p.id IS NULL"]
    where_missing = "WHERE " + " AND ".join(missing_predicates) if missing_predicates else ""

    missing_limit = None if limit is None else int(limit)
    missing_sql_limit = " LIMIT ?" if missing_limit is not None else ""
    missing_params = list(params)
    if missing_limit is not None:
        missing_params.append(int(missing_limit))

    conn_read = open_db(db_path)
    try:
        missing_rows = conn_read.execute(
            f"""
SELECT es.endpoint_id, es.field_name, es.page_canonical_url, es.page_content_hash
FROM endpoint_sources es
JOIN endpoints e ON e.endpoint_id = es.endpoint_id
LEFT JOIN pages p ON p.canonical_url = es.page_canonical_url
{where_missing}
ORDER BY es.endpoint_id, es.field_name, es.page_canonical_url
{missing_sql_limit};
""",
            tuple(missing_params),
        ).fetchall()

        remaining = None
        if limit is not None:
            remaining = max(0, int(limit) - len(missing_rows))
        stale_limit = remaining
        stale_sql_limit = " LIMIT ?" if stale_limit is not None else ""

        stale_predicates = list(base_predicates) + ["p.content_hash IS NOT NULL", "es.page_content_hash != p.content_hash"]
        where_stale = "WHERE " + " AND ".join(stale_predicates) if stale_predicates else ""

        stale_params = list(params)
        if stale_limit is not None:
            stale_params.append(int(stale_limit))

        stale_rows = conn_read.execute(
            f"""
SELECT es.endpoint_id, es.field_name, es.page_canonical_url, es.page_content_hash AS cited_hash, p.content_hash AS current_hash
FROM endpoint_sources es
JOIN endpoints e ON e.endpoint_id = es.endpoint_id
JOIN pages p ON p.canonical_url = es.page_canonical_url
{where_stale}
ORDER BY es.endpoint_id, es.field_name, es.page_canonical_url
{stale_sql_limit};
""",
            tuple(stale_params),
        ).fetchall()
    finally:
        conn_read.close()

    findings: list[StaleCitationFinding] = []
    for r in missing_rows:
        findings.append(
            StaleCitationFinding(
                kind="missing_source",
                endpoint_id=str(r["endpoint_id"]),
                field_name=str(r["field_name"]),
                page_canonical_url=str(r["page_canonical_url"]),
                cited_hash=str(r["page_content_hash"]) if r["page_content_hash"] else None,
                current_hash=None,
            )
        )
    for r in stale_rows:
        findings.append(
            StaleCitationFinding(
                kind="stale_citation",
                endpoint_id=str(r["endpoint_id"]),
                field_name=str(r["field_name"]),
                page_canonical_url=str(r["page_canonical_url"]),
                cited_hash=str(r["cited_hash"]) if r["cited_hash"] else None,
                current_hash=str(r["current_hash"]) if r["current_hash"] else None,
            )
        )

    # Phase 2: Write review queue items under the write lock.
    if not dry_run and findings:
        with acquire_write_lock(lock_path, timeout_s=float(lock_timeout_s)):
            conn = open_db(db_path)
            try:
                for f in findings:
                    kind = "stale_citation" if f.kind == "stale_citation" else "missing_source"
                    reason = "Citation no longer matches current stored source." if kind == "stale_citation" else "Cited source page is missing from the store."
                    details = {
                        "page_canonical_url": f.page_canonical_url,
                        "cited_hash": f.cited_hash,
                        "current_hash": f.current_hash,
                    }
                    details_json = json.dumps(details, sort_keys=True)

                    exists = conn.execute(
                        """
SELECT 1
FROM review_queue
WHERE status = 'open' AND kind = ? AND endpoint_id = ? AND field_name = ? AND details_json = ?
LIMIT 1;
""",
                        (kind, f.endpoint_id, f.field_name, details_json),
                    ).fetchone()
                    if exists is not None:
                        continue

                    conn.execute(
                        """
INSERT INTO review_queue (kind, endpoint_id, field_name, reason, status, created_at, details_json)
VALUES (?, ?, ?, ?, 'open', ?, ?);
""",
                        (kind, f.endpoint_id, f.field_name, reason, created_at, details_json),
                    )
                    created += 1

                conn.commit()
            finally:
                conn.close()

    return {
        "cmd": "detect-stale-citations",
        "schema_version": "v1",
        "filters": {"exchange": exchange, "section": section},
        "dry_run": bool(dry_run),
        "counts": {
            "missing_source": sum(1 for f in findings if f.kind == "missing_source"),
            "stale_citation": sum(1 for f in findings if f.kind == "stale_citation"),
            "total_findings": len(findings),
            "review_items_created": int(created),
        },
        "sample": [asdict(f) for f in findings[:10]],
    }
