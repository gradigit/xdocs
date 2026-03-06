# FTS5 Best Practices Research

## Critical Findings

### 1. Consolidate Query Sanitization (HIGH)
- Two duplicate `_sanitize_fts_query` in answer.py:17 and endpoints.py:624
- Different ad-hoc approaches in lookup.py:98 and answer.py:241
- resolve_docs_urls.py:78 passes raw paths with NO sanitization
- **Fix**: Single shared function, use try-raw-then-quote-fallback pattern (SQLite.org recommended)

### 2. Add Porter Stemming (HIGH)
- Current: `tokenize = 'unicode61'`
- Recommended: `tokenize = 'porter unicode61'`
- Enables: "connect" matches "connecting", "connected", "connection"
- Safe for Korean docs (porter only affects English morphological suffixes)
- **Do NOT add `tokenchars='-'`** — creates compound tokens, breaks individual segment search

### 3. Configure BM25 Column Weights (HIGH)
- `pages_fts(canonical_url UNINDEXED, title, markdown)`
  - `bm25(pages_fts, 0, 10.0, 1.0)` — title 10x body
- `endpoints_fts(endpoint_id UNINDEXED, exchange UNINDEXED, section UNINDEXED, method UNINDEXED, path, search_text)`
  - `bm25(endpoints_fts, 0, 0, 0, 0, 5.0, 1.0)` — path 5x search_text
- Set via: `INSERT INTO pages_fts(pages_fts, rank) VALUES('rank', 'bm25(0, 10.0, 1.0)')`

### 4. Switch to ORDER BY rank (MEDIUM)
- 3 modules use slower `ORDER BY bm25()`: answer.py:58, answer.py:138, resolve_docs_urls.py:97
- 5 modules already correctly use `ORDER BY rank`
- Same results, but `rank` enables internal pre-sorting optimization

### 5. Use NEAR Queries for Precision (MEDIUM)
- `NEAR(rate limit, 2)` — terms within 2 tokens
- Critical for large docs (256K-word Gate.io SPA) where "rate" and "limit" appear far apart
- Not used anywhere in current codebase

### 6. Fix Snippet Quality (MEDIUM)
- `snippet()` returns raw markdown: `# >>>Rate<<< Limits\n\n## Overview\n\n...`
- endpoints_fts search_text is JSON dump: `{"description": "Send in a new [order]"...}`
- **Fix**: Post-process snippets to strip markdown syntax; restructure search_text from JSON to plain text

### 7. Prefix Indexes (LOW — future)
- `prefix='2 3 4'` would accelerate prefix queries (`get*`, `trade*`)
- No current usage, but would enable autocomplete

## Schema Changes Needed

```sql
-- pages_fts: add porter stemming
CREATE VIRTUAL TABLE pages_fts USING fts5(
    canonical_url UNINDEXED,
    title,
    markdown,
    content=pages,
    content_rowid=id,
    tokenize = 'porter unicode61'
);

-- endpoints_fts: add porter stemming
CREATE VIRTUAL TABLE endpoints_fts USING fts5(
    endpoint_id UNINDEXED,
    exchange UNINDEXED,
    section UNINDEXED,
    method UNINDEXED,
    path,
    search_text,
    tokenize = 'porter unicode61'
);

-- Configure rank weights after table creation
INSERT INTO pages_fts(pages_fts, rank) VALUES('rank', 'bm25(0, 10.0, 1.0)');
INSERT INTO endpoints_fts(endpoints_fts, rank) VALUES('rank', 'bm25(0, 0, 0, 0, 5.0, 1.0)');
```

Requires `fts-rebuild` after schema change.

## Shared Sanitization Function

```python
def sanitize_fts_query(query: str) -> str:
    """Sanitize user input for FTS5 MATCH.

    Wraps terms containing special characters in double-quotes.
    FTS5 interprets: hyphens as NOT, colons as column prefix,
    parentheses as grouping, asterisks as prefix.
    """
    tokens = query.split()
    safe = []
    for t in tokens:
        # Skip FTS5 operators
        if t.upper() in ('AND', 'OR', 'NOT', 'NEAR'):
            safe.append(t)
            continue
        if re.search(r'[-:"/{}()*]', t):
            # Escape internal double-quotes
            escaped = t.replace('"', '""')
            safe.append(f'"{escaped}"')
        else:
            safe.append(t)
    return " ".join(safe)
```

Place in a shared module (e.g., `fts_util.py`) and import from all 6 FTS5-using modules.
