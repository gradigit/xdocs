# CEX API Documentation Intelligence Layer

## What This Is

A system for crawling, understanding, and structuring cryptocurrency exchange API documentation.
Two skills designed for Claude Code:

1. **doc-crawler** — General-purpose documentation crawler (crawl any doc site → SQLite FTS5 index)
2. **cex-api-docs** — CEX/DEX-specific layer on top (endpoint extraction, rate limits, permissions, canonical mapping, CCXT cross-referencing)

## Architecture: AI-Native

The key design decision: **the AI agent handles understanding, scripts handle I/O.**

- **AI does**: crawling decisions, content parsing, endpoint extraction, canonical mapping, confidence scoring, bilingual Korean handling, CCXT cross-referencing
- **Scripts do**: file writes, SQLite indexing, FTS5 search, change detection, review queue management
- **No regex-based parsing, no heuristic extraction** — the agent reads docs like a human

This is intentional. CEX docs are too varied and messy for deterministic parsing. AI reads the page, understands it, extracts structured data, assigns confidence scores.

## What's In This Package

```
doc-crawler/doc-crawler/
├── SKILL.md                        # General crawler skill definition
├── scripts/
│   ├── crawl.py                    # BFS web crawler → SQLite FTS5 + markdown + metadata
│   ├── search.py                   # Query the crawled index
│   └── diff.py                     # Detect changes between crawls
└── references/
    └── storage-schema.md           # SQLite schema + file layout

cex-api-docs/cex-api-docs/
├── SKILL.md                        # CEX-specific skill (this is the main briefing)
├── scripts/
│   ├── save.py                     # Persistence: save pages + endpoints + review queue
│   ├── cex_search.py               # CEX-specific search (by exchange, canonical op, rate limits)
│   └── cex_update.py               # Cron-friendly change detection + alerts
└── references/
    ├── exchanges.md                # Registry of 17+ exchanges with doc URLs, API quirks
    ├── canonical-ops.md            # Canonical operation names (get_open_orders, place_order, etc.)
    └── endpoint-schema.md          # JSON schema for extracted endpoint data
```

## What's Already Decided (Don't Re-Litigate)

These decisions were made after extensive discussion and competitive analysis:

1. **AI-native architecture** — No heuristic parsing. Agent reads pages and extracts structured data.
2. **SQLite FTS5 as primary search** — Not vector search, not embeddings. FTS5 is deterministic, fast, portable.
3. **Playwright as JS fallback** — Most exchange docs are SPA/JS-rendered. If curl gets empty HTML, use Playwright.
4. **Human-seeded canonical mappings** — The canonical ops list in `references/canonical-ops.md` is the starting point. Agent maps exchange endpoints to these.
5. **CCXT as cross-reference only** — Never as source of truth. Official docs always win.
6. **Confidence scoring on every field** — high/medium/low/undocumented. Medium and low go to review queue.
7. **Bilingual for Korean exchanges** — Crawl both English and Korean versions. English primary, Korean authoritative backup.
8. **No existing tool does this** — Verified via market research. CCXT abstracts away the details we need. Context7 doesn't index exchange API docs. Data aggregators provide market data, not doc intelligence.

## Competitive Context

- **CCXT**: Trade execution wrapper. Incomplete rate limit weights (ongoing pain point, see GitHub issues #778, #13949, #18878). Hides endpoint-level details behind unified abstraction.
- **Context7**: Closest concept — indexes 33k+ software library docs for LLM consumption. But only covers software libraries, not exchange API docs. Also does general text chunking, not domain-specific structured extraction.
- **CoinAPI/CoinGecko/etc**: Market data feeds, not documentation intelligence.
- **This project**: Fills the gap. "Context7 for CEX API docs" with domain-specific extraction.

## First Steps for the Agent

1. Read `cex-api-docs/cex-api-docs/SKILL.md` — this is the detailed workflow
2. Read `cex-api-docs/cex-api-docs/references/exchanges.md` — the exchange registry
3. Start with ONE exchange (recommend: Bybit — single v5 API, clean docs, moderate complexity)
4. Follow the workflow: Find docs → Crawl → Parse/Extract → Canonical Map → Save
5. Verify scripts work: test `save.py`, `cex_search.py` against the extracted data
6. Then expand to Binance (harder: 4+ separate doc sites, complex rate limit weights)

## Dependencies

```bash
pip install requests beautifulsoup4 html2text --break-system-packages
# For JS-rendered doc sites:
pip install playwright --break-system-packages && playwright install chromium
```

## Target Exchanges (Priority Order)

Tier 1 (do first): Binance, OKX, Bybit, Bitget
Tier 2: Gate.io, KuCoin, HTX, Crypto.com
Tier 3: Bitstamp, Bitfinex
DEX: dYdX, Hyperliquid
Korean: Upbit, Bithumb, Coinone, Korbit

## Pain Points This Solves

| Pain Point | How |
|---|---|
| Outdated/wrong doc URLs | Web search to verify, content hash change detection |
| Rate limit weights per endpoint | AI reads rate limit tables/sections, extracts per-endpoint weights |
| Permission requirements per endpoint | AI reads permission docs, maps to endpoints |
| Error codes across exchanges | AI extracts error code tables, cross-references |
| Cross-exchange endpoint comparison | Canonical operation mapping |
| Bilingual Korean exchange docs | Crawl both versions, Korean as authoritative backup |
| Doc change detection/alerting | Content hash tracking, cex_update.py for cron |
