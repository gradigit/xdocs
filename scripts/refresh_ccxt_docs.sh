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

echo "[1/3] Re-syncing CCXT docs (force-refetch)..."
"$PY" -m cex_api_docs.cli sync --exchange ccxt --force-refetch --docs-dir "$DOCS_DIR" 2>&1 | tee /tmp/ccxt_sync.json
echo ""

echo "[2/3] Checking for changed pages..."
"$PY" -c "
import json, sys
try:
    data = json.load(open('/tmp/ccxt_sync.json'))
    sections = data.get('result', {}).get('sections', [])
    for s in sections:
        fetched = s.get('fetch_result', {})
        changed = fetched.get('changed', 0)
        total = fetched.get('total', 0)
        print(f\"  {s.get('exchange_id', '?')}/{s.get('section_id', '?')}: {changed}/{total} pages changed\")
except Exception as e:
    print(f'  Could not parse sync output: {e}', file=sys.stderr)
"
echo ""

echo "[3/3] Running CCXT cross-reference..."
"$PY" -m cex_api_docs.cli ccxt-xref --docs-dir "$DOCS_DIR" 2>&1 | head -50
echo ""

echo "CCXT refresh complete."
