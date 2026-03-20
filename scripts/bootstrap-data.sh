#!/usr/bin/env bash
# Download the xdocs data snapshot from GitHub Releases.
#
# Usage:
#   ./scripts/bootstrap-data.sh          # download latest
#   ./scripts/bootstrap-data.sh data-2026.03.17  # download specific tag
#
# Requires: gh (GitHub CLI), zstd
set -euo pipefail

REPO="gradigit/xdocs"
TAG="${1:-latest}"
TMPFILE="$(mktemp)"

cleanup() { rm -f "$TMPFILE"; }
trap cleanup EXIT

# Check prerequisites
for cmd in gh zstd; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is required but not installed." >&2
    exit 1
  fi
done

# Download
echo "Downloading cex-docs snapshot (tag: $TAG)..."
if [ "$TAG" = "latest" ]; then
  gh release download --repo "$REPO" --pattern "cex-docs.tar.zst" --output "$TMPFILE" --clobber
else
  gh release download "$TAG" --repo "$REPO" --pattern "cex-docs.tar.zst" --output "$TMPFILE" --clobber
fi

SIZE=$(du -h "$TMPFILE" | cut -f1)
echo "Downloaded $SIZE compressed."

# Extract (overwrites existing cex-docs/)
echo "Extracting..."
rm -rf cex-docs/
zstd -d "$TMPFILE" --stdout | tar xf -
echo "Extracted to cex-docs/ ($(du -sh cex-docs/ | cut -f1))"

# Quick sanity check
DB="cex-docs/db/docs.db"
if [ -f "$DB" ]; then
  PAGES=$(python3 -c "import sqlite3; print(sqlite3.connect('$DB').execute('SELECT count(*) FROM pages').fetchone()[0])" 2>/dev/null || echo "?")
  echo "Pages in DB: $PAGES"
else
  echo "WARNING: $DB not found" >&2
fi

# Record which tag was downloaded
ACTUAL_TAG="$TAG"
if [ "$TAG" = "latest" ]; then
  ACTUAL_TAG=$(gh release view --repo "$REPO" --json tagName -q .tagName 2>/dev/null || echo "latest")
fi
echo "$ACTUAL_TAG" > cex-docs/.data-tag

echo "Done. Run 'xdocs store-report' to verify."
