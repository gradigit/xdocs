# POC: Playwright vs HTTP Fetch for Binance API Docs

**Date:** 2026-02-11
**Pages tested:** 5 representative Binance doc pages (account-endpoints, limits, general-info, error-codes, trading-endpoints)
**Methods compared:** HTTP fetch (project pipeline), Playwright MCP, agent-browser CLI

## Raw Data

### Word Counts

| Page | HTTP | Playwright MCP | agent-browser |
|------|------|----------------|---------------|
| account-endpoints | 2393 | 2008 | 1706 |
| limits | 517 | 353 | 354 |
| general-info | 2583 | 2051 | 1988 |
| error-codes | 144 | 31 | 29 |
| trading-endpoints | 8369 | 7827 | 6584 |

### Endpoint Signatures (GET/POST/PUT/DELETE + path)

| Page | HTTP | Playwright MCP | agent-browser |
|------|------|----------------|---------------|
| account-endpoints | 14 | 14 | 14 |
| limits | 0 | 0 | 0 |
| general-info | 10 | 6 | 6 |
| error-codes | 0 | 0 | 0 |
| trading-endpoints | 20 | 20 | 20 |

### Headings

| Page | HTTP | Playwright MCP |
|------|------|----------------|
| account-endpoints | 15 | 15 |
| limits | 4 | 4 |
| general-info | 25 | 25 |
| error-codes | 1 | 1 |
| trading-endpoints | 18 | 18 |

## Key Findings

### 1. Binance uses Docusaurus SSR

Confirmed by `data-has-hydrated="false"` in the raw HTML `<html>` tag. All documentation content is server-side rendered. JavaScript is used only for interactivity (search, sidebar collapse, theme toggle), not for rendering content.

### 2. Headings: identical across HTTP and Playwright

Zero content structure loss from plain HTTP fetch.

### 3. Endpoint signatures: match or HTTP gets more

HTTP picks up 4 extra endpoint paths on the general-info page because it includes sidebar navigation content that references endpoint paths. For all other pages, counts are identical across all three methods.

### 4. HTTP word counts are consistently higher

The delta (16-19% for content pages) is navigation/sidebar noise (~57 lines per page). This includes sidebar links, language picker, search button, and footer. This doesn't hurt FTS5 search — more text means more searchable context.

### 5. Code blocks and tables: present in all methods, different format

- **HTTP + html2text**: `[code]...[/code]` blocks with indentation; pipe-less table syntax (`Name| Type| ...`). Content is complete.
- **Playwright MCP**: DOM-level access to `<pre><code>` and `<tr>` elements. Can extract structured data.
- **agent-browser**: Pure `innerText` — tables collapse into run-on strings (`NameTypeMandatoryDescription...`), JSON code blocks lose newlines and become single-line strings.

### 6. Error-codes page is intentionally tiny

The page just says "see Errors Codes page" with a link to the full error list. All three methods capture this correctly.

## Content Scoping

| Method | Scope | Nav noise |
|--------|-------|-----------|
| HTTP + html2text | Full page | ~57 lines of sidebar, footer, language picker per page |
| Playwright MCP (`article` selector) | Article only | None |
| agent-browser (`get text "article"`) | Article only | None |

## Formatting Quality

| Method | Code blocks | Tables | JSON examples |
|--------|------------|--------|---------------|
| HTTP + html2text | `[code]...[/code]` with indentation (359 indented lines on account-endpoints) | `Name\| Type\| Mandatory\| Description` format | Multi-line, readable |
| Playwright MCP | DOM `<pre><code>` elements (56 on account-endpoints) | DOM `<tr>` elements (94 on account-endpoints) | Structured, extractable |
| agent-browser | Collapsed to single-line plaintext | Run-on strings, no structure | One-liner, hard to parse |

## Ergonomics

| Method | Speed | Complexity | Dependencies |
|--------|-------|-----------|--------------|
| HTTP fetch | Fastest (~200ms/page) | Built-in pipeline | requests, html2text |
| Playwright MCP | Slow (~3-5s/page) | JS evaluate for custom extraction | Playwright browser |
| agent-browser | Slow (~3-5s/page) | Simple CLI commands | agent-browser npm package |

## Verdict

**HTTP fetch is sufficient for Binance docs.** Playwright and agent-browser add no content value for SSR sites. The existing `_needs_playwright` fallback heuristic (triggers on HTTP 4xx or word_count=0) correctly never fires for Binance.

## Recommendations

1. **Do not** set `render_mode: auto` for Binance in `exchanges.yaml` — adds latency with zero content benefit.
2. **Consider** adding optional `content_selector` (e.g., `article`) to the HTML-to-markdown pipeline for cleaner output across all exchanges. This would strip the ~57 lines of nav noise per page.
3. **For JS-heavy exchange docs** (SPAs where HTTP returns empty shells), the existing Playwright fallback in `inventory_fetch.py` handles this correctly.
4. **agent-browser** could simplify `playwrightfetch.py` as a lighter-weight browser automation layer, but this is a codebase simplification discussion, not a content capture issue.
