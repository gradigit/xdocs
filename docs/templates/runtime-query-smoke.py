#!/usr/bin/env python3
"""Runtime smoke test — validates a cex-api-docs data snapshot is usable.

Usage:
    python scripts/runtime_query_smoke.py [DOCS_DIR]

Defaults to ./cex-docs if DOCS_DIR is not provided.
Uses only Python stdlib (sqlite3) — no extra dependencies.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main() -> int:
    docs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./cex-docs")
    db_path = docs_dir / "db" / "docs.db"

    print("=== Runtime Smoke Test ===")

    # 1. DB exists and is reasonable size
    if not db_path.exists():
        print(f"FAIL: DB not found at {db_path}")
        print("  Run ./scripts/bootstrap-data.sh to download the data snapshot.")
        return 1
    db_size = db_path.stat().st_size
    print(f"DB size: {db_size} bytes")
    if db_size < 100_000_000:
        print("FAIL: DB too small (<100MB)")
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        # 2. Schema version
        schema_ver = conn.execute("PRAGMA user_version;").fetchone()[0]
        print(f"Schema version: {schema_ver}")
        if schema_ver < 6:
            print(f"FAIL: Schema version {schema_ver} < 6")
            return 1

        # 3. Page count
        page_count = conn.execute("SELECT count(*) FROM pages;").fetchone()[0]
        print(f"Pages: {page_count}")
        if page_count < 10000:
            print(f"FAIL: Page count {page_count} < 10000")
            return 1

        # 4. Endpoint count
        ep_count = conn.execute("SELECT count(*) FROM endpoints;").fetchone()[0]
        print(f"Endpoints: {ep_count}")
        if ep_count < 4500:
            print(f"FAIL: Endpoint count {ep_count} < 4500")
            return 1

        # 5. FTS5 functional
        fts_count = conn.execute(
            "SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'rate limit';"
        ).fetchone()[0]
        print(f"FTS5 test ('rate limit'): {fts_count} matches")
        if fts_count < 1:
            print("FAIL: FTS5 returned 0 results")
            return 1

        # 6. Maintenance tables stripped (if applicable)
        try:
            inv_count = conn.execute("SELECT count(*) FROM inventories;").fetchone()[0]
            print(f"Inventories rows: {inv_count}")
        except sqlite3.OperationalError:
            print("Inventories rows: N/A")

        # 7. Quick integrity check
        integrity = conn.execute("PRAGMA quick_check;").fetchone()[0]
        print(f"Integrity: {integrity}")
        if integrity != "ok":
            print("FAIL: Integrity check failed")
            return 1

    finally:
        conn.close()

    print("=== All checks passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
