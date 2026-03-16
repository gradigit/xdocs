#!/usr/bin/env bash
set -euo pipefail

PRESET="fast-daytime"
DOCS_DIR="./cex-docs"
if [[ $# -ge 1 ]]; then
  PRESET="$1"
  shift
fi
if [[ $# -ge 1 && "${1:0:1}" != "-" ]]; then
  DOCS_DIR="$1"
  shift
fi

ENTRYPOINT_MODE="${CEX_API_DOCS_ENTRYPOINT:-module}" # module|cli
RUN_CMD=()
if [[ "$ENTRYPOINT_MODE" == "module" ]]; then
  PY="${CEX_API_DOCS_PYTHON:-.venv/bin/python}"
  if [[ ! -x "$PY" ]]; then
    echo "Missing python executable: $PY" >&2
    exit 1
  fi
  export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"
  RUN_CMD=("$PY" -m xdocs.cli)
else
  CLI="${CEX_API_DOCS_CLI:-.venv/bin/xdocs}"
  if [[ ! -x "$CLI" ]]; then
    echo "Missing CLI executable: $CLI" >&2
    exit 1
  fi
  RUN_CMD=("$CLI")
fi

case "$PRESET" in
  fast-daytime)
    exec "${RUN_CMD[@]}" sync \
      --docs-dir "$DOCS_DIR" \
      --resume \
      --render auto \
      --concurrency 2 \
      --delay-s 0.20 \
      --timeout-s 20 \
      --retries 1 \
      --conditional \
      --adaptive-delay \
      --max-domain-delay 10 \
      --scope-dedupe \
      "$@"
    ;;
  overnight-safe)
    exec "${RUN_CMD[@]}" sync \
      --docs-dir "$DOCS_DIR" \
      --force-refetch \
      --render auto \
      --concurrency 1 \
      --delay-s 0.80 \
      --timeout-s 25 \
      --retries 2 \
      --conditional \
      --adaptive-delay \
      --max-domain-delay 60 \
      --scope-dedupe \
      "$@"
    ;;
  *)
    echo "Unknown preset: $PRESET" >&2
    echo "Usage: scripts/run_sync_preset.sh [fast-daytime|overnight-safe] [docs_dir] [extra sync args...]" >&2
    exit 2
    ;;
esac
