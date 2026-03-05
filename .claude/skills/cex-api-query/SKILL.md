---
name: cex-api-query
description: >
  Answers questions about cryptocurrency exchange APIs using the local cex-api-docs
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
  version: "2.8.0"
---

# CEX API Query v2

Answer user questions about cryptocurrency exchange APIs. Route input through classification, search the local doc store, and compose answers with citations.

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
Use cex-api-query skill for this CEX API docs query.
```

Then run classification and the standard workflow below.

Run classification first to route correctly:

```bash
source .venv/bin/activate && cex-api-docs classify "USER_INPUT_HERE" --docs-dir ./cex-docs
```

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
# Search across endpoints + pages
cex-api-docs search-error -- -1002 --exchange binance --docs-dir ./cex-docs

# If error code is in the patterns file, check common meaning first
# e.g. Binance -1002 = "Unauthorized — API key missing or invalid"
```

4. If the search finds endpoint results, get the full record:

```bash
cex-api-docs get-endpoint ENDPOINT_ID --docs-dir ./cex-docs
```

5. Read the source page for full context (some errors require out-of-band steps like the Binance Convert API questionnaire).

**Example:** User pastes "Error -1002: You are not authorized" from Binance Convert API:
- `search-error -- -1002 --exchange binance` → finds Convert endpoint
- `get-endpoint <id>` → shows required permissions
- Page markdown reveals: must complete Convert API questionnaire on binance.com before enabling API access

## Step 3: Endpoint Path Routing

When `input_type == "endpoint_path"`:

```bash
# Direct path lookup (uses SQL LIKE, handles {{url}} prefix)
cex-api-docs lookup-endpoint /sapi/v1/convert/getQuote --method POST --exchange binance --docs-dir ./cex-docs

# Get full record with all fields
cex-api-docs get-endpoint ENDPOINT_ID --docs-dir ./cex-docs

# Browse endpoints by exchange/section
cex-api-docs list-endpoints --exchange okx --section rest --limit 20 --docs-dir ./cex-docs
```

The full endpoint JSON contains:
- `http.method`, `http.path`, `http.base_url` — the API call
- `description` — what the endpoint does
- `request_schema.parameters` — parameters with name, type, required, enum values
- `response_schema.responses` — response structure with examples
- `rate_limit`, `required_permissions`, `error_codes` — if documented (check `field_status`)
- `sources` — citation URLs back to original doc pages

## Step 4: Search Pages

For documentation context beyond endpoint records — authentication flows, conceptual explanations, changelogs, general rules:

```bash
# Primary for natural-language questions (agent-decided rerank):
cex-api-docs semantic-search "how to calculate signature" --exchange binance --docs-dir ./cex-docs --mode hybrid --rerank-policy auto --limit 8

# Use FTS5 only for literal anchors (exact error code/path/header string):
cex-api-docs search-pages "X-MBX-APIKEY -1021 recvWindow" --docs-dir ./cex-docs --limit 5
```

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
import sqlite3
conn = sqlite3.connect('cex-docs/db/docs.db')
row = conn.execute('SELECT markdown_path, word_count FROM pages WHERE canonical_url = ?', ('URL_HERE',)).fetchone()
if row: print(row[0], f'({row[1]} words)')
"
```

Then use the **Read tool** to read the markdown file at that path. Don't use `cat` or `python3` to print it.

**For large single-page docs** (OKX, Gate.io, HTX, etc.), use Grep to find the relevant section within the file first, then Read with an offset.

**Nav chrome:** Most stored pages start with navigation menus and sidebars. The actual content begins at the first `# Heading` that matches the topic. Skip everything before it.

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

- `skill_used`: `cex-api-query@2.8.0`
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

SQLite database at `cex-docs/db/docs.db` with FTS5 indexes on pages and endpoints.

```bash
source .venv/bin/activate && cex-api-docs store-report --docs-dir ./cex-docs
```

**Exchanges with endpoints:** Binance (spot, futures_usdm, futures_coinm, portfolio_margin), OKX (rest), Gate.io (v4), HTX (spot, dm, coin_margined_swap, usdt_swap), Bybit (v5), Bitget (v2), Bitstamp (rest), Bitfinex (v2), Hyperliquid (api), KuCoin (spot, futures), Crypto.com (exchange), Upbit (rest_en), dYdX (docs), Bithumb (rest), Korbit (rest), Coinone (rest), Kraken (spot, futures), Coinbase (advanced_trade, exchange, intx), BitMEX (rest), BitMart (spot), Mercado Bitcoin (rest).

**DEX protocols with pages:** Aster (docs), ApeX (docs), GRVT (docs), Paradex (docs).

**CCXT reference docs:** 188 wiki pages + docs.ccxt.com landing page. Used for cross-reference validation via `ccxt-xref` command.

**Additional sections with pages but no extracted endpoints yet:** Binance (options, margin_trading, wallet, copy_trading, portfolio_margin_pro), Bitget (copy_trading, margin, earn, broker), OKX (websocket, broker, changelog), Bybit (websocket).

**Single-page doc sites:** OKX, Gate.io, HTX, Crypto.com, Bitstamp, Korbit serve their entire API reference from 1-4 large HTML pages (up to 325K words each). When reading these, search within the file — don't print all of it.

## Gotchas

- **Always activate venv first:** `source .venv/bin/activate`
- `{{url}}`** in paths:** Some Postman-imported endpoints have `{{url}}/sapi/v1/...` paths. `lookup-endpoint` handles this automatically.
- **Korean exchanges:** Upbit, Bithumb, Coinone, Korbit docs are partially in Korean.
- **Unresolved **`$ref`**:** OpenAPI-imported request/response schemas may contain `$ref` pointers. If you need the referenced definition, search for the component name in the source page.
- **Negative error codes:** Use `--` before negative numbers in CLI args: `search-error -- -1002`
- **Semantic search requires **`[semantic]`** extra:** If `semantic-search` fails with ImportError, fall back to FTS5.
- **Reranker requires **`[reranker]`** extra:** if reranker import fails, continue with semantic results and mark `rerank_applied: no` + `rerank_reason: reranker_unavailable`.

## Self-Evolution

Update this skill when:
1. **New exchanges added** — update the exchange list
2. **New endpoints extracted** — coverage numbers change (run `store-report` to check)
3. **Better retrieval patterns discovered** — add to routing table or query patterns
4. **Agent fails to find known information** — add the successful search strategy as a pattern

Current version: 2.8.0
