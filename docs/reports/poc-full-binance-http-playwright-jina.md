# POC: Full Binance Docs — HTTP vs Playwright vs Jina Reader

**Date:** 2026-02-11
**Scope:** 1,072 English doc pages (2,144 total including zh-CN mirrors)
**Methods:** HTTP fetch + html2text, Playwright headless (article extraction), Jina Reader API (r.jina.ai)

## Executive Summary

All three methods successfully fetched the full Binance API documentation with near-perfect reliability. **HTTP fetch remains the best option for this project** — it is 5x faster than Playwright and 9x faster than Jina, with zero errors. However, each method has distinct formatting strengths that matter for downstream processing.

| Winner | Category |
|--------|----------|
| HTTP | Speed, reliability, completeness |
| Jina | Table formatting (proper pipe tables) |
| Playwright | Code block readability, DOM-level structure access |
| HTTP | Code/JSON formatting (indented, multi-line) |
| Jina | Zero nav noise (article-scoped by default) |

## Results Summary

| Metric | HTTP (full page) | HTTP (article only) | Playwright | Jina Reader |
|--------|------------------|---------------------|------------|-------------|
| Pages OK | 1,072 | 1,072 | 1,072 | 1,070 |
| Errors | 0 | 0 | 0 | 2 (503s) |
| Total words | 785,017 | 587,371 | 477,370 | 805,240 |
| Avg words/page | 732 | 548 | 445 | 753 |
| Total endpoints | 2,404 | — | 2,935 | 2,339 |
| Total time (s) | 275 | — | 1,288 | 2,488 |
| Wall time (w/ delay) | ~10m | — | ~27m | ~47m |
| Avg per page (s) | 0.29 | — | 1.22 | 2.31 |
| Disk usage | 21 MB | — | 33 MB | 14 MB |
| Thin pages (<50 words) | 1 | — | 74 | 1 |

## Formatting Quality (Side-by-Side)

### Tables

**HTTP (html2text)** — pipeless format, parseable but non-standard:
```
Name| Type| Mandatory| Description
---|---|---|---
omitZeroBalances| BOOLEAN| NO| When set to `true`...
```

**Jina Reader** — proper GFM pipe tables:
```
| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| omitZeroBalances | BOOLEAN | NO | When set to `true`... |
```

**Playwright** — tab-separated plain text:
```
Name	Type	Mandatory	Description
omitZeroBalances	BOOLEAN	NO	When set to true...
```

### Code Blocks / JSON Responses

**HTTP (html2text)** — indented multi-line, readable:
```
    {
        "makerCommission": 15,
        "takerCommission": 15,
        "buyerCommission": 0,
        ...
    }
```

**Playwright** — proper multi-line from `innerText`:
```
{
    "makerCommission": 15,
    "takerCommission": 15,
    "buyerCommission": 0,
    ...
}
```

**Jina Reader** — collapsed into single-line inline code (DESTRUCTIVE):
```
`{    "makerCommission": 15,    "takerCommission": 15,    "buyerCommission": 0, ...}`
```

### Endpoint Signatures

**HTTP**: `GET /api/v3/account` (indented, no backticks)
**Jina**: `` `GET /api/v3/account` `` (inline code)
**Playwright**: `GET /api/v3/account` (plain text)

## Key Findings

### 1. Jina collapses code blocks — critical quality issue

Jina Reader converts all `<pre><code>` blocks into single-line inline code spans (backtick-wrapped). For API docs where JSON response examples are essential, this is a **deal-breaker for structured extraction**. Multi-line JSON like:
```json
{
    "orderId": 1,
    "symbol": "BTCUSDT"
}
```
becomes: `` `{    "orderId": 1,    "symbol": "BTCUSDT"}` ``

This makes JSON responses unreadable and unparseable without post-processing.

### 2. Jina excels at table formatting

Jina's pipe tables are the cleanest output. HTTP's pipeless tables require custom parsing. Jina detected 13,904 table rows vs HTTP's 2,399 (because pipe-style tables are easier to regex-count).

### 3. Playwright has thin-page problem

74 pages (7%) returned <50 words via `article` selector. These are section intro pages where the `<article>` element contains only a title and a brief description, while the actual content is in sidebar navigation. HTTP and Jina both capture this content.

### 4. Playwright finds more endpoints via innerText

Playwright detected 2,935 endpoint signatures vs HTTP's 2,404 and Jina's 2,339. The `innerText` extraction picks up endpoint paths in sidebar navigation and breadcrumbs that HTML-to-markdown conversion may strip or format differently.

### 5. Jina adds useful metadata

Each Jina response includes `Title`, `URL Source`, and `Published Time` — useful for freshness tracking. This metadata inflates word counts by ~15-20% but is easy to strip.

### 6. HTTP navigation noise is ~25%

Full-page HTTP word count (785K) is 34% higher than article-only (587K). The delta is consistent: ~57 lines of sidebar, footer, and language picker per page. An optional `content_selector` in the pipeline would eliminate this.

### 7. Speed differences are dramatic at scale

| Method | 1 page | 100 pages | 1,072 pages |
|--------|--------|-----------|-------------|
| HTTP | 0.3s | 30s | 4.6m |
| Playwright | 1.2s | 2m | 21.5m |
| Jina | 2.3s | 3.8m | 41.5m |

HTTP is 4.7x faster than Playwright and 9x faster than Jina.

## Reliability

| Method | Success rate | Error type |
|--------|-------------|------------|
| HTTP | 100.0% (1072/1072) | — |
| Playwright | 100.0% (1072/1072) | — |
| Jina | 99.8% (1070/1072) | 2x HTTP 503 from upstream |

Jina's 2 failures were on pages that HTTP and Playwright fetched fine — intermittent upstream errors that Jina's proxy didn't retry.

## Verdict

**HTTP fetch + html2text remains the best method for this project.** Specifically:

1. **For Binance (SSR)**: HTTP is sufficient. No JavaScript rendering needed.
2. **Jina is NOT recommended** despite good table formatting, because its code block collapse destroys JSON response examples — critical content for API documentation.
3. **Playwright adds no content value** for SSR sites but is 4.7x slower. Reserve for JS-rendered SPAs.
4. **Consider** adding `content_selector: article` to the HTTP pipeline to strip 25% navigation noise, matching Jina's scope advantage without Jina's code block problem.

## Recommendations

1. **Keep HTTP as primary fetch method** — fastest, most reliable, best code formatting
2. **Add optional `content_selector`** to strip nav noise (25% of words are sidebar/footer)
3. **Do not integrate Jina Reader** for API docs — code block collapse is destructive
4. **Keep Playwright as fallback** for JS-heavy exchanges only (existing `--render auto` behavior)
5. **Post-processing opportunity**: convert html2text pipeless tables to GFM pipe tables for better downstream compatibility

## Failed URLs (Jina only)

- `https://developers.binance.com/docs/binance-spot-api-docs/testnet/rest-api/market-data-endpoints` (503, 14.6s timeout)
- `https://developers.binance.com/docs/mining/rest-api/Acquiring-CoinName` (503, 1.5s)

## Reproduction

```bash
source .venv/bin/activate

# Phase 1: Discover URLs
python scripts/poc_full_binance.py discover

# Phase 2: Fetch (run in parallel)
python scripts/poc_full_binance.py fetch-http &
python scripts/poc_full_binance.py fetch-playwright &
JINA_API_KEY=<key> python scripts/poc_full_binance.py fetch-jina &
wait

# Phase 3: Compare
python scripts/poc_full_binance.py compare
```

Results stored in `poc-binance-full/` (gitignored).
