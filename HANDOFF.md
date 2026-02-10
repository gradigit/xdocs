# Context Handoff — 2026-02-11

## First Steps (Read in Order)
1. Read CLAUDE.md — project context, architecture, conventions
2. Read TODO.md — current task list (points to `todos/` directory)
3. Read docs/reports/poc-playwright-vs-http-binance.md — POC findings

## Session Summary

### What Was Done
- Ran POC comparing three fetch methods for Binance API docs:
  - HTTP fetch (project pipeline) vs Playwright MCP vs agent-browser CLI
  - Tested 5 representative pages (account-endpoints, limits, general-info, error-codes, trading-endpoints)
  - Verdict: **HTTP fetch is sufficient** — Binance uses Docusaurus SSR, all content server-rendered
- Updated skills/cex-api-docs/SKILL.md: replaced deprecated crawl references with sync/inventory/fetch pipeline, added store-report, quality commands, import specs, review queue sections
- CLAUDE.md quality audit (B → B+): moved `extract_page_markdown` return tuple to Gotchas, cleaned Current Phase, added test commands
- Updated .doc-manifest.yaml with new report and sync timestamp

### Current State
- Branch: main
- Last commit: 86e6097 — docs: POC Playwright vs HTTP fetch for Binance + skill update
- Working tree: clean (except HANDOFF.md and temp screenshot)
- All 20 todos: complete
- All 20 tests: passing

### What's Next
1. Consider adding optional `content_selector` (e.g., `article`) to HTML-to-markdown pipeline to strip ~57 lines of nav noise per page
2. Run a real `cex-api-docs sync` against Binance to validate end-to-end with the regex fixes from the deep-review session
3. Try the "wow query" demo per docs/runbooks/binance-wow-query.md
4. Test other exchanges that may need Playwright (JS-rendered SPAs)

### Failed Approaches
- First HTTP fetch test script unpacked `extract_page_markdown` return tuple incorrectly — the function returns `(html, title, md_norm, word_count)`, not `(md_norm, title, config_hash, word_count)`. Added to CLAUDE.md Gotchas to prevent recurrence.
- Regex counting for code blocks/tables in HTTP markdown initially showed 0 — `html2text` uses `[code]...[/code]` and pipe-less table syntax, not triple-backtick fenced blocks or `|`-prefixed rows. Content was present, just different format.

### Key Context
- Binance docs at developers.binance.com run Docusaurus v3.4.0 with SSR (`data-has-hydrated="false"`)
- HTTP fetch gets identical headings and endpoint signatures as browser-based methods
- HTTP word counts are ~16-19% higher due to navigation/sidebar noise (~57 lines per page)
- `html2text` produces `[code]...[/code]` blocks (not fenced) and pipe-less tables — content is complete but format differs from standard markdown
- agent-browser loses all formatting (tables become run-on text, JSON one-liners) — not suitable for structured content extraction

## Reference Files
| File | Purpose |
|------|---------|
| CLAUDE.md | Project context, architecture, conventions |
| TODO.md | Points to `todos/` for work tracking |
| docs/reports/poc-playwright-vs-http-binance.md | Full POC comparison report |
| skills/cex-api-docs/SKILL.md | Updated agent skill definition |
| src/cex_api_docs/page_store.py | `extract_page_markdown` — returns (html, title, md_norm, wc) |
| src/cex_api_docs/httpfetch.py | HTTP fetch function used in POC |
| src/cex_api_docs/playwrightfetch.py | Existing Playwright fallback |
| docs/runbooks/binance-wow-query.md | Demo runbook for "wow query" |
