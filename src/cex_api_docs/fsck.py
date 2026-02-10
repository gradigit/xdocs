from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .db import open_db
from .errors import CexApiDocsError


def _require_store_db(docs_dir: str) -> Path:
    db_path = Path(docs_dir) / "db" / "docs.db"
    if not db_path.exists():
        raise CexApiDocsError(code="ENOINIT", message="Store not initialized. Run `cex-api-docs init` first.", details={"docs_dir": docs_dir})
    return db_path


def _iter_files(root: Path, *, suffix: str) -> Iterable[Path]:
    if not root.exists():
        return []
    return root.rglob(f"*{suffix}")


def fsck_store(*, docs_dir: str, limit: int = 200, scan_orphans: bool = False) -> dict[str, Any]:
    """
    Detect (and optionally report) inconsistencies between the SQLite DB and on-disk artifacts.

    v1 behavior is detection-only: it does not delete or rewrite data by default.
    """

    db_path = _require_store_db(docs_dir)
    root = Path(docs_dir)

    issues: list[dict[str, Any]] = []

    conn = open_db(db_path)
    try:
        # 1) DB rows pointing at missing files.
        pages = conn.execute("SELECT canonical_url, raw_path, markdown_path, meta_path FROM pages;").fetchall()
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

        endpoints = conn.execute("SELECT endpoint_id, exchange, section FROM endpoints;").fetchall()
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

        return {
            "cmd": "fsck",
            "docs_dir": str(root),
            "scan_orphans": bool(scan_orphans),
            "limit": int(limit),
            "counts": {
                "issues": len(issues),
                "pages": len(pages),
                "endpoints": len(endpoints),
            },
            "issues": issues,
        }
    finally:
        conn.close()
