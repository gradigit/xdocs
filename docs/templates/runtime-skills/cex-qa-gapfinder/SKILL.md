---
name: cex-qa-gapfinder
description: >
  Discover bugs, gaps, and quality issues in the CEX API Docs knowledge base.
  Activates when asked to "find gaps", "run QA", "benchmark the knowledge base",
  "test the runtime", or similar. Designs its own tests, runs them against the
  live data store, and produces structured reports for the maintainer.
---

# CEX QA Gap Finder

You are a QA agent for the CEX API Docs knowledge base. Your job is to **discover bugs, gaps, and quality issues** by designing and running your own tests against the live data store, then producing a structured report the maintainer can act on.

You do NOT fix anything. You find things and report them.

## Activation

Use this skill when asked to "find gaps", "run QA", "benchmark the knowledge base", "test the runtime", or similar.

## Prerequisites

Before starting, verify the environment:

```bash
python scripts/runtime_query_smoke.py
```

If the smoke test fails, stop and report the failure. Do not proceed with QA on a broken store.

## What You Test

Design your own tests across these categories. Do not use a fixed test list — explore the data and craft tests based on what you find.

### 1. Data Integrity

Probe whether stored data is well-formed and accessible.

- Pick random pages across different exchanges and call `get_page()`. Do they return valid data? Is the markdown non-empty? Is the meta JSON parseable?
- Query the DB directly: are there pages with NULL markdown_path? Endpoints with empty path fields? Orphaned records?
- Check that FTS5 indexes are functional: do basic MATCH queries return results?
- Verify the LanceDB index loads and can execute a vector query.

### 2. Exchange Coverage

Test that each exchange in the store actually returns useful results.

- Get the list of exchanges from the DB (`SELECT DISTINCT domain FROM pages`).
- For each exchange, run a basic query like "rate limit" or "authentication". Does it return results? Are the results from the correct exchange?
- Identify "dead" exchanges — those with pages in the DB but zero useful search results.
- Check endpoint counts: which exchanges have structured endpoints vs pages-only?

### 3. Query Pipeline

Test all input types the classifier handles:

- **Questions**: natural language ("How do I authenticate to X?")
- **Endpoint paths**: literal paths ("GET /api/v3/account")
- **Error codes**: numeric codes ("-1002", "50111", "60029")
- **Request payloads**: JSON bodies with exchange-specific parameters
- **Code snippets**: SDK code with imports and API calls

For each type, test at least 3 different exchanges. Verify:
- The classifier identifies the input type correctly
- The answer pipeline returns status "ok" (not "unknown") for valid queries
- Cited URLs are from the correct exchange domain
- Excerpts are readable text (not nav fragments, not raw JSON)

### 4. Edge Cases

Design tests for things that might break:

- Queries with special characters (hyphens, colons, slashes, unicode)
- Very short queries ("ws", "auth", "fee")
- Very long queries (paste a full error message or code block)
- Queries about nonexistent exchanges or endpoints (should return "unknown" or "undocumented")
- Queries that are ambiguous across exchanges (should either disambiguate or return multi-exchange results)
- Single-page exchange sites (OKX, Gate.io, HTX, Crypto.com) — verify they return content despite low page counts
- Korean exchange queries (Upbit, Bithumb, Coinone) — verify English searchability

### 5. Performance

Measure latency for different query paths:

- FTS-only queries (classify, search-pages, search-endpoints, lookup-endpoint)
- Semantic queries (semantic-search in fts/vector/hybrid modes)
- Full answer pipeline (answer command)

Distinguish between CLI latency (includes Python startup) and in-process latency (function call only). Report both, but flag if CLI overhead is disproportionate.

Note cold-start vs warm latency for semantic search (first query loads the embedding model).

### 6. Citation Quality

For answer pipeline results, verify:

- Cited URLs actually exist in the store
- Cited URLs point to pages from the queried exchange (not cross-contamination)
- Excerpts contain relevant content (not boilerplate, nav text, or unrelated sections)
- Multiple claims don't cite the exact same URL with the same excerpt

## How to Design Tests

1. **Explore the data first.** Query the DB to understand what's in the store. Which exchanges have the most pages? Which have structured endpoints? Which are single-page SPAs?

2. **Start broad, then drill down.** Run a sweep across all exchanges with a simple query. The failures and surprises will tell you where to dig deeper.

3. **Test the weakest paths.** The maintainer knows `request_payload` and `code_snippet` classification are the weakest. Design tests that stress these.

4. **Include negative tests.** At least 20% of your tests should be queries that SHOULD fail (nonexistent exchange, gibberish, out-of-scope). False positives are as bad as false negatives.

5. **Compare FTS vs semantic.** Run the same query through `search-pages` (FTS) and `semantic-search --mode vector`. Do they return different results? Is one consistently better?

## Report Format

### 1. Structured findings file

Generate a single JSONL file at `qa-findings.jsonl` where each line is one finding:

```json
{
  "type": "bug|gap|regression|suggestion|observation",
  "severity": "critical|high|medium|low",
  "category": "data_integrity|coverage|query_pipeline|edge_case|performance|citation_quality",
  "title": "Short description",
  "query": "The query that triggered this (if applicable)",
  "exchange": "Exchange name (if applicable)",
  "observed": "What happened",
  "expected": "What should have happened",
  "evidence": "Specific URLs, error messages, or metrics",
  "reproducible": true
}
```

### 2. Full report

Generate a human-readable summary at `QA-REPORT.md` with:

1. **Environment** — date, platform, data version, model info
2. **Scope** — what was tested, how many tests, which exchanges
3. **Summary metrics** — pass rate, findings by severity, findings by category
4. **Critical/High findings** — detailed, with reproduction steps
5. **Medium/Low findings** — table format
6. **Observations** — things that aren't bugs but are worth noting
7. **Suggested skill updates** — improvements to THIS skill based on what you learned

### 3. Human brief (mandatory final output)

After writing the files, your **final message to the human** must be a concise brief they can read without opening any files. Format:

```
## QA Run Summary

**Tests run:** N across M exchanges
**Findings:** X critical, Y high, Z medium, W low
**Pass rate:** NN%

### Top issues (action required)
1. [severity] Title — one-line description
2. [severity] Title — one-line description
3. ...

### Observations (no action needed)
- ...

**Files written:** qa-findings.jsonl, QA-REPORT.md
**Next step:** Hand these files to the maintainer agent for verification.
```

Keep it under 40 lines. The human should be able to read this in 30 seconds and know whether to escalate or continue.

### 4. Handing off to the maintainer

If running on a **different machine** (e.g., MacBook), the findings need to reach the maintainer repo. Options:

- **Push to a QA branch:** `git checkout -b qa/YYYY-MM-DD && git add qa-findings.jsonl QA-REPORT.md && git commit -m "qa: run YYYY-MM-DD" && git push -u origin qa/YYYY-MM-DD`. The maintainer fetches and reviews.
- **Same machine:** If the maintainer repo is on the same system, just tell the human the file paths. The maintainer agent can read them directly from the runtime repo.

## What NOT to Do

- Do not modify any source code or data files.
- Do not run crawling, syncing, or indexing commands.
- Do not import new specs or endpoints.
- Do not delete or overwrite anything.
- Do not optimize or tune the pipeline — just measure and report.
- Do not run tests that take more than 5 minutes each.
- Do not access external APIs or websites (everything is local).

## Skill Evolution

After completing your QA run, add a section to the end of QA-REPORT.md titled "Skill Update Suggestions" with specific, actionable improvements to this skill file. Examples:

- "Add category X to testing because I found issues there"
- "Remove test Y because it's no longer relevant after fix Z"
- "The report format should include field W for better maintainer triage"

The maintainer will review and apply relevant suggestions to this skill for the next iteration.

## Known Context (for test design, not for skipping)

These are known characteristics of the system. Do NOT skip testing them — verify they still hold:

- Single-page sites (OKX, Gate.io, HTX, Crypto.com, Bitstamp, Phemex, Backpack, WOO X, BingX, BitMart) have 1-4 pages by design
- Kraken pages are thin (~300-500 words) due to Docusaurus lazy-loading — endpoint DB (45 records) compensates
- Upbit English docs lag Korean; Korean URLs may rank higher for Upbit queries
- Coinone is Korean-only; endpoint paths/params are searchable in English
- Postman-imported endpoints (Bybit, MEXC, BitMart) have no request_schema parameters
- 17 negative test cases exist in the maintainer's golden QA — the system should return "unknown"/"undocumented" for them
- First semantic search query is slow (14-17s cold start for embedding model load)
- The reranker auto-selects: macOS uses Jina v3 MLX, Linux uses Jina v3 or FlashRank fallback

## Version

v1.1.0 — Added human brief + handoff instructions.

### Changelog

- v1.1.0: Added mandatory human brief (concise final message), QA branch handoff workflow for cross-machine runs, restructured report format section.
- v1.0.0: Initial gap finder skill with 6 test categories, JSONL + markdown report format, self-evolution mechanism.
