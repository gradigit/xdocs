-- Authoritative schema for cex-docs/db/docs.db
-- v1: greenfield, local-only, cite-only.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS crawl_runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
  id INTEGER PRIMARY KEY,
  canonical_url TEXT NOT NULL UNIQUE,
  url TEXT NOT NULL,
  final_url TEXT NOT NULL,
  domain TEXT NOT NULL,
  path_hash TEXT NOT NULL,
  title TEXT,
  http_status INTEGER,
  content_type TEXT,
  render_mode TEXT,
  raw_hash TEXT,
  content_hash TEXT,
  prev_content_hash TEXT,
  crawled_at TEXT,
  raw_path TEXT,
  markdown_path TEXT,
  meta_path TEXT,
  word_count INTEGER,
  extractor_name TEXT,
  extractor_version TEXT,
  extractor_config_json TEXT,
  extractor_config_hash TEXT,
  last_crawl_run_id INTEGER REFERENCES crawl_runs(id)
);

CREATE INDEX IF NOT EXISTS pages_domain_idx ON pages(domain);
CREATE INDEX IF NOT EXISTS pages_content_hash_idx ON pages(content_hash);

CREATE TABLE IF NOT EXISTS page_versions (
  id INTEGER PRIMARY KEY,
  page_id INTEGER NOT NULL REFERENCES pages(id),
  crawl_run_id INTEGER NOT NULL REFERENCES crawl_runs(id),
  crawled_at TEXT NOT NULL,
  http_status INTEGER,
  content_type TEXT,
  raw_hash TEXT,
  content_hash TEXT,
  raw_path TEXT,
  markdown_path TEXT,
  meta_path TEXT
);

CREATE INDEX IF NOT EXISTS page_versions_page_id_idx ON page_versions(page_id);
CREATE INDEX IF NOT EXISTS page_versions_crawl_run_id_idx ON page_versions(crawl_run_id);

-- FTS5 tables (fail at runtime if FTS5 not enabled).
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
  canonical_url UNINDEXED,
  title,
  markdown,
  tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS endpoints (
  endpoint_id TEXT PRIMARY KEY,
  exchange TEXT NOT NULL,
  section TEXT NOT NULL,
  protocol TEXT NOT NULL,
  method TEXT,
  path TEXT,
  base_url TEXT,
  api_version TEXT,
  description TEXT,
  docs_url TEXT,
  json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS endpoints_exchange_section_idx ON endpoints(exchange, section);

CREATE VIRTUAL TABLE IF NOT EXISTS endpoints_fts USING fts5(
  endpoint_id UNINDEXED,
  exchange UNINDEXED,
  section UNINDEXED,
  method UNINDEXED,
  path,
  search_text,
  tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS endpoint_sources (
  endpoint_id TEXT NOT NULL REFERENCES endpoints(endpoint_id),
  field_name TEXT NOT NULL,
  page_canonical_url TEXT NOT NULL,
  page_content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (endpoint_id, field_name, page_canonical_url, page_content_hash)
);

CREATE TABLE IF NOT EXISTS review_queue (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  endpoint_id TEXT,
  field_name TEXT,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  details_json TEXT
);

CREATE INDEX IF NOT EXISTS review_queue_status_idx ON review_queue(status);

-- Inventories (deterministic URL enumeration per exchange section).
-- These enable "exhaustive" fetch runs that are diffable and cron-friendly.
CREATE TABLE IF NOT EXISTS inventories (
  id INTEGER PRIMARY KEY,
  exchange_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  sources_json TEXT NOT NULL,      -- JSON: seeds, discovered sitemaps, scopes, config
  url_count INTEGER NOT NULL,
  inventory_hash TEXT NOT NULL     -- sha256 of canonical URL list (stable ordering)
);

CREATE INDEX IF NOT EXISTS inventories_exchange_section_idx ON inventories(exchange_id, section_id);
CREATE INDEX IF NOT EXISTS inventories_generated_at_idx ON inventories(generated_at);

CREATE TABLE IF NOT EXISTS inventory_entries (
  id INTEGER PRIMARY KEY,
  inventory_id INTEGER NOT NULL REFERENCES inventories(id),
  canonical_url TEXT NOT NULL,
  status TEXT NOT NULL,            -- pending|fetched|error|skipped
  last_fetched_at TEXT,
  last_http_status INTEGER,
  last_content_hash TEXT,
  last_final_url TEXT,
  last_page_canonical_url TEXT,
  last_etag TEXT,
  last_last_modified TEXT,
  last_cache_control TEXT,
  error_json TEXT,
  UNIQUE (inventory_id, canonical_url)
);

CREATE INDEX IF NOT EXISTS inventory_entries_inventory_id_idx ON inventory_entries(inventory_id);
CREATE INDEX IF NOT EXISTS inventory_entries_status_idx ON inventory_entries(status);

-- Cross-section ownership cache used by scope-dedupe.
CREATE TABLE IF NOT EXISTS inventory_scope_ownership (
  scope_group TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  owner_exchange_id TEXT NOT NULL,
  owner_section_id TEXT NOT NULL,
  owner_inventory_id INTEGER NOT NULL REFERENCES inventories(id),
  owner_priority INTEGER NOT NULL DEFAULT 100,
  owned_at TEXT NOT NULL,
  PRIMARY KEY (scope_group, canonical_url)
);

CREATE INDEX IF NOT EXISTS inventory_scope_ownership_owner_idx
  ON inventory_scope_ownership(owner_exchange_id, owner_section_id, owner_priority);

-- Aggregated endpoint completeness gaps. This is a scale-safe alternative to
-- creating per-endpoint review items for missing fields.
CREATE TABLE IF NOT EXISTS coverage_gaps (
  exchange TEXT NOT NULL,
  section TEXT NOT NULL,
  protocol TEXT NOT NULL,
  field_name TEXT NOT NULL,
  status_counts_json TEXT NOT NULL,        -- JSON: {"documented": 10, "unknown": 2, ...}
  sample_endpoint_ids_json TEXT NOT NULL,  -- JSON: {"unknown": ["..."], "undocumented": ["..."]}
  updated_at TEXT NOT NULL,
  PRIMARY KEY (exchange, section, protocol, field_name)
);

-- Structured changelog entries extracted from stored changelog pages.
-- Used for drift detection: new entries appearing after a sync indicate API changes.
CREATE TABLE IF NOT EXISTS changelog_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exchange_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  source_url TEXT NOT NULL,              -- canonical_url of the page this was extracted from
  entry_date TEXT,                       -- ISO date (YYYY-MM-DD), NULL if not parseable
  entry_text TEXT NOT NULL,              -- full markdown text of the entry
  content_hash TEXT NOT NULL,            -- SHA-256 of entry_text (for dedup)
  extracted_at TEXT NOT NULL,
  UNIQUE(source_url, content_hash)
);

CREATE INDEX IF NOT EXISTS changelog_entries_exchange_section_idx
  ON changelog_entries(exchange_id, section_id);

CREATE INDEX IF NOT EXISTS changelog_entries_date_idx
  ON changelog_entries(entry_date);

CREATE VIRTUAL TABLE IF NOT EXISTS changelog_entries_fts
  USING fts5(
    exchange_id UNINDEXED,
    section_id UNINDEXED,
    entry_date UNINDEXED,
    entry_text,
    content=changelog_entries,
    content_rowid=id,
    tokenize = 'porter unicode61'
  );
