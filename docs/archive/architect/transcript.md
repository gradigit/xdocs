# Forging Plans Transcript

## Project Context: new project (greenfield)

## Raw Input

We want to build a **CEX API documentation intelligence layer** that can crawl, understand, and structure cryptocurrency exchange API documentation into a deterministic local knowledge base.

Key intent from prior drafts (treat as design notes/pseudocode, not implemented code):

- Two components:
  - `doc-crawler`: general-purpose doc crawler + SQLite FTS5 index.
  - `cex-api-docs`: CEX/DEX-specific extraction layer (endpoints, rate limits, permissions, error codes, canonical mapping, CCXT cross-reference, bilingual handling for Korean exchanges).
- Architecture principle: **AI agent handles understanding; scripts handle deterministic I/O**.
- Deterministic local search: **SQLite FTS5** as primary index (no embeddings for MVP).
- JS-rendered docs fallback: Playwright for SPA docs when curl/requests gets empty HTML.
- Canonical ops mapping: human-seeded canonical vocabulary (bootstrapped from CCXT unified methods but not reliant on CCXT as source of truth).
- Confidence scoring on extracted fields; medium/low confidence goes to a human review queue.
- Change detection: content hashes and diffs between crawls; cron-friendly update runner.

Existing materials in this repo (reference only):
- Draft plan: `docs/plans/2026-02-09-feat-cex-api-docs-intelligence-layer-plan.md`
- Prior handoff notes: `docs/archive/cex-api-docs-plan-handoff/` (contains reference schemas and draft scripts that should be treated as pseudocode)

User clarification: the “pre existing code” is effectively pseudocode; nothing has been built yet.

---

## Questionnaire

### Category 1: Core Vision

Q: What exactly is this (one sentence)? Also: is it a CLI tool, a library, or both, and who is it for?  
A: Both. For our team first.

Q: What problem does it solve for your team, specifically?  
A: Eliminates confusion about which endpoints to use, rate limits per endpoint, and API key permissions. Aids debugging data collection and development issues. Useful for onboarding so new teammates can query/talk to a unified API documentation knowledge base.

Q: What’s the single most important thing this must do well?  
A: It must give one hundred percent accurate information always.

Q: What’s the MVP “wow” query it must answer end-to-end?  
A: "What's the rate limit difference between Binance unified trading endpoint and the binance spot endpoint? And in order to look up the balance of our Binance Subaccount in Portfolio Margin Mode What permissions does the API key need?"

Q: Success criteria for MVP (measurable outcomes)?  
A: Information accuracy. Frictionless retrieval of API information.

### Category 2: Requirements & Constraints

Q: Hard constraints (language/tech, storage)?  
A: Any language is acceptable as long as it's best for the job. Data is stored locally.

Q: Soft constraints / preferences (what makes it “frictionless”)?  
A: "Just prompt the agent who has the skill installed with the right tools and everything just works."

Q: Compliance constraints?  
A: None specified. Internal use; docs are public.

Q: Integration constraints?  
A: None.

Q: Accuracy policy choice (for “100% accurate”)?  
A: Cite-only: never infer; every answer must be backed by stored sources and provenance. Otherwise return unknown/undocumented.

Q: Scope for exchanges?  
A: All 16 exchanges in the current registry (binance, okx, bybit, bitget, gateio, kucoin, htx, cryptocom, bitstamp, bitfinex, dydx, hyperliquid, upbit, bithumb, coinone, korbit).

Q: Explicit exclusions (what must it NOT do in v1)?  
A: No automatic trading. No hosted service. Purely designed to be a knowledge base.

Q: Primary interface / consumption?  
A: This should be a skill for Claude Code (and ideally usable by other agents as well). Deliverable is `SKILL.md` plus deterministic CLI commands returning JSON.

Q: Ingestion / extraction approach?  
A: Agent-run extraction: an agent reads the crawled docs and writes structured JSON; scripts do deterministic I/O only.

Q: Clarification: what do you mean by “Binance unified trading endpoint”?  
A: Binance supports unified trading through a unified sub-account (trade spot and futures on the same account with the same API key). There are different endpoints and different permissions for different endpoints, and portfolio margin mode adds more complexity and confusion.

### Category 3: Prior Art & Context

Q: Does anything like this already exist? Any prior attempts?  
A: Nothing like this exists. No prior attempts.

Q: Any reference implementations or inspirations?  
A: None.

### Category 4: Architecture & Structure

Q: What's the high-level structure? (components, layers, modules)  
A: Left up to the planner (agent) to decide.

Q: What technologies, tools, or frameworks are required or preferred?  
A: Left up to the planner (agent) to decide. Target runtime is macOS.

Q: What are the key interfaces between components?  
A: Left up to the planner (agent) to decide.

Q: What data flows through the system? In what format?  
A: Left up to the planner (agent) to decide.

Follow-up: Proposed defaults for Categories 4-6 were approved by user ("yes"):

- Category 4 defaults (approved):
  - Modules: `doc_store/` (crawl + store + index), `cex_extract/` (schemas and record helpers), `cli/` (deterministic JSON commands), `skills/` docs (`SKILL.md`).
  - Tech: Python 3 on macOS for v1, SQLite FTS5, Playwright optional for JS-rendered docs.
  - Interfaces: library API + CLI; storage is a single local store root with stable paths and one `db/docs.db`.
  - Data flow: raw HTML (stored) -> extracted markdown (stored) -> indexed text (SQLite); extracted CEX records as JSON + indexed JSON (SQLite). Cite-only provenance required for any answerable field.
  - Patterns: scripts do deterministic I/O; agent does interpretation/extraction; schema validation before writes; no heuristic endpoint parsing in code.
  - Version control/docs: initialize git; ignore local crawl outputs by default; README + SKILL.md + runbook for a Binance "wow query" end-to-end.

- Category 5 defaults (approved):
  - Validate CLI inputs; handle 429/5xx/timeouts/JS-only pages; continue on partial failures; single-writer per store for v1; concise user errors with detailed logs.

- Category 6 defaults (approved):
  - Expect hundreds to low-thousands of pages; common queries <1s; incremental recrawls; local-only store; retention knobs to bound disk growth.

### Categories 7-12: Defaults (approved)

User approved the proposed defaults for:
- Category 7: Security & Privacy
- Category 8: Integration & Dependencies
- Category 9: Testing & Verification
- Category 10: Deployment & Operations
- Category 11: Trade-offs & Priorities
- Category 12: Scope & Boundaries

### Categories 7-12 Defaults (Recorded)

Category 7: Security & Privacy (approved defaults)
- Local-only store. Do not store real API keys. No authenticated exchange API calls in v1.
- Strict domain scoping/allowlists for crawls to reduce SSRF risk.
- Conservative robots.txt defaults with explicit `--ignore-robots` override (internal use only).
- Treat translations as derived; preserve original excerpts for verification.

Category 8: Integration & Dependencies (approved defaults)
- Keep dependencies minimal. SQLite (via stdlib) as the only database.
- Optional Playwright path for JS-rendered docs.
- No hosted services; no external search infra.

Category 9: Testing & Verification (approved defaults)
- Pytest baseline with:
  - schema validation tests for endpoint/page JSON outputs
  - golden tests for CLI JSON shape (schema_version + error shapes)
  - small fixture-based crawl tests (avoid flaky live-network tests as the only verification)

Category 10: Deployment & Operations (approved defaults)
- macOS developer-first. No “deployment” beyond running locally.
- Cron-friendly update runner (periodic crawl + diff + re-review triggers).
- Structured logs (JSONL) for crawl actions and failures.

Category 11: Trade-offs & Priorities (approved defaults)
- Correctness and provenance over coverage.
- Deterministic indexing/search over embeddings for v1.
- If content is blocked (captcha/login), record limitation; don’t hack around it.

Category 12: Scope & Boundaries (approved defaults)
- Support a registry for all 16 exchanges, but MVP may fully crawl/extract only a subset.
- No automatic trading; no private data ingestion.

---

## Prior-Art Research

### Existing Solutions

| Solution | URL | Relevance | Quality | Notes |
|----------|-----|-----------|---------|-------|
| SQLite FTS5 (full-text search) | https://www.sqlite.org/fts5.html | High | Accepted (official) | Core for deterministic local search (ranking, snippets/highlights, optimize/rebuild maintenance commands). |
| Robots Exclusion Protocol (REP) RFC 9309 | https://www.rfc-editor.org/rfc/rfc9309.html | High | Accepted (IETF RFC) | Defines robots.txt parsing, error handling, caching; useful as a default crawler etiquette baseline even for internal/public docs. |
| Playwright `page.goto` / navigation loading strategies | https://playwright.dev/docs/api/class-page#page-goto | High | Accepted (official) | JS-rendered docs need a browser fallback. Official docs discourage `networkidle` in many cases; prefer explicit readiness checks. |
| Algolia DocSearch (legacy scraper migration, crawler-backed infra) | https://docsearch.algolia.com/docs/v3/migrating-from-legacy/ | Med | Accepted (official) | Prior art for doc crawling + record extraction; primarily a hosted workflow (Algolia Crawler) and tied to Algolia indices. Not aligned with local-only + CEX-specific structured extraction + provenance-first constraints. |
| Algolia Support: legacy docsearch-scraper not maintained | https://support.algolia.com/hc/en-us/articles/10360611138833-Can-I-still-use-the-legacy-DocSearch-scraper-locally | Med | Accepted (official) | Confirms the legacy local scraper is available but not maintained; reinforces not building on it as a foundation. |
| Typesense DocSearch guide (DocSearch-style scraping into Typesense) | https://typesense.org/docs/guide/docsearch.html | Low | Caution | Shows an alternative ecosystem approach (self-hosted search server). Not a fit for “no hosted service” / local-only. Included as landscape context only. |

### Key Findings

1. **FTS5 supports built-in ranking and snippet/highlight helpers**, including `bm25()` and `snippet()` (and related helpers) to implement fast deterministic search UI/CLI responses without embeddings. Source: SQLite FTS5 docs.  
2. **FTS5 has explicit maintenance commands** via the “special INSERT” mechanism (e.g., `optimize`, `rebuild`, `delete-all`) which should be used for index lifecycle operations (reindex, compaction, and resets) rather than ad-hoc hacks. Source: SQLite FTS5 docs.  
3. **Crawler robots.txt error handling is specified**: if `robots.txt` is unreachable due to server/network errors (e.g., HTTP 5xx), crawlers MUST assume complete disallow; if unavailable (e.g., HTTP 4xx), crawlers MAY access any resources. Source: RFC 9309 Section 2.3.1.3–2.3.1.4.  
4. **Playwright guidance cautions against using `networkidle` as a generic readiness strategy** (it can be unreliable on “chatty” sites). Prefer `domcontentloaded` plus explicit checks (e.g., required selector present, stable content length, etc.) for JS-rendered docs. Source: Playwright `page.goto` docs.  
5. **DocSearch has moved away from legacy scraper workflows** and now leverages Algolia Crawler infrastructure, with a hosted interface to schedule/monitor crawls. This is strong prior art for “docs to index” but does not meet local-only + cite-only provenance requirements as-is. Source: DocSearch migration docs.  

### Unverified Claims

- None recorded. (All core factual claims above are from official sources.)

### Conflicts

- None recorded.

### Sources

- SQLite: “FTS5 Extension” — Quality: Accepted — Accessed: 2026-02-10
- RFC 9309: “Robots Exclusion Protocol (REP)” — Quality: Accepted — Accessed: 2026-02-10
- Playwright docs: “class Page: page.goto” — Quality: Accepted — Accessed: 2026-02-10
- Algolia DocSearch: “Migrating from the legacy scraper” — Quality: Accepted — Accessed: 2026-02-10
- Algolia Support: “Can I still use the legacy DocSearch scraper locally?” — Quality: Accepted — Accessed: 2026-02-10
- Typesense docs: “Search for Documentation Sites” — Quality: Caution — Accessed: 2026-02-10

---

## Gap Analysis (Defaults Proposed)

### 1) “Cite-only” vs Derived Outputs

**Gap:** The product requirement is “cite-only” and “100% accurate always”, but user queries often ask for comparisons (“difference between rate limits”) which are not explicitly written as a single statement in docs.

**Default:** Allow *derived* statements only when they are pure, deterministic computations or transformations over cited facts (example: numeric difference between two cited weights). Label these as `[DERIVED]` and include citations for every input fact.

### 2) Ambiguity in “Unified Trading Endpoint”

**Gap:** “Unified trading” is overloaded (exchange marketing vs account mode vs API family).

**Default:** Model at the level of **doc site + base URL + section** (e.g., Binance `spot`/`futures_usdm`/`portfolio_margin`) and never collapse these unless the docs explicitly say they are equivalent. Queries that reference “unified” must be resolved to a specific section or return a clarifying question.

### 3) Permissions Taxonomy Across Exchanges

**Gap:** Every exchange uses different permission language (API-key flags, scopes, “read/trade/withdraw”, sub-account restrictions, portfolio margin capabilities).

**Default:** Store permissions as exchange-native strings plus free-form notes, and keep a separate optional normalization layer that is explicitly `[DERIVED]` (never the source of truth).

### 4) Rate Limit Modeling

**Gap:** Rate limits vary (request weights, order counts, per-IP vs per-UID, parameter-dependent weights, VIP tiers).

**Default:** Capture a minimum viable structure:
- `rate_limit.weight` + `weight_conditions`
- `rate_limit.rate_limit_type` + `interval` + `limit`
- `rate_limit.ip_or_uid` + `limit_notes`
Always keep `source_url` for the rate-limit statement (table/section URL).

### 5) Robots / ToS Posture

**Gap:** Even internal tools should avoid causing harm; REP handling affects reliability and etiquette.

**Default:** Respect robots.txt by default and follow RFC 9309 semantics. Provide an explicit `--ignore-robots` escape hatch for internal scenarios. If robots.txt is unreachable with 5xx, default to complete disallow (per RFC) until a later successful fetch.

### 6) Provenance Granularity

**Gap:** Endpoint schema implies per-endpoint provenance, but “cite-only” ideally needs per-field provenance.

**Default:** v1 stores:
- Per-endpoint provenance (`source.url`, `crawled_at`, `content_hash`, `page_title`)
- Optional per-field provenance for the most failure-prone fields (`required_permissions`, `rate_limit`, `error_codes`) as separate `{source_url, excerpt}` objects when feasible.
If per-field provenance is missing, the tool must be conservative: output `undocumented` rather than guessing.

### 7) Translation (Korean Exchanges)

**Gap:** Translation can silently introduce errors.

**Default:** Treat translations as `[DERIVED]`. Store original text excerpt + language code; allow translated helper text but never treat it as canonical.

### 8) SQLite Concurrency

**Gap:** Multi-agent crawling suggests concurrent writes; SQLite is single-writer.

**Default:** v1 uses a single writer process for DB writes. Parallel agents can produce JSON artifacts; a single ingest step persists into SQLite.

---

## Challenge: Self-Critique (Phase A)

### Self-Critique Results

| # | Severity | Category | Issue | Suggested Fix |
|---|----------|----------|-------|---------------|
| 1 | High | Completeness | “Frictionless” setup wasn’t concretely addressed (packaging/install path). | Add explicit packaging + install expectations (pyproject, console script, optional Playwright extra). |
| 2 | High | Feasibility | Multi-agent ingestion vs SQLite single-writer needed to be explicit. | State that v1 uses single writer; parallel agents output JSON; one ingest step writes DB. |
| 3 | Medium | Clarity | Derived vs source facts were conceptually defined but not tied to an output contract. | Require `citations[]` on outputs and mark derived computations explicitly. |
| 4 | Medium | Security | Crawl safety constraints were underspecified (schemes, redirects, size limits, retries). | Add explicit crawl safety defaults and bounded retries/backoff. |
| 5 | Medium | Completeness | Field-level provenance is essential for trust on rate limits/permissions. | Add optional per-field `excerpt` support for key fields. |
| 6 | Low | Consistency | “answer” command could be interpreted as doing interpretation beyond stored facts. | Clarify that `answer` assembles responses strictly from stored records + citations; no new extraction. |

### Fixes Applied

- Updated `docs/archive/architect/prompt.md` to include packaging/install requirements, crawl safety defaults, explicit citations output contract, and optional excerpts for key fields.
- Re-emphasized single-writer ingestion as a default for SQLite.

---

## Challenge: Sub-Agent Review (Phase B) and Reconciliation

### Key Issues Raised (Selected)

| Severity | Issue | Resolution |
|----------|-------|------------|
| Critical | “local-only” ambiguous vs agent/LLM usage | Defined “local-only” as local storage + local retrieval (LLM may be remote). |
| Critical | “no inference” wording was unworkable | Replaced with “no unsupported claims” and enumerated allowed output kinds: `[SOURCE]` / `[DERIVED]`. |
| Critical | Citations could be “sprayed” without per-claim support | Required claim-level/per-field sources, and mandatory excerpts for critical fields. |
| Critical | “deterministic” conflicted with agent-run extraction | Added explicit determinism note + extraction metadata requirements (model, prompt hash, temperature=0). |
| High | Single-source provenance structurally wrong | Required multiple `sources[]` and an `endpoint_sources` mapping table. |
| High | REST-only schema incompatible with some exchanges | Added `protocol` field and rules for non-HTTP endpoints. |
| High | Raw storage forcing `.html` extension | Switched raw storage to `.bin` with content_type/encoding in metadata. |
| High | Missing endpoint identity definition | Defined `endpoint_id` as a stable sha256 over canonical endpoint identity fields. |
| Medium | Unknown/undocumented/conflict semantics missing | Added explicit definitions in prompt. |
| Medium | Missing review-queue + init + FTS ops in CLI | Added required CLI commands (`init`, `review-*`, `fts-*`). |
| Medium | Missing exchange registry contract | Required `data/exchanges.yaml` with seeds/domains/sections/render hints and ToS/robots metadata. |

### Notes

- Some transcript statements are user-provided beliefs (e.g., “nothing like this exists”) and are not externally verified. They are kept as context, not as researched facts.

---

## Assumptions / Unverified Context (Explicit)

These are kept as context only. They must not be treated as verified facts in cite-only outputs unless backed by stored sources.

- “Nothing like this exists” refers to the team’s experience, not an externally validated market scan.
- Binance “unified trading through unified sub-account” and related terminology is user-provided; the implementation must resolve it to explicit doc sections and treat ambiguity as a clarification requirement.
- Public docs may be incomplete on permissions or rate limits for some endpoints; the system must return `undocumented` rather than guessing.
- Scale expectations (number of pages per exchange, query latency) are hypotheses until measured; plan for benchmarks and caps.
