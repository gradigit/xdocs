# Research: CEX API Docs Crawling/Scraping Stack Review
Date: 2026-02-26
Depth: Full

## Executive Summary
The current crawler is robust in core safety areas (domain allowlists, robots-aware behavior, retries, byte limits, deterministic storage), but it has three high-impact efficiency/fidelity gaps:
1) **Section overlap causes heavy duplicate fetching** (42.4% duplicate inventory entries across latest inventories; 57.7% duplicate ratio on `developers.binance.com`).
2) **No conditional HTTP revalidation** despite storing ETag/Last-Modified metadata, so refresh runs can send avoidable full responses.
3) **Extraction fidelity for code snippets is lossy/awkward for downstream NLP** (`[code] ... [/code]` markers dominate instead of fenced code blocks).

Net: the stack is solid, but with targeted changes it can become significantly faster, less block-prone, and higher-fidelity without changing your core architecture.

---

## Sub-Questions Investigated
1. What does the current crawling/scraping stack actually do (from code + store evidence)?
2. Which anti-blocking methods are implemented vs missing compared to standards/docs?
3. How well does the stack preserve API-doc content (especially code blocks)?
4. What are the best-practice methods from official sources?
5. What concrete upgrades give highest ROI for this specific repo?

---

## Current Stack (Repository-grounded)

### Pipeline
- `sync` orchestration: inventory generation + fetch per section (`src/cex_api_docs/sync.py`).
- Inventory/fetch split with resume/refetch modes (`inventory.py`, `inventory_fetch.py`).
- Fetchers:
  - HTTP fetch: `requests` + retries + redirect/domain checks (`httpfetch.py`)
  - Playwright fallback for JS-heavy pages (`playwrightfetch.py`)
- Extraction: HTML -> markdown via `html2text` (`markdown.py`), then normalization.
- Persistence:
  - raw bytes (`raw/`)
  - markdown (`pages/`)
  - metadata JSON (`meta/`)
  - SQLite tables + FTS5 (`docs.db`)
- Quality gate: empty/thin/tiny_html (`quality.py`)

### What is working well
- Deterministic store + versioning (`page_versions`).
- Per-domain allowlist enforcement + redirect host validation.
- Basic anti-overload controls (`delay_s`, retries, per-domain rate limiter in concurrent mode).
- Render fallback path for JS docs (`--render auto`).

---

## Empirical Findings (local store/runtime)

### Crawl scale and duration
- Latest inventories: **37 sections**, **7,133 inventory entries**.
- Pages stored: **3,819**.
- Historical first non-resume section runs: **~59.2 min total** for **6,944 fetched pages**.

### Duplication gap (major)
Across latest inventories:
- Total entries: 7,133
- Unique canonical URLs: 4,107
- Duplicate entries: 3,026 (**42.4% duplicate rate**)

By host:
- `developers.binance.com`: 4,391 total / 1,857 unique (**57.7% duplicate**)
- `www.kucoin.com`: 868 total / 435 unique (**49.9% duplicate**)

Notable section overlap:
- `binance/copy_trading` and `binance/wallet`: **1,853/1,853 URLs overlap (100%)**.

### Content-quality signals
`quality-check` currently reports:
- total 3,819
- empty 3
- thin 146
- tiny_html 0

Interpretation: extraction largely succeeds, but quality thresholds likely over-flag some concise docs.

### Code block preservation signal
In stored markdown:
- files containing `[code]`: **2,460**
- `[code]` occurrences: **11,531**
- triple-backtick fences are rare.

Interpretation: code survives but in a format less ideal for downstream chunking/retrieval and model prompting.

---

## External Best-Practice Research (official/primary sources)

### 1) Robots handling and crawl politeness
- RFC 9309 defines robots semantics, including treatment of successful/unavailable/"unreachable" robots fetches and caching guidance.
- Your current behavior aligns on core 2xx/4xx/5xx posture, but caching/revalidation policy can be tightened.

### 2) Retry/backoff behavior
- RFC 6585 defines `429 Too Many Requests` and notes `Retry-After` usage.
- RFC 9110 defines `Retry-After` semantics.
- urllib3 supports retry policies with `respect_retry_after_header`.

Gap: current fetch path retries on 429/5xx with backoff, but does not explicitly honor `Retry-After`.

### 3) Conditional revalidation to reduce load/block risk
- RFC 9110 defines conditional requests (`If-None-Match`, `If-Modified-Since`) and `304 Not Modified`.

Gap: metadata already stores ETag/Last-Modified, but crawler does not currently issue conditional revalidation headers.

### 4) Crawl state persistence and resumability patterns
- Scrapy documents resumable crawl jobs (`JOBDIR`) and disk-backed scheduler state.

Your stack has strong section-level resume semantics already; opportunity is broader dedupe/state across sections.

### 5) Adaptive throttling
- Scrapy AutoThrottle adjusts delay based on measured latency/load.

Gap: current delay is static (`delay_s`) and only lightly adaptive via retries.

### 6) Extraction fidelity options
- Playwright `page.content()` returns full HTML contents of the page.
- `html2text` exposes `mark_code` behavior (used in your pipeline), producing code markers.
- Trafilatura supports richer extraction and multiple output formats (markdown/XML/JSON/TEI).

Implication: keeping your current extractor is fine for stability, but a code-block-aware extractor mode would improve downstream retrieval quality.

### 7) Background operation on macOS
- Apple docs describe `launchd`/`launchctl` as the native persistent background scheduling mechanism.

Implication: move long recurring syncs to launchd jobs rather than ad-hoc terminal backgrounding.

---

## Comparison: Current vs Best Methods

| Area | Current | Best-practice target | Gap severity |
|---|---|---|---|
| Section overlap control | Per-section inventories, no global URL dedupe | Global dedupe registry + tighter section scope prefixes | **High** |
| HTTP freshness | Full fetch/refetch patterns | Conditional revalidation (`If-None-Match`/`If-Modified-Since`) | **High** |
| Rate control | Static delay + retries | Adaptive throttling + Retry-After honoring + domain budgets | **High** |
| JS rendering | HTTP first + Playwright fallback | Keep this; add clearer per-domain render policy and fallback caps | Medium |
| Content fidelity | html2text markdown with `[code]` markers | Code-fence-preserving extraction mode + optional structured blocks | **High** |
| Resumability | Good (`--resume`) | Keep + add cross-section global fetch memoization | Medium |
| Background ops | Manual command/nohup usage | launchd-managed periodic sync + logging | Medium |

---

## Priority Improvements (recommended order)

### P0 (do first)
1. **Fix inventory scope overlap for Binance/KuCoin sections**
   - Add explicit section scope prefixes or stricter seed normalization.
   - Add cross-section dedupe before fetch execution.
   - Expected impact: major runtime and block-risk reduction.

2. **Add conditional revalidation**
   - Send `If-None-Match` / `If-Modified-Since` from stored metadata.
   - Persist 304 stats in sync report.
   - Expected impact: lower bandwidth + fewer anti-bot triggers.

3. **Honor `Retry-After` + stronger 429 policy**
   - Parse header and enforce minimum sleep.
   - Add exponential jittered backoff cap per domain.

### P1
4. **Code-block fidelity mode**
   - Normalize `[code]` blocks to fenced markdown (` ``` `) or store structured `code_blocks` alongside markdown.
   - Keep raw bytes and rendered HTML for provenance.

5. **Adaptive domain throttling**
   - Start with per-domain config file (default delay/concurrency/max burst).
   - Optional later: latency/429-driven auto-adjust.

6. **launchd production runner**
   - Ship a sample `plist` and log rotation strategy.

### P2
7. **Extractor A/B harness**
   - Compare html2text vs alternate extractor on a gold set.
   - Score on: word recall, code-block integrity, link integrity, citation stability.

---

## Hypothesis Tracking

| Hypothesis | Confidence | Supporting Evidence | Contradicting Evidence |
|---|---|---|---|
| H1: Duplicate section inventory is your #1 crawl-time waste | High | 42.4% duplicate entries globally; 57.7% dup on developers.binance.com; 100% overlap in major sections | None observed in local stats |
| H2: Conditional requests will reduce block risk and runtime on refresh | High | RFC 9110 conditional semantics; ETag/Last-Modified already captured in metadata | Effect size depends on server support |
| H3: Current code-block output format hurts downstream retrieval quality | Medium-High | 11,531 `[code]` markers and very few fenced blocks | Some downstream pipelines can still parse `[code]` |
| H4: Fully replacing custom crawler with Scrapy is necessary | Low | Scrapy has strong features | Current architecture already covers many core needs; targeted upgrades likely enough |

---

## Verification Status

### Verified (2+ sources)
- Respecting `429`/`Retry-After` is standard-compliant and should influence retry timing (RFC 6585 + RFC 9110 + urllib3 retry API).
- Conditional requests are standard for efficient revalidation (RFC 9110 + RFC 9111).
- Adaptive throttling is an established crawler pattern (Scrapy AutoThrottle docs + Scrapy broad crawler design guidance).

### Unverified / environment-dependent
- Exact percentage runtime improvement from each change (needs A/B run in your environment).
- Whether alternate extractor beats html2text on your specific doc corpus (needs benchmark harness).

### Conflicts
- No major source conflicts; differences were mostly implementation choices rather than factual contradictions.

---

## Limitations & Gaps
- I did not run a brand-new full crawl benchmark in this pass (used historical runtime + store stats).
- Anti-bot behavior varies by exchange/CDN over time; real-world tuning should remain domain-specific.

---

## Sources (quality-filtered)

| Source | URL | Quality | Notes |
|---|---|---|---|
| RFC 9309 (Robots Exclusion Protocol) | https://www.rfc-editor.org/rfc/rfc9309 | High | Canonical robots semantics |
| RFC 6585 (429 status code) | https://www.rfc-editor.org/rfc/rfc6585 | High | Defines 429 and Retry-After usage |
| RFC 9110 (HTTP semantics) | https://www.rfc-editor.org/rfc/rfc9110 | High | Retry-After + conditional request semantics |
| RFC 9111 (HTTP caching) | https://www.rfc-editor.org/rfc/rfc9111 | High | Cache/revalidation model |
| urllib3 Retry API docs | https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html#urllib3.util.Retry | High | Practical retry policy knobs |
| Scrapy AutoThrottle docs | https://docs.scrapy.org/en/latest/topics/autothrottle.html | High | Adaptive crawl delay guidance |
| Scrapy Jobs (pause/resume) docs | https://docs.scrapy.org/en/latest/topics/jobs.html | High | Durable crawl state patterns |
| Scrapy HTTP cache docs | https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcachemiddleware | High | Revalidation/cache middleware patterns |
| Playwright `page.content()` API | https://playwright.dev/python/docs/api/class-page#page-content | High | Rendered HTML capture semantics |
| html2text project docs | https://github.com/Alir3z4/html2text | Medium-High | Code-marking behavior and conversion controls |
| Trafilatura docs | https://trafilatura.readthedocs.io/en/latest/ | Medium-High | Alternative extraction output options |
| Apple launchd/launchctl guide | https://support.apple.com/en-il/guide/terminal/apdc6c1077b-5d08-4a28-8f9d-7146f865a66f/mac | High | Native macOS background scheduling |

