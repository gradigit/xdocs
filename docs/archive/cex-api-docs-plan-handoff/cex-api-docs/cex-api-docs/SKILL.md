---
name: cex-api-docs
description: >
  CEX/DEX API documentation crawler, parser, and retrieval system. AI-native: the agent itself
  crawls, reads, understands, and extracts structured endpoint data — no heuristic regex parsing.
  Handles canonical endpoint mapping, rate limits, permissions, error codes, multi-API-URL
  awareness (sapi/fapi/papi), version detection, CCXT cross-referencing, and bilingual Korean
  exchange docs. Use when: needing CEX/DEX API endpoint info, checking permissions, looking up
  rate limits, finding error codes, comparing exchanges, or building an offline API doc cache.
  Covers Binance, OKX, Bybit, Bitget, Gate.io, KuCoin, HTX, Crypto.com, Bitstamp, Bitfinex,
  dYdX, Hyperliquid, Upbit, Bithumb, Coinone, Korbit and more. Every fact cited with source
  URL. Designed for dedicated retrieval sessions to avoid context bloat.
---

# CEX API Docs

## Architecture: What the AI Does vs What Scripts Do

**The AI agent** (you, running in Claude Code) handles:
- Finding official doc pages (web search to verify correct/latest URL)
- Crawling pages (fetch + read + decide what to follow)
- Understanding content (is this an endpoint page? marketing? changelog?)
- Extracting structured endpoint data (reading docs like a human would)
- Canonical mapping (understanding that OKX's "orders-pending" = Binance's "openOrders")
- CCXT cross-referencing (reading CCXT source code and comparing)
- Bilingual handling (reading both Korean + English versions)
- Confidence scoring (how certain are you about each extracted fact?)

**Scripts** handle only deterministic I/O:
- `save.py` — Write structured data to files + SQLite index
- `cex_search.py` — Query the saved index (FTS5 search, endpoint lookup)
- `cex_update.py` — Cron-friendly change detection + Slack alerts

This separation is intentional. AI is better at understanding docs. Scripts are better at
file management and search indexing. Never use regex heuristics for parsing API docs.

## Workflow

### Step 1: Find Official Documentation

Do NOT rely on the registry URLs blindly — they may be outdated. For each exchange:

1. Web search: `"{exchange_name} official API documentation {year}"`
2. Verify the URL is on the exchange's official domain
3. Check for version info — always find the **latest** API version
4. Check the registry (`references/exchanges.md`) and update if the URL has changed

For Korean exchanges (Upbit, Bithumb, Coinone, Korbit): find BOTH the Korean and English
doc URLs. Most provide English versions. Crawl English as primary, Korean as authoritative
backup.

### Step 2: Crawl (AI-Driven)

For each exchange doc site, the agent reads pages and follows links intelligently:

1. Fetch the entry page (use curl/requests; if content is empty or JS-only, install and
   use Playwright: `pip install playwright && playwright install chromium`)
2. Read the page content — understand its structure
3. Identify all navigation links (sidebar, table of contents, "next page" links)
4. Decide which links lead to API endpoint docs vs marketing/changelog/irrelevant
5. Follow relevant links, reading each page
6. For each page, save raw content using `scripts/save.py`
7. Continue until all endpoint documentation pages are covered

**Critical**: Do not stop at the first page. CEX docs are deeply nested. Check for:
- Sidebar navigation with expandable sections
- "Next" / pagination links
- Separate pages per endpoint or per category
- Separate sections for spot/futures/margin/websocket
- Sub-pages for authentication, rate limiting, error codes

**Crawl depth guidance by exchange** (see `references/exchanges.md` for full details):
- Binance: 4+ separate doc sites (spot, futures USDM, futures COINM, portfolio margin)
- OKX: single unified doc but very deep (trade/market/account/asset/sub-account/earn)
- Bybit: single v5 doc, organized by category parameter
- Korean exchanges: usually simpler structure, fewer pages

### Step 3: Parse (AI-Driven)

As you read each page (or after crawling), extract structured endpoint data following the
schema in `references/endpoint-schema.md`. For each endpoint found:

1. **Read the full page context** — don't just grab the first table you see
2. **Extract all fields** from the schema: method, path, params, permissions, rate limits,
   error codes, request/response examples
3. **Assign confidence scores**:
   - `high`: the information is explicitly and clearly stated on the page
   - `medium`: the information is present but ambiguous or could be interpreted differently
   - `low`: you're inferring this from context, it's not explicitly documented
4. **Flag unknowns**: if permissions aren't documented for an endpoint, say so explicitly
   rather than guessing. Set `"permissions": {"permissions": [], "confidence": "undocumented"}`
5. **Save using** `scripts/save.py`

**Exchange-specific parsing notes** (see `references/exchanges.md`):
- Binance: different URL prefixes mean different APIs (sapi/fapi/papi/dapi)
- Binance: endpoint weights vary by parameter (e.g., with vs without symbol)
- OKX: all under /api/v5/ — the next path segment determines the section
- Hyperliquid: not REST — all POST to /info or /exchange with JSON body discriminators
- Korean exchanges: check both language versions; Korean may have more detail

### Step 4: Canonical Mapping (AI-Driven)

After extracting endpoints, map them to canonical operations from `references/canonical-ops.md`.

Rules:
- Only map when you're confident the endpoint does the same thing as the canonical operation
- One endpoint can map to multiple canonical ops (e.g., a "get account" that returns both
  balances and positions)
- If no canonical op fits, tag as `unmapped` and suggest a new canonical name
- **Never modify the original extracted data** — canonical mapping is additive metadata
- Include your reasoning: "Mapped to get_open_orders because this endpoint returns all
  unfilled orders for the account, matching the canonical description"

### Step 5: CCXT Cross-Reference (AI-Driven)

If CCXT reference is needed:

1. Clone the CCXT repo: `git clone --depth 1 https://github.com/ccxt/ccxt.git`
2. Read the exchange's implementation file: `ts/src/{exchange}.ts`
3. Read the exchange config: look for URL patterns, endpoint definitions, method mappings
4. For each extracted endpoint, check if CCXT implements it and note:
   - Does CCXT use the same endpoint path?
   - Are there parameter differences?
   - Does CCXT document anything the official docs don't (or vice versa)?
5. **Official docs always win**. CCXT is reference only. Flag discrepancies clearly.

### Step 6: Save & Index

Use `scripts/save.py` to persist all extracted data:

```bash
# Save a single endpoint
python3 scripts/save.py --save-endpoint endpoint.json --docs-dir ./cex-docs

# Save a batch of endpoints
python3 scripts/save.py --save-batch endpoints/ --docs-dir ./cex-docs

# Save a raw crawled page
python3 scripts/save.py --save-page --url "https://..." --content page.md --docs-dir ./cex-docs

# Rebuild search index
python3 scripts/save.py --reindex --docs-dir ./cex-docs
```

### Step 7: Human Review

After parsing, any items with `medium` or `low` confidence go to the review queue:

```bash
# Show pending review items
python3 scripts/save.py --review-queue --docs-dir ./cex-docs

# After human confirms, mark as reviewed
python3 scripts/save.py --approve --id <item_id> --docs-dir ./cex-docs
```

Once confirmed by human → the item's confidence is set to `verified` → future crawls only
need to re-review if the source page content hash changes (i.e., the exchange updated their docs).

## Subagent Strategy (Claude Code)

For parallel crawling/parsing, spawn one Claude Code subagent per exchange:

```bash
# In your orchestrator session:
claude-code "Read the cex-api-docs skill. Crawl and parse Binance spot API docs. \
  Save to ./cex-docs/" &

claude-code "Read the cex-api-docs skill. Crawl and parse OKX unified API docs. \
  Save to ./cex-docs/" &

claude-code "Read the cex-api-docs skill. Crawl and parse Bybit v5 API docs. \
  Save to ./cex-docs/" &

wait
```

Each subagent reads this SKILL.md, reads the exchange registry, crawls independently,
and saves to the shared `./cex-docs/` directory. SQLite with WAL mode handles concurrent writes.

For finer parallelism (e.g., Binance spot + Binance futures in parallel):

```bash
claude-code "Crawl Binance spot docs only (binance-docs.github.io/apidocs/spot/en/). \
  Save to ./cex-docs/" &
claude-code "Crawl Binance USDM futures docs only (binance-docs.github.io/apidocs/futures/en/). \
  Save to ./cex-docs/" &
```

## Retrieval (from working session)

In your actual working session (not the crawl session), search the saved docs:

```bash
# Search for endpoint info
python3 scripts/cex_search.py --query "open orders" --exchange binance

# Cross-exchange comparison
python3 scripts/cex_search.py --canonical "get_open_orders"

# Rate limits
python3 scripts/cex_search.py --rate-limits --exchange binance --section futures_usdm

# Permissions for an endpoint
python3 scripts/cex_search.py --permissions --endpoint "POST /fapi/v1/order" --exchange binance

# Error codes
python3 scripts/cex_search.py --error-code "-1021" --exchange binance

# Get full page content for a specific URL
python3 scripts/cex_search.py --url "https://binance-docs.github.io/apidocs/futures/en/#new-order-trade"
```

## Critical Rules

1. **Source of truth is ALWAYS official exchange documentation** — never CCXT, never inferred
2. **Every fact needs a source URL and crawl timestamp** — no exceptions
3. **Never fabricate endpoint info** — if not documented, mark as "undocumented"
4. **Confidence scoring is mandatory** — high/medium/low/undocumented for every field
5. **Human review for medium/low confidence** — don't trust your own parsing blindly
6. **Canonical mappings are additive** — original exchange data is never modified
7. **Always get latest API version** — verify via web search, don't assume
8. **Store bilingual for Korean exchanges** — English primary, Korean authoritative backup
9. **CCXT is cross-reference only** — flag discrepancies, never override official docs
10. **Prefer fetching the page over guessing** — if unsure, read the actual page again
