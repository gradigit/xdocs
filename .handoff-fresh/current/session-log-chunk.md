# Session Log Chunks

**Generated**: 2026-03-12
**Token budget**: 8000 target / ~4000 actual

## Chunk 1: BUG-21 Root Cause (from code explorer agent)

```
Root Cause: sanitize_fts_query() in fts_util.py:80
Regex: r'[-:"/{}()*?=&+#@!<>]' is missing single-quote '

Code paths affected:
- search-pages (pages.py:21) — CRASHES
- search-endpoints (endpoints.py:627) — has retry fallback, doesn't crash
- search-error (lookup.py:156) — SAFE (allowlist regex)
- answer._search_pages (answer.py:471) — SAFE (upstream extract_search_terms strips punctuation)

Fix: Added ' and ; to character class.
```

## Chunk 2: BUG-18 Root Cause (from code explorer agent)

```
answer.py direct route citation construction:

Line 1223 (endpoint_path):
  "citations": [{"url": docs_url}] if docs_url else []

Line 1258 (error SOURCE):
  "citations": [{"url": url}] if url else []

Line 1266 (error ENDPOINT):
  "citations": []  # completely empty!

Generic search path (lines 854-862) builds full citations:
  citation = {"url": ..., "crawled_at": ..., "content_hash": ...,
              "path_hash": ..., "excerpt": ..., "excerpt_start": ..., "excerpt_end": ...}

Fix: After resolving docs_url, read page markdown, call _make_excerpt(),
attach result to citation dict. ~15 LOC per path.
```

## Chunk 3: 10-Run Batch Statistics

```
Runs: #3-#12 (5 normal, 5 blind)
340 total checks, avg 34/run, avg 74.3s/run
Mean pass rate: 61.1%
Verified answers: 11 clean, 9 mixed, 11 fail
Golden QA URL match: 7/34 (20.6%)
Adversarial: 33/41 graceful, 8 unhandled (all FTS5 crash — now fixed)

Finding frequency:
- Exchange detection miss: 10/10
- Numeric misclass: 10/10
- Nav chrome: 9/10
- Bare endpoint unknown: 8/10
- Multi-exchange collapse: 7/10
- FTS5 crash: 7/10 (FIXED)
- URL-only citations: 5/10
```

## Chunk 4: Gapfinder Skill Version History

```
v1.0.0: Initial template (8 test categories, JSONL + report output)
v2.0.0: Answer correctness, adversarial fuzzing, golden QA cross-check,
        regression tracking, blind mode rotation
v2.1.0: Answer Output Schema docs, exchange detection sweep,
        bare endpoint path tests, nav chrome gate
v2.1.1: Runtime model stack detection (embedding, reranker, fusion)
v2.2.0: Citation schema gate, answer grading tiers (clean/mixed/fail),
        multi-exchange ambiguity test, >30s adversarial threshold
```

## Chunk 5: cex-api-query v2.11.0 Addition

```
Step 5c: Negative Evidence and Third-Party Queries

Negative evidence (feature/protocol support questions):
1. Check structured endpoints for protocol/feature keywords
2. Grep stored markdown for the feature name
3. If both negative: "Not found in the local docs snapshot" — valid answer
4. Do NOT escalate to web search just because local retrieval is empty
5. Only browse live if user explicitly asks for current verification

Third-party vendor questions:
1. Answer official-exchange portion from local store first
2. Label named vendors as out-of-corpus
3. Do not browse to validate vendor claims unless user requests it
```
