# Context Handoff — 2026-02-11

## First Steps (Read in Order)
1. Read CLAUDE.md — project context, architecture, conventions
2. Read TODO.md — current task queue (file-based in `todos/`)
3. Read docs/reports/poc-full-binance-http-playwright-jina.md — latest POC findings

## Session Summary

### What Was Done
- **Full-scale POC**: Compared HTTP vs Playwright vs Jina Reader on all 1,072 Binance English doc pages
  - HTTP: 1,072/1,072, 785K words, 275s — best speed and code formatting
  - Playwright: 1,072/1,072, 477K words, 1,288s — 74 thin pages from article extraction
  - Jina: 1,070/1,072, 805K words, 2,488s — collapses `<pre><code>` blocks into inline code (deal-breaker)
  - **Verdict**: HTTP fetch remains the best method for all exchanges
- **Full 16-exchange sync**: Synced all exchanges via HTTP — 2,286 pages, 3.13M words, zero errors
- **Registry expansion**: Added 5 missing doc sections:
  - HTX: derivatives, coin_margined_swap, usdt_swap (241K additional words)
  - OKX: broker, changelog (60K additional words)
- **Docs sync**: Updated CLAUDE.md (current phase, gotchas, session learnings), ran quality audit (Grade B, 88/100)

### Current State
- **Store**: 2,286 pages, 3,133,962 words across 16 exchanges (28 sections) in `cex-docs/` (731 MB)
- **Branch**: main
- **Last commit**: e79fc63 — feat: full 16-exchange sync + POC HTTP vs Playwright vs Jina

### What's Next
1. Work through `todos/` queue (prioritized follow-ups)
2. Run endpoint ingest on the freshly synced docs
3. Test the "wow query" demo: `docs/runbooks/binance-wow-query.md`
4. Consider Gate.io re-sync with longer delays (currently 403 after rate limiting)

### Failed Approaches
- **Jina Reader for API docs**: Collapses `<pre><code>` blocks into single-line inline code spans — JSON responses become unreadable. Not usable for technical documentation.
- **Playwright for Binance**: Works but 5x slower than HTTP with no content advantage. Binance uses Docusaurus SSR, so all content is server-rendered.

### Key Context
- **Single-page doc exchanges**: OKX (224K words), Gate.io (256K), HTX (325K across 4 pages), Crypto.com (35K), Bitstamp (22K), Korbit (25K) serve full API refs from 1-2 HTML files. Low page counts are not errors.
- **Gate.io rate-limits**: Returns 403 after syncing. Data is in the store; re-sync needs longer delays or `--render auto`.
- **Binance sitemap is 404**: Pipeline falls back to link-follow automatically.

## Reference Files
| File | Purpose |
|------|---------|
| data/exchanges.yaml | Exchange registry — 16 exchanges, 28 sections |
| scripts/poc_full_binance.py | Full POC script (discover + 3-method fetch + compare) |
| docs/reports/poc-full-binance-http-playwright-jina.md | Full POC comparison report |
| docs/reports/poc-playwright-vs-http-binance.md | Earlier 5-page sample POC |
| CLAUDE.md | Project context, architecture, conventions |
| todos/ | Prioritized work queue |
