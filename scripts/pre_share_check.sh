#!/usr/bin/env bash
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

echo "[1/8] Schema migration dry-run..."
"$PY" -m xdocs.cli migrate-schema --docs-dir "$DOCS_DIR" >/tmp/cex_migrate_schema.json
jq -r '.result | "schema_user_version=\(.schema_user_version) target=\(.target_schema_user_version) upgrade_required=\(.upgrade_required)"' /tmp/cex_migrate_schema.json

echo "[2/8] Registry/base-url validation smoke..."
"$PY" -m xdocs.cli validate-base-urls --exchange bitfinex --section v2 --timeout-s 10 --retries 1 >/tmp/cex_baseurl_smoke.json
jq -r '.ok' /tmp/cex_baseurl_smoke.json

echo "[3/8] Retrieval command smoke..."
"$PY" -m xdocs.cli classify "How do I check API key permissions on Binance?" --docs-dir "$DOCS_DIR" >/tmp/cex_classify_smoke.json
jq -r '.result.input_type' /tmp/cex_classify_smoke.json

echo "[4/8] Sync preset smoke..."
./scripts/run_sync_preset.sh fast-daytime "$DOCS_DIR" --exchange bitfinex --section v2 --limit 1 >/tmp/cex_sync_smoke.json
jq -r '.ok' /tmp/cex_sync_smoke.json

echo "[5/8] Unit/integration tests..."
"$PY" -m pytest -q

DEMO_ROOT="${DEMO_ROOT:-}"
if [[ -n "$DEMO_ROOT" ]]; then
  echo "[6/8] Demo skill sync check..."
  "$PY" scripts/sync_demo_skills.py --demo-root "$DEMO_ROOT" >/tmp/cex_demo_sync.log
  tail -n 2 /tmp/cex_demo_sync.log
else
  echo "[6/8] Demo skill sync check... SKIPPED (set DEMO_ROOT env var to enable)"
fi

echo "[7/8] Runtime repo export smoke..."
"$PY" scripts/sync_runtime_repo.py --runtime-root /tmp/cex-runtime-export-check --docs-dir "$DOCS_DIR" --no-data --clean >/tmp/cex_runtime_export.log
tail -n 2 /tmp/cex_runtime_export.log

echo "[8/8] Link reachability spot-check (sample=20)..."
"$PY" -m xdocs.cli check-links --sample 20 --docs-dir "$DOCS_DIR" >/tmp/cex_link_check.json
jq -r '"checked=\(.result.checked) ok=\(.result.ok) errors=\(.result.client_error + .result.server_error + .result.network_error)"' /tmp/cex_link_check.json

echo "✅ pre_share_check completed"
