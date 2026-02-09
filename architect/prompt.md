# Build: CEX API Docs Intelligence Layer (Cite-Only, Local-Only)

You are implementing a **greenfield** project in the repo `cex-api-docs/`.

Important context:
- The folder `cex-api-docs-plan-handoff/` contains prior drafts and pseudocode. Treat it as **reference only**. Nothing is implemented yet.
- This tool is for **internal team use** and must prioritize **information accuracy** and **frictionless retrieval**.

## One-Sentence Description

Build a local-only, cite-only CEX API documentation knowledge base (library + CLI + agent skill) that crawls official exchange docs, stores and indexes them deterministically (SQLite FTS5), and enables agents to answer endpoint/rate-limit/permission questions with strict provenance.

## Non-Negotiable Requirements

### Accuracy Policy: Cite-Only

- **No unsupported factual claims.**
- Every factual statement returned must be backed by stored sources and provenance.
- Outputs must be one of:
  - `[SOURCE]` direct quotes/excerpts from stored pages
  - `[SOURCE]` extracted structured facts with per-field citations/excerpts
  - `[DERIVED]` deterministic computations/transforms over cited inputs (mark as `[DERIVED]` and include citations for every input)
- If a requested fact cannot be backed by stored sources, return `unknown` / `undocumented` / `conflict` (see definitions below) and cite what you *do* have.
- This project must never require storing real API keys. Do not call authenticated exchange endpoints in v1. Only crawl public documentation.

Definitions (must be used consistently):
- `unknown`: the store does not contain the needed source pages/records yet (not crawled / not indexed).
- `undocumented`: relevant docs were crawled, but the field is not specified anywhere in the sources.
- `conflict`: two or more sources disagree. Return both claims with citations and do not resolve unless a source explicitly supersedes another.

### Local-Only

- All crawled pages, extracted records, and search indexes are stored locally on disk (macOS).
- No hosted service. No cloud dependency for query serving.
- No automatic trading. No calling exchange trading APIs in v1. This is a documentation knowledge base only.
  - Clarification: “local-only” refers to storage and retrieval. Using Claude Code (a remote LLM) to perform extraction is acceptable, but the knowledge base itself must run from local artifacts and must not depend on hosted search.

### Interfaces

- Provide both:
  - A **Python library API** (importable module).
  - A **CLI** (JSON-first, stable output) for scripts and agents.
- Primary consumption is as a **Claude Code skill**, but keep interfaces agent-agnostic.

### Supported Exchanges (Registry Must Include These 16)

`binance`, `okx`, `bybit`, `bitget`, `gateio`, `kucoin`, `htx`, `cryptocom`, `bitstamp`, `bitfinex`, `dydx`, `hyperliquid`, `upbit`, `bithumb`, `coinone`, `korbit`

The system must allow adding more exchanges without schema changes.

## Exchange Registry (Machine-Readable, Required)

Create a machine-readable exchange registry file that is the source of truth for:
- seed/entry URLs
- allowed domains (crawl scoping)
- sections per exchange (spot/futures/portfolio margin/etc)
- base URLs per section
- JS-rendering hints (if needed)
- robots and ToS metadata (URLs and any overrides)

Pin exact path: `data/exchanges.yaml`

Minimum fields per exchange:
- `exchange_id` (one of the 16 above for v1)
- `display_name`
- `seed_urls[]` (per section if needed)
- `allowed_domains[]`
- `sections[]` with `{section_id, base_urls[], seed_urls[]}`
- optional `playwright_ready_selectors[]` and `playwright_max_wait_s`
- optional `tos_url` and `robots_url`

## MVP “Wow Query” (Must Work End-to-End)

Answer the following in a cite-only way:

> “What’s the rate limit difference between Binance unified trading endpoint and the Binance spot endpoint? And in order to look up the balance of our Binance subaccount in Portfolio Margin mode, what permissions does the API key need?”

Notes:
- “Unified trading” is ambiguous. The system must resolve this to a specific **Binance section** (e.g., portfolio margin / unified account) or ask a clarifying question.
- Portfolio margin adds complexity. Do not collapse Binance APIs. Treat Spot vs Futures vs Portfolio Margin as distinct sections with distinct base URLs and doc sources.

## Architecture Principle: AI-Native Boundary

Enforce a hard boundary:
- **Agent/LLM responsibilities**: interpret docs, decide which pages matter, extract structured facts, perform canonical mapping, produce structured JSON records with provenance.
- **Code responsibilities**: deterministic I/O only: crawl/fetch, store raw + extracted text, compute hashes, write/read SQLite, run queries, diff changes, manage review queue state, output JSON.

Do not implement heuristic endpoint parsers in code (no regex scraping of endpoints to “guess” things). If the tool extracts endpoints, it must be via agent-produced JSON validated by schemas.

## Data Storage (Single Unified Store Root)

Default store root: `./cex-docs/` (override with `--docs-dir`).

Store layout (stable paths):
```
cex-docs/
  db/
    docs.db
  raw/
    {domain}/{path_hash}.bin
  pages/
    {domain}/{path_hash}.md
  meta/
    {domain}/{path_hash}.json
  endpoints/
    {exchange}/{section}/{endpoint_id}.json
  review/
    queue.jsonl
  crawl-log.jsonl
```

Provenance requirements:
- Every stored page has: `url`, `crawled_at`, `http_status`, `content_type`, `raw_hash`, `content_hash` (hash of extracted markdown), and `path_hash`.
- Raw files are stored as bytes (`.bin`); use metadata to interpret (`content_type`, encoding where possible).
- Every extracted endpoint record includes **multiple sources** when needed (facts often live across multiple pages):
  - Endpoint-level `sources[]` (one or more)
  - Per-field `sources[]` for key fields
- For the most failure-prone fields (`required_permissions`, `rate_limit`, `error_codes`), an `excerpt` is **required** for each cited source (or the field must be set to `undocumented` and pushed to review).

## SQLite Schema Requirements

Use one SQLite DB at `cex-docs/db/docs.db`.

Minimum tables:
- `pages` + `pages_fts` (FTS5) for markdown content search
- `links` for crawl graph traversal (optional for MVP but useful)
- `crawl_runs` for reproducibility and change tracking
- `page_versions` for immutable crawl history (at minimum: url, crawled_at, raw_hash, content_hash, crawl_run_id)
- `endpoints` for structured endpoint records (one row per endpoint)
- `endpoints_fts` (FTS5) for querying endpoints and permission/rate-limit/error-code text
- `review_queue` for low/medium confidence items and re-review triggers
- `endpoint_sources` to map endpoint_id -> source page(s) -> field names, so page hash changes deterministically trigger re-review.

FTS5 best-practice requirements (from official SQLite docs):
- Use FTS5 helper functions for ranking and snippets (e.g., `bm25()`, `snippet()`).
- Provide explicit commands for FTS5 maintenance (`optimize`, `rebuild`, `delete-all`) rather than ad-hoc “drop tables” operations.

SQLite capability requirement:
- On startup (or `init`), verify that SQLite has FTS5 enabled. If not, fail fast with a clear error and remediation steps.

Schema contract requirement:
- Check in a concrete SQL schema reference in-repo (DDL) and keep it authoritative (tests should assert DB tables/columns exist as documented).

## Crawling Requirements

### Domain Scoping and Safety

- Default to strict domain scoping per crawl (avoid SSRF-style link following).
- Provide allowlist support (only follow links whose domain matches `domain_scope` for that exchange’s doc site).
- Only allow `http`/`https` schemes. Enforce sane timeouts, max response sizes, and redirect limits.
- Implement polite per-domain throttling (default delay) and bounded retries with backoff for 429/5xx.

Concrete crawl defaults (override via flags):
- `timeout_s=20`
- `max_bytes=10_000_000`
- `max_redirects=5`
- `delay_s=1.0`
- `retries=2`
- backoff: exponential with jitter for 429/5xx

Metadata must include:
- `requested_url`, `final_url`, `redirect_chain[]`
- selected response headers (`etag`, `last-modified`, `cache-control`, `content-length`)
- `render_mode` (`http` vs `playwright`)

### Robots / Etiquette Defaults

- Respect robots.txt by default.
- Implement REP behavior aligned to RFC 9309 (explicit cases):
  - 2xx: parse and apply rules for your User-Agent
  - 4xx (unavailable): treat as allow
  - 5xx or network error/timeout (unreachable): treat as complete disallow until successfully fetched later
- Provide an explicit `--ignore-robots` override for internal use.

### ToS / Disclosure Defaults

- Record the exchange documentation ToS URL (if known) in `data/exchanges.yaml`.
- Log which policy flags were used for a crawl run (`--ignore-robots`, User-Agent string, delay, render mode) into `crawl_runs.config_json` so future readers can audit behavior.

### JS-Rendered Docs

- Support a browser fallback for JS-rendered documentation.
- If Playwright is used, do not rely on `networkidle` as a generic readiness signal; prefer `domcontentloaded` plus explicit checks (e.g., selector present, content length threshold).
- Add per-exchange render hints in the exchange registry (selectors or heuristics to decide “page is ready”).

### Change Detection

- Compute hashes and store `prev_content_hash` for pages.
- Provide a `diff` command that reports new/updated/stale pages.
- When a source page hash changes, endpoints derived from that page should be flagged for re-review.
- Ensure filesystem + DB writes are consistent (transactional where possible). Do not leave the store in a state where DB claims a page exists but the corresponding raw/meta/page files are missing.

## Extraction (Agent-Run) Requirements

### Endpoint Records

Define and validate a JSON schema for extracted endpoints. Minimum fields:
- exchange, section, protocol (`http|ws|rpc|other`)
- for HTTP: method, path, base_url, api_version
- description (and original language if not English)
- parameters, headers (when available)
- required_permissions (explicit strings + notes + source)
- rate_limit (weight + limit + type + conditions + source)
- error_codes (when available)
- canonical mapping (optional for MVP)
- extraction metadata (model, temperature, prompt_hash, input_content_hash)
- sources/provenance (sources[] with url, crawled_at, content_hash, page_title, excerpt)

Endpoint identity:
- Define `endpoint_id = sha256("{exchange}|{section}|{protocol}|{base_url}|{api_version}|{method}|{path}")` (omit fields that do not apply, but keep the canonical string stable).
- Use `endpoint_id` as the stable filename and DB primary key.

Confidence policy:
- Any field not explicitly documented should be marked `undocumented` rather than guessed.
- Low/medium confidence items go to `review_queue`.
- For the most failure-prone fields (`required_permissions`, `rate_limit`, `error_codes`), require an `excerpt` for each cited source so humans can quickly verify extraction. If no excerpt can be captured reliably, set the field to `undocumented` and push to review.

Determinism note (must be explicit in implementation):
- Storage/indexing/query logic must be deterministic.
- Agent extraction is not fully deterministic; mitigate by forcing `temperature=0` and recording extraction metadata so results are auditable and reproducible “enough”.

### Translation (Korean Exchanges)

- If translation is used, store it as `[DERIVED]` and preserve original excerpts.
- Never treat translations as the only source of truth.

## CLI Requirements (JSON-First)

The CLI must be scriptable and return machine-readable JSON by default. Include:

- `init`: initialize a new store root and apply DB migrations (idempotent).
- `crawl`: crawl from an entry URL with domain scoping, store pages, update index.
- `search-pages`: FTS5 search over pages with snippets and ranked results.
- `get-page`: fetch a stored page and its metadata by URL.
- `diff`: compare crawls via hashes and report changes.
- `save-endpoint`: persist an endpoint JSON (agent-produced) into storage + DB.
- `search-endpoints`: query endpoints (by exchange/section, permission keyword, path, etc).
- `review-list` / `review-show` / `review-resolve`: manage the review queue.
- `fts-optimize` / `fts-rebuild`: FTS5 maintenance operations (guardrails required).
- `answer`: optional convenience command to assemble a cite-only answer from stored artifacts (may be implemented later; can be a library helper first).

All commands must accept `--docs-dir`.

Output contract requirement:
- Every command prints JSON to stdout and logs to stderr.
- Provide `schema_version` in outputs and a consistent error shape (e.g., `ok`, `errors[]`).
- Any command that returns facts must include claim-level citations:
  - Prefer per-field `sources[]` (url/crawled_at/content_hash/excerpt), not just a global `citations[]`.

## Library API Requirements

Expose a small stable API that wraps the CLI functionality:
- open/create store
- crawl
- search pages
- upsert endpoint record
- query endpoints
- compute diffs

## Skill Deliverable

Create a Claude Code skill file in-repo describing how an agent uses the CLI/library to:
- crawl or update docs
- extract endpoint records (agent writes JSON)
- query the knowledge base
- answer questions with citations only

The skill must explicitly instruct:
- never output unsupported claims; if no citation, answer unknown/undocumented
- include provenance (source URL + crawled_at + content_hash) in outputs
- ask a clarifying question if the user query is ambiguous (e.g., “unified trading endpoint”)

Pin exact path: `skills/cex-api-docs/SKILL.md`

## Packaging / Install (Frictionless)

Ship as a Python package with:
- `pyproject.toml`
- an installable console script (e.g., `cex-api-docs`)
- minimal dependencies for the non-Playwright path
- optional extra for Playwright (`pip install .[playwright]` or similar)

Goal: a teammate can set up and run the CLI on macOS with a small number of commands, and the skill docs should reflect that.

## Acceptance Criteria (Definition of Done)

1. A user (or agent) can create a fresh local store, crawl at least one exchange doc site, and search pages via SQLite FTS5.
2. A user (or agent) can persist a small set of endpoint JSON records and query them back with citations and provenance.
3. The system can support Binance being represented as multiple sections (spot/futures/portfolio margin) without conflation.
4. Provide a runnable demo path to answer the MVP wow query:
   - Crawl the relevant Binance doc sites (at minimum: spot + portfolio margin).
   - Include whichever additional Binance section is needed to satisfy the user’s clarified meaning of “unified trading” (ask clarification if needed).
   - Extract the specific endpoints needed for the query, including:
     - rate limit statements for each endpoint
     - permissions required for the portfolio margin subaccount balance endpoint (or explicitly `undocumented` if docs do not state it)
   - Return an answer that is cite-only, with any computed “difference” marked `[DERIVED]` and fully traceable to cited inputs.
   - If the query is ambiguous (“unified trading”), the demo must show the clarifying question and then the cited answer.

## Constraints and Trade-offs (Apply Consistently)

- Prefer correctness and provenance over coverage.
- Prefer deterministic storage/indexing over embeddings in v1.
- If a doc site is blocked by captcha/auth, record it explicitly as a limitation and do not hack around it.
- Keep the implementation minimal and maintainable; avoid adding a server UI in v1.
