# Deep Review: cex-api-docs (Readable Report)

**Date:** 2026-02-10
**Scope:** Complete project review — 36 source modules, SQL schema, exchange registry, test suite, configuration
**Verdict:** USE WITH CAUTION

---

## Executive Summary

cex-api-docs is a local-only, cite-only documentation knowledge base for cryptocurrency exchange APIs. It crawls official docs, stores them in SQLite with FTS5 indexing, and enables agents to answer questions with strict provenance. The architecture is well-designed and the code quality is generally high, with several noteworthy engineering decisions (3-phase write locking, SSRF hardening, atomic file writes, content-addressed storage).

However, the review uncovered one critical bug class (double-escaped regex patterns that silently break two features), several significant structural issues (lock contention, missing schema migration path), and a collection of minor code quality findings. None are show-stoppers for the current use case, but the critical bug should be fixed before production reliance.

---

## Critical Findings

### Broken Regex Patterns (F1)

**Severity:** CRITICAL
**Where:** crawler.py:38, page_store.py:26, registry_validate.py:17, inventory.py:86

Four files contain regex patterns with double-escaped characters in raw strings. This is a subtle Python gotcha: in a raw string `r"..."`, writing `\\w` produces the literal two characters `\w` in the string, which the regex engine interprets as "escaped backslash followed by literal w" — not the word-character class `\w`.

**What's broken:**

1. **Charset detection** (`_parse_charset`): The regex `r"charset=([\\w\\-]+)"` can never match a real charset like `charset=utf-8` because the character class only matches literal backslashes, literal `w`, and hyphens. The function silently returns `None`, and callers fall back to `"utf-8"`. This works by accident — most web pages are UTF-8 — but any non-UTF-8 page (e.g., `charset=gbk`, `charset=euc-kr`) will be decoded incorrectly.

2. **Robots.txt sitemap discovery** (`_robot_sitemaps`): The regex `r"(?i)\\s*sitemap\\s*:\\s*(\\S+)\\s*$"` can never match a real robots.txt `Sitemap:` directive because `\\s` matches literal `\s`, not whitespace. Sitemap URLs extracted from robots.txt are the primary discovery mechanism for many exchanges; this bug forces the system to rely entirely on heuristic candidates (`/sitemap.xml`, `/sitemap_index.xml`) and link-follow fallback.

**Why it hasn't been caught:** Both failures degrade gracefully — charset defaults to UTF-8, and sitemaps are found through alternative paths. No tests specifically verify these regex patterns against real-world inputs.

**Fix:** Replace `\\w` with `\w`, `\\s` with `\s`, `\\S` with `\S` in all four files.

---

## Significant Findings

### Write Lock Held During Entire Stale Citation Sweep (F2)

**Severity:** SIGNIFICANT
**Where:** stale_citations.py:49

The `detect_stale_citations` function acquires the exclusive file-based write lock before doing anything, then holds it through multiple read queries and final writes. In contrast, `inventory_fetch.py` uses an elegant 3-phase locking pattern where the lock is only held during brief database write operations.

For large stores with thousands of endpoints, this sweep could take significant time, during which all other write operations (sync, fetch, ingest) are blocked.

### Legacy Crawl Command Blocks All Writers (F3)

**Severity:** SIGNIFICANT
**Where:** crawler.py

The deprecated `crawl` command acquires the write lock at the start and holds it for the entire crawl. For large doc sections, this could mean minutes of blocking. The replacement `sync` command uses `inventory_fetch.py` which has proper 3-phase locking, but `crawl` is still callable.

### Thread-Safety Gap in Concurrent Fetch (F4)

**Severity:** SIGNIFICANT (low practical impact)
**Where:** inventory_fetch.py:164-173

The `robots_can_fetch` closure accesses a shared `robots_cache` dictionary from multiple threads in the `ThreadPoolExecutor` without synchronization. The check-then-act pattern (`if h not in cache: cache[h] = ...`) is technically a race condition.

Python's GIL prevents data corruption of the dict itself, so the worst case is duplicate `fetch_robots_policy` calls for the same host — a performance issue rather than a correctness bug. Still, this is the kind of pattern that could bite if the code is ever ported to multiprocessing or if Python removes the GIL (PEP 703).

### No Schema Migration Path (F5)

**Severity:** SIGNIFICANT
**Where:** db.py:57-63

The `apply_schema` function only accepts `PRAGMA user_version` of 0 (fresh database) or the expected version (currently 1). Any other version raises an error. There's no mechanism to migrate from v1 to v2 — users would need to destroy and recreate their store, losing all crawled data.

---

## Minor Findings

### Dead Schema: `links` Table (F6)

The schema defines a `links` table (from_url, to_url, link_type, anchor_text) but no code ever inserts into it. Likely planned for future link graph analysis but currently dead weight.

### Dual-Defined Table: `coverage_gaps` (F7)

The `coverage_gaps` table is defined in both `schema/schema.sql` (applied at init) and dynamically in `coverage_gaps.py:_ensure_table()`. The dynamic version is a safety net for stores created before the table was added to the schema. Any changes to the table structure must be synchronized in two places.

### `_host()` Duplicated 7 Times (F8)

The same one-liner — `return (urlsplit(url).hostname or "").lower()` — appears in 7 separate modules. Should be extracted to a shared utility.

### Duplicate `_require_db` in `pages.py` (F9)

`pages.py` has its own `_require_db` function that duplicates `store.require_store_db`. Every other module uses the shared version from `store.py`.

### `SystemExit(0)` Used for Flow Control (F12)

All CLI subcommands end with `raise SystemExit(0)` rather than returning normally. This makes the CLI harder to invoke programmatically without catching SystemExit.

### Test Coverage Gaps (F11)

12 test files cover 36 source modules. Notable gaps include: `sync.py` (the main orchestrator), `pages.py` (FTS5 search), `report.py`, `db.py`, `lock.py`, `httpfetch.py`, `page_store.py`, and `cli.py`. Some are exercised indirectly through integration tests.

---

## What's Done Well

The review identified several genuinely well-engineered aspects:

1. **3-Phase Locking** (`inventory_fetch.py`): The fetch pipeline acquires the write lock only in brief bursts — Phase A for crawl_run creation, Phase B for per-entry DB writes during otherwise unlocked fetching, Phase C for finalization. This is the right design for a single-writer SQLite system handling multi-hour crawls.

2. **SSRF Hardening** (`playwrightfetch.py`): The Playwright fetcher blocks private IPs, localhost, and link-local addresses. It includes DNS rebinding defense by re-checking resolved IPs after page navigation. Route interception allows subresources (CSS, JS, images) but blocks navigation to non-allowed domains.

3. **Cite-Only Answer Assembly** (`answer.py`): The answer pipeline returns `unknown`, `undocumented`, or `conflict` when sources are insufficient. Every claim traces back to a specific page and citation hash. This is the right foundation for agent-facing tools where hallucination is costly.

4. **Atomic File Writes** (`page_store.py`): Content blobs are written via `tempfile.mkstemp` + `os.replace`, ensuring crash safety. The content-addressed blob store (SHA-256 based) provides natural deduplication.

5. **Structured Error Handling**: Every error is a `CexApiDocsError` with a machine-readable code (`ENOINIT`, `EBADARG`, `EFTS5`, `ESCHEMAVER`, etc.) and JSON-serializable details. This makes error handling predictable across the CLI and library interfaces.

6. **Per-Domain Rate Limiting**: The `_DomainRateLimiter` class in `inventory_fetch.py` uses per-domain threading locks to enforce `delay_s` between requests to the same host, even under concurrent fetching. This is polite and prevents accidental DDoS of exchange doc sites.

---

## What's Missing

1. **No 429 backoff:** The fetcher retries on error but doesn't detect or back off from HTTP 429 (Too Many Requests) responses.
2. **No graceful shutdown:** Killing a concurrent sync mid-run leaves entries in partial states (mitigated by `--resume`).
3. **No connection pooling:** Each DB operation opens/closes a connection rather than using a pool.
4. **No exponential backoff:** Retries use a fixed `delay_s` rather than increasing delays.
5. **No registry self-validation:** Nothing checks that `allowed_domains` in the registry actually match the hostnames in `seed_urls`.

---

## AI Slop Assessment

No signs of AI-generated filler. The code is consistently purposeful and domain-specific. There are no generic "best practice" comments, no placeholder implementations, no aspirational TODOs disguised as features, and no unnecessary abstractions. Variable names are specific to the problem domain (exchange, section, inventory, citation, canonical_url). The codebase reads as authored by someone with genuine understanding of web crawling, SQLite, and the exchange documentation landscape.

---

## Verdict: USE WITH CAUTION

**Bottom line:** The architecture is sound, the design decisions are well-reasoned, and the cite-only semantics are properly enforced. The codebase is ready for its intended use case (local-only crawl + search + answer) with two caveats:

1. **Fix the regex bugs (F1) before relying on charset detection or robots.txt sitemap discovery.** These are silent failures that degrade gracefully today but will produce incorrect results for non-UTF-8 pages and reduce sitemap coverage.

2. **Plan for schema migration (F5) before the store accumulates data you can't afford to lose.** Currently, any schema change requires a fresh store.

Everything else is quality-of-life improvements that can be addressed incrementally.
