# M23 Phase 2: Parameter Table Extraction

## Status: PLAN — needs iteration and refinement before building

## Goal

Extract structured parameter data from markdown tables near endpoint definitions. Store as `request_schema.parameters[]` in endpoint JSON records with character-offset citations.

## Current State

- 1,648 endpoints extracted from crawled markdown (Phase 1 complete)
- Endpoints have: method, path, description, rate_limit (400 have it), docs_url, citations
- Endpoints do NOT have: request_schema, response_schema, required_permissions, error_codes
- Parameter tables exist in the page markdown but aren't structured into endpoint records

## Table Format Survey (from real data)

### Pipe tables (`|` separator) — most common
- **cryptocom**: `Name | Type | Required | Description` (1,886 rows)
- **phemex**: `Field | Type | Description | Possible values` (1,601 rows)  
- **apex**: `Parameter | Position | Type | Type | Comment` (1,444 rows)
- **bybit**: `Parameter| Type| Comments` (4 rows per page, clean)
- **bitbank**: `Name | Type | Mandatory | Description` (86 rows)
- **woo**: `Name | Type | Required | Description` (5 rows per page)
- **okx**: `Parameter | Type | Required | Description` (1 row visible, most in JS widgets)

### Tab tables (`\t` separator)
- **coinone**: `field\ttype\trequired/optional\tdescription` (Korean descriptions)
- **aster**: tab-separated (82 rows)

### No tables
- **aevo**: per-endpoint ReadMe.io pages, different structure
- **gains**: no visible param tables
- **coinex**: sparse pages

## Proposed Algorithm

1. For each endpoint candidate, look within ±2000 chars of `char_start`
2. Find the nearest "Request" / "Parameters" / "Request Body" section heading
3. Detect table format (pipe or tab)
4. Parse header row to identify column mapping:
   - Name column: matches `name|field|parameter|param`
   - Type column: matches `type`
   - Required column: matches `required|mandatory|optional|required/optional`
   - Description column: matches `description|comment|desc`
5. Parse data rows into `{name: str, type: str, required: bool, description: str}`
6. Store as `request_schema: {"parameters": [...]}` in endpoint record
7. Set `field_status.request_schema = "documented"` with citation

## Files to Modify

- `src/xdocs/endpoint_extract.py` — add `extract_params_near()`, wire into `_build_endpoint_record()`
- `tests/test_endpoint_extract.py` — add parameter extraction tests (pipe + tab formats)

## Also in This Milestone

- [ ] Verify Coinone's 2 potentially missing endpoints (audit showed 43 paths in pages vs 41 in store)
- [ ] Check the 3 skipped Coinone pages (empty .markdown-body — are they important?)
- [ ] Update xdocs-query skill: specify Coinone is Korean-only exchange
- [ ] Update xdocs-maintain skill: add "update skills after data changes" to maintenance checklist
- [ ] Run A/B eval after parameter extraction to confirm no regressions

## Open Questions (need iteration)

1. How to handle nested parameters? Some tables have `- available` (dash prefix = child of previous row)
2. How to handle response_schema? Same table format but under "Response Body" heading. Build now or defer?
3. Should the extractor also update EXISTING spec-imported endpoints that have empty request_schema?
4. How to handle exchanges where params are in description text, not tables (e.g., "Parameters: symbol (string, required)")
5. Coinone's tables use literal `\n` in the stored content — need to handle the unescaping

## Affected Exchanges (by expected yield)

| Exchange | Pipe rows | Tab rows | Expected params |
|----------|-----------|----------|-----------------|
| cryptocom | 1,886 | 0 | High |
| phemex | 1,601 | 0 | High |
| apex | 1,444 | 0 | High |
| bybit | 4/page | 0 | Medium (304 pages) |
| bitbank | 86 | 0 | Medium |
| okx | 1 | 0 | Low (most in JS widgets) |
| coinone | 0 | varies | Medium (tab format) |
| aster | 0 | 82 | Medium |
| woo | 5/page | 0 | Low (1 page) |
