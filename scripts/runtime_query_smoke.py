"""Smoke test — validates an xdocs data snapshot is usable."""
import sqlite3, sys
from pathlib import Path

def main():
    db = Path(__import__("xdocs").__file__).resolve().parents[2] / "cex-docs/db/docs.db"
    if not db.exists():
        print(f"FAIL: {db} not found"); return 1
    conn = sqlite3.connect(str(db))
    pages = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
    eps = conn.execute("SELECT count(*) FROM endpoints").fetchone()[0]
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    fts = conn.execute("SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'rate'").fetchone()[0]
    print(f"Pages: {pages}, Endpoints: {eps}, Schema: v{ver}, FTS5: {'ok' if fts > 0 else 'EMPTY'}")
    ok = pages > 10000 and eps > 4500 and ver >= 6 and fts > 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
