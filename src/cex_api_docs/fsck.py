from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .db import open_db
from .hashing import sha256_hex_text
from .store import require_store_db


def _iter_files(root: Path, *, suffix: str) -> Iterable[Path]:
    if not root.exists():
        return []
    return root.rglob(f"*{suffix}")


def fsck_store(
    *,
    docs_dir: str,
    limit: int = 200,
    scan_orphans: bool = False,
    verify_hashes: bool = False,
    verify_fts: bool = False,
    verify_endpoint_json: bool = False,
) -> dict[str, Any]:
    """
    Detect (and optionally report) inconsistencies between the SQLite DB and on-disk artifacts.

    v1 behavior is detection-only: it does not delete or rewrite data by default.
    """

    db_path = require_store_db(docs_dir)
    root = Path(docs_dir)

    issues: list[dict[str, Any]] = []

    conn = open_db(db_path)
    try:
        # 1) DB rows pointing at missing files.
        pages = conn.execute(
            "SELECT canonical_url, raw_path, markdown_path, meta_path, content_hash FROM pages;"
        ).fetchall()
        for r in pages:
            canonical_url = str(r["canonical_url"])
            for field in ("raw_path", "meta_path"):
                p = r[field]
                if not p:
                    issues.append({"kind": "page_missing_path", "canonical_url": canonical_url, "field": field})
                    continue
                if not Path(str(p)).exists():
                    issues.append({"kind": "page_missing_file", "canonical_url": canonical_url, "field": field, "path": str(p)})
                    if len(issues) >= limit:
                        break
            if len(issues) >= limit:
                break

            mdp = r["markdown_path"]
            if mdp and not Path(str(mdp)).exists():
                issues.append({"kind": "page_missing_file", "canonical_url": canonical_url, "field": "markdown_path", "path": str(mdp)})
                if len(issues) >= limit:
                    break

        endpoints = conn.execute("SELECT endpoint_id, exchange, section, json FROM endpoints;").fetchall()
        if len(issues) < limit:
            for r in endpoints:
                endpoint_id = str(r["endpoint_id"])
                exchange = str(r["exchange"])
                section = str(r["section"])
                expected = root / "endpoints" / exchange / section / f"{endpoint_id}.json"
                if not expected.exists():
                    issues.append(
                        {
                            "kind": "endpoint_missing_file",
                            "endpoint_id": endpoint_id,
                            "exchange": exchange,
                            "section": section,
                            "path": str(expected),
                        }
                    )
                    if len(issues) >= limit:
                        break

        # 2) Orphan files (optional; can be expensive on large stores).
        orphan_files: list[dict[str, Any]] = []
        if scan_orphans and len(issues) < limit:
            referenced: set[str] = set()
            for r in pages:
                for field in ("raw_path", "markdown_path", "meta_path"):
                    p = r[field]
                    if p:
                        referenced.add(str(p))

            for r in endpoints:
                endpoint_id = str(r["endpoint_id"])
                exchange = str(r["exchange"])
                section = str(r["section"])
                referenced.add(str(root / "endpoints" / exchange / section / f"{endpoint_id}.json"))

            for base, suffix in ((root / "raw", ".bin"), (root / "pages", ".md"), (root / "meta", ".json")):
                for p in _iter_files(base, suffix=suffix):
                    sp = str(p)
                    if sp not in referenced:
                        orphan_files.append({"kind": "orphan_file", "path": sp})
                        if len(orphan_files) + len(issues) >= limit:
                            break
                if len(orphan_files) + len(issues) >= limit:
                    break

            issues.extend(orphan_files[: max(0, limit - len(issues))])

        # 3) Content hash re-verification (optional; reads every markdown file).
        hash_checked = 0
        hash_mismatches = 0
        hash_missing_file = 0
        if verify_hashes and len(issues) < limit:
            for r in pages:
                if len(issues) >= limit:
                    break
                md_path_str = r["markdown_path"]
                content_hash_db = r["content_hash"]
                canonical_url = str(r["canonical_url"])

                if not md_path_str:
                    continue

                md_path = Path(str(md_path_str))
                if not md_path.exists():
                    hash_missing_file += 1
                    continue

                hash_checked += 1
                md_text = md_path.read_text(encoding="utf-8", errors="replace")
                computed_hash = sha256_hex_text(md_text)

                if content_hash_db and computed_hash != content_hash_db:
                    issues.append({
                        "kind": "content_hash_mismatch",
                        "canonical_url": canonical_url,
                        "db_hash": content_hash_db,
                        "file_hash": computed_hash,
                        "markdown_path": str(md_path),
                    })
                    hash_mismatches += 1

        # 4) FTS5 consistency check (optional).
        fts_verification: dict[str, Any] = {}
        if verify_fts and len(issues) < limit:
            pages_with_md_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM pages WHERE markdown_path IS NOT NULL;"
            ).fetchone()["cnt"]
            fts_page_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM pages_fts;"
            ).fetchone()["cnt"]

            if fts_page_count != pages_with_md_count:
                issues.append({
                    "kind": "fts_row_count_mismatch",
                    "table": "pages_fts",
                    "expected": pages_with_md_count,
                    "actual": fts_page_count,
                })

            orphan_fts_pages = conn.execute(
                "SELECT COUNT(*) AS cnt FROM pages_fts WHERE rowid NOT IN (SELECT id FROM pages);"
            ).fetchone()["cnt"]
            if orphan_fts_pages > 0:
                issues.append({
                    "kind": "fts_orphan_entries",
                    "table": "pages_fts",
                    "count": orphan_fts_pages,
                })

            missing_fts_pages = conn.execute(
                """SELECT COUNT(*) AS cnt FROM pages
                   WHERE markdown_path IS NOT NULL
                   AND id NOT IN (SELECT rowid FROM pages_fts);"""
            ).fetchone()["cnt"]
            if missing_fts_pages > 0:
                issues.append({
                    "kind": "fts_missing_entries",
                    "table": "pages_fts",
                    "count": missing_fts_pages,
                })

            endpoint_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM endpoints;"
            ).fetchone()["cnt"]
            fts_endpoint_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM endpoints_fts;"
            ).fetchone()["cnt"]

            if fts_endpoint_count != endpoint_count:
                issues.append({
                    "kind": "fts_row_count_mismatch",
                    "table": "endpoints_fts",
                    "expected": endpoint_count,
                    "actual": fts_endpoint_count,
                })

            orphan_fts_endpoints = conn.execute(
                "SELECT COUNT(*) AS cnt FROM endpoints_fts WHERE rowid NOT IN (SELECT rowid FROM endpoints);"
            ).fetchone()["cnt"]
            if orphan_fts_endpoints > 0:
                issues.append({
                    "kind": "fts_orphan_entries",
                    "table": "endpoints_fts",
                    "count": orphan_fts_endpoints,
                })

            fts_verification = {
                "pages_fts_count": fts_page_count,
                "pages_with_markdown": pages_with_md_count,
                "pages_fts_orphans": orphan_fts_pages,
                "pages_fts_missing": missing_fts_pages,
                "endpoints_fts_count": fts_endpoint_count,
                "endpoints_count": endpoint_count,
                "endpoints_fts_orphans": orphan_fts_endpoints,
            }

        # 5) Endpoint JSON on-disk vs DB consistency (optional).
        ej_checked = 0
        ej_mismatches = 0
        if verify_endpoint_json and len(issues) < limit:
            for r in endpoints:
                if len(issues) >= limit:
                    break
                eid = str(r["endpoint_id"])
                exchange = str(r["exchange"])
                section = str(r["section"])
                db_json_str = str(r["json"])

                file_path = root / "endpoints" / exchange / section / f"{eid}.json"
                if not file_path.exists():
                    continue  # Already reported as endpoint_missing_file

                ej_checked += 1
                try:
                    file_record = json.loads(file_path.read_text(encoding="utf-8"))
                    file_json_str = json.dumps(file_record, sort_keys=True, ensure_ascii=False)
                except (json.JSONDecodeError, OSError) as e:
                    issues.append({
                        "kind": "endpoint_json_unreadable",
                        "endpoint_id": eid,
                        "exchange": exchange,
                        "section": section,
                        "path": str(file_path),
                        "error": str(e),
                    })
                    continue

                if file_json_str != db_json_str:
                    issues.append({
                        "kind": "endpoint_json_mismatch",
                        "endpoint_id": eid,
                        "exchange": exchange,
                        "section": section,
                        "path": str(file_path),
                    })
                    ej_mismatches += 1

        result: dict[str, Any] = {
            "cmd": "fsck",
            "docs_dir": str(root),
            "scan_orphans": bool(scan_orphans),
            "verify_hashes": bool(verify_hashes),
            "verify_fts": bool(verify_fts),
            "verify_endpoint_json": bool(verify_endpoint_json),
            "limit": int(limit),
            "counts": {
                "issues": len(issues),
                "pages": len(pages),
                "endpoints": len(endpoints),
            },
            "issues": issues,
        }

        if verify_hashes:
            result["hash_verification"] = {
                "checked": hash_checked,
                "mismatches": hash_mismatches,
                "missing_file": hash_missing_file,
            }
        if verify_fts:
            result["fts_verification"] = fts_verification
        if verify_endpoint_json:
            result["endpoint_json_verification"] = {
                "checked": ej_checked,
                "mismatches": ej_mismatches,
            }

        return result
    finally:
        conn.close()
