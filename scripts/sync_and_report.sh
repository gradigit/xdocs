#!/usr/bin/env bash
set -euo pipefail

# Cron-friendly runner for macOS (launchd/cron).
#
# Outputs timestamped artifacts under the local store (default: ./cex-docs/reports/):
# - sync JSON (machine-readable, stable)
# - sync Markdown (human-readable)
# - quality JSON
# - changelog JSON (new entries since last run signal API changes)
#
# Usage:
#   scripts/sync_and_report.sh
#   scripts/sync_and_report.sh ./cex-docs
#
# Notes:
# - Exits non-zero only on command failure.
# - Missing/undocumented endpoint fields are not treated as failures (handled at the reporting/review layer).
# - Semantic index build requires [semantic] extras. Skipped silently if unavailable.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STORE_DIR="${1:-$ROOT_DIR/cex-docs}"
REPORT_DIR="$STORE_DIR/reports"
CLI="${CEX_API_DOCS_CLI:-.venv/bin/cex-api-docs}"

mkdir -p "$REPORT_DIR"

TS_UTC="$(date -u +"%Y-%m-%dT%H%M%SZ")"
JSON_OUT="$REPORT_DIR/$TS_UTC-sync.json"
MD_OUT="$REPORT_DIR/$TS_UTC-sync.md"
QUALITY_OUT="$REPORT_DIR/$TS_UTC-quality.json"
CHANGELOG_OUT="$REPORT_DIR/$TS_UTC-changelogs.json"

cd "$ROOT_DIR"

if [[ ! -x "$CLI" ]]; then
  echo "Missing $CLI. Create venv and install deps first." >&2
  exit 2
fi

# ── 1. Init + Sync ──────────────────────────────────────────────────────────
echo "[1/4] Syncing..."
"$CLI" init --docs-dir "$STORE_DIR" >/dev/null
"$CLI" sync --docs-dir "$STORE_DIR" > "$JSON_OUT"
"$CLI" report --input "$JSON_OUT" --output "$MD_OUT"
echo "  sync: $JSON_OUT"
echo "  report: $MD_OUT"

# ── 2. Quality gate ──────────────────────────────────────────────────────────
echo "[2/4] Quality check..."
"$CLI" quality-check --docs-dir "$STORE_DIR" > "$QUALITY_OUT"
python3 -c "
import json, sys
d = json.load(open('$QUALITY_OUT'))
r = d.get('result', d)
issues = r.get('issues', [])
thin   = sum(1 for i in issues if i.get('flag') == 'thin')
empty  = sum(1 for i in issues if i.get('flag') == 'empty')
tiny   = sum(1 for i in issues if i.get('flag') == 'tiny_html')
print(f'  empty={empty} thin={thin} tiny_html={tiny} total_issues={len(issues)}')
" 2>/dev/null || echo "  (could not parse quality output)"

# ── 3. Changelog extraction ──────────────────────────────────────────────────
echo "[3/4] Extracting changelogs..."
"$CLI" extract-changelogs --docs-dir "$STORE_DIR" > "$CHANGELOG_OUT"
python3 -c "
import json
d = json.load(open('$CHANGELOG_OUT'))
new = d.get('entries_new', 0)
pages = d.get('pages_processed', 0)
flag = ' ← NEW API CHANGES DETECTED' if new > 0 else ''
print(f'  pages={pages} new_entries={new}{flag}')
" 2>/dev/null || echo "  (could not parse changelog output)"

# ── 4. Incremental semantic index ────────────────────────────────────────────
echo "[4/4] Updating semantic index (incremental)..."
if "$CLI" build-index --incremental --docs-dir "$STORE_DIR" 2>/dev/null | \
    python3 -c "
import json, sys
d = json.load(sys.stdin)
r = d.get('result', d)
embedded = r.get('chunks_embedded', 0)
total = r.get('total_rows', 0)
print(f'  chunks_embedded={embedded} total_rows={total}')
" 2>/dev/null; then
  :
else
  echo "  SKIPPED (semantic extras not installed or index error)"
fi

echo ""
echo "Done. Artifacts in $REPORT_DIR/"
