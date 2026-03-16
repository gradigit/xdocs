#!/usr/bin/env bash
# Periodic CCXT docs refresh.
#
# Usage:
#   bash scripts/refresh_ccxt_docs.sh [docs-dir]
#
# Steps:
# 1. Re-sync CCXT exchange (--force-refetch detects content changes via content_hash/prev_content_hash)
# 2. Report changed pages
# 3. Run ccxt-xref for validation
# 4. Run check-links on CCXT pages (sample 50)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DOCS_DIR="${1:-./cex-docs}"
PY="${CEX_API_DOCS_PYTHON:-.venv/bin/python}"

if [[ ! -x "$PY" ]]; then
  echo "Missing python executable: $PY" >&2
  exit 1
fi

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"

echo "[1/4] Re-syncing CCXT docs (force-refetch)..."
"$PY" -m xdocs.cli sync --exchange ccxt --force-refetch --docs-dir "$DOCS_DIR" 2>&1 | tee /tmp/ccxt_sync.json
echo ""

echo "[2/4] Checking for changed pages..."
"$PY" -c "
import json, sys
try:
    data = json.load(open('/tmp/ccxt_sync.json'))
    t = data.get('result', {}).get('totals', {})
    fetched = t.get('fetched', 0)
    updated = t.get('updated_pages', 0)
    unchanged = t.get('unchanged_pages', 0)
    new_p = t.get('new_pages', 0)
    print(f'  fetched={fetched}  updated={updated}  new={new_p}  unchanged={unchanged}')
except Exception as e:
    print(f'  Could not parse sync output: {e}', file=sys.stderr)
"
echo ""

echo "[3/4] Running CCXT cross-reference (requires pip install ccxt)..."
"$PY" -m xdocs.cli ccxt-xref --docs-dir "$DOCS_DIR" 2>&1 | head -50
echo ""

echo "[4/4] Checking CCXT page link reachability (sample 50)..."
"$PY" -m xdocs.cli check-links \
  --docs-dir "$DOCS_DIR" \
  --exchange ccxt \
  --sample 50 \
  --concurrency 4 \
  --delay-s 0.30 2>&1 | tail -20
echo ""

echo "CCXT refresh complete."
