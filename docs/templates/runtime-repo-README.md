# CEX Docs Copilot Runtime

```bash
git clone https://github.com/gradigit/xdocs.git && cd xdocs && uv tool install -e . && ./scripts/bootstrap-data.sh && mkdir -p ~/.claude/skills ~/.agents/skills && ln -sf "$(pwd)/.claude/skills/xdocs-query" ~/.claude/skills/xdocs-query && ln -sf "$(pwd)/.agents/skills/xdocs-query" ~/.agents/skills/xdocs-query
```

Query exchange API documentation from any project, any directory, on both Claude Code and Codex CLI.

## What you get

- `xdocs` CLI — globally on PATH, works from anywhere
- `xdocs-query` skill — available in every project (Claude Code + Codex)
- 10,700+ pages, 4,900+ endpoints across 46 exchanges

Data snapshots (`cex-docs/`) are distributed via GitHub Releases, not git.

## Step-by-step install

```bash
git clone https://github.com/gradigit/xdocs.git
cd xdocs
uv tool install -e .
./scripts/bootstrap-data.sh

# Make skill available globally (Claude Code + Codex)
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sf "$(pwd)/.claude/skills/xdocs-query" ~/.claude/skills/xdocs-query
ln -sf "$(pwd)/.agents/skills/xdocs-query" ~/.agents/skills/xdocs-query
```

## Update

```bash
cd /path/to/xdocs-runtime
git pull && uv tool install -e .
```

Data updates (published separately):
```bash
cd /path/to/xdocs-runtime
./scripts/bootstrap-data.sh
```

## Smoke check

```bash
xdocs store-report
```
