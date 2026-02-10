# Deep Adversarial Review: cex-api-docs

**Review date:** 2026-02-10
**Scope:** Full project — all 36 source modules, SQL schema, registry, tests, config
**Verdict:** USE WITH CAUTION

---

## Findings

### F1 [CRITICAL] Double-escaped regex patterns break charset detection and robots.txt sitemap parsing

**Files:** crawler.py:38, page_store.py:26, registry_validate.py:17, inventory.py:86

The `_parse_charset` function uses `r"charset=([\\w\\-]+)"`. In a raw string, `\\w` produces the literal two-character sequence `\w` in the Python string, which the regex engine interprets as an escaped backslash followed by literal `w` — NOT the `\w` word-character class. The character class `[\\w\\-]` matches only literal `\`, literal `w`, and literal `-`. It will never match `charset=utf-8`.

Similarly, `inventory.py:86` uses `r"(?i)\\s*sitemap\\s*:\\s*(\\S+)\\s*$"` — every `\\s` matches literal backslash followed by `s`, not whitespace. This regex will never match a real robots.txt `Sitemap:` directive.

**Impact:** Charset detection always falls through to default `"utf-8"` (graceful degradation). Sitemap discovery from robots.txt is completely broken — the system only finds sitemaps via `_common_sitemap_candidates` heuristics and link-follow fallback.

**Fix:** Change `\\w` to `\w`, `\\s` to `\s`, `\\S` to `\S` in all affected raw strings.

---

### F2 [SIGNIFICANT] `stale_citations.py` holds write lock for entire read+write operation

**File:** stale_citations.py:49

`detect_stale_citations` acquires the exclusive write lock before opening the DB connection and holds it for ALL queries (including pure reads) plus the final writes. The `inventory_fetch.py` module solved this with 3-phase locking (brief lock → unlocked work → brief lock), but `stale_citations.py` does not.

**Impact:** On stores with many endpoints, this blocks all other writers (sync, fetch, ingest) for the full duration of the sweep. Not a correctness bug but degrades throughput under concurrent workloads.

---

### F3 [SIGNIFICANT] `crawler.py` holds write lock for entire crawl duration

**File:** crawler.py (the legacy `crawl` command)

Unlike `inventory_fetch.py` which uses 3-phase locking, the deprecated `crawl` command acquires the exclusive file lock at the start and holds it until the crawl completes. For large sections this could be minutes.

**Impact:** Mitigated by deprecation — `sync` uses `inventory_fetch.py` instead. But `crawl` is still callable and has no lock timeout guardrail beyond the user-specified `--lock-timeout-s`.

---

### F4 [SIGNIFICANT] `robots_can_fetch` closure shares dict across threads without synchronization

**File:** inventory_fetch.py:164-173

The `robots_cache` dict is accessed by `robots_can_fetch()` from multiple threads in the `ThreadPoolExecutor`. The check-then-act pattern (`if h not in robots_cache: robots_cache[h] = ...`) is a classic race condition.

**Impact:** Python's GIL makes dict operations atomic at the bytecode level, so there's no data corruption risk. Worst case: duplicate `fetch_robots_policy` calls for the same host if two threads race. Low severity in practice, but conceptually unsound for threaded code.

---

### F5 [SIGNIFICANT] No schema migration path

**File:** db.py:57-63

`apply_schema` rejects any `PRAGMA user_version` that is not 0 (fresh DB) or the expected version (currently 1). If the schema ever needs to evolve (e.g., adding columns, new tables), there is no migration mechanism. Users would need to destroy and recreate their store.

**Impact:** Not a bug today but a structural limitation that will bite when the schema needs to change.

---

### F6 [MINOR] `links` table defined in schema but never populated

**File:** schema/schema.sql:59

The `links` table (`from_url`, `to_url`, `link_type`, `anchor_text`) is defined in the schema but no code in the project inserts into it. Dead schema.

---

### F7 [MINOR] `coverage_gaps` table dual-defined

**Files:** schema/schema.sql, coverage_gaps.py:16-30

The `coverage_gaps` table is defined both in the authoritative `schema.sql` (applied at init) and dynamically via `_ensure_table()` with `CREATE TABLE IF NOT EXISTS`. The `_ensure_table` version is a safety net for stores initialized before the table was added to the schema, but it creates a maintenance risk: changes to the table must be made in two places.

---

### F8 [MINOR] `_host()` function duplicated across 7 modules

**Files:** inventory.py:48, crawler.py:80, inventory_fetch.py:34, discover_sources.py:31, page_store.py:21, playwrightfetch.py:15, httpfetch.py:49

All 7 are identical: `return (urlsplit(url).hostname or "").lower()`. Should be a single utility.

---

### F9 [MINOR] `pages.py` has its own `_require_db` duplicating `store.require_store_db`

**File:** pages.py:17-21 vs store.py:31

Same logic, different function name. All other modules use `require_store_db` from `store.py`.

---

### F10 [MINOR] `_set_user_version` uses f-string for PRAGMA

**File:** db.py:50

`conn.execute(f"PRAGMA user_version = {int(version)};")` — the `int()` call prevents injection, but PRAGMA statements don't support parameter binding so this is the correct approach. Still, the f-string pattern is worth noting for reviewers.

---

### F11 [MINOR] Test coverage gaps

12 test files for 36 source modules. Notable untested modules: `sync.py`, `pages.py`, `report.py`, `db.py`, `lock.py`, `fs.py`, `httpfetch.py`, `page_store.py`, `markdown.py`, `coverage.py`, `coverage_gaps.py`, `cli.py`, `hashing.py`, `timeutil.py`, `errors.py`.

Some are indirectly exercised through integration tests, but there are no direct unit tests for the locking mechanism, the FTS5 search queries, or the sync orchestrator.

---

### F12 [MINOR] `raise SystemExit(0)` used for flow control in `cli.py`

All CLI subcommands use `raise SystemExit(0)` at the end rather than simply returning. This is unusual and makes the CLI harder to call programmatically (e.g., from tests or other scripts) without catching SystemExit.

---

## Verified Strengths

1. **3-phase locking in `inventory_fetch.py`** — well-designed pattern that minimizes lock hold time during multi-hour fetches. Brief lock for crawl_run creation → unlocked per-entry fetch with brief per-write locks → brief lock to finalize.

2. **SSRF hardening in `playwrightfetch.py`** — IP validation blocks private ranges, link-local, localhost. DNS rebinding defense re-checks resolved IPs after navigation. Route interception allows subresources but blocks navigation to non-allowed domains.

3. **Deterministic URL canonicalization** — consistent scheme normalization, trailing-slash handling, fragment stripping, and sorted query parameters across the pipeline.

4. **Cite-only answer assembly** — `answer.py` returns `unknown`/`undocumented`/`conflict` when sources are insufficient rather than hallucinating. Proper provenance chain from pages to endpoints to citations.

5. **Atomic file writes** — `page_store.py` uses `tempfile.mkstemp` + `os.replace` for crash-safe writes to the content-addressed blob store.

6. **Per-domain rate limiting** — `_DomainRateLimiter` in `inventory_fetch.py` with per-domain threading locks ensures polite crawling even under concurrency.

7. **Structured error handling** — `CexApiDocsError` with error codes (`ENOINIT`, `EBADARG`, `EFTS5`, etc.) throughout. Consistent JSON-serializable error surfaces.

8. **Content-addressed storage** — SHA-256 based deduplication for page content with change detection.

---

## Omissions

1. No graceful shutdown for concurrent fetches — killing a `sync --concurrency 4` mid-run leaves entries in `pending`/`error` state (mitigated by `--resume`).
2. No connection pooling — each DB operation opens and closes a connection.
3. No retry with exponential backoff — retries use fixed `delay_s`.
4. No rate limit detection/backoff from HTTP 429 responses.
5. No telemetry, metrics, or structured logging (stderr messages only).
6. No validation that `allowed_domains` in the registry actually match the `seed_urls` hostnames.

---

## AI Slop Assessment

No signs of AI-generated filler. Code is consistently purposeful with specific domain logic. No generic "best practice" comments, no placeholder implementations, no aspirational TODOs disguised as features. The codebase reads as authored by someone who understands the problem domain deeply.

---

## Confidence

**High confidence** in all CRITICAL and SIGNIFICANT findings. The regex analysis is mechanically verifiable. The locking and threading observations are based on direct code reading. The schema migration gap and dead table are structural facts.

**Medium confidence** on the "test coverage gaps" finding — some modules may be adequately tested through integration paths that aren't obvious from file names alone.

---

## Verdict: USE WITH CAUTION

The architecture is sound and the code is well-organized for a local-first tool. The cite-only semantics, atomic writes, SSRF hardening, and 3-phase locking are genuinely well-implemented. However, the double-escaped regex bugs (F1) silently break two important features (charset detection and robots.txt sitemap parsing), and the lock contention issues (F2, F3) could cause problems at scale. Fix F1 before relying on charset detection or sitemap-from-robots discovery. The remaining findings are quality improvements rather than blockers.
