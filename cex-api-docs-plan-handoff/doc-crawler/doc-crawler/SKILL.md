---
name: doc-crawler
description: >
  General-purpose documentation crawler, indexer, and retrieval system. Crawls any documentation
  website, API reference, wiki, or knowledge base — extracts structured content, builds a local
  searchable index (SQLite FTS5 + JSON/Markdown files), and enables fast retrieval without
  re-crawling. Use this skill when: (1) needing to deeply crawl and save external documentation
  for offline/cached reference, (2) building a local knowledge base from web docs, (3) retrieving
  previously crawled docs without context bloat, (4) indexing internal docs exported from Notion,
  GitHub wikis, or other sources. This skill is the foundation for domain-specific crawlers like
  cex-api-docs. Designed to run in a dedicated "retrieval session" — crawl first, save to shared
  storage, then use from a clean working session. Every piece of stored information includes its
  source URL, crawl timestamp, and content hash for verification.
---

# Doc Crawler

## Overview

A general-purpose documentation crawler that fetches, structures, indexes, and stores documentation
from any web source. Designed for zero-hallucination retrieval — every fact is cited with source URL,
crawl timestamp, and content hash.

## Architecture

```
doc-crawler/
├── SKILL.md
├── scripts/
│   ├── crawl.py          # Main crawler engine
│   ├── index.py          # SQLite FTS5 indexer
│   ├── search.py         # Search/retrieve from index
│   └── diff.py           # Detect changes between crawls
└── references/
    └── storage-schema.md # Database and file storage schema
```

## Storage Layout

All crawled data stored under configurable `DOCS_ROOT` (default: `./doc-store/`):

```
doc-store/
├── db/
│   └── docs.db                 # SQLite FTS5 search index
├── raw/                        # Raw crawled pages (HTML preserved)
│   └── {domain}/{path_hash}.html
├── pages/                      # Structured markdown per page
│   └── {domain}/{path_hash}.md
├── meta/                       # Crawl metadata JSON per page
│   └── {domain}/{path_hash}.json
└── crawl-log.jsonl             # Append-only crawl history
```

## Workflow

### Phase 1: Crawl (dedicated retrieval session)

```bash
python3 scripts/crawl.py \
  --url "https://docs.example.com/api/" \
  --domain-scope "docs.example.com" \
  --output-dir "./doc-store" \
  --max-depth 10 \
  --include-patterns "/api/,/reference/" \
  --exclude-patterns "/blog/" \
  --delay 1.0
```

Key flags:
- `--url`: Entry point URL (required)
- `--domain-scope`: Restrict crawl to this domain (default: extracted from URL)
- `--max-depth`: Max link depth (default: 10, 0=unlimited)
- `--include-patterns` / `--exclude-patterns`: URL path filters (comma-separated)
- `--delay`: Seconds between requests (default: 1.0)
- `--force-recrawl`: Re-fetch even if content hash unchanged

The crawler: fetches entry URL → discovers all linked doc pages → follows internal links to
max depth → saves raw HTML + extracted markdown + metadata JSON → updates SQLite FTS5 index.

### Phase 2: Index (auto-runs after crawl, or standalone)

```bash
python3 scripts/index.py --docs-dir "./doc-store"
```

### Phase 3: Search (from working session — no re-crawling)

```bash
# Full-text search
python3 scripts/search.py --query "rate limiting" --docs-dir "./doc-store"

# Scoped to domain
python3 scripts/search.py --query "websocket auth" --domain "docs.binance.com"

# Fetch specific page
python3 scripts/search.py --url "https://docs.example.com/api/orders"

# List crawled domains / pages
python3 scripts/search.py --list-domains
python3 scripts/search.py --list-pages --domain "docs.example.com"
```

### Phase 4: Diff (detect changes)

```bash
python3 scripts/diff.py --docs-dir "./doc-store" --domain "docs.example.com"
```

Outputs added/removed/modified pages with unified diffs.

## Page Metadata Schema

See `references/storage-schema.md` for full schema. Key fields per page:

```json
{
  "url": "https://docs.example.com/api/orders",
  "domain": "docs.example.com",
  "title": "Orders API",
  "crawled_at": "2026-02-06T12:00:00Z",
  "content_hash": "sha256:abc123...",
  "prev_content_hash": "sha256:def456...",
  "link_depth": 2,
  "parent_url": "https://docs.example.com/api/",
  "outbound_links": ["..."],
  "word_count": 1450
}
```

## Critical Rules

1. **NEVER fabricate or infer** — only store what is explicitly on the page
2. **ALWAYS cite source URL + crawl timestamp** with every piece of data
3. **ALWAYS preserve original content** — extractions are additive, never destructive
4. **Respect rate limits** — default 1s delay between requests
5. **Check content hash before overwriting** — skip unchanged pages
6. **Log every action** to crawl-log.jsonl for auditability
