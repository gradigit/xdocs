# M23 Phase 2: Parameter Table Extraction

## Status: PLAN v2 — refined after data research, awaiting approval

## Goal

Extract structured parameter data from markdown tables near endpoint definitions. Store as `request_schema.parameters[]` in endpoint JSON records with character-offset citations.

## Scope

**In scope (this phase):**
- Request parameter extraction from pipe tables and Coinone tab tables
- Single-level nested parameter support (dash-prefix `| - field |`)
- Filling gaps for crawl-extracted endpoints (1,648 with empty request_schema)
- Filling gaps for Postman-imported endpoints (1,070 with empty request_schema)

**Deferred:**
- Response schema extraction (different heading, different column counts — separate phase)
- Inline/bullet parameter formats (gains, woo — only ~11 endpoints affected)
- Aevo (ReadMe.io template pages — no extractable params in markdown)
- Multi-level nesting (not observed in any exchange)

## Research Findings

### Q1: Nested Parameters → Single-level dash-prefix, universal

All 6 pipe-table exchanges use `| - fieldname |` for child params. No multi-level nesting (`| -- |` or deeper) exists anywhere. No dot-notation or bracket-notation in tables.

| Exchange | `| - ` occurrences | Format |
|----------|-------------------|--------|
| bybit | 110,649 | `| - field | Type | Comments |` |
| apex | 23,824 | `| - field | Position | Type | Type | Comment |` |
| phemex | 12,913 | `| - field | Type | Description | Possible values |` |
| cryptocom | 12,552 | `| - field | Type | Required | Description |` |
| woo | 6,580 | `| - field | Type | Required | Description |` |
| coinone | 2,380 | `| - field | type | description |` (tab-separated) |

**Decision:** Support single-level nesting. When a row name starts with `- `, mark it as `parent: <previous_non_nested_name>`. Ignore multi-level.

### Q2: Response Schema → Defer

Response tables exist for bybit (332 files) and apex (3 files) but:
- Different heading patterns ("Response Parameters", "Response Attributes")
- Different column counts (apex response has 5 cols vs 4 for request)
- Different nesting symbols (bybit uses `>` prefix for response nesting vs `-` for request)
- Phemex/woo/coinone document responses as JSON examples, not tables

**Decision:** Defer response_schema to Phase 3. The format diversity means a separate, well-tested extraction pass.

### Q3: Update existing spec-imported endpoints? → Yes, Postman only

| Import source | Total | Empty request_schema | % empty |
|--------------|-------|---------------------|---------|
| import-postman | 1,112 | 1,070 | 96.2% |
| import-openapi | 2,393 | 149 | 6.2% |
| extract-markdown | 1,648 | 1,648 | 100% |

Postman imports almost never capture params. OpenAPI imports mostly have them.

**Decision:** Run param extraction for:
1. All `extract-markdown` endpoints (1,648) — primary target
2. All `import-postman` endpoints with empty request_schema (1,070) — high-value gap fill
3. Skip `import-openapi` endpoints (93.8% already have params, don't overwrite good data)

### Q4: Non-table formats → Defer

Only gains (9 endpoints) and woo (2 endpoints) use pure inline bullet params. All other exchanges use tables as primary format. Mixed formats (bybit, coinex) have tables as primary with inline supplements that aren't core param definitions.

**Decision:** Defer inline extraction. 11 endpoints not worth the complexity.

### Q5: Coinone literal `\n` → Confirmed, straightforward

Coinone pages store all content as a single string with literal `\n` (two chars: backslash + n) as row separators and `\t` (actual tab) as column separators. The `\"` escape is also present.

Raw stored format example:
```
"Request Body\n필드\t유형\t필수\t설명\naccess_token\tString\ttrue\t사용자의 액세스 토큰\nnonce\tString\ttrue\tUUID nonce"
```

Column headers (Korean):
- `필드` = field name
- `유형` / `타입` = type
- `필수` = required
- `설명` = description

**Decision:** Pre-process Coinone markdown: unescape `\n` → real newlines, `\"` → `"`. Then parse with the same tab-table logic. Header detection: match both Korean (`필드|유형|타입|필수|설명`) and English (`Key|Type|Description`) keywords.

## Table Format Survey (confirmed from real data)

### Format A: Pipe tables (7 exchanges)

```markdown
### Request Params

Name | Type | Required | Description
---|---|---|---
category | string | N | filter by category
product_type | string | N | filter by product type
```

Observed on: **cryptocom**, **phemex**, **apex**, **bybit**, **bitbank**, **woo**, **okx**

Header variations:
- `Name | Type | Required | Description` (cryptocom, woo)
- `Field | Type | Description | Possible values` (phemex)
- `Parameter | Type | Comments` (bybit, 3 cols)
- `Parameter | Position | Type | Type | Comment` (apex, 5 cols)
- `Name | Type | Mandatory | Description` (bitbank)

Separator row: `---|---|---` (any number of dashes, pipes)

### Format B: Tab tables (2 exchanges)

Coinone and aster use tab-separated columns. After `\n` unescaping, rows look like:
```
필드	유형	필수	설명
access_token	String	true	사용자의 액세스 토큰
```

### Format C: Description tables (phemex — supplementary)

Phemex also has `Field | Type | Description | Possible values` tables that describe request body fields. These are pipe tables and handled by Format A.

## Algorithm (refined)

### Step 1: Locate endpoint in markdown

For each endpoint, get its `char_start` from the citation. Also get the page markdown (from `markdown_path`).

### Step 2: Find nearest parameter section heading

Search **forward** from `char_start` up to 3000 chars for a section heading matching:
```regex
(?:^|\n)(#{1,4}\s+(?:Request\s+(?:Param(?:eter)?s?|Body|Fields?)|Param(?:eter)?s?|Query\s+Param|Body\s+Param|Headers?))\b
```

Also match Coinone Korean headings: `Request Body`, `Request Header` (these appear inline after `\n` unescaping).

If no heading found within 3000 chars forward, also search 500 chars backward (some tables appear before the endpoint definition).

### Step 3: Detect table format and parse

**Pipe table detection:** Look for separator row `---|---` within 200 chars after the heading.

**Tab table detection (Coinone/aster):** Look for `\t` characters in the lines after the heading (after `\n` unescaping for Coinone).

### Step 4: Parse header row

Map column positions by matching header cell text (case-insensitive):
- **Name column:** `name|field|parameter|param|필드|key` → index
- **Type column:** `type|유형|타입` → index
- **Required column:** `required|mandatory|optional|required/optional|필수` → index (optional — some tables don't have it)
- **Description column:** `description|comment|desc|설명|possible values` → index (optional)

If neither a name nor type column is detected, skip the table (not a parameter table).

### Step 5: Parse data rows

For each data row after the header:
1. Split by `|` (pipe) or `\t` (tab), strip whitespace
2. Extract name, type, required, description from mapped columns
3. **Nesting:** If name starts with `- ` (dash-space), strip the prefix and set `parent` to the last non-nested row's name
4. **Required normalization:** Map to boolean:
   - True: `true`, `yes`, `y`, `required`, `mandatory`, `O` (Korean convention)
   - False: `false`, `no`, `n`, `optional`, `X`, empty string
   - Leave as string if ambiguous (e.g., `conditional`)
5. Stop parsing when hitting: next heading (`#`), empty line followed by non-table content, or end of search window

### Step 6: Build request_schema

```python
{
    "parameters": [
        {
            "name": "symbol",
            "type": "string",
            "required": True,
            "description": "Trading pair symbol",
            "in": "body"  # or "query" for GET endpoints
        },
        {
            "name": "side",
            "type": "string",
            "required": True,
            "description": "BUY or SELL",
            "in": "body",
            "parent": None
        },
        {
            "name": "price",
            "type": "string",
            "required": False,
            "description": "Order price",
            "in": "body",
            "parent": "order_config"  # nested param
        }
    ]
}
```

Omit `parent` key when None (top-level params). Include `in` as `"query"` for GET/DELETE, `"body"` for POST/PUT/PATCH.

### Step 7: Store with citation

Update the endpoint record:
- Set `request_schema` to the parsed structure
- Set `field_status.request_schema` to `"documented"`
- Add a citation source pointing to the table's character range

For Postman-imported endpoints: match by exchange + path + method, only update if current `request_schema` is null.

## Files to Modify

| File | Change |
|------|--------|
| `src/xdocs/endpoint_extract.py` | Add `extract_params_near()` function |
| `src/xdocs/endpoint_extract.py` | Wire into `_build_endpoint_record()` call |
| `src/xdocs/endpoint_extract.py` | Add `backfill_params()` for Postman endpoints |
| `tests/test_endpoint_extract.py` | Add pipe table tests (cryptocom, bybit, apex formats) |
| `tests/test_endpoint_extract.py` | Add tab table tests (Coinone format) |
| `tests/test_endpoint_extract.py` | Add nested param tests (dash-prefix) |
| `tests/test_endpoint_extract.py` | Add edge cases (no table, non-param table, partial cols) |

## Implementation Order

1. **`extract_params_near(md, char_pos, method)`** — pure function, no DB:
   - Find heading → detect format → parse header → parse rows → return list[dict]
   - Coinone preprocessing: unescape `\n` → newlines before parsing
   - Returns empty list if no params found (not an error)

2. **Wire into `_build_endpoint_record()`** — set `request_schema` and `field_status`

3. **`backfill_params_cmd()`** — CLI command to fill Postman gaps:
   - For each Postman-imported endpoint with null request_schema:
     - Find its docs page via docs_url or page_url
     - Read the page markdown
     - Find the endpoint's char position (search for method+path)
     - Run `extract_params_near()`
     - Update the endpoint record

4. **Tests first** — write tests for `extract_params_near()` before implementation, using real markdown snippets from the data research above.

## Expected Yield

| Exchange | Endpoints | Expected params extracted |
|----------|-----------|-------------------------|
| cryptocom | 73 | ~60 (high — clean pipe tables) |
| phemex | 120 | ~40 (medium — many shared-page endpoints, description tables) |
| apex | 37 | ~30 (high — well-structured tables) |
| bybit | 304 | ~250 (high — consistent format across 300+ pages) |
| bitbank | 389 | ~80 (medium — 86 table rows across fewer endpoint pages) |
| coinone | 19 | ~19 (high — every endpoint has table) |
| aster | 21 | ~15 (medium — tab format) |
| woo | 73 | ~50 (medium — compact tables on single page) |
| okx | 353 | ~5 (low — most params in JS widgets) |
| coinex | 134 | ~50 (medium — varies by page) |
| **Postman backfill** | 1,070 | ~300-500 (depends on page availability) |

**Conservative total: ~600-900 new param records from crawl-extracted, ~300-500 from Postman backfill.**

## Also in This Milestone

- [ ] Verify Coinone's 2 potentially missing endpoints (43 paths in pages vs 41 in store)
- [ ] Check the 3 skipped Coinone pages (empty .markdown-body)
- [ ] Update xdocs-query skill: Coinone is Korean-only
- [ ] Update xdocs-maintain skill: add skill update to maintenance checklist
- [ ] Run A/B eval after parameter extraction to confirm no regressions

## Risks

1. **Table misidentification:** Non-param tables (error code tables, status tables) could be confused for param tables. Mitigation: require heading match AND header column match (name + type minimum).
2. **Phemex shared pages:** Single-page docs have many endpoints. Param tables may be far from the endpoint definition. Mitigation: strict forward-search with 3000 char limit.
3. **Coinone unescaping side effects:** The `\n` → newline conversion could break character offsets for citations. Mitigation: track offset adjustment, or compute citations on the original string.
4. **Postman backfill path matching:** Finding the right char position for a Postman-imported endpoint in the page requires searching for `METHOD /path` in the markdown. Fuzzy matching may be needed for `{{url}}`-prefixed paths.
