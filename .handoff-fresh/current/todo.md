# TODO (Fresh Bundle)

**Generated**: 2026-03-12

## Completed Milestones (M1-M22b)

All complete. 22 milestones across research, building, evaluation, and optimization phases. See root `TODO.md` for full history.

Key achievements: 46-exchange knowledge base, semantic search with Jina v5-small embeddings, Jina v3 reranker, RRF fusion, 200+ query golden QA benchmark, 559 tests.

## Open Bugs (Priority Order)

### High

- **BUG-18**: Direct-routed endpoint/error citations missing excerpts. `answer.py` ~lines 1223/1258/1266 build `{"url": docs_url}` without calling `_make_excerpt()`. ~15 LOC.
- **BUG-15**: Numeric literals in code → `error_message` misclassification. `classify.py` generic `\d{5,6}` pattern fires on order prices like `30000`. ~5 LOC.
- **BUG-16**: Nav chrome in excerpts. `_is_nav_region()` threshold 55% too high — "Skip to main content" passes through. ~30 LOC.
- **BUG-21**: ~~FTS5 crash on single quotes~~ **FIXED** this session. `sanitize_fts_query()` was missing `'` and `;` from regex.

### Medium

- **BUG-19**: Multi-exchange ambiguity silently picks first exchange. `_detect_exchange()` returns list, caller takes `matches[0]`. ~15 LOC.
- **BUG-17**: Path-only endpoint queries return unknown. No exchange auto-detection from path prefixes. ~20 LOC.
- **BUG-20**: No distinct `not_found` status for negative-evidence answers. `unknown` conflates "can't route" with "searched, found nothing." ~10 LOC.
- **BUG-7**: Semantic search snippet window too narrow for multi-detail queries.
- **BUG-8**: Blended score overrides reranker correction at top ranks.
- **BUG-9**: LanceDB chunks lose heading context (section title not prepended).

### Low

- **BUG-13**: Section hint from classification not threaded through to search.

## Deferred Milestones

- **M23**: Structured endpoint extraction from crawled docs (reduce Postman/spec dependency)
- **M24**: Content quality — Paradex URL drift, dYdX/Kraken thin pages, Bluefin login-gated, KuCoin nav pollution

## Deferred Research

- Score-aware CC fusion (only if MRR 0.65 target needed)
- GTE-ModernBERT-base reranker benchmark
- PRF (pseudo-relevance feedback)
- Korean language classification
- Param FTS enrichment (needs selective approach — A/B showed -12.6% when adding all params)
