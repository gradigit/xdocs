# xdocs

```bash
git clone https://github.com/gradigit/xdocs.git && cd xdocs && uv tool install -e . && ./scripts/bootstrap-data.sh
```

Local-first, cite-only knowledge base for exchange API documentation (CEX + DEX).

Ask natural-language questions like:

- “What permission does this private endpoint need?”
- “Why is this auth request failing on OKX/Bybit/Bitget?”
- “What is the safest rollout plan across exchanges?”

…and get answers backed by local sources, with citations.

---

## Who this is for

Teams integrating multiple CEX APIs who need:

- consistent endpoint/auth/rate-limit answers,
- fewer production mistakes from doc drift,
- auditable outputs (not “LLM guesses”),
- a workflow that works in **Codex CLI** and **Claude Code**.

No internal contacts are required. If you can run the CLI, you can use this repo.

---

## What this project is

`cex-api-docs` combines three things:

1. **CLI tool** (`cex-api-docs`)  
   Crawls/syncs docs, indexes data, searches, and assembles cite-only answers.

2. **Local knowledge store** (`./cex-docs` by default)  
   SQLite + FTS + endpoint records + optional LanceDB semantic index.

3. **Agent skill** (`.claude/skills/cex-api-query/SKILL.md`)  
   A workflow so agents can query docs via natural language with strict citations.

---

## Why this helps

Without this project, teams often lose time on:

- wrong endpoint variants (spot vs margin vs futures),
- missing permission scopes,
- exchange-specific signature/timestamp gotchas,
- conflicting docs and unclear source of truth.

With this project, the workflow is:

- retrieve from local docs,
- verify with endpoint/page evidence,
- fail closed (`unknown` / `undocumented` / `conflict`) when evidence is missing.

---

## Core principles

- **Cite-only**: no unsupported factual claims.
- **Local-first**: answers come from your local store.
- **Deterministic ingestion**: inventory + fetch + stable storage.
- **Fail-closed output**: unknown/conflict instead of hallucination.

---

## Quick start

```bash
git clone https://github.com/gradigit/xdocs.git
cd xdocs
uv tool install -e .
./scripts/bootstrap-data.sh
```

Make the skill available globally (Claude Code + Codex):
```bash
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sf "$(pwd)/.claude/skills/cex-api-query" ~/.claude/skills/cex-api-query
ln -sf "$(pwd)/.agents/skills/cex-api-query" ~/.agents/skills/cex-api-query
```

### First queries

```bash
cex-api-docs search-pages "rate limit OR weight" --docs-dir ./cex-docs
cex-api-docs semantic-search "binance api key permissions" --exchange binance --mode hybrid --docs-dir ./cex-docs
cex-api-docs answer "What permissions are required for Binance private balance endpoints?" --docs-dir ./cex-docs
```

---

## Natural-language agent workflow (Codex or Claude)

In a new session at the repo root, prompt:

```text
Use cex-api-query skill.
Find private balance endpoints for Binance/OKX/Bybit and list auth headers, permissions, and top auth failure codes with citations.
```

Bootstrap guard snippet (recommended for every fresh session):

```text
Use cex-api-query skill for this CEX API docs query.
```

The skill uses this retrieval strategy for question-style prompts:

1. semantic search (`hybrid`) with **auto rerank policy**,
2. targeted endpoint/page verification,
3. bounded fallback search,
4. citation-ledger style output.

---

## Supported exchanges

Registry currently includes 46 exchanges (29 CEX, 16 DEX, 1 reference):

**CEX (29):** binance, okx, bybit, bitget, gateio, kucoin, htx, cryptocom, bitstamp, bitfinex, upbit, bithumb, coinone, korbit, kraken, coinbase, bitmex, bitmart, whitebit, bitbank, mercadobitcoin, mexc, bingx, deribit, backpack, coinex, woo, phemex, gemini

**DEX (16):** dydx, hyperliquid, gmx, drift, aevo, perpetual, gains, kwenta, lighter, aster, apex, grvt, paradex, orderly, bluefin, nado

**Reference:** ccxt

---

## Important commands

### Ingestion / sync

```bash
cex-api-docs sync --docs-dir ./cex-docs
cex-api-docs sync --docs-dir ./cex-docs --resume --concurrency 4
cex-api-docs store-report --docs-dir ./cex-docs
```

### Retrieval

```bash
cex-api-docs search-pages "jwt verification" --docs-dir ./cex-docs
cex-api-docs search-endpoints "wallet balance" --exchange bybit --docs-dir ./cex-docs
cex-api-docs semantic-search "how to sign okx request" --exchange okx --mode hybrid --docs-dir ./cex-docs
```

### Answer assembly

```bash
cex-api-docs answer "Explain Upbit private account auth requirements with citations" --docs-dir ./cex-docs
```

### Endpoint import

```bash
cex-api-docs import-openapi --exchange kucoin --section spot --url <spec-url> --base-url https://api.kucoin.com --docs-dir ./cex-docs --continue-on-error
cex-api-docs import-postman --exchange bitmart --section spot --url <collection-url> --docs-dir ./cex-docs --continue-on-error
cex-api-docs link-endpoints --docs-dir ./cex-docs    # resolve docs_url for imported endpoints
cex-api-docs ccxt-xref --docs-dir ./cex-docs          # cross-reference against CCXT
```

### Validation / quality

```bash
cex-api-docs validate-base-urls
cex-api-docs validate-retrieval --qa-file tests/golden_qa.jsonl --limit 5 --docs-dir ./cex-docs
cex-api-docs fsck --docs-dir ./cex-docs
cex-api-docs migrate-schema --docs-dir ./cex-docs          # dry-run
cex-api-docs migrate-schema --docs-dir ./cex-docs --apply  # apply pending DB migrations
cex-api-docs quality-check --docs-dir ./cex-docs
cex-api-docs coverage --docs-dir ./cex-docs
cex-api-docs detect-stale-citations --docs-dir ./cex-docs

# Crawl validation
cex-api-docs sanitize-check --docs-dir ./cex-docs
cex-api-docs crawl-coverage --exchange binance --docs-dir ./cex-docs
cex-api-docs check-links --sample 50 --docs-dir ./cex-docs
```

---

## Reranking policy (how it works)

`semantic-search` supports:

- `--rerank-policy auto` (default): apply reranking only when candidates are ambiguous,
- `--rerank-policy always`: always rerank,
- `--rerank-policy never`: never rerank,
- `--rerank/--no-rerank`: manual override.

Example:

```bash
cex-api-docs semantic-search "binance api key permissions" --exchange binance --mode hybrid --rerank-policy auto --docs-dir ./cex-docs
```

CLI output includes rerank audit fields:

- `rerank_policy`
- `rerank_applied`
- `rerank_reason`

---

## Team operating model (recommended)

Use two roles:

### A) Maintainers (1–2 people)

- run scheduled sync/index refresh,
- run retrieval validation,
- publish versioned data bundle (`cex-docs` snapshot + changelog).

### B) Consumers (everyone else)

- pull latest repo,
- use latest shared `cex-docs` snapshot,
- run natural-language queries via skill.

This keeps day-to-day usage fast and consistent.

### Update

```bash
git pull && uv tool install -e . && ./scripts/bootstrap-data.sh
```

---

## Project structure

- `src/cex_api_docs/cli.py` — CLI entrypoint (51 subcommands)
- `src/cex_api_docs/sync.py` — inventory + fetch orchestration (cron-friendly)
- `src/cex_api_docs/inventory.py` — doc URL enumeration (sitemaps + link-follow)
- `src/cex_api_docs/inventory_fetch.py` — page fetching (--resume, --concurrency, --render auto)
- `src/cex_api_docs/endpoints.py` — endpoint CRUD, FTS search, review queue
- `src/cex_api_docs/openapi_import.py` — OpenAPI/Swagger spec import
- `src/cex_api_docs/postman_import.py` — Postman collection import
- `src/cex_api_docs/semantic.py` — vector/fts/hybrid retrieval + rerank policy
- `src/cex_api_docs/answer.py` — cite-only answer composition
- `src/cex_api_docs/lookup.py` — endpoint path lookup + error code search
- `src/cex_api_docs/classify.py` — input classification (error/endpoint/payload/code/question)
- `src/cex_api_docs/crawl_targets.py` — multi-method URL discovery
- `src/cex_api_docs/crawl_coverage.py` — coverage audit + gap backfill
- `src/cex_api_docs/ccxt_xref.py` — CCXT cross-reference validation
- `src/cex_api_docs/quality.py` — content quality gate (empty/thin/tiny_html)
- `src/cex_api_docs/changelog.py` — changelog extraction for API drift detection
- `src/cex_api_docs/validate.py` — golden QA retrieval evaluation
- `src/cex_api_docs/embeddings.py` — embedding backend selection (Jina MLX / SentenceTransformers)
- `scripts/sync_runtime_repo.py` — sync maintainer repo → runtime repo
- `schema/schema.sql` — SQLite schema (v6)
- `data/exchanges.yaml` — exchange registry (46 exchanges, 78 sections)
- `.claude/skills/cex-api-docs/SKILL.md` — maintainer workflow skill
- `.claude/skills/cex-api-query/SKILL.md` — query/answer agent skill
- `.claude/skills/cex-discovery/SKILL.md` — exhaustive crawl target discovery skill

---

## Safety / non-goals

- Not a hosted SaaS.
- Does not store real API keys.
- Does not place trades.
- Does not make authenticated exchange calls.

---

## Troubleshooting

- `command not found`: run `uv tool install -e .` from the repo root
- `ENOINIT`: run `./scripts/bootstrap-data.sh` to download data
- Semantic search fails with ImportError: install extras `uv pip install -e ".[semantic]"`
- Interrupted sync: re-run with `--resume`

---

## Development

Run tests:

```bash
python3 -m pytest -q
```

---

## License

MIT
