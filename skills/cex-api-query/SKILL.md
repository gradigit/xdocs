---
name: cex-api-query
description: >
  Answers questions about cryptocurrency exchange APIs using the local cex-api-docs
  SQLite store. Searches endpoints and documentation pages across 16 exchanges.
  Activates when user asks about exchange API endpoints, rate limits, authentication,
  parameters, error codes, or mentions Binance, OKX, Bybit, Bitget, KuCoin, Gate.io,
  HTX, Crypto.com, Bitstamp, Bitfinex, dYdX, Hyperliquid, Upbit, Bithumb, Coinone,
  or Korbit API documentation.
metadata:
  version: "1.0.0"
---

# CEX API Query

Answer user questions about cryptocurrency exchange APIs by searching a local doc store.

## Workflow

- [ ] 1. Identify the exchange and topic from the user's question
- [ ] 2. Search endpoints and/or pages for relevant results
- [ ] 3. Read stored markdown for full context when snippets aren't enough
- [ ] 4. Synthesize a readable answer with source URLs
- [ ] 5. If nothing found, say so — never guess

## What's In The Store

SQLite database at `cex-docs/db/docs.db` with FTS5 indexes on pages and endpoints.

Run `store-report` to see current coverage:

```bash
source .venv/bin/activate && cex-api-docs store-report --docs-dir ./cex-docs
```

**Exchanges with endpoints:** Binance (spot, futures_usdm, futures_coinm, portfolio_margin), OKX (rest), Gate.io (v4), HTX (spot, dm, coin_margined_swap, usdt_swap), Bybit (v5), Bitget (v2), Bitstamp (rest), Bitfinex (v2), Hyperliquid (api), KuCoin (spot, futures), Crypto.com (exchange), Upbit (rest_en), dYdX (docs), Bithumb (rest), Korbit (rest), Coinone (rest).

**Additional sections with pages but no extracted endpoints yet:** Binance (options, margin_trading, wallet, copy_trading, portfolio_margin_pro), Bitget (copy_trading, margin, earn, broker), OKX (websocket, broker, changelog), Bybit (websocket).

**Single-page doc sites:** OKX, Gate.io, HTX, Crypto.com, Bitstamp, Korbit serve their entire API reference from 1-4 large HTML pages (up to 325K words each). When reading these, search within the file — don't print all of it.

## Step 1: Search Endpoints

Use when the user asks about a specific API endpoint, method, path, or parameters.

```bash
source .venv/bin/activate

# Search by keyword, scoped to an exchange
cex-api-docs search-endpoints "place order" --exchange binance --docs-dir ./cex-docs

# Broader search across all exchanges
cex-api-docs search-endpoints "withdraw" --docs-dir ./cex-docs --limit 10
```

This returns JSON with `endpoint_id`, `exchange`, `section`, `method`, `path`, and a `snippet`.

To get the **full endpoint record** (parameters, schemas, rate limits):

```bash
python3 -c "
import sqlite3, json
conn = sqlite3.connect('cex-docs/db/docs.db')
row = conn.execute('SELECT json FROM endpoints WHERE endpoint_id = ?', ('ENDPOINT_ID',)).fetchone()
if row: print(json.dumps(json.loads(row[0]), indent=2))
"
```

The endpoint JSON contains:
- `http.method`, `http.path`, `http.base_url` — the API call
- `description` — what the endpoint does
- `request_schema.parameters` — parameters with name, type, required, enum values
- `response_schema.responses` — response structure with examples
- `rate_limit`, `required_permissions`, `error_codes` — if documented (check `field_status`)
- `sources` — citation URLs back to original doc pages

Note: OpenAPI-imported endpoints may have unresolved `$ref` values in schemas.

## Step 2: Search Pages

Use for documentation context beyond endpoint records — authentication flows, conceptual explanations, changelogs, general rules.

```bash
cex-api-docs search-pages "rate limit weight" --docs-dir ./cex-docs --limit 5
```

Returns JSON with `canonical_url`, `title`, `snippet`, and `rank`.

## Step 3: Read Full Page Content

When you find the right page but need more than the snippet, get the file path and read it directly.

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

**For large single-page docs** (OKX, Gate.io, HTX, etc.), use Grep to find the relevant section within the file first, then Read with an offset:

```bash
# Find the section heading offset
grep -n "universal transfer\|Universal Transfer" /path/to/file.md
```

Then Read from that line number with a limit.

**Nav chrome:** Most stored pages start with navigation menus and sidebars. The actual content begins at the first `# Heading` that matches the topic. Skip everything before it.

## Step 4: Synthesize

Present the answer with:
- The endpoint: `METHOD /path` at `base_url`
- Parameters table (name, type, required, description)
- Key rules or usage notes from the doc content
- Response example if available
- Source URL for reference

## Step 5: When Information Is Missing

- **Exchange not in store:** Tell the user which exchanges are available.
- **No search results:** Try broader keywords. Try `search-pages` if `search-endpoints` found nothing, and vice versa. After 2-3 searches with no useful results, tell the user the topic isn't covered in the stored docs.
- **Endpoint found but fields are "unknown":** The endpoint record exists but that specific detail (rate limit, permissions, error codes) wasn't extracted. Check `field_status` to see what's documented vs unknown. Search pages for the missing info.
- **Partial information:** Present what you found and note what's missing. Don't fill gaps with guesses.

## Query Patterns

### "What endpoint do I use to X?"
Search endpoints → get full JSON → present method, path, params, response.

### "How does authentication/signing work on X?"
Search pages for auth/signing docs → read the markdown section → extract the procedure.

### "What are the rate limits for X?"
Search endpoints (check `rate_limit` and `field_status`) + search pages for "rate limit" → combine.

### "What parameters does X need?"
Search endpoints → get full JSON → extract `request_schema.parameters` into a table.

### "Compare X on exchange A vs B"
Run searches on both exchanges → present side by side.

### "What error codes does X return?"
Search endpoints (check `error_codes`) + search pages for "error" → combine.

## Example

**User asks:** "What endpoint do I need to transfer between my Binance master account and a sub-account?"

**Agent workflow:**

1. Search endpoints:
```bash
cex-api-docs search-endpoints "sub account transfer" --exchange binance --docs-dir ./cex-docs
```
Finds `POST /sapi/v1/sub-account/universalTransfer` — "Universal Transfer (For Master Account)"

2. Get full endpoint record by endpoint_id → extracts parameters:
   - `fromAccountType` (required): enum `SPOT`, `USDT_FUTURE`, `COIN_FUTURE`, `MARGIN`, `ISOLATED_MARGIN`
   - `toAccountType` (required): same enum
   - `fromEmail` (optional): defaults to master if omitted
   - `toEmail` (optional): defaults to master if omitted
   - `asset` (required), `amount` (required)

3. Search pages for the doc URL:
```bash
cex-api-docs search-pages "universalTransfer fromAccountType toAccountType" --docs-dir ./cex-docs
```
Finds `https://developers.binance.com/docs/sub_account/asset-management/Universal-Transfer`

4. Read the stored markdown → extracts key rules:
   - Must enable "internal transfer" on the API key
   - Transfer from master by default if `fromEmail` omitted
   - SPOT can transfer to/from USDT_FUTURE, COIN_FUTURE, MARGIN
   - Rate limit: weight 1 (IP) / 360 (UID)

**Agent presents:**

> **Endpoint:** `POST /sapi/v1/sub-account/universalTransfer` at `https://api.binance.com`
>
> | Parameter | Type | Required | Description |
> |-----------|------|----------|-------------|
> | toEmail | STRING | No | Sub-account email (defaults to master) |
> | fromAccountType | STRING | Yes | SPOT, USDT_FUTURE, COIN_FUTURE, MARGIN, ISOLATED_MARGIN |
> | toAccountType | STRING | Yes | Same options |
> | asset | STRING | Yes | e.g. USDT |
> | amount | DECIMAL | Yes | |
>
> You must enable "internal transfer" on your API key. Omit `fromEmail` to transfer from master.
>
> **Source:** https://developers.binance.com/docs/sub_account/asset-management/Universal-Transfer

## Gotchas

- **Always activate venv first:** `source .venv/bin/activate`
- **`{{url}}` in paths:** Some Postman-imported endpoints have `{{url}}/sapi/v1/...` paths. The clean version without `{{url}}` also exists — prefer it.
- **Korean exchanges:** Upbit, Bithumb, Coinone, Korbit docs are partially in Korean.
- **Unresolved `$ref`:** OpenAPI-imported request/response schemas may contain `$ref` pointers. If you need the referenced definition, search for the component name in the source page.

## Self-Evolution

Update this skill when:
1. **New exchanges added** — update the exchange list
2. **New endpoints extracted** — coverage numbers change (run `store-report` to check)
3. **Better retrieval patterns discovered** — add to Query Patterns
4. **Agent fails to find known information** — add the successful search strategy as a pattern

Current version: 1.0.0
