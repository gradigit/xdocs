from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import CexApiDocsError


SCHEMA_USER_VERSION_V1 = 1


@dataclass(frozen=True, slots=True)
class DbInitResult:
    db_path: Path
    schema_user_version: int
    fts5_available: bool


def open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # WAL helps concurrent readers; still single-writer at the app level.
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _check_fts5(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __fts5_check USING fts5(content);")
        conn.execute("DROP TABLE IF EXISTS __fts5_check;")
    except sqlite3.OperationalError as e:
        raise CexApiDocsError(
            code="EFTS5",
            message="SQLite FTS5 is required but not available in this build.",
            details={"sqlite_error": str(e)},
        ) from e


def _get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version;").fetchone()
    assert row is not None
    return int(row[0])


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)};")


def apply_schema(conn: sqlite3.Connection, schema_sql_path: Path, expected_user_version: int) -> int:
    """
    Apply authoritative schema idempotently and set/verify PRAGMA user_version.
    """
    current = _get_user_version(conn)
    if current not in (0, expected_user_version):
        raise CexApiDocsError(
            code="ESCHEMAVER",
            message="Unsupported docs.db schema version.",
            details={"current_user_version": current, "expected_user_version": expected_user_version},
        )

    schema_sql = schema_sql_path.read_text(encoding="utf-8")
    try:
        conn.executescript(schema_sql)
    except sqlite3.OperationalError as e:
        raise CexApiDocsError(
            code="ESCHEMA",
            message="Failed applying schema/schema.sql to SQLite database.",
            details={"sqlite_error": str(e), "schema_sql_path": str(schema_sql_path)},
        ) from e

    if current == 0:
        _set_user_version(conn, expected_user_version)

    return _get_user_version(conn)


def init_db(db_path: Path, schema_sql_path: Path) -> DbInitResult:
    conn = open_db(db_path)
    try:
        _check_fts5(conn)
        user_version = apply_schema(conn, schema_sql_path=schema_sql_path, expected_user_version=SCHEMA_USER_VERSION_V1)
        conn.commit()
        return DbInitResult(db_path=db_path, schema_user_version=user_version, fts5_available=True)
    finally:
        conn.close()

