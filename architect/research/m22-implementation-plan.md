# M22 Implementation Plan — Clinical Query Optimization

## Execution Order (by data-driven impact, not original phase numbers)

### Step 0: A/B Testing Infrastructure (PREREQUISITE)
**Files**: `tests/eval_answer_pipeline.py`, `scripts/ab_test_m22.py`

Before ANY code change, enhance the eval framework:

1. **Per-path regression detection** in `_compare_baselines()`: currently only checks aggregate metrics. Must flag per-type regressions (e.g., "request_payload MRR dropped 5% even though overall improved")
2. **A/B test script** (`scripts/ab_test_m22.py`): automates running baseline → change → compare. Outputs per-type deltas and regression warnings.
3. **Baseline locked**: `reports/m22-baseline.json` (already saved)

Acceptance: eval script catches any per-type regression >= 3%

### Step 1: Lower Auto-Rerank Threshold (1 LOC, VERY LOW risk)
**File**: `src/cex_api_docs/semantic.py`
**Change**: `_AUTO_RERANK_MIN_CANDIDATES = 12` → `6`

Rationale: 17 golden QA queries on small exchanges currently skip reranking. This is a trivial fix with zero risk of regression on other types.

A/B: Run eval, compare small-exchange queries specifically.

### Step 2: BUG-13 Section Hint Enhancement (30 LOC, LOW risk)
**File**: `src/cex_api_docs/answer.py`

Currently: `_detect_binance_section()` detects section but only reorders, doesn't filter.
Fix: When section detected AND confidence high, add URL-prefix filtering to ensure at least 1 result from detected section appears in top-3.

Approach:
- After collecting all_section_candidates, if detected_section exists, ensure the top result from that section is promoted to rank 1-3
- NOT a hard filter (that would miss cross-section results) — a "guaranteed inclusion" approach
- Only applies when question text explicitly mentions a section keyword (spot, futures, margin, etc.)

A/B: Test on the 13 Binance queries with section keywords. Check for regression on remaining Binance queries.

### Step 3: Page-Type Boost Enhancement (20 LOC, LOW risk)
**File**: `src/cex_api_docs/answer.py`

Currently: `_apply_page_type_boost()` uses 1.4x for overview/intro URLs on broad queries.
Fix:
- Broaden URL patterns: add `quickstart`, `getting-started`, `quick-start`, `overview`, `intro`, `authentication`, `rate-limit`
- Increase boost to 1.8x (A/B test 1.4 vs 1.6 vs 1.8 vs 2.0)
- Broaden query patterns: "what API", "how does X work", "X API", section-level queries

Addresses 8 question misses where overview/intro pages lose to specific endpoint pages.

A/B: Compare 1.4x baseline vs enhanced patterns + higher boost.

### Step 4: Code-Syntax Stopwords (30 LOC, LOW risk)
**Files**: `src/cex_api_docs/fts_util.py`, `src/cex_api_docs/answer.py`

Add CODE_STOPWORDS set + BUG-14 patterns (crypto/API patterns) in same change.

Fallback: if ALL terms are stopwords after filtering, keep the 2 most distinctive (longest non-stopword tokens).

A/B: Compare code_snippet MRR with/without stopwords.

### Step 5: Operation-Type Inference (80 LOC, LOW risk)
**Files**: `src/cex_api_docs/classify.py`, `src/cex_api_docs/answer.py`

Build `_PAYLOAD_ACTION_MAP` (15 patterns) + fix exchange signature ordering.

A/B: Compare request_payload MRR with/without operation inference.

### Step 6: Endpoint search_text Enrichment (15 LOC, VERY LOW risk)
**Files**: `src/cex_api_docs/fts_util.py`, FTS rebuild

Add param names to search_text. Requires FTS rebuild.

A/B: Compare endpoint_path and request_payload after FTS rebuild.

### Step 7: FTS/Semantic Query Separation (20 LOC, LOW risk)
**Files**: `src/cex_api_docs/semantic.py`, `src/cex_api_docs/answer.py`

Clean "AND" tokens from vector queries.

A/B: Compare embedding quality on multi-term queries.

### Step 8: Score-Aware Fusion [CONDITIONAL]
**Only if Steps 1-7 don't reach MRR 0.65 target.**

CC fusion with per-type alpha. Feature-flagged. Extensive A/B required.

## Self-Critique

1. **Risk: Page-type boost overshoot** — boosting overview pages too aggressively could regress specific endpoint queries that correctly rank first. Mitigated by: only applying to broad queries (detected via pattern).

2. **Risk: Section filtering too aggressive** — hard filtering by section could miss correct cross-section results (e.g., a general API page that covers both spot and futures). Mitigated by: "guaranteed inclusion" instead of hard filter.

3. **Risk: Code stopwords too aggressive** — removing too many terms could leave queries with 0-1 meaningful terms. Mitigated by: minimum 2 terms fallback.

4. **Risk: Operation inference overfitting** — the 15 patterns are tuned to golden QA. Real-world payloads may not match. Mitigated by: fallback to existing param-based search.

5. **Risk: CC fusion regression** — score normalization is query-dependent. Fixed alpha may regress some types. Mitigated by: feature flag + only if needed.

## Metrics to Track Per Step

After each step, record:
- Overall MRR, nDCG@5, pfx%
- Per-type MRR for all 5 types
- Specific targeted queries (named list)
- Test suite count and pass rate
