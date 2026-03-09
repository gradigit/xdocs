#!/usr/bin/env bash
set -euo pipefail

DOCS_DIR="${1:-./cex-docs}"
DB="$DOCS_DIR/db/docs.db"

echo "=== Runtime Smoke Test ==="

# 1. DB exists and is reasonable size
if [ ! -f "$DB" ]; then
    echo "FAIL: DB not found at $DB"
    exit 1
fi
DB_SIZE=$(stat -f%z "$DB" 2>/dev/null || stat -c%s "$DB")
echo "DB size: $DB_SIZE bytes"
if [ "$DB_SIZE" -lt 100000000 ]; then
    echo "FAIL: DB too small (<100MB)"
    exit 1
fi

# 2. Schema version
SCHEMA_VER=$(sqlite3 "$DB" "PRAGMA user_version;")
echo "Schema version: $SCHEMA_VER"
if [ "$SCHEMA_VER" -lt 6 ]; then
    echo "FAIL: Schema version $SCHEMA_VER < 6"
    exit 1
fi

# 3. Page count
PAGE_COUNT=$(sqlite3 "$DB" "SELECT count(*) FROM pages;")
echo "Pages: $PAGE_COUNT"
if [ "$PAGE_COUNT" -lt 10000 ]; then
    echo "FAIL: Page count $PAGE_COUNT < 10000"
    exit 1
fi

# 4. Endpoint count
EP_COUNT=$(sqlite3 "$DB" "SELECT count(*) FROM endpoints;")
echo "Endpoints: $EP_COUNT"
if [ "$EP_COUNT" -lt 4500 ]; then
    echo "FAIL: Endpoint count $EP_COUNT < 4500"
    exit 1
fi

# 5. FTS5 functional
FTS_COUNT=$(sqlite3 "$DB" "SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'rate limit';")
echo "FTS5 test ('rate limit'): $FTS_COUNT matches"
if [ "$FTS_COUNT" -lt 1 ]; then
    echo "FAIL: FTS5 returned 0 results"
    exit 1
fi

# 6. Maintenance tables stripped (if applicable)
INV_COUNT=$(sqlite3 "$DB" "SELECT count(*) FROM inventories;" 2>/dev/null || echo "N/A")
echo "Inventories rows: $INV_COUNT"

# 7. Quick integrity check
INTEGRITY=$(sqlite3 "$DB" "PRAGMA quick_check;")
echo "Integrity: $INTEGRITY"
if [ "$INTEGRITY" != "ok" ]; then
    echo "FAIL: Integrity check failed"
    exit 1
fi

echo "=== All checks passed ==="
