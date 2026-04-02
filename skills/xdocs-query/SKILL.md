---
name: xdocs-query
description: >
  Answers questions about cryptocurrency exchange APIs using the local xdocs
  SQLite store. Searches endpoints and documentation pages across CEX, perp DEX,
  and CCXT documentation sources.
  Activates when user asks about exchange API endpoints, rate limits, authentication,
  parameters, error codes, or mentions Binance, OKX, Bybit, Bitget, KuCoin, Gate.io,
  HTX, Crypto.com, Bitstamp, Bitfinex, dYdX, Hyperliquid, GMX, Drift, Aevo,
  Perpetual Protocol, Gains Network, Kwenta, Lighter, CCXT, Upbit, Bithumb, Coinone,
  Korbit, Kraken, Coinbase, BitMEX, BitMart, WhiteBIT, Bitbank, Mercado Bitcoin,
  Aster, ApeX, GRVT, or Paradex API documentation. Also activates when user pastes
  API errors, endpoint paths, request payloads, or code snippets related to exchange APIs.
metadata:
  version: "2.13.0"
---

# CEX API Query v2

Answer user questions about cryptocurrency exchange APIs. Route input through classification, search the local doc store, and compose answers with citations.

## Pre-check (first query in session)

Before the first query, verify the tool is installed, data is available, and check for updates:

```bash
command -v xdocs && xdocs --version && xdocs store-report 2>&1 | head -5
```

If `command not found` or `store-report` fails, tell the user to run setup:

```
uv tool install -e . && ./scripts/bootstrap-data.sh
```

### Update check

After confirming the CLI works, check for updates (non-blocking — respond to the user first):

```bash
LOCAL=$(xdocs --version 2>/dev/null | awk '{print $2}')
REMOTE=$(curl -sf https://raw.githubusercontent.com/gradigit/xdocs/main/VERSION 2>/dev/null | tr -d '[:space:]')
```

- If `REMOTE` is newer than `LOCAL`: tell the user after your response — "Update available (LOCAL → REMOTE). Run: `cd /path/to/repo && git pull && uv tool install -e . && ./scripts/bootstrap-data.sh`"
- If fetch fails or versions match: continue silently
- **Never block the user's first query** — answer first, then notify about updates

Skip all pre-checks on subsequent queries in the same session.

## Workflow

- [ ] 1. Classify the input to determine routing
- [ ] 2. Execute the primary command for that input type (semantic-first for questions)
- [ ] 3. If primary returns weak/empty, use bounded fallback commands
- [ ] 4. Read stored markdown for full context when snippets aren't enough
- [ ] 5. Synthesize a readable answer with source URLs and persona-appropriate framing
- [ ] 6. Always include relevant doc links as OSC-8 hyperlinks with full URL destinations
- [ ] 7. Enforce strict citation contract (every material claim must map to citation ID)
- [ ] 8. Include retrieval audit line (skill + mode + rerank + fallbacks + source-link mode)
- [ ] 9. If nothing found, say so — never guess

## Step 1: Classify Input

### Fresh Session Guard (Required)

At the beginning of a brand-new session, if the user asks a CEX API docs question, explicitly set routing context first:

```text
Use xdocs-query skill for this CEX API docs query.
```

Then run classification and the standard workflow below.

Run classification first to route correctly:

```bash
xdocs classify "USER_INPUT_HERE"```

Returns `input_type`, `confidence`, and `signals` (extracted error codes, paths, exchange hints).

### Routing Table

| Input Type | Primary Command | Fallback |
| --- | --- | --- |
| `error_message` | `search-error <code> --exchange <hint>` | `search-pages "<error text>"` |
| `endpoint_path` | `lookup-endpoint <path> --method <M>` then `get-endpoint <id>` | `search-endpoints "<path>"` |
| `request_payload` | Extract endpoint hints from keys → `lookup-endpoint` | `search-endpoints` with param names |
| `code_snippet` | Extract method/path → `lookup-endpoint` | `search-pages` with SDK method name |
| `question` | `semantic-search --mode hybrid --rerank-policy auto` (+ targeted endpoint/page fetch) | `search-endpoints`/`search-pages` for exact strings only |

## Step 2: Error Message Routing

When `input_type == "error_message"`:

1. Extract error code from `signals.error_codes[].code` and `exchange_hint`.
2. Look up in `data/error_code_patterns.yaml` for quick classification (permission vs rate limit vs other).
3. Search for details:

```bash
# IMPORTANT: Only use -- before NEGATIVE error codes (codes starting with -)
# Negative codes: -- is required to prevent argparse interpreting the dash as a flag
xdocs search-error -- -1002 --exchange binance
# Positive codes: do NOT use -- (it breaks --exchange and --docs-dir parsing)
xdocs search-error 60029 --exchange okx
# If error code is in the patterns file, check common meaning first
# e.g. Binance -1002 = "Unauthorized — API key missing or invalid"
```

4. If the search finds endpoint results, get the full record:

```bash
xdocs get-endpoint ENDPOINT_ID```

5. Read the source page for full context (some errors require out-of-band steps like the Binance Convert API questionnaire).

**Example 1:** User pastes "Error -1002: You are not authorized" from Binance Convert API:
- `search-error -- -1002 --exchange binance` → finds Convert endpoint (note: `--` needed for negative code)
- `get-endpoint <id>` → shows required permissions
- Page markdown reveals: must complete Convert API questionnaire on binance.com before enabling API access

**Example 2:** User gets OKX error 60029 subscribing to fills channel:
- `search-error 60029 --exchange okx` → finds fills channel section (note: no `--` for positive code)
- Snippet shows "VIP6 or above" restriction

## Step 3: Endpoint Path Routing

When `input_type == "endpoint_path"`:

```bash
# Direct path lookup (uses SQL LIKE, handles {{url}} prefix)
xdocs lookup-endpoint /sapi/v1/convert/getQuote --method POST --exchange binance
# Get full record with all fields
xdocs get-endpoint ENDPOINT_ID
# Browse endpoints by exchange/section
xdocs list-endpoints --exchange okx --section rest --limit 20```

The full endpoint JSON contains:
- `http.method`, `http.path`, `http.base_url` — the API call
- `description` — what the endpoint does
- `request_schema.parameters` — parameters with name, type, required, enum values
- `response_schema.responses` — response structure with examples
- `rate_limit` — extracted for OKX, WOO, Bitget endpoints (400+ endpoints have this). Contains `{text, requests, period_seconds}`. Check `field_status.rate_limit == "documented"`.
- `required_permissions`, `error_codes` — if documented (check `field_status`)
- `sources` — citation URLs back to original doc pages

## Step 4: Search Pages

For documentation context beyond endpoint records — authentication flows, conceptual explanations, changelogs, general rules:

```bash
# Primary for natural-language questions (agent-decided rerank):
xdocs semantic-search "how to calculate signature" --exchange binance --mode hybrid --rerank-policy auto --limit 8

# Use FTS5 only for literal anchors (exact error code/path/header string):
xdocs search-pages "X-MBX-APIKEY -1021 recvWindow" --limit 5
xdocs search-pages "withdrawal history" --exchange bitget --limit 5  # filter by exchange
```

### Drill-Down: get-page

`get-page` takes a **URL**, not a page ID. Use the `url` field from semantic-search or search-pages results:

```bash
xdocs get-page "https://developers.binance.com/docs/wallet/capital/withdraw-history"
```

The `page_id` field in semantic-search results is a LanceDB internal row ID — do NOT pass it to `get-page`.

### Retrieval Budget (Efficiency Guardrail)

For one user query, stay within this default budget unless user asks for exhaustive mode:

- semantic-search calls: `<= 8` total (typically 1 per exchange)
- endpoint/page drill-down calls (`lookup-endpoint` / `get-endpoint` / `get-page`): `<= 24`
- raw file scans (`sed`, broad `rg` over markdown dumps): avoid by default; use only when retrieval fails

If you exceed budget, stop and surface what is still missing.

## Step 5: Read Full Page Content

When you find the right page but need more than the snippet:

```bash
# Get the markdown file path for a page URL
python3 -c "
from pathlib import Path; import sqlite3
db = Path(__import__('xdocs').__file__).resolve().parents[2] / 'cex-docs/db/docs.db'
conn = sqlite3.connect(str(db))
row = conn.execute('SELECT markdown_path, word_count FROM pages WHERE canonical_url = ?', ('URL_HERE',)).fetchone()
if row: print(row[0], f'({row[1]} words)')
"
```

Then use the **Read tool** to read the markdown file at that path. Don't use `cat` or `python3` to print it.

**For large single-page docs** (OKX, Gate.io, HTX, etc.), use Grep to find the relevant section within the file first, then Read with an offset.

**Nav chrome:** Most stored pages start with navigation menus and sidebars. The actual content begins at the first `# Heading` that matches the topic. Skip everything before it.

## Step 5b: WebSocket Channel Queries

WebSocket channel data is stored in crawled page content (not in the endpoints table). When a user asks about WS channels, subscriptions, or WS-specific errors:

1. **WS error codes** (OKX 60xxx, Binance negative codes, etc.):
   ```bash
   # Positive codes — no -- prefix
   xdocs search-error 60029 --exchange okx
   # Negative codes — use -- prefix
   xdocs search-error -- -1102 --exchange binance   ```

2. **WS channel lookup** — try semantic search first:
   ```bash
   xdocs semantic-search "fills channel websocket" --exchange okx --mode hybrid --limit 5   ```

3. **If semantic results have generic headings** ("Response parameters", "URL Path", a date), the chunk lost its parent heading context. Fall back to FTS:
   ```bash
   xdocs search-pages "deposit-info business websocket"   ```

4. **If still insufficient**, find the section directly in the stored markdown:
   ```bash
   # Grep for the channel name in the exchange's pages directory
   Grep pattern="deposit-info channel|Deposit info channel" path="cex-docs/pages/www.okx.com" context=3

   # Then Read with offset to get full context
   Read file_path="<markdown_path>" offset=<line_number> limit=30
   ```

**Key WS URL paths by exchange:**
- **OKX**: `/ws/v5/public`, `/ws/v5/private`, `/ws/v5/business` (deposit/withdrawal channels are on `/business`, not `/private`)
- **Binance**: `/ws`, `/ws/<listenKey>` (user data streams)
- **Bybit**: `/v5/public`, `/v5/private`, `/v5/trade`

**Common WS errors:**
- OKX 60018: "Wrong URL or channel doesn't exist" — usually means connecting to wrong WS path (e.g., `/private` instead of `/business`)
- OKX 60029: "VIP6+ only" — channel has tier restriction (e.g., fills channel)

## Step 5c: Negative Evidence and Third-Party Queries

**Negative evidence (feature/protocol support questions):**

When the user asks "Does exchange X support feature Y?" and local retrieval finds nothing:

1. Check structured endpoints for protocol/feature keywords (e.g., `SELECT count(*) FROM endpoints WHERE exchange=? AND lower(protocol) LIKE '%fix%'`).
2. Grep stored markdown for the feature name.
3. If both are negative, this is a valid local answer: **"Not found in the local docs snapshot."** Do not escalate to web search just because local retrieval is empty — absence of evidence in the store is useful information.
4. The answer pipeline returns distinct statuses for these cases:
   - `not_found` — routing succeeded, search ran, nothing relevant found
   - `undocumented` — exchange recognized, specific endpoint/error code not in DB
   - `unknown` — could not route the query at all (no exchange detected)
   - `needs_clarification` — multiple exchanges detected, user must disambiguate
5. Only browse live if the user explicitly asks for current verification or if you need to confirm a time-sensitive claim.

**Third-party vendor questions:**

When a query mixes official exchange docs with named third-party vendors (e.g., "Does Gate.io support FIX, or is Axon Trade the only option?"):

1. Answer the official-exchange portion from the local store first.
2. Label any named vendor or bridge as **out-of-corpus** — the store only contains official exchange documentation.
3. Do not browse to validate vendor claims unless the user explicitly requests third-party verification.

## Step 6: Synthesize Answer

### Persona Templates

**Developer** (default — when user asks about endpoints, parameters, code):
- Endpoint: `METHOD /path` at `base_url`
- Parameters table (name, type, required, description)
- Rate limits (documented or inferred with label)
- Error codes and their meanings
- Code example if relevant
- Source URL for reference

**Trading Admin** (when user asks about permissions, access, key setup):
- Permission checklist: what API key permissions are needed
- Access requirements: IP whitelist, questionnaire, KYC level
- Validation steps: how to verify the setup is correct
- Source URL for reference

**Front Office** (when user asks "what data can I get" or business questions):
- Business-language explanation of what the endpoint does
- What data is available and in what format
- Source URL for reference

### Link Output (Mandatory)

Always add a **Source Docs** section at the end of the answer.

- Include the most relevant endpoint/doc page URLs used for the answer.
- Render each source as an OSC-8 hyperlink (full URL destination, short label).
- Prioritize canonical docs page links over spec blobs when both exist.
- When an endpoint record has a `docs_url` field, use it instead of `sources[].url`. The `docs_url` points to the official docs page (human-readable, navigable). Only fall back to `sources[].url` if `docs_url` is absent.
- If multiple exchanges are discussed, group links by exchange.

Expected style:
- `Binance — API Key Permission` (clickable OSC-8 link to full docs URL)
- `Bitfinex — Key Permissions` (clickable OSC-8 link to full docs URL)

### Retrieval Audit (Mandatory)

Add this block before final answer close:

- `skill_used`: `xdocs-query@2.13.0`
- `search_mode`: `semantic/hybrid` | `fts` | `mixed`
- `rerank_policy`: `auto` | `always` | `never`
- `rerank_applied`: `yes/no`
- `rerank_reason`: e.g. `ambiguous_top_scores` | `confident_ranking` | `policy_always` | `reranker_unavailable`
- `semantic_calls`: integer
- `fallback_calls`: integer
- `raw_scan_used`: `yes/no`
- `source_links_mode`: `osc8_full_url`

This must reflect commands actually used in the run.

### Strict Citation Contract (Mandatory, Fail-Closed)

For dense comparison answers (tables/checklists), use this contract:

1. Add citation IDs inline for every material claim/cell (`[C1]`, `[C2]`, ...).
2. Add a **Citation Ledger** section mapping each ID to:
   - exchange
   - source URL (OSC-8 link)
   - short evidence note (what that source proves)
3. If a claim has no direct support in stored docs, output only:
   - `unknown`, `undocumented`, or `conflict`
   - never inferred prose.
4. For conflicts, cite both sides explicitly (e.g., `conflict [C7][C8]`).
5. Endpoint rows should include explicit evidence for:
   - method/path/base URL
   - permission scope (or `unknown`)
   - auth headers/signing requirements
   - rate limit (or `undocumented`)
   - error codes/remediation (or `undocumented`)

Minimum table style example:

| Exchange | Endpoint | Permission | Rate limit |
| --- | --- | --- | --- |
| OKX | `GET /api/v5/account/subaccount/balances` [C1] | `Read` [C2] | `6 req / 2s` [C3] |
| Bybit | `GET /v5/.../query-account-coins-balance` [C4] | `unknown` | `5 req/s` [C5] |

Before sending, self-check:
- every non-trivial cell has citation ID(s) or `unknown`/`undocumented`/`conflict`
- all cited IDs exist in Citation Ledger
- no claim text without support

### Rate Limit Inference

1. Check endpoint record first (`field_status.rate_limit`).
2. If `"documented"`, use the `rate_limit` field directly.
3. If `"unknown"`, search page markdown for weight/limit near the endpoint path.
4. Present inferred values labeled as "inferred from documentation" with citation.

### Special Requirements

Some API access requires out-of-band steps not captured in the endpoint record:
- **Binance Convert**: must complete questionnaire on binance.com before API access works
- **Binance Portfolio Margin Pro**: separate application process
- **OKX Travel Rule (58237)**: withdrawal requires rcvrInfo for certain jurisdictions
- Reference `data/error_code_patterns.yaml` for quick error code classification

## What's In The Store

Run `xdocs store-report` for current page/endpoint counts. The pre-check already does this on first query.

The store covers 46 exchanges (CEX, perp DEX, CCXT reference) with:
- SQLite FTS5 indexes on pages and endpoints
- LanceDB vector index for semantic/hybrid search
- Structured endpoint records from OpenAPI/Postman spec imports

**Single-page doc sites:** OKX, Gate.io, HTX, Crypto.com, Bitstamp, Korbit serve their entire API reference from 1-4 large HTML pages (up to 325K words each). When reading these, search within the file — don't print all of it.

## Gotchas

- **CLI auto-discovers data:** `--docs-dir` is resolved from the package install location. No flags or env vars needed if installed via `uv tool install -e .` or `uv sync`.
- `{{url}}`** in paths:** Some Postman-imported endpoints have `{{url}}/sapi/v1/...` paths. `lookup-endpoint` handles this automatically.
- **Korean exchanges:** Upbit, Bithumb, Coinone docs are partially/fully in Korean. Korbit is in English. Endpoint paths and parameter names are in English and searchable via FTS5. Upbit English docs lag Korean by ~3 minor versions.
- **Unresolved **`$ref`**:** OpenAPI-imported request/response schemas may contain `$ref` pointers. If you need the referenced definition, search for the component name in the source page.
- **Negative error codes:** Use `--` before negative numbers in CLI args: `search-error -- -1002`. Do NOT use `--` for positive codes like `search-error 60029` — it breaks flag parsing.
- **Semantic search requires **`[semantic]`** extra:** If `semantic-search` fails with ImportError, fall back to FTS5.
- **Reranker is bundled** with `[semantic-query]` and `[semantic]` extras. If reranker import still fails, continue with semantic results and mark `rerank_applied: no` + `rerank_reason: reranker_unavailable`.

## Self-Evolution

Update this skill when:
1. **New exchanges added** — update the exchange list
2. **New endpoints extracted** — coverage numbers change (run `store-report` to check)
3. **Better retrieval patterns discovered** — add to routing table or query patterns
4. **Agent fails to find known information** — add the successful search strategy as a pattern

Current version: 2.13.0

### Changelog

- v2.13.0: Replaced hardcoded store stats with dynamic `store-report` (no more stale numbers). Added `not_found`, `needs_clarification` status documentation. Expanded Korean exchange notes. Removed flashrank from reranker (Jina v3 only).
- v2.12.0: Removed all `--docs-dir ./cex-docs` flags and `source .venv/bin/activate` prefixes. CLI now auto-discovers data via `__file__` resolution. Skill works globally when installed via `uv tool install -e .` and symlinked to `~/.claude/skills/` or `~/.agents/skills/`.
- v2.11.0: Added Step 5c — negative-evidence answer guidance (don't escalate to web for empty local results) and third-party vendor split (answer official-exchange portion from store, label vendors as out-of-corpus).
