from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import CexApiDocsError


SCHEMA_USER_VERSION = 4


def _migrate_2_to_3(conn: sqlite3.Connection) -> None:
    """Add docs_url column to endpoints table (idempotent)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(endpoints);").fetchall()}
    if "docs_url" not in cols:
        conn.execute("ALTER TABLE endpoints ADD COLUMN docs_url TEXT;")


# Migrations: dict mapping (from_version -> to_version) to steps.
# Each step is either a SQL string (run via executescript) or a callable(conn).
MIGRATIONS: dict[tuple[int, int], list[str | Callable[[sqlite3.Connection], None]]] = {
    (1, 2): [
        """
ALTER TABLE inventory_entries ADD COLUMN last_etag TEXT;
""",
        """
ALTER TABLE inventory_entries ADD COLUMN last_last_modified TEXT;
""",
        """
ALTER TABLE inventory_entries ADD COLUMN last_cache_control TEXT;
""",
        """
CREATE TABLE IF NOT EXISTS inventory_scope_ownership (
  scope_group TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  owner_exchange_id TEXT NOT NULL,
  owner_section_id TEXT NOT NULL,
  owner_inventory_id INTEGER NOT NULL REFERENCES inventories(id),
  owner_priority INTEGER NOT NULL DEFAULT 100,
  owned_at TEXT NOT NULL,
  PRIMARY KEY (scope_group, canonical_url)
);
""",
        """
CREATE INDEX IF NOT EXISTS inventory_scope_ownership_owner_idx
ON inventory_scope_ownership(owner_exchange_id, owner_section_id, owner_priority);
""",
    ],
    (2, 3): [_migrate_2_to_3],
    (3, 4): [
        """
CREATE TABLE IF NOT EXISTS changelog_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exchange_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  entry_date TEXT,
  entry_text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  extracted_at TEXT NOT NULL,
  UNIQUE(source_url, content_hash)
);
""",
        """
CREATE INDEX IF NOT EXISTS changelog_entries_exchange_section_idx
  ON changelog_entries(exchange_id, section_id);
""",
        """
CREATE INDEX IF NOT EXISTS changelog_entries_date_idx
  ON changelog_entries(entry_date);
""",
        """
CREATE VIRTUAL TABLE IF NOT EXISTS changelog_entries_fts
  USING fts5(exchange_id, section_id, entry_date, entry_text, content=changelog_entries, content_rowid=id);
""",
    ],
}


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

    Supports forward migration: if the DB is at an older version, applies
    registered migrations sequentially to reach expected_user_version.
    """
    current = _get_user_version(conn)
    if current > expected_user_version:
        raise CexApiDocsError(
            code="ESCHEMAVER",
            message="Database schema is newer than this code supports.",
            details={"current_user_version": current, "expected_user_version": expected_user_version},
        )

    # Apply the base schema (all CREATE IF NOT EXISTS, safe to re-run).
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
        # Fresh database — set to expected version directly.
        _set_user_version(conn, expected_user_version)
    elif current < expected_user_version:
        # Apply migrations sequentially from current to expected.
        v = current
        while v < expected_user_version:
            key = (v, v + 1)
            if key not in MIGRATIONS:
                raise CexApiDocsError(
                    code="ESCHEMAVER",
                    message=f"No migration path from schema v{v} to v{v + 1}.",
                    details={"current_user_version": v, "expected_user_version": expected_user_version},
                )
            for step in MIGRATIONS[key]:
                try:
                    if callable(step):
                        step(conn)
                    else:
                        conn.executescript(step)
                except sqlite3.OperationalError as e:
                    raise CexApiDocsError(
                        code="ESCHEMA",
                        message=f"Migration v{v}->v{v + 1} failed.",
                        details={"sqlite_error": str(e), "migration": key},
                    ) from e
            v += 1
            _set_user_version(conn, v)

    return _get_user_version(conn)


def init_db(db_path: Path, schema_sql_path: Path) -> DbInitResult:
    conn = open_db(db_path)
    try:
        _check_fts5(conn)
        user_version = apply_schema(conn, schema_sql_path=schema_sql_path, expected_user_version=SCHEMA_USER_VERSION)
        conn.commit()
        return DbInitResult(db_path=db_path, schema_user_version=user_version, fts5_available=True)
    finally:
        conn.close()
