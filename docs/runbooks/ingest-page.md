---
title: "Runbook: Browser Capture + ingest-page"
date: 2026-02-10
---

# Runbook: Browser Capture + ingest-page

Use this when a documentation URL cannot be fetched deterministically (WAF/captcha/JS-only rendering) but the content is publicly accessible in a browser.

Goal: capture the rendered HTML (or extracted markdown) and ingest it into the normal `cex-docs/` store so it is searchable and diffable like any other page.

## When To Use

- `cex-api-docs fetch-inventory` returns persistent failures (403/captcha/timeout/empty content) for some URLs
- the page loads correctly in a normal browser
- you want the store to stay canonical (same hashing/versioning/indexing as deterministic pages)

## Steps

### 1) Capture HTML

Use whichever tool you have available:

- `agent-browser` CLI (recommended for agents)
- Playwright (manual script)
- Any browser: “Save Page Source” / DevTools “Copy outerHTML”

Save the result to a local file, e.g.:

- `~/Downloads/binance-foo.html`

### 2) Ingest Into The Store

```bash
.venv/bin/cex-api-docs ingest-page \\
  --docs-dir ./cex-docs \\
  --url "https://example.com/docs/some/page" \\
  --html-path ~/Downloads/binance-foo.html \\
  --tool agent-browser \\
  --notes "Captured due to 403 in deterministic fetch"
```

### 3) Verify It’s Searchable

```bash
.venv/bin/cex-api-docs search-pages --docs-dir ./cex-docs "some unique phrase" --limit 5
```

### 4) Re-run Fetch

Re-run `fetch-inventory` for the section to confirm the failure count is shrinking over time.

## Notes / Gotchas

- `ingest-page` writes `render_mode=ingest` metadata into the stored page meta JSON so you can distinguish deterministic vs captured pages later.
- Prefer capturing HTML over markdown, so the extractor can re-run deterministically if needed.
- If the captured HTML includes dynamic/collapsed sections, expand them before capture so the saved page source contains the relevant content.

