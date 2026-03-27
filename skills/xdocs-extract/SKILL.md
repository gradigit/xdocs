---
name: xdocs-extract
description: >
  Extract structured endpoint records from crawled API documentation pages. Uses regex-based
  candidate scanning for high recall, with agent-driven false positive filtering for precision.
  Activates when user asks to "extract endpoints", "scan for endpoints", "find API endpoints in docs",
  or wants to populate endpoint records for exchanges without OpenAPI/Postman specs.
---

# CEX Endpoint Extraction

## Core Rule: Cite-Only

Every extracted endpoint must cite the source page with exact character offsets. The save pipeline (`save_endpoints_bulk`) verifies `md[excerpt_start:excerpt_end] == excerpt` mechanically. If citations don't match, the record is rejected.

## When To Use

- Exchange has crawled documentation pages but 0 structured endpoint records
- No OpenAPI/Postman spec is available for the exchange
- After crawling new pages that document previously unrecorded endpoints
- User explicitly asks to extract endpoints from docs

## Prerequisites

- Active Python venv with `xdocs` installed
- Store initialized with crawled pages (`xdocs store-report` to check)
- Exchange registered in `data/exchanges.yaml` with `allowed_domains` and `base_urls`

## Workflow

### Step 1: Assess Current State

```bash
xdocs store-report --exchange {exchange_id} --docs-dir ./cex-docs
xdocs list-endpoints --exchange {exchange_id} --limit 5 --docs-dir ./cex-docs
```

If endpoints already exist (from spec imports), note the count. Extraction will skip duplicates.

### Step 2: Dry-Run Scan

```bash
xdocs scan-endpoints --exchange {exchange_id} --section {section_id} --docs-dir ./cex-docs --dry-run
```

Review the JSON output. Key fields per candidate:
- `method`: HTTP method (GET, POST, etc.)
- `path`: normalized API path
- `heading`: nearest heading above the match (context for review)
- `pattern`: which regex matched (P2 = code block, P3 = heading+block, P4 = heading, P1 = inline, P5 = backtick)
- `line`: line number in the source page

### Step 3: Evaluate False Positive Rate

Scan the candidate list for common false positive patterns:
- **Changelog entries**: heading mentions "changelog", "release notes", "what's new" — endpoints listed are references, not definitions
- **Response/example blocks**: endpoint appears inside a JSON/code example section, not as a definition
- **Rate limit tables**: endpoints listed as members of rate limit groups
- **Auth tutorials**: endpoints shown in string concatenation for signing

### Step 4: Save

**If false positive rate is low (<10%)** — save directly:
```bash
xdocs scan-endpoints --exchange {exchange_id} --section {section_id} --docs-dir ./cex-docs
```

**If false positive rate is high** — read the page markdown, identify valid endpoints manually, and write a Python script:
```python
from xdocs.endpoint_extract import save_extracted_endpoints

candidates = [
    {"method": "GET", "path": "/public/products", "char_start": 1234, "char_end": 1258,
     "page_url": "https://...", "md": open("path/to/markdown").read(),
     "crawled_at": "2026-...", "content_hash": "...", "path_hash": "..."},
    # ... more approved candidates
]

result = save_extracted_endpoints(
    docs_dir="./cex-docs", lock_timeout_s=10,
    candidates=candidates, exchange="...", section="...",
    base_url="https://api.example.com",
)
print(result)
```

### Step 5: Verify

```bash
xdocs list-endpoints --exchange {exchange_id} --limit 10 --docs-dir ./cex-docs
xdocs lookup-endpoint /public/products --exchange {exchange_id} --docs-dir ./cex-docs
```

Spot-check 5-10 endpoints: verify method, path, and description match the source documentation.

## Exchange Notes

| Exchange | Section | Key Notes |
|----------|---------|-----------|
| phemex | `api` | Slate monolith (53K words). Endpoints in code blocks after `> Request`. Same paths in multiple sub-sections (COIN-M, Spot). First-wins dedup. |
| woo | `api` | SPA monolith (20K words). Backtick-wrapped + code blocks. Large changelog section with endpoint references (not definitions). |
| coinex | `api` | Docusaurus (489 pages). Rate limit page lists endpoints as references. Auth page shows endpoints in code examples. |
| aevo | `api` | ReadMe.io (144 per-endpoint pages). Corrupted markdown links: `[GET /assets get](url)`. Index page has link references. |
| bitbank | `rest` | Clean GitHub markdown (175 pages). Dual base_urls: private (`api.bitbank.cc/v1`) vs public (`public.bitbank.cc`). |
| apex | `api` | ReadMe.io (5 pages, 3 dupes). Language-toggle duplicates handled by dedup. |

## Dual Base URL Handling

For exchanges with multiple base_urls (e.g., bitbank), each candidate dict can include a `base_url` field to override the default:

```python
{"method": "GET", "path": "/v1/user/assets", "base_url": "https://api.bitbank.cc/v1", ...}
{"method": "GET", "path": "/{pair}/ticker", "base_url": "https://public.bitbank.cc", ...}
```

## What This Skill Does NOT Do

- Parameter table extraction (Phase 2, not yet implemented)
- Rate limit extraction (Phase 3, not yet implemented)
- Overwrite spec-imported endpoints (`skip_existing=True` by default)
- Require any LLM or external API calls
