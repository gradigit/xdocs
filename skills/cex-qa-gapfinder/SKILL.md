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
python3 scripts/runtime_query_smoke.py
```

If the smoke test fails, stop and report the failure. Do not proceed with QA on a broken store.

## Blind Mode

Check if this is a **blind run** (every other run should be blind):

- If `qa-findings.jsonl` exists from a previous run, count the number of previous runs from `QA-REPORT.md` headers or file timestamps.
- **Odd-numbered runs** (1st, 3rd, 5th...): normal mode — read the full skill including Known Context.
- **Even-numbered runs** (2nd, 4th, 6th...): **blind mode** — skip the "Known Context" section entirely. Do not read it. Discover the system's characteristics from scratch.

Blind mode prevents anchoring to known issues and forces fresh exploration. Report which mode was used in the QA report.

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

### 7. Answer Correctness (source verification)

This is the most important category. Structural checks (status=ok, right domain) can pass while the answer is wrong.

For **10-15 answer pipeline results**, do deep verification:

1. Run `cex-api-docs answer "<query>" --docs-dir ./cex-docs` and capture the output.
2. For each cited URL in the response, find the corresponding page markdown. Use `cex-api-docs search-pages "<url fragment>" --docs-dir ./cex-docs` or query the DB directly: `SELECT markdown_path FROM pages WHERE canonical_url LIKE '%<fragment>%'`.
3. Read the actual markdown file from `cex-docs/pages/`.
4. Verify: does the excerpt in the answer actually appear in the source page? Does the claim match what the source page says? Is the information attributed to the right exchange?

Flag any answer where:
- The excerpt doesn't appear in the source page (hallucinated citation)
- The claim contradicts the source page (misattribution)
- The answer cites a page that exists but has no relevant content for the query (irrelevant citation)
- The answer is technically correct but misleading (e.g., cites a deprecated endpoint for a "how do I" question)

### 8. Adversarial / Fuzzing

Deliberately try to break the system with hostile inputs. This is NOT the same as "edge cases" — these are inputs a malicious or confused user might send.

Test at minimum:
- **SQL injection**: `'; DROP TABLE pages;--`, `" OR 1=1 --`, `UNION SELECT * FROM endpoints`
- **FTS5 injection**: `pages_fts MATCH 'rate AND limit'`, `NEAR(a b)`, unbalanced quotes `"rate limit`
- **Empty/whitespace**: empty string, spaces only, tabs, newlines
- **Binary/garbage**: random bytes, null bytes (`\x00`), control characters
- **Extreme length**: 50KB query string, single word repeated 10,000 times
- **Only stopwords**: "the and or is a", "of to in for"
- **Unicode edge cases**: RTL text, zero-width joiners, emoji-only queries, CJK characters
- **Path traversal**: `../../etc/passwd`, `..%2f..%2f`
- **Format confusion**: XML tags in queries, HTML entities, markdown formatting

For each test: does the system crash, hang, return an error, or handle it gracefully? Any unhandled exception is a critical finding. Any hang >30s is a high finding.

### 9. Golden QA Cross-Check

The maintainer has a golden QA file with expected results. Use it as an independent oracle.

1. Check if `tests/golden_qa.jsonl` exists. If not, skip this section.
2. Load a **random sample of 20-30 entries** (not all — time budget).
3. For each entry, run the answer pipeline with the query.
4. Compare:
   - Does the `status` match? (If golden QA expects a URL match but answer returns "unknown", that's a gap.)
   - Does the returned URL match or prefix-match the expected URL?
   - For entries with `classification` field, does `classify` produce the same type?
5. Report any mismatches as findings with type `regression` if the system should have handled them.

Do not treat the golden QA as infallible — it's a reference, not ground truth. If the system returns a better result than the golden QA expects, note it as an `observation`, not a bug.

## Regression Tracking

If `qa-findings.jsonl` exists from a **previous** QA run:

1. Load the previous findings.
2. For each previous finding with `reproducible: true`, re-run the test.
3. Classify each as:
   - **Fixed**: the issue no longer reproduces → type: `observation`, title: "FIXED: <original title>"
   - **Still present**: the issue still reproduces → type: `regression`, with original evidence + new evidence
   - **Changed**: the behavior changed but is still wrong → type: `bug`, describe both old and new behavior
4. Include a "Regression Summary" section in QA-REPORT.md: N fixed, M still present, K changed.

If no previous `qa-findings.jsonl` exists, skip this section and note "first run — no regression baseline" in the report.

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
  "category": "data_integrity|coverage|query_pipeline|edge_case|performance|citation_quality|answer_correctness|adversarial|golden_qa",
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
2. **Mode** — normal or blind (and run number if known)
3. **Scope** — what was tested, how many tests, which exchanges
4. **Regression summary** — N fixed, M still present, K changed (or "first run")
5. **Summary metrics** — pass rate, findings by severity, findings by category
6. **Critical/High findings** — detailed, with reproduction steps
7. **Medium/Low findings** — table format
8. **Answer correctness results** — table of verified answers with pass/fail and reason
9. **Golden QA cross-check results** — match rate, mismatches
10. **Adversarial results** — table of inputs with crash/hang/error/graceful outcome
11. **Observations** — things that aren't bugs but are worth noting
12. **Suggested skill updates** — improvements to THIS skill based on what you learned

### 3. Human brief (mandatory final output)

After writing the files, your **final message to the human** must be a concise brief they can read without opening any files. Format:

```
## QA Run Summary

**Mode:** normal|blind (run #N)
**Tests run:** N across M exchanges
**Findings:** X critical, Y high, Z medium, W low
**Regressions:** N fixed, M still present (or "first run")
**Pass rate:** NN%

### Top issues (action required)
1. [severity] Title — one-line description
2. [severity] Title — one-line description
3. ...

### Answer correctness
- N/M answers verified correct
- Key failures: ...

### Observations (no action needed)
- ...

**Files written:** qa-findings.jsonl, QA-REPORT.md
**Next step:** Hand these files to the maintainer agent for verification.
```

Keep it under 50 lines. The human should be able to read this in 30 seconds and know whether to escalate or continue.

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

**If this is a blind mode run (even-numbered), STOP READING HERE. Skip to the Version section.**

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

v2.0.0 — Major update: answer correctness, adversarial fuzzing, golden QA cross-check, regression tracking, blind mode.

### Changelog

- v2.0.0: Added 3 new test categories (answer correctness, adversarial/fuzzing, golden QA cross-check). Added regression tracking against previous qa-findings.jsonl. Added blind mode rotation (even runs skip Known Context). Updated report format with new sections. Updated JSONL category enum. Bumped human brief to 50 lines.
- v1.1.0: Added mandatory human brief (concise final message), QA branch handoff workflow for cross-machine runs, restructured report format section.
- v1.0.0: Initial gap finder skill with 6 test categories, JSONL + markdown report format, self-evolution mechanism.
