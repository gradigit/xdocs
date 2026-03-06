# TODO — Exhaustive Crawl Targets Bible

## Goal
Produce a reference document ("Bible") cataloging ALL crawlable API documentation sources for every exchange in our registry, plus gap analysis and registry updates. The Bible becomes the authoritative source for maintaining exchanges.yaml entries and onboarding new exchanges.

## Context — What We Already Have

- **35 exchanges, 61 sections** in `data/exchanges.yaml`
- **5,716 pages, 7.7M words** crawled and indexed
- **3,603 structured endpoints** across 35 sections (29 sections still have 0 endpoints)
- **28 sitemaps** configured across 13 exchanges
- **CCXT wiki** synced (188 pages) + `ccxt_xref.py` cross-reference tool (20/21 CEXes mapped)
- **OpenAPI imports** completed: bitmex, mercadobitcoin, coinbase/intx
- **Crawl validation pipeline**: 10-phase (sanitization, extraction verify, sitemap health, nav extraction, URL discovery, live validation, coverage audit, gap backfill, link checks)
- **Known single-page sites** (correct, not fixable): OKX, HTX, Gate.io, BitMart, Bitstamp, Crypto.com, Korbit

## What the Generic Prompt Gets Wrong

- Lists 12 exchanges — we have 35 (21 CEX, 13 DEX, 1 ref)
- Suggests crawling Discord/Telegram/StackOverflow — waste of time, not crawlable for our pipeline
- Suggests Wayback Machine — we need current docs, not historical
- Suggests "hidden docs from CCXT describe()" — we already researched this; cite-only constraint prevents generating synthetic docs from CCXT data
- Suggests Google cache probing — fragile, not reproducible
- Suggests developer forums — dead for every exchange
- The "Known URLs" table is outdated vs our registry
- Some platform probing patterns are useful (ReadMe.io changelog RSS, Swagger path probing, GitHub deep dive for OpenAPI specs)

## Milestones

## Milestone 1: Audit Existing Coverage & Produce Gap Analysis
- **Goal**: For each of 35 exchanges, document what we have (pages, endpoints, sitemaps, OpenAPI imports) vs what's available but not yet captured
- **Dependencies**: none
- **Files in scope**: own: [architect/research/*], read: [data/exchanges.yaml, cex-docs/db/docs.db, src/cex_api_docs/ccxt_xref.py]
- **Quality criteria**: Every exchange has a coverage assessment. Gap list is concrete (specific URLs, not vague "might exist").
- **Research needed**: Compare registry entries against actual doc site structure for each exchange
- **Steps**:
  1. Generate per-exchange coverage summary from DB + registry
     - Success criteria: Table with columns: exchange, sections, pages, endpoints, has_sitemap, has_openapi, has_changelog, platform_type
     - Artifacts: `architect/research/coverage-audit.md`
  2. Run ccxt_xref for all 20 mapped exchanges to quantify endpoint gaps
     - Success criteria: Summary of missing_from_us counts per exchange
     - Artifacts: `architect/research/ccxt-xref-gaps.md`
  3. Identify which 29 zero-endpoint sections could benefit from OpenAPI/Postman imports
     - Success criteria: List of sections with known importable spec URLs
     - Artifacts: included in coverage-audit.md

## Milestone 2: Deep Discovery — CEX Exchanges (parallel)
- **Goal**: For each CEX exchange (21 total), research all documentation sources using systematic probing
- **Dependencies**: Milestone 1 (need gap analysis to focus effort)
- **Files in scope**: own: [architect/research/exchanges/*], read: [data/exchanges.yaml]
- **Quality criteria**: Every discovered URL is verified live (HTTP 200). Platform type identified. Changelog/RSS feeds discovered where they exist.
- **Research needed**: Per-exchange probing (sitemaps, robots.txt, GitHub repos, OpenAPI specs, ReadMe.io changelogs, Postman collections)
- **Steps**:
  1. Research Tier 1 CEXes (Binance, OKX, Bybit, Bitget, KuCoin, Gate.io) — parallel fan-out
     - Success criteria: Per-exchange findings doc with all checklist items filled
     - Artifacts: `architect/research/exchanges/{exchange}.md`
  2. Research Tier 2 CEXes (Bitfinex, HTX, Crypto.com, Bitstamp, Kraken, Coinbase, dYdX) — parallel
     - Success criteria: Same checklist completion
     - Artifacts: `architect/research/exchanges/{exchange}.md`
  3. Research Tier 3 CEXes (Upbit, Bithumb, Coinone, Korbit, BitMEX, BitMart, WhiteBIT, Bitbank, MercadoBitcoin, Hyperliquid) — parallel
     - Success criteria: Same checklist completion
     - Artifacts: `architect/research/exchanges/{exchange}.md`

## Milestone 3: Deep Discovery — DEX Protocols + CCXT
- **Goal**: For each DEX protocol (13 total) and CCXT, research all documentation sources
- **Dependencies**: Milestone 1
- **Files in scope**: own: [architect/research/exchanges/*], read: [data/exchanges.yaml]
- **Quality criteria**: Same as M2. Additionally: identify which DEXes have OpenAPI specs or structured endpoint docs vs just narrative docs.
- **Research needed**: DEX docs are often on GitBook/Docusaurus — platform detection matters for crawl method
- **Steps**:
  1. Research Tier 1 DEXes (Aster, ApeX, GRVT, Paradex) + Tier 2 candidates (Orderly, Pacifica, Nado, Bluefin) — parallel
     - Success criteria: Per-DEX findings, Tier 2 candidates assessed for viability
     - Artifacts: `architect/research/exchanges/{exchange}.md`
  2. Research remaining DEXes (GMX, Drift, Aevo, Perp, Gains, Kwenta, Lighter) — parallel
     - Success criteria: Same checklist
     - Artifacts: `architect/research/exchanges/{exchange}.md`
  3. Research CCXT ecosystem
     - Success criteria: All CCXT doc sources cataloged (wiki, exchange implementations, changelogs, exchanges.json)
     - Artifacts: `architect/research/exchanges/ccxt.md`

## Milestone 4: Compile Bible Document + Registry Updates
- **Goal**: Consolidate all findings into the Bible reference document and produce actionable registry updates
- **Dependencies**: Milestones 2, 3
- **Files in scope**: own: [docs/crawl-targets-bible.md, architect/research/registry-updates.md], read: [architect/research/exchanges/*, data/exchanges.yaml]
- **Quality criteria**: Bible document has all 35 exchanges + CCXT. Cross-exchange summary tables complete. New Exchange Template included. Registry update diff is concrete.
- **Research needed**: none (consolidation only)
- **Steps**:
  1. Compile per-exchange sections into Bible document
     - Success criteria: `docs/crawl-targets-bible.md` exists with all 35+CCXT sections
     - Artifacts: `docs/crawl-targets-bible.md`
  2. Generate cross-exchange summary tables
     - Success criteria: Tables for: platform types, changelog availability, OpenAPI spec availability, GitHub repos, crawl methods needed
     - Artifacts: included in Bible
  3. Create New Exchange Template (reusable checklist)
     - Success criteria: Template section in Bible with step-by-step discovery process
     - Artifacts: included in Bible
  4. Produce registry update recommendations
     - Success criteria: Concrete list of changes to exchanges.yaml (new sitemaps, seed URLs, doc_sources, scope_prefixes, render modes)
     - Artifacts: `architect/research/registry-updates.md`
