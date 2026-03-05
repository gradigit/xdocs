#!/usr/bin/env bash
set -euo pipefail

# Bootstrap: clone-to-running setup for cex-api-docs.
# Usage: scripts/bootstrap.sh [docs-dir]

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS_DIR="${1:-$REPO_ROOT/cex-docs}"

echo "=== CEX API Docs Bootstrap ==="
echo "Repo:     $REPO_ROOT"
echo "Docs dir: $DOCS_DIR"

# 1. Create venv if not exists
if [ ! -d "$REPO_ROOT/.venv" ]; then
    echo ""
    echo "--- Creating virtual environment ---"
    python3 -m venv "$REPO_ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$REPO_ROOT/.venv/bin/activate"

# 2. Install deps (detect platform for extras)
echo ""
echo "--- Installing dependencies ---"
if [[ "$(uname)" == "Darwin" ]]; then
    pip install -e "$REPO_ROOT[dev,semantic]"
    # Playwright for JS-rendered exchanges (optional)
    if pip install -e "$REPO_ROOT[playwright]" 2>/dev/null; then
        playwright install chromium 2>/dev/null || true
    fi
else
    pip install -e "$REPO_ROOT[dev,semantic]"
fi

# 3. Init store if not exists
echo ""
echo "--- Checking store ---"
if [ ! -d "$DOCS_DIR/db" ]; then
    cex-api-docs init --docs-dir "$DOCS_DIR"
    echo "Store initialized at $DOCS_DIR"
    echo "Next: run 'cex-api-docs sync --docs-dir $DOCS_DIR' to crawl exchanges"
else
    echo "Store already exists at $DOCS_DIR"
fi

# 4. Verify
echo ""
echo "--- Running tests ---"
python3 -m pytest "$REPO_ROOT/tests" -q --tb=no 2>&1 | tail -5

echo ""
echo "=== Bootstrap complete ==="
