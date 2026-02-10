#!/usr/bin/env bash
set -euo pipefail

# Cron-friendly runner for macOS (launchd/cron).
#
# Outputs timestamped artifacts under the local store (default: ./cex-docs/reports/):
# - sync JSON (machine-readable, stable)
# - sync Markdown (human-readable)
#
# Usage:
#   scripts/sync_and_report.sh
#   scripts/sync_and_report.sh ./cex-docs
#
# Notes:
# - Exits non-zero only on command failure.
# - Missing/undocumented endpoint fields are not treated as failures (that's handled at the reporting/review layer).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STORE_DIR="${1:-$ROOT_DIR/cex-docs}"
REPORT_DIR="$STORE_DIR/reports"

mkdir -p "$REPORT_DIR"

TS_UTC="$(date -u +"%Y-%m-%dT%H%M%SZ")"
JSON_OUT="$REPORT_DIR/$TS_UTC-sync.json"
MD_OUT="$REPORT_DIR/$TS_UTC-sync.md"

cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/cex-api-docs" ]]; then
  echo "Missing .venv/bin/cex-api-docs. Create venv and install deps first." >&2
  exit 2
fi

.venv/bin/cex-api-docs init --docs-dir "$STORE_DIR" >/dev/null
.venv/bin/cex-api-docs sync --docs-dir "$STORE_DIR" > "$JSON_OUT"
.venv/bin/cex-api-docs report --input "$JSON_OUT" --output "$MD_OUT"

echo "Wrote:"
echo "  $JSON_OUT"
echo "  $MD_OUT"

