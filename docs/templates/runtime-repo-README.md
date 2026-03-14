# CEX Docs Copilot Runtime

```bash
git clone https://github.com/henryaxis/cex-api-docs-runtime.git && cd cex-api-docs-runtime && uv tool install -e . && ./scripts/bootstrap-data.sh && mkdir -p ~/.claude/skills ~/.agents/skills && ln -sf "$(pwd)/.claude/skills/cex-api-query" ~/.claude/skills/cex-api-query && ln -sf "$(pwd)/.agents/skills/cex-api-query" ~/.agents/skills/cex-api-query
```

Query exchange API documentation from any project, any directory, on both Claude Code and Codex CLI.

## What you get

- `cex-api-docs` CLI — globally on PATH, works from anywhere
- `cex-api-query` skill — available in every project (Claude Code + Codex)
- 10,700+ pages, 4,900+ endpoints across 46 exchanges

Data snapshots (`cex-docs/`) are distributed via GitHub Releases, not git.

## Step-by-step install

```bash
git clone https://github.com/henryaxis/cex-api-docs-runtime.git
cd cex-api-docs-runtime
uv tool install -e .
./scripts/bootstrap-data.sh

# Make skill available globally (Claude Code + Codex)
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sf "$(pwd)/.claude/skills/cex-api-query" ~/.claude/skills/cex-api-query
ln -sf "$(pwd)/.agents/skills/cex-api-query" ~/.agents/skills/cex-api-query
```

## Update

```bash
cd /path/to/cex-api-docs-runtime
git pull && uv tool install -e .
```

Data updates (published separately):
```bash
cd /path/to/cex-api-docs-runtime
./scripts/bootstrap-data.sh
```

## Smoke check

```bash
cex-api-docs store-report
```
