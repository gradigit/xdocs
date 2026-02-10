from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import DbInitResult, init_db
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
