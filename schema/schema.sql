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

CREATE TABLE IF NOT EXISTS links (
  id INTEGER PRIMARY KEY,
  from_page_id INTEGER NOT NULL REFERENCES pages(id),
  to_url TEXT NOT NULL,
  to_canonical_url TEXT,
  depth INTEGER,
  found_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS links_from_page_id_idx ON links(from_page_id);

-- FTS5 tables (fail at runtime if FTS5 not enabled).
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
  canonical_url UNINDEXED,
  title,
  markdown,
  tokenize = 'unicode61'
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
  tokenize = 'unicode61'
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

