# Storage Schema Reference

## SQLite Database Schema (docs.db)

```sql
-- Core pages table
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    path TEXT NOT NULL,
    path_hash TEXT NOT NULL,
    title TEXT,
    content_md TEXT,           -- Extracted markdown content
    content_hash TEXT,         -- SHA256 of content_md
    prev_content_hash TEXT,    -- Previous crawl's hash (for diff detection)
    http_status INTEGER,
    content_type TEXT,
    link_depth INTEGER,
    parent_url TEXT,
    word_count INTEGER,
    has_code_blocks BOOLEAN DEFAULT 0,
    has_tables BOOLEAN DEFAULT 0,
    crawled_at TEXT NOT NULL,   -- ISO 8601
    updated_at TEXT NOT NULL,   -- ISO 8601
    is_stale BOOLEAN DEFAULT 0  -- Marked if page returns 404 on recrawl
);

-- Full-text search index
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    url,
    title,
    content_md,
    domain,
    content='pages',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, url, title, content_md, domain)
    VALUES (new.id, new.url, new.title, new.content_md, new.domain);
END;

CREATE TRIGGER pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, url, title, content_md, domain)
    VALUES ('delete', old.id, old.url, old.title, old.content_md, old.domain);
END;

CREATE TRIGGER pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, url, title, content_md, domain)
    VALUES ('delete', old.id, old.url, old.title, old.content_md, old.domain);
    INSERT INTO pages_fts(rowid, url, title, content_md, domain)
    VALUES (new.id, new.url, new.title, new.content_md, new.domain);
END;

-- Outbound links for graph traversal
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT NOT NULL,
    target_url TEXT NOT NULL,
    link_text TEXT,
    UNIQUE(source_url, target_url)
);

-- Crawl history log
CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    entry_url TEXT NOT NULL,
    domain_scope TEXT,
    pages_crawled INTEGER DEFAULT 0,
    pages_new INTEGER DEFAULT 0,
    pages_updated INTEGER DEFAULT 0,
    pages_unchanged INTEGER DEFAULT 0,
    pages_failed INTEGER DEFAULT 0,
    config_json TEXT  -- Stores crawl parameters for reproducibility
);

CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain);
CREATE INDEX IF NOT EXISTS idx_pages_path_hash ON pages(path_hash);
CREATE INDEX IF NOT EXISTS idx_pages_crawled_at ON pages(crawled_at);
CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_url);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_url);
```

## Metadata JSON Schema (per page)

Stored at `meta/{domain}/{path_hash}.json`:

```json
{
  "url": "string (absolute URL)",
  "domain": "string",
  "path": "string (URL path component)",
  "path_hash": "string (SHA256 of path, used for filenames)",
  "title": "string (page title)",
  "crawled_at": "string (ISO 8601)",
  "content_hash": "string (sha256:hex)",
  "prev_content_hash": "string|null",
  "http_status": "integer",
  "content_type": "string",
  "link_depth": "integer (hops from entry URL)",
  "parent_url": "string|null (page that linked to this one)",
  "outbound_links": ["array of absolute URLs found on page"],
  "word_count": "integer",
  "has_code_blocks": "boolean",
  "has_tables": "boolean",
  "headers": {
    "description": "HTTP response headers (selected)",
    "last-modified": "string|null",
    "etag": "string|null"
  }
}
```

## Crawl Log Schema (crawl-log.jsonl)

Append-only, one JSON object per line:

```json
{
  "timestamp": "2026-02-06T12:00:00Z",
  "action": "fetch|skip|error|index",
  "url": "https://...",
  "status": 200,
  "content_hash": "sha256:...",
  "changed": true,
  "error": null,
  "duration_ms": 450
}
```
