# Pipeline Gap Analysis

## Summary

6 gaps identified. Binance section disambiguation accounts for 54% of prefix misses (7/13). Spec URL citations affect 70% of endpoints. Changelog FTS and LanceDB injection are trivial fixes. If all gaps are fixed, prefix hit rate could improve from 74% to ~90-94%.

## Gap 1: Binance Section Disambiguation (HIGH — 7/13 misses)

**Problem**: `_binance_answer` uses raw seed URLs (line 558) instead of `_directory_prefix()`. Additionally, `_infer_rate_limit_from_pages` (line 532) has the same issue. No section keyword mapping exists — queries about "margin", "futures", "options" all fall through to generic search.

**Root cause**: `_binance_answer` only has specialized logic for "unified trading", rate limits, and permissions. All other queries fall through to `_generic_search_answer` at line 742.

**Additional issue**: `wallet` and `copy_trading` seed URLs collapse to the same prefix `https://developers.binance.com/docs/`.

**Fix**:
1. Apply `_directory_prefix()` consistently in `_binance_answer` and `_infer_rate_limit_from_pages`
2. Add section keyword detection: "margin" -> margin_trading, "futures"/"usdm" -> futures_usdm, "options" -> options, "spot" -> spot, "websocket"/"ws" -> websocket
3. Use `scope_prefixes` from `inventory_policy` when available for wallet/copy_trading
4. Same pattern for Coinbase (3 sections overlap)

**Complexity**: medium
**Impact**: Fixes 7 of 13 prefix misses (+ 2 Coinbase)

## Gap 2: Spec URL Citations (MEDIUM — 70% of endpoints)

**Problem**: 3,410 of 4,872 endpoints (70%) have NULL `docs_url`. 17 exchanges have never had `link-endpoints` run. Unresolved endpoints cite raw spec URLs (e.g., `raw.githubusercontent.com`).

**Algorithm limitation**: `resolve_docs_url` uses only last 2 path segments via FTS, then requires literal path match in markdown. Fails for single-page exchanges and endpoints documented by description only.

**Fix**:
1. Run `link-endpoints` for all 27 exchanges with endpoints (batch script)
2. Add fuzzy path matching for exchanges with 0% resolution
3. Suppress spec URLs in answer claims — show "no docs URL" instead of misleading YAML links

**Complexity**: medium

## Gap 3: Changelog FTS Porter Stemming (LOW — trivial)

**Problem**: `changelog_entries_fts` created in v3→v4 without porter stemming. v4→v5 migration added porter to pages_fts and endpoints_fts but not changelog.

**Fix**: v5→v6 migration:
- Drop + recreate `changelog_entries_fts` with `tokenize = 'porter unicode61'`
- Mark exchange_id, section_id, entry_date as UNINDEXED
- Update schema.sql
- Bump SCHEMA_USER_VERSION to 6
- Require fts-rebuild after migration (1,095 rows)

**Complexity**: trivial (identical to v4→v5 pattern)

## Gap 4: Typed Query Routing (MEDIUM — efficiency + quality)

**Problem**: Classification is used only for augmentation, not routing. Full generic FTS search always runs first. For endpoint_path and error_message queries, this produces low-quality results before augmentation overrides them.

**Current design**: "F4: augment, not replace" (line 778). Intentional choice to avoid zero results on misclassification.

**Fix**: For high-confidence classifications (>= 0.7):
- endpoint_path → direct `lookup_endpoint_by_path` as primary
- error_message → direct `search_error_code` as primary
- question, code_snippet, request_payload → generic + augmentation (current behavior)

Add augmentation for request_payload (extract field names → search by parameter) and code_snippet (extract library references → link to SDK docs).

**Complexity**: medium
**Risk**: Must validate confidence threshold against golden QA to avoid regression

## Gap 5: Prefix Miss Root Causes (analyzed)

| Failure Mode | Count | Fix |
|---|---|---|
| Binance spot disambiguation | 5 | Gap 1 (section keywords) |
| Binance cross-section routing | 2 | Gap 1 (section keywords) |
| Coinbase section overlap | 2 | Gap 1 pattern |
| Spec URL citation | 1 | Gap 2 (link-endpoints) |
| Sub-page ranking | 1 | URL pattern boost for intro/overview |
| URL encoding mismatch | 1 | unquote() in eval script |
| Language mismatch (Upbit) | 1 | Update golden QA |

## Gap 6: LanceDB Exchange Filter Injection (LOW — trivial)

**Problem**: `semantic.py:477` uses f-string in `.where()`. Crafted exchange value could bypass filter.

**Severity**: Low (local CLI, exchange comes from registry in answer.py).

**Fix**: Add regex validation `r'^[a-z0-9_]+$'` before interpolation.

**Complexity**: trivial

## Priority Order

1. Gap 1 (Binance section disambiguation) — highest impact, fixes 7-9 misses
2. Gap 2 (spec URL citations) — improves citation quality for 70% of endpoints
3. Gap 3 (changelog FTS) — trivial, should just do it
4. Gap 6 (LanceDB injection) — trivial, defense-in-depth
5. Gap 4 (typed routing) — moderate impact, needs careful testing
6. Gap 5 (eval fixes) — trivial fixes for golden QA and eval script
