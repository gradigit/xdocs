# Query Pipeline Quality Issues

18 issues identified. Priority-ordered.

## CRITICAL

### Issue 1: answer.py never calls classify.py
- answer.py has no import of classify — error codes, endpoint paths, and questions all use same generic FTS path
- Error code "-1002" → terms `['error', '1002', 'mean']` → FTS `"error OR 1002 OR mean"` → matches everything
- **Fix**: Integrate `classify_input()` at top of `answer_question()`. Route error_message → `search_error_code()`, endpoint_path → `lookup_endpoint_by_path()`, question → generic FTS.

### Issue 2: JSON key names pollute endpoints_fts
- `search_text` is `json.dumps({"error_codes": ..., "rate_limit": ..., "field_status": ...})`
- FTS5 tokenizes key names: ALL 1,425 Binance endpoints match query "error" because every search_text has `"error_codes"` key
- **Fix**: Store only VALUES as plain text: `f"{description}\n{rate_limit_text}\n{error_codes_text}"`
- Location: endpoints.py:514-524

## HIGH

### Issue 3: OR-joined FTS with no relevance threshold
- `_search_endpoints_for_answer` uses `" OR ".join(terms[:8])`, all matches become claims
- "rate limit" → "rate OR limit" → every endpoint mentioning either word
- **Fix**: Use AND for multi-term. Add BM25 score threshold. Discard results with rank > -1.0.
- Location: answer.py:241-242

### Issue 4: Seed URL prefix too narrow for page filtering
- `seed_urls[0]` is a specific page URL, not directory prefix
- Bybit websocket: `ws/connect` matches only 1 page, misses all other WS pages
- **Fix**: Extract directory prefix (strip trailing path segment), or use scope_prefixes from registry

### Issue 5: Bybit websocket 0 results (compound of #4)
- No WS endpoints in DB + seed prefix too narrow + domain fallback only triggers on zero claims
- **Fix**: Always search domain-level, not just seed prefix

### Issue 8: Error code search prioritizes endpoints over pages
- `search_error_code()` fills limit with endpoint matches, pages never searched
- Error definition page ranked 7th/8th for "-1002"
- **Fix**: Search pages FIRST (definitions), then augment with affected endpoints
- Location: lookup.py:74-86

### Issue 9: BM25 poor for numeric error codes
- "1002" appears as parameter values, example IDs, group IDs — not just error definitions
- **Fix**: Boost pages with "error" in URL path. Use phrase match "-1002" with context words.

## MEDIUM

### Issue 6: Excerpt extraction produces broken text
- `_make_excerpt` cuts at arbitrary char positions — mid-word, mid-table, mid-URL
- **Fix**: Snap to word/line boundaries. Strip broken markdown. Add structural context (nearest heading).
- Location: answer.py:68-82

### Issue 7: FTS5 hyphen handling fragile
- answer.py:353 `re.sub(r"[^\w\s]", " ", norm)` strips hyphens BEFORE sanitizer sees them
- **Fix**: Preserve hyphens: `re.sub(r"[^\w\s\-]", " ", norm)`

### Issue 10: Reranker macOS-only (jina-reranker-v3-mlx)
- **Fix**: Replace with FlashRank (see reranker-survey.md)

### Issue 11: Exchange detection false positives
- `ex_id in norm` substring match: "woo" matches "wooden", "perp" matches "perpetual"
- **Fix**: `re.search(rf"\b{re.escape(ex_id)}\b", norm)`
- Location: answer.py:285-293

### Issue 13: Silent exception swallowing in semantic fallback
- `except (ImportError, Exception): pass` hides all errors
- **Fix**: Log at warning level, separate ImportError from other exceptions
- Location: answer.py:183-185

### Issue 15: No structural context in page claim excerpts
- Claims show raw markdown slice with no heading/title context
- **Fix**: Include page title + nearest heading above excerpt

### Issue 16: Hard 20-claim limit regardless of relevance
- **Fix**: Reduce to 10, add relevance score threshold before adding claims

## LOW

### Issue 12: No zero-width char handling in excerpts
### Issue 14: Duplicate _sanitize_fts_query (answer.py + endpoints.py)
### Issue 17: URL prefix LIKE not SQL-escaped
### Issue 18: Minimal stopword list (14 words)
