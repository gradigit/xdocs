#!/usr/bin/env bash
# Stored page URL reachability check.
#
# Runs check-links against the store and reports dead/redirected URLs.
# Use --sample N to limit scope (default: all pages).
#
# Usage:
#   bash scripts/check_links.sh [docs-dir] [--exchange X] [--sample N] [extra args...]
#
# Examples:
#   bash scripts/check_links.sh ./cex-docs
#   bash scripts/check_links.sh ./cex-docs --exchange binance --sample 100
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DOCS_DIR="${1:-./cex-docs}"
if [[ $# -ge 1 && "${1:0:1}" != "-" ]]; then
  shift
fi

PY="${CEX_API_DOCS_PYTHON:-.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "Missing python executable: $PY" >&2
  exit 1
fi

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"

echo "[check-links] Running URL reachability check (concurrency=4, delay=0.3s)..."
"$PY" -m xdocs.cli check-links \
  --docs-dir "$DOCS_DIR" \
  --concurrency 4 \
  --delay-s 0.30 \
  "$@" 2>&1 | tee /tmp/check_links_result.json

echo ""

# Summarise dead and redirect counts from JSON output.
"$PY" -c "
import json, sys
try:
    data = json.load(open('/tmp/check_links_result.json'))
    r = data.get('result', data)
    total = r.get('total', 0)
    dead = r.get('dead', 0)
    redirected = r.get('redirected', 0)
    ok = r.get('ok', 0)
    errors = r.get('errors', 0)
    print(f'  Total checked : {total}')
    print(f'  OK            : {ok}')
    print(f'  Redirected    : {redirected}')
    print(f'  Dead (4xx/5xx): {dead}')
    print(f'  Errors        : {errors}')
    if dead > 0:
        dead_urls = r.get('dead_urls', [])
        if dead_urls:
            print(f'  Dead URLs (first 10):')
            for u in dead_urls[:10]:
                print(f'    {u}')
except Exception as e:
    print(f'  Could not parse result: {e}', file=sys.stderr)
"
echo ""
echo "check-links complete."
