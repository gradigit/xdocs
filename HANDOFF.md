# HANDOFF — 2026-03-05

## Session Summary

Migrated embedding model from Qwen3-Embedding-0.6B (1024 dims) to jina-embeddings-v5-text-nano (768 dims). Committed all accumulated work (89 files, +19K lines) plus doc sync.

## What Was Done

### Jina v5 Embedding Migration (complete)
- **embeddings.py**: Replaced `MlxEmbedder` with `JinaMlxEmbedder` (Jina-native MLX loader via `snapshot_download` + `importlib` from HF repo). Updated `SentenceTransformerEmbedder` with `trust_remote_code`, `peft`, `default_task="retrieval"`.
- **semantic.py**: Added `compact_index()` for LanceDB maintenance.
- **cli.py**: Added `compact-index` subcommand.
- **sync_runtime_repo.py**: Pre-copy compaction, `--strip-maintenance` flag, embedding metadata in manifest.
- **pyproject.toml**: New `semantic-query` extra (lightweight Mac), platform markers for mlx, added peft.
- Both backends verified: cross-backend cosine similarity >0.9999.
- 337 tests pass.

### Large Accumulated Commit
- 17 new source modules (crawl validation pipeline, embeddings, chunker, reranker, audit, ccxt_xref, etc.)
- 18 new test files
- CI workflow, scripts, runtime repo templates
- 13 new exchanges in registry (35 total, 62 sections)

### Doc Sync
- CLAUDE.md, AGENTS.md, README.md all updated for Jina v5 model, compact-index, new key files, semantic-query install.
- .gitignore updated to exclude ephemeral files.

## What's Pending

### Immediate: Rebuild Semantic Index
The LanceDB index still has old Qwen3 1024-dim vectors. A full rebuild is required (dim-check auto-triggers it).

```bash
# On PC (CUDA, primary builder):
cd ~/Projects/cex-api-docs
git pull
source .venv/bin/activate
pip install -e ".[semantic]"
nohup cex-api-docs build-index --docs-dir ./cex-docs > logs/rebuild-index.log 2>&1 &
# After rebuild:
cex-api-docs compact-index --docs-dir ./cex-docs
```

### Then: Sync Runtime Repo
```bash
python3 scripts/sync_runtime_repo.py --docs-dir ./cex-docs --clean --hash-tree --strip-maintenance
```

### Backlog
- Add link validation to maintainer workflow
- Periodic CCXT docs refresh
- Add Tier 2 DEXes (Orderly, Pacifica, Nado, Bluefin)
- Structured changelog extraction for drift detection

## Git State

- Branch: `main`
- Last commits:
  - `88b8e94` docs: sync CLAUDE.md, AGENTS.md, README.md for Jina v5 migration
  - `00d0bab` feat: crawl validation pipeline, Jina v5 embeddings, 17 new modules, CI
- No remote configured (local-only repo, transfer via SSH/git clone)

## Key Architecture Decision

The Jina MLX integration uses Jina's **native** model loader — NOT a custom MLX backend. The pattern (from jina-grep-cli): `snapshot_download` the HF repo → `importlib` dynamic import of their `utils.py` → `load_model()` → `switch_task("retrieval")` → `encode()`. No `mlx-embeddings` package involved.
