# M19 Research: Binance Coverage Test Regression

## Current Results: 1 FULL / 4 PARTIAL

## Per-Question Root Causes

### Q1: Parameters (PARTIAL — 16/19)
- **Missing**: pegPriceType, pegOffsetValue, pegOffsetType
- **Root cause**: Not in Binance official OpenAPI spec at all (0 matches in raw YAML)
- **Exists on**: 13 Binance doc pages (changelogs, trading-endpoints, pegged_orders FAQ)
- **Fix difficulty**: Hard — requires doc page parameter extraction or upstream spec update

### Q2: Enums (FULL)
- All 5 enum fields found after $ref resolution (commit f82f018)
- Was PARTIAL before — success story

### Q3: Order Lists (PARTIAL — 3/5 schemas)
- OCO, OTO, OTOCO: Full schemas from OpenAPI (27/26/36 params)
- OPO, OPOCO: Only in Postman with request_schema=NULL
- **Root cause**: postman_import.py line 221 sets request_schema: None for ALL imports
- Postman collection also has empty urlencoded arrays for these endpoints
- **Fix**: Enhance postman_import.py to extract urlencoded/formdata params

### Q4: Authentication (PARTIAL — 1/5)
- **Found**: Only "RSA" (appears in page headings)
- **Missing**: X-MBX-APIKEY, HMAC-SHA256, Ed25519, recvWindow
- **Bug 1**: search_pages() in pages.py:36 lacks FTS5 sanitization — crashes on "X-MBX-APIKEY"
- **Bug 2**: semantic-search results lack text/snippet content — only title/heading/url/score
- **Content exists**: request-security page has all 5 terms (X-MBX-APIKEY 9x, HMAC 7x, RSA 7x, Ed25519 6x, recvWindow 45x)
- **Fix**: Add sanitize_fts_query() to search_pages(), add text field to semantic-search results

### Q5: Newer Endpoints (PARTIAL — 0/3 schemas)
- All 3 found as Postman-imported records
- All lack schemas (not in OpenAPI spec, Postman has empty params)
- **Root cause**: Same as Q3 — postman_import.py doesn't extract params
- **Fix**: Same as Q3

## Fixable vs Not-Fixable

### Quick wins (code bugs):
1. search_pages() FTS5 sanitization — fixes Q4 crash
2. semantic-search text/snippet field — fixes Q4 content detection

### Medium effort (data pipeline):
3. postman_import.py parameter extraction — fixes Q3/Q5 for endpoints with Postman params
   (but OPO/OPOCO have empty arrays even in Postman, so still won't help those)

### Longer term (upstream/extraction):
4. Doc page parameter extraction — would fix Q1 (peg), Q3 (OPO/OPOCO), Q5 (all 3)
5. More complete upstream spec — unlikely, Binance spec maintenance is slow

## Key Insight
This is NOT a regression from a previous "good" state. The test was always going to show these gaps because:
- The peg params were never in the spec
- Postman import never extracted params
- The search_pages bug has always existed
Q2 genuinely improved from PARTIAL→FULL thanks to $ref resolution.
