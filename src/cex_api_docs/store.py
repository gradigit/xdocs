from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import SCHEMA_USER_VERSION, DbInitResult, apply_schema, init_db, open_db
from .errors import CexApiDocsError
from .lock import acquire_write_lock


STORE_DIRS = [
    "db",
    "raw",
    "pages",
    "meta",
    "endpoints",
    "review",
]


@dataclass(frozen=True, slots=True)
class StorePaths:
    root: Path
    db_path: Path
    lock_path: Path
    crawl_log_path: Path
    review_queue_path: Path


def require_store_db(docs_dir: str) -> Path:
    """Return the DB path, raising ENOINIT if the store hasn't been initialized."""
    db_path = Path(docs_dir) / "db" / "docs.db"
    if not db_path.exists():
        raise CexApiDocsError(
            code="ENOINIT",
            message="Store not initialized. Run `cex-api-docs init` first.",
            details={"docs_dir": docs_dir},
        )
    return db_path


def ensure_store_schema(*, docs_dir: str, lock_timeout_s: float) -> dict[str, Any]:
    """
    Ensure an initialized store DB is migrated to the current schema version.

    This is safe to call before normal operations; it performs a cheap user_version
    check and only acquires the write lock when an upgrade is needed.
    """
    db_path = require_store_db(docs_dir)

    conn = open_db(db_path)
    try:
        row = conn.execute("PRAGMA user_version;").fetchone()
        assert row is not None
        current = int(row[0])
    finally:
        conn.close()

    if current >= SCHEMA_USER_VERSION:
        return {
            "db_path": str(db_path),
            "schema_user_version_before": current,
            "schema_user_version_after": current,
            "upgraded": False,
        }

    lock_path = Path(docs_dir) / "db" / ".write.lock"
    schema_sql_path = Path(__file__).resolve().parents[2] / "schema" / "schema.sql"

    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn2 = open_db(db_path)
        try:
            row2 = conn2.execute("PRAGMA user_version;").fetchone()
            assert row2 is not None
            before = int(row2[0])
            after = apply_schema(conn2, schema_sql_path=schema_sql_path, expected_user_version=SCHEMA_USER_VERSION)
            conn2.commit()
        finally:
            conn2.close()

    return {
        "db_path": str(db_path),
        "schema_user_version_before": before,
        "schema_user_version_after": after,
        "upgraded": bool(after > before),
    }


def get_store_schema_status(*, docs_dir: str) -> dict[str, Any]:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        row = conn.execute("PRAGMA user_version;").fetchone()
        assert row is not None
        current = int(row[0])
    finally:
        conn.close()

    return {
        "db_path": str(db_path),
        "schema_user_version": current,
        "target_schema_user_version": int(SCHEMA_USER_VERSION),
        "upgrade_required": bool(current < SCHEMA_USER_VERSION),
    }


def migrate_store_schema(*, docs_dir: str, lock_timeout_s: float, dry_run: bool = True) -> dict[str, Any]:
    status = get_store_schema_status(docs_dir=docs_dir)
    if dry_run:
        return {"dry_run": True, **status}

    mig = ensure_store_schema(docs_dir=docs_dir, lock_timeout_s=lock_timeout_s)
    after = get_store_schema_status(docs_dir=docs_dir)
    return {
        "dry_run": False,
        **after,
        "schema_user_version_before": mig["schema_user_version_before"],
        "schema_user_version_after": mig["schema_user_version_after"],
        "upgraded": mig["upgraded"],
    }


def resolve_store_paths(docs_dir: str) -> StorePaths:
    root = Path(docs_dir)
    return StorePaths(
        root=root,
        db_path=root / "db" / "docs.db",
        lock_path=root / "db" / ".write.lock",
        crawl_log_path=root / "crawl-log.jsonl",
        review_queue_path=root / "review" / "queue.jsonl",
    )


def _ensure_dirs(root: Path) -> dict[str, Any]:
    created: list[str] = []
    existed: list[str] = []
    for d in STORE_DIRS:
        p = root / d
        if p.exists():
            existed.append(str(p))
        else:
            p.mkdir(parents=True, exist_ok=True)
            created.append(str(p))
    return {"created": created, "existed": existed}


def _ensure_file(path: Path) -> dict[str, Any]:
    if path.exists():
        return {"path": str(path), "created": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return {"path": str(path), "created": True}


def init_store(
    *,
    docs_dir: str,
    schema_sql_path: Path,
    lock_timeout_s: float,
) -> dict[str, Any]:
    paths = resolve_store_paths(docs_dir)

    dirs_info = _ensure_dirs(paths.root)
    crawl_log_info = _ensure_file(paths.crawl_log_path)
    review_queue_info = _ensure_file(paths.review_queue_path)

    with acquire_write_lock(paths.lock_path, timeout_s=lock_timeout_s) as lock:
        db_result: DbInitResult = init_db(paths.db_path, schema_sql_path=schema_sql_path)

    return {
        "cmd": "init",
        "docs_dir": str(paths.root),
        "lock": {"path": str(lock.path), "timeout_s": lock_timeout_s},
        "dirs": dirs_info,
        "files": {
            "crawl_log": crawl_log_info,
            "review_queue": review_queue_info,
        },
        "db": {
            "path": str(db_result.db_path),
            "schema_user_version": db_result.schema_user_version,
            "fts5_available": db_result.fts5_available,
        },
    }
