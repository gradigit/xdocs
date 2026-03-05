#!/usr/bin/env bash
set -euo pipefail

DOCS_DIR="${1:-./cex-docs}"
PY="${CEX_API_DOCS_PYTHON:-.venv/bin/python}"

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"

"$PY" -m cex_api_docs.cli classify "How do I check API key permissions on Binance?" --docs-dir "$DOCS_DIR" >/tmp/runtime_classify.json
jq -r '.ok, .result.input_type' /tmp/runtime_classify.json

echo "✅ runtime query smoke passed"
