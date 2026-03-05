from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from jsonschema import Draft202012Validator

from .db import open_db
from .errors import CexApiDocsError
from .fs import atomic_write_text
from .hashing import sha256_hex_text
from .lock import acquire_write_lock
from .store import require_store_db
from .timeutil import now_iso_utc
from .urlcanon import canonicalize_url


HARD_MAX_EXCERPT_CHARS = 600

# Field completeness contract.
# These keys are used in endpoint JSON as field_status{} keys.
# Dotted keys address nested objects (e.g. "http.method").
REQUIRED_HTTP_FIELD_STATUS_KEYS: tuple[str, ...] = (
    "http.method",
    "http.path",
    "http.base_url",
    "description",
    "request_schema",
    "response_schema",
    "required_permissions",
    "rate_limit",
    "error_codes",
)

# Review queue must be scale-aware; only flag per-endpoint inconsistencies for high-risk fields.
INCONSISTENT_STATUS_REVIEW_FIELDS: frozenset[str] = frozenset(
    {
        "required_permissions",
        "rate_limit",
        "error_codes",
        "request_schema",
        "response_schema",
    }
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_endpoint_schema(schema_path: Path) -> Draft202012Validator:
    schema = _load_json(schema_path)
    return Draft202012Validator(schema)


def compute_endpoint_id(record: dict[str, Any]) -> str:
    exchange = str(record.get("exchange", "")).strip()
    section = str(record.get("section", "")).strip()
    protocol = str(record.get("protocol", "")).strip()

    http = record.get("http") or {}
    if protocol == "http" and isinstance(http, dict):
        method = str(http.get("method", "")).upper()
        path = str(http.get("path", ""))
        base_url = str(http.get("base_url", ""))
        api_version = http.get("api_version")
        api_version_str = "" if api_version is None else str(api_version)
    else:
        method = ""
        path = ""
        base_url = ""
        api_version_str = ""

    raw = f"{exchange}|{section}|{protocol}|{base_url}|{api_version_str}|{method}|{path}"
    return sha256_hex_text(raw)


def _verify_citation_against_store(*, conn, citation: dict[str, Any]) -> None:
    url = str(citation.get("url", ""))
    canonical = canonicalize_url(url)
    want_path_hash = str(citation.get("path_hash", ""))
    want_content_hash = str(citation.get("content_hash", ""))

    start = int(citation.get("excerpt_start", 0))
    end = int(citation.get("excerpt_end", 0))
    excerpt = str(citation.get("excerpt", ""))

    if end <= start:
        raise CexApiDocsError(
            code="EBADCITE",
            message="Invalid citation excerpt offsets (end must be > start).",
            details={"canonical_url": canonical, "excerpt_start": start, "excerpt_end": end},
        )
    if len(excerpt) > HARD_MAX_EXCERPT_CHARS:
        raise CexApiDocsError(
            code="EBADCITE",
            message="Citation excerpt exceeds hard max length.",
            details={"canonical_url": canonical, "excerpt_len": len(excerpt), "hard_max": HARD_MAX_EXCERPT_CHARS},
        )

    row = conn.execute(
        "SELECT canonical_url, path_hash, content_hash, markdown_path FROM pages WHERE canonical_url = ?;",
        (canonical,),
    ).fetchone()
    if row is None:
        raise CexApiDocsError(code="ESOURCE", message="Citation URL not found in local store.", details={"canonical_url": canonical})

    if want_path_hash and str(row["path_hash"]) != want_path_hash:
        raise CexApiDocsError(
            code="ESOURCE",
            message="Citation path_hash does not match stored page.",
            details={"canonical_url": canonical, "want": want_path_hash, "got": row["path_hash"]},
        )
    if want_content_hash and str(row["content_hash"]) != want_content_hash:
        raise CexApiDocsError(
            code="ESOURCE",
            message="Citation content_hash does not match stored page.",
            details={"canonical_url": canonical, "want": want_content_hash, "got": row["content_hash"]},
        )

    md_path = Path(row["markdown_path"]) if row["markdown_path"] else None
    if not md_path or not md_path.exists():
        raise CexApiDocsError(code="ESOURCE", message="Citation page has no stored markdown.", details={"canonical_url": canonical})

    md = md_path.read_text(encoding="utf-8")
    if end > len(md):
        raise CexApiDocsError(
            code="EBADCITE",
            message="Citation excerpt_end is out of bounds for stored markdown.",
            details={"canonical_url": canonical, "excerpt_end": end, "markdown_len": len(md)},
        )

    got = md[start:end]
    if got != excerpt:
        raise CexApiDocsError(
            code="EBADCITE",
            message="Citation excerpt does not match stored markdown at provided offsets.",
            details={"canonical_url": canonical, "excerpt_start": start, "excerpt_end": end},
        )


def save_endpoint(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    endpoint_json_path: Path,
    schema_path: Path,
) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"

    record = _load_json(endpoint_json_path)
    if not isinstance(record, dict):
        raise CexApiDocsError(code="EBADJSON", message="Endpoint JSON must be an object.", details={"path": str(endpoint_json_path)})

    validator = load_endpoint_schema(schema_path)
    _validate_endpoint_record_schema(validator=validator, record=record, path=str(endpoint_json_path))

    computed_id = compute_endpoint_id(record)
    provided_id = str(record.get("endpoint_id", ""))
    if provided_id != computed_id:
        raise CexApiDocsError(
            code="EIDMISMATCH",
            message="endpoint_id does not match computed identity.",
            details={"provided": provided_id, "computed": computed_id},
        )

    exchange = str(record.get("exchange"))
    section = str(record.get("section"))
    protocol = str(record.get("protocol"))
    http = record.get("http") or {}
    method = str(http.get("method")) if isinstance(http, dict) and http.get("method") is not None else None
    path = str(http.get("path")) if isinstance(http, dict) and http.get("path") is not None else None
    base_url = str(http.get("base_url")) if isinstance(http, dict) and http.get("base_url") is not None else None
    api_version = http.get("api_version") if isinstance(http, dict) else None
    api_version_str = None if api_version is None else str(api_version)
    description = record.get("description")
    description_str = None if description is None else str(description)

    sources = record.get("sources") or []
    if not isinstance(sources, list):
        raise CexApiDocsError(code="EBADSRC", message="Endpoint record sources[] must be a list.")

    field_status = record.get("field_status")
    if not isinstance(field_status, dict):
        raise CexApiDocsError(code="EBADFIELDSTATUS", message="Endpoint record must include field_status{} object.")

    if protocol == "http":
        if not isinstance(record.get("http"), dict):
            raise CexApiDocsError(code="EBADHTTP", message="HTTP endpoints must include http{} object.")
        missing = [k for k in REQUIRED_HTTP_FIELD_STATUS_KEYS if k not in field_status]
        if missing:
            raise CexApiDocsError(
                code="EBADFIELDSTATUS",
                message="field_status{} is missing required keys for protocol=http.",
                details={"endpoint_id": computed_id, "missing_keys": missing},
            )

    updated_at = now_iso_utc()

    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn = open_db(db_path)
        try:
            res = _save_endpoint_record(
                conn=conn,
                docs_dir=docs_dir,
                record=record,
                computed_id=computed_id,
                exchange=exchange,
                section=section,
                protocol=protocol,
                method=method,
                path=path,
                base_url=base_url,
                api_version_str=api_version_str,
                description_str=description_str,
                sources=sources,
                field_status=field_status,
                updated_at=updated_at,
            )
            conn.commit()
            return res
        finally:
            conn.close()


def save_endpoints_bulk(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    schema_path: Path,
    records: list[dict[str, Any]],
    continue_on_error: bool = True,
) -> dict[str, Any]:
    """
    Bulk ingest endpoints under a single write lock + DB connection.

    This is primarily used by deterministic importers (OpenAPI/Postman).
    """
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"

    validator = load_endpoint_schema(schema_path)

    counts = {"ok": 0, "errors": 0, "total": int(len(records))}
    errors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn = open_db(db_path)
        try:
            for i, record in enumerate(records):
                try:
                    if not isinstance(record, dict):
                        raise CexApiDocsError(code="EBADJSON", message="Endpoint record must be an object.", details={"index": i})

                    _validate_endpoint_record_schema(validator=validator, record=record, path=f"<bulk:{i}>")

                    computed_id = compute_endpoint_id(record)
                    provided_id = str(record.get("endpoint_id", ""))
                    if provided_id != computed_id:
                        raise CexApiDocsError(
                            code="EIDMISMATCH",
                            message="endpoint_id does not match computed identity.",
                            details={"index": i, "provided": provided_id, "computed": computed_id},
                        )

                    exchange = str(record.get("exchange"))
                    section = str(record.get("section"))
                    protocol = str(record.get("protocol"))

                    http = record.get("http") or {}
                    method = str(http.get("method")) if isinstance(http, dict) and http.get("method") is not None else None
                    path = str(http.get("path")) if isinstance(http, dict) and http.get("path") is not None else None
                    base_url = str(http.get("base_url")) if isinstance(http, dict) and http.get("base_url") is not None else None
                    api_version = http.get("api_version") if isinstance(http, dict) else None
                    api_version_str = None if api_version is None else str(api_version)
                    description = record.get("description")
                    description_str = None if description is None else str(description)

                    sources = record.get("sources") or []
                    if not isinstance(sources, list):
                        raise CexApiDocsError(code="EBADSRC", message="Endpoint record sources[] must be a list.")

                    field_status = record.get("field_status")
                    if not isinstance(field_status, dict):
                        raise CexApiDocsError(code="EBADFIELDSTATUS", message="Endpoint record must include field_status{} object.")

                    if protocol == "http":
                        if not isinstance(record.get("http"), dict):
                            raise CexApiDocsError(code="EBADHTTP", message="HTTP endpoints must include http{} object.")
                        missing = [k for k in REQUIRED_HTTP_FIELD_STATUS_KEYS if k not in field_status]
                        if missing:
                            raise CexApiDocsError(
                                code="EBADFIELDSTATUS",
                                message="field_status{} is missing required keys for protocol=http.",
                                details={"endpoint_id": computed_id, "missing_keys": missing},
                            )

                    updated_at = now_iso_utc()

                    res = _save_endpoint_record(
                        conn=conn,
                        docs_dir=docs_dir,
                        record=record,
                        computed_id=computed_id,
                        exchange=exchange,
                        section=section,
                        protocol=protocol,
                        method=method,
                        path=path,
                        base_url=base_url,
                        api_version_str=api_version_str,
                        description_str=description_str,
                        sources=sources,
                        field_status=field_status,
                        updated_at=updated_at,
                    )
                    results.append(res)
                    counts["ok"] += 1
                except Exception as e:
                    counts["errors"] += 1
                    if isinstance(e, CexApiDocsError):
                        errors.append({"index": i, "code": e.code, "message": e.message, "details": e.details})
                    else:
                        errors.append({"index": i, "code": "EUNEXPECTED", "message": str(e), "details": {}})
                    if not continue_on_error:
                        break

            conn.commit()
        finally:
            conn.close()

    return {"cmd": "save-endpoints-bulk", "schema_version": "v1", "docs_dir": docs_dir, "counts": counts, "errors": errors[:50], "results": results}


def _validate_endpoint_record_schema(*, validator: Draft202012Validator, record: dict[str, Any], path: str) -> None:
    errors = sorted(validator.iter_errors(record), key=lambda e: e.path)
    if errors:
        raise CexApiDocsError(
            code="ESCHEMA",
            message="Endpoint JSON failed schema validation.",
            details={"path": path, "errors": [e.message for e in errors[:10]]},
        )


def _get_field_value(record: dict[str, Any], key: str) -> Any:
    # Dotted keys allow nested field status, e.g. "http.method".
    if "." in key:
        prefix, rest = key.split(".", 1)
        obj = record.get(prefix)
        if isinstance(obj, dict):
            return obj.get(rest)
        return None
    return record.get(key)


def _save_endpoint_record(
    *,
    conn,
    docs_dir: str,
    record: dict[str, Any],
    computed_id: str,
    exchange: str,
    section: str,
    protocol: str,
    method: str | None,
    path: str | None,
    base_url: str | None,
    api_version_str: str | None,
    description_str: str | None,
    sources: list[Any],
    field_status: dict[str, Any],
    updated_at: str,
) -> dict[str, Any]:
    # Verify citations against the local store.
    for c in sources:
        if not isinstance(c, dict):
            raise CexApiDocsError(code="EBADSRC", message="sources[] must contain objects.")
        _verify_citation_against_store(conn=conn, citation=c)

    documented_fields = [str(k) for k, v in field_status.items() if str(v) == "documented"]
    source_fields = {str(c.get("field_name")) for c in sources if isinstance(c, dict) and c.get("field_name")}

    missing_citations = sorted([f for f in documented_fields if f not in source_fields])
    if missing_citations:
        raise CexApiDocsError(
            code="EBADCITE",
            message="Documented fields are missing required citations.",
            details={"endpoint_id": computed_id, "missing_field_names": missing_citations},
        )

    missing_values: list[str] = []
    for f in documented_fields:
        v = _get_field_value(record, f)
        if v is None:
            missing_values.append(f)
        elif isinstance(v, str) and not v.strip():
            missing_values.append(f)
    if missing_values:
        raise CexApiDocsError(
            code="EBADFIELDSTATUS",
            message="Documented fields must have non-empty values.",
            details={"endpoint_id": computed_id, "missing_values": sorted(missing_values)},
        )

    # Persist endpoint JSON to disk.
    endpoint_dir = Path(docs_dir) / "endpoints" / exchange / section
    endpoint_path = endpoint_dir / f"{computed_id}.json"
    atomic_write_text(endpoint_path, json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n")

    # Upsert endpoints row without REPLACE (preserve rowid).
    with conn:
        existing = conn.execute("SELECT rowid FROM endpoints WHERE endpoint_id = ?;", (computed_id,)).fetchone()
        if existing is None:
            cur = conn.execute(
                """
INSERT INTO endpoints (
  endpoint_id, exchange, section, protocol, method, path, base_url, api_version,
  description, json, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                (
                    computed_id,
                    exchange,
                    section,
                    protocol,
                    method,
                    path,
                    base_url,
                    api_version_str,
                    description_str,
                    json.dumps(record, sort_keys=True, ensure_ascii=False),
                    updated_at,
                ),
            )
            endpoint_rowid = int(cur.lastrowid)
        else:
            endpoint_rowid = int(existing["rowid"])
            conn.execute(
                """
UPDATE endpoints
SET exchange = ?, section = ?, protocol = ?, method = ?, path = ?, base_url = ?, api_version = ?,
    description = ?, json = ?, updated_at = ?
WHERE endpoint_id = ?;
""",
                (
                    exchange,
                    section,
                    protocol,
                    method,
                    path,
                    base_url,
                    api_version_str,
                    description_str,
                    json.dumps(record, sort_keys=True, ensure_ascii=False),
                    updated_at,
                    computed_id,
                ),
            )

        # Keep endpoint_sources consistent with the endpoint's current sources.
        # The sources[] array is treated as the full, current set of citations.
        conn.execute("DELETE FROM endpoint_sources WHERE endpoint_id = ?;", (computed_id,))

        # Endpoint sources mapping (field_name must exist).
        for c in sources:
            if not isinstance(c, dict):
                continue
            field = c.get("field_name")
            if not field:
                continue
            canonical = canonicalize_url(str(c.get("url", "")))
            content_hash = str(c.get("content_hash", ""))
            conn.execute(
                """
INSERT OR IGNORE INTO endpoint_sources (
  endpoint_id, field_name, page_canonical_url, page_content_hash, created_at
) VALUES (?, ?, ?, ?, ?);
""",
                (computed_id, str(field), canonical, content_hash, updated_at),
            )

        # Review queue rules: inconsistent field_status vs values (high-risk fields only).
        for field_name, status in field_status.items():
            k = str(field_name)
            st = str(status)
            if k not in INCONSISTENT_STATUS_REVIEW_FIELDS:
                continue
            v = _get_field_value(record, k)
            if v is None:
                continue
            if st in ("undocumented", "unknown"):
                conn.execute(
                    """
INSERT INTO review_queue (
  kind, endpoint_id, field_name, reason, status, created_at, details_json
) VALUES (?, ?, ?, ?, 'open', ?, ?);
""",
                    (
                        "inconsistent_field_status",
                        computed_id,
                        k,
                        "Field has a value but field_status is not documented",
                        updated_at,
                        json.dumps({"field_status": st, "endpoint_path": str(endpoint_path)}, sort_keys=True),
                    ),
                )

        # Update endpoints_fts (rowid = endpoints.rowid).
        search_text = json.dumps(
            {
                "description": description_str,
                "required_permissions": record.get("required_permissions"),
                "rate_limit": record.get("rate_limit"),
                "error_codes": record.get("error_codes"),
                "field_status": field_status,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        conn.execute("DELETE FROM endpoints_fts WHERE rowid = ?;", (endpoint_rowid,))
        conn.execute(
            """
INSERT INTO endpoints_fts (
  rowid, endpoint_id, exchange, section, method, path, search_text
) VALUES (?, ?, ?, ?, ?, ?, ?);
""",
            (
                endpoint_rowid,
                computed_id,
                exchange,
                section,
                method or "",
                path or "",
                search_text,
            ),
        )

    return {"endpoint_id": computed_id, "path": str(endpoint_path), "updated_at": updated_at}


def get_endpoint(
    *,
    docs_dir: str,
    endpoint_id: str,
) -> dict[str, Any]:
    """Return the full parsed JSON blob for a single endpoint by ID."""
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        row = conn.execute(
            "SELECT json, docs_url FROM endpoints WHERE endpoint_id = ?;",
            (endpoint_id,),
        ).fetchone()
        if row is None:
            raise CexApiDocsError(
                code="ENOTFOUND",
                message="Endpoint not found.",
                details={"endpoint_id": endpoint_id},
            )
        record = json.loads(row["json"])
        if row["docs_url"]:
            record["docs_url"] = row["docs_url"]
        return record
    finally:
        conn.close()


def list_endpoints(
    *,
    docs_dir: str,
    exchange: str | None = None,
    section: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return endpoint summaries filtered by exchange/section."""
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        where: list[str] = []
        params: list[Any] = []
        if exchange:
            where.append("exchange = ?")
            params.append(exchange)
        if section:
            where.append("section = ?")
            params.append(section)
        params.append(int(limit))

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
SELECT endpoint_id, exchange, section, protocol, method, path, base_url, description, json, updated_at
FROM endpoints
{where_clause}
ORDER BY exchange, section, method, path
LIMIT ?;
"""
        cur = conn.execute(sql, tuple(params))
        out: list[dict[str, Any]] = []
        for r in cur.fetchall():
            record = json.loads(r["json"])
            field_status = record.get("field_status", {})
            out.append({
                "endpoint_id": r["endpoint_id"],
                "exchange": r["exchange"],
                "section": r["section"],
                "protocol": r["protocol"],
                "method": r["method"],
                "path": r["path"],
                "base_url": r["base_url"],
                "description": r["description"],
                "field_status": field_status,
                "updated_at": r["updated_at"],
            })
        return out
    finally:
        conn.close()


def search_endpoints(
    *,
    docs_dir: str,
    query: str,
    exchange: str | None = None,
    section: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        where = ["endpoints_fts MATCH ?"]
        params: list[Any] = [query]
        if exchange:
            where.append("endpoints_fts.exchange = ?")
            params.append(exchange)
        if section:
            where.append("endpoints_fts.section = ?")
            params.append(section)
        params.append(int(limit))

        sql = f"""
SELECT
  endpoints_fts.endpoint_id,
  endpoints_fts.exchange,
  endpoints_fts.section,
  endpoints_fts.method,
  endpoints_fts.path,
  snippet(endpoints_fts, 5, '[', ']', '...', 12) AS snippet,
  bm25(endpoints_fts) AS rank
FROM endpoints_fts
WHERE {' AND '.join(where)}
ORDER BY rank
LIMIT ?;
"""
        try:
            cur = conn.execute(sql, tuple(params))
        except sqlite3.OperationalError as e:
            # FTS5 query syntax is picky; users often paste paths like "/api/v3/time".
            # Retry with a sanitized token query (best-effort).
            msg = str(e)
            if "fts5" not in msg.lower() or "syntax error" not in msg.lower():
                raise
            sanitized = " ".join(re.findall(r"[A-Za-z0-9_]+", query))
            if not sanitized:
                raise
            params[0] = sanitized
            cur = conn.execute(sql, tuple(params))
        out: list[dict[str, Any]] = []
        for r in cur.fetchall():
            out.append(
                {
                    "endpoint_id": r["endpoint_id"],
                    "exchange": r["exchange"],
                    "section": r["section"],
                    "method": r["method"],
                    "path": r["path"],
                    "snippet": r["snippet"],
                    "rank": r["rank"],
                }
            )
        return out
    finally:
        conn.close()


def review_list(*, docs_dir: str, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        cur = conn.execute(
            """
SELECT id, kind, endpoint_id, field_name, reason, status, created_at, resolved_at
FROM review_queue
WHERE status = ?
ORDER BY created_at DESC
LIMIT ?;
""",
            (status, int(limit)),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def review_show(*, docs_dir: str, review_id: int) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        row = conn.execute("SELECT * FROM review_queue WHERE id = ?;", (int(review_id),)).fetchone()
        if row is None:
            raise CexApiDocsError(code="ENOTFOUND", message="Review item not found.", details={"id": review_id})
        return dict(row)
    finally:
        conn.close()


def review_resolve(*, docs_dir: str, lock_timeout_s: float, review_id: int, resolution: str | None = None) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"
    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn = open_db(db_path)
        try:
            resolved_at = now_iso_utc()
            with conn:
                row = conn.execute("SELECT id, details_json FROM review_queue WHERE id = ?;", (int(review_id),)).fetchone()
                if row is None:
                    raise CexApiDocsError(code="ENOTFOUND", message="Review item not found.", details={"id": review_id})
                details = {}
                if row["details_json"]:
                    try:
                        details = json.loads(row["details_json"])
                    except Exception:
                        details = {"_raw": row["details_json"]}
                if resolution:
                    details["resolution"] = resolution
                    details["resolved_at"] = resolved_at
                conn.execute(
                    """
UPDATE review_queue
SET status = 'resolved', resolved_at = ?, details_json = ?
WHERE id = ?;
""",
                    (resolved_at, json.dumps(details, sort_keys=True, ensure_ascii=False), int(review_id)),
                )
            conn.commit()
            return {"id": int(review_id), "resolved_at": resolved_at, "resolution": resolution}
        finally:
            conn.close()
