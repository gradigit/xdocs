#!/usr/bin/env bash
# Install xdocs — exchange API docs knowledge base
# Usage: curl -fsSL https://raw.githubusercontent.com/gradigit/xdocs/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/gradigit/xdocs.git"
INSTALL_DIR="${XDOCS_DIR:-$HOME/xdocs}"

info()  { printf "\033[1;34m→\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
fail()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

# --- Prerequisites ---
for cmd in git python3; do
  command -v "$cmd" &>/dev/null || fail "$cmd is required but not installed"
done

if ! command -v uv &>/dev/null; then
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv &>/dev/null || fail "uv install failed"
  ok "uv installed"
fi

if ! command -v gh &>/dev/null; then
  fail "gh (GitHub CLI) is required for data download. Install: https://cli.github.com — then run: gh auth login"
fi

# --- Clone ---
if [ -d "$INSTALL_DIR" ]; then
  info "Updating existing install at $INSTALL_DIR..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  info "Cloning to $INSTALL_DIR..."
  git clone "$REPO" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# --- Install CLI ---
info "Installing xdocs CLI globally..."
if [[ "$(uname)" == "Darwin" ]]; then
  uv tool install -e ".[semantic-query]" --force 2>&1 | tail -1
else
  uv tool install -e ".[semantic]" --force 2>&1 | tail -1
fi
ok "xdocs CLI installed ($(xdocs --version 2>/dev/null || echo 'check PATH'))"

# --- Download data ---
if [ -f "cex-docs/db/docs.db" ]; then
  ok "Data already present ($(python3 -c "import sqlite3; print(sqlite3.connect('cex-docs/db/docs.db').execute('SELECT count(*) FROM pages').fetchone()[0])" 2>/dev/null || echo '?') pages)"
else
  info "Downloading data snapshot..."
  ./scripts/bootstrap-data.sh
  ok "Data ready"
fi

# --- Skill symlinks ---
info "Setting up agent skills..."
mkdir -p "$HOME/.claude/skills" "$HOME/.agents/skills"
ln -sf "$INSTALL_DIR/.claude/skills/xdocs-query" "$HOME/.claude/skills/xdocs-query"
ln -sf "$INSTALL_DIR/.agents/skills/xdocs-query" "$HOME/.agents/skills/xdocs-query"
ok "Skills available globally (Claude Code + Codex)"

# --- Done ---
echo ""
ok "xdocs installed successfully!"
echo ""
echo "  CLI:    xdocs --help"
echo "  Query:  xdocs answer \"How do I authenticate to Binance?\""
echo "  Skill:  Ask any AI agent about exchange APIs"
echo ""
echo "  Update: curl -fsSL https://raw.githubusercontent.com/gradigit/xdocs/main/install.sh | bash"
