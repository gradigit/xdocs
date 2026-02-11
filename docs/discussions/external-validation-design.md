# External Validation Design

**Started:** 2026-02-11
**Status:** Design agreed, building

## The Problem

The store has 3,813 pages and 3,125 endpoints, but no mechanism to verify:
1. **Discovery completeness** — are there pages the exchanges publish that we never discovered?
2. **Content freshness** — has anything changed since the 2026-02-10 crawl?
3. **Content quality** — is what we fetched real API documentation or empty shells?

Internal consistency (fsck) passes with 0 issues. But internal consistency only proves the pipeline didn't corrupt data it knew about.

## Investigation Findings (2026-02-11)

### Content Quality: Better Than Expected

Automated sweep of all 3,813 pages:
- Sampled 5 random pages from each of 17 domains, stripped nav chrome, checked for API content
- **100% of sampled pages across 15/17 domains have real content**
- Only exceptions: `binance-docs.github.io` (2 redirect stubs, 0.4 KB) and 1 Gate.io TOC page
- The initial "56% real" figure was a false alarm from overly strict regex (KuCoin puts `GET` and URL on separate lines)

### JS Rendering: Non-Issue Today

- All 3,811 real pages were fetched with plain HTTP (no Playwright)
- Zero pages show signs of empty JS shells (raw HTML sizes are substantial: 22 KB to 3.7 MB)
- `--render auto` exists as safety net but wasn't triggered
- Headless cron with HTTP-only is viable; add Playwright only if quality gate detects failures

### Discovery Gaps: Real

- **466 pending inventory entries** never fetched (343 binance/spot, 122 binance/portfolio_margin, 1 gateio)
- **511 inventory entries** fetched but redirected to different URLs (accounted for)
- **No sitemap vs link-follow cross-validation** exists
- **`links` table** exists in schema but has 0 rows (internal link tracking never implemented)
- **Upbit** has 35% of discovered URLs missing from pages table
- **Bithumb** has 51% missing

### Endpoint Extraction: Massively Incomplete

| Field | Documented | Unknown/Undocumented |
|-------|-----------|---------------------|
| description | 681 (22%) | 2,444 (78%) |
| rate_limit | 0 (0%) | 3,125 (100%) |
| request_schema | 1,077 (34%) | 2,048 (66%) |
| response_schema | 1,143 (37%) | 1,982 (63%) |

The pages contain the information; it hasn't been extracted into structured endpoint records.

## Design: Three Validation Components

### Component 1: Content Freshness — `--force-refetch`

**What:** Re-fetch every page, compare content hashes, report what changed.

**How:** The `sync` command's fetch phase currently skips pages with `status='fetched'`. Add a `--force-refetch` flag that re-downloads everything and compares:
- `content_hash` unchanged → no-op
- `content_hash` differs → update page, set `prev_content_hash`, report as "changed"
- HTTP 404/410 → report as "gone" (don't auto-delete)
- New URL in inventory but not in pages → report as "new"

**Output:** JSON report with changed/unchanged/gone/new counts and sample URLs.

**Builds on:** Existing `inventory_fetch.py` infrastructure. The `content_hash` and `prev_content_hash` columns already exist.

### Component 2: Discovery Audit — `validate-discovery`

**What:** Check for pages that exist on the exchange but aren't in our store.

**How:**

1. **Sitemap freshness check**: For exchanges with sitemaps, re-fetch the sitemap and compare URL list against inventory. New URLs = gaps.

2. **Internal link audit**: For every stored page, extract all `<a href>` links to the same domain. Check if each target URL is in our pages table. Targets not found = potential missing pages.

3. **Dual-mode comparison** (optional, expensive): For a given section, run both sitemap and link-follow discovery, compare results. URLs only in one = gaps.

**Output:** JSON report with new URLs found per exchange/section, broken internal links.

**Builds on:** Existing `inventory.py` discovery logic. The `links` table schema exists but needs population.

### Component 3: Content Quality Gate — post-fetch validation

**What:** After every fetch, automatically check content isn't empty or nav-only.

**Checks per page:**
- Raw HTML > 1 KB (catches empty JS shells)
- Word count > 50 (catches redirect stubs, nav-only pages)
- At least 1 API content signal (HTTP methods, JSON blocks, parameter keywords, code blocks)

**Pages that fail:** Flagged in a quality report. Not silently accepted.

**Builds on:** New code, runs as a post-fetch step.

### Automation: Cron Script

```
Weekly:
  1. sync --force-refetch --render auto   # re-fetch all, detect changes
  2. validate-discovery                    # check for new pages
  3. fsck                                  # internal consistency
  4. quality-report                        # content quality gate
  → validation-report.json
  → Alert if: changes detected, new pages, quality failures, 404s
```

**Docker:**
- Start with `python:3.11-slim` (HTTP-only, ~200 MB)
- If quality gate detects JS rendering needed: switch to `mcr.microsoft.com/playwright/python:v1.48.0` (~1.5 GB)

**Full sync time:** ~15-25 minutes (concurrency=1, 0.25s delay). With `--concurrency 4`: ~5-8 minutes.

## Build Order

| Step | Component | Effort | Dependencies |
|------|-----------|--------|-------------|
| 1 | `--force-refetch` on sync/fetch | Small-Medium | None — extends existing fetch |
| 2 | Content quality gate (post-fetch) | Small | None — new validation step |
| 3 | `validate-discovery` command | Medium | Needs sitemap re-fetch + link extraction |
| 4 | Populate `links` table during fetch | Medium | Needs `validate-discovery` to consume it |
| 5 | Dockerfile + cron script | Small | Needs 1-3 to be useful |
| 6 | Delta report format | Small | Needs 1 for change data |

**Starting with:** Step 1 (`--force-refetch`) — builds on existing infrastructure, gives immediate value.

## Transcript

### 2026-02-11 — Investigation

User asked: "How can we be confident that the database has all of the documentation in an exhaustive way with 100 percent accuracy?"

Analysis revealed:
- Internal consistency passes (fsck 0 issues)
- No external validation exists (no comparison against live sites)
- Discovery gaps are real (466 pending entries, Upbit/Bithumb fetch gaps, no internal link tracking)
- Endpoint extraction is 22-37% complete
- Content is real (verified by sampling)
- JS rendering is not needed today (HTTP works for everything)

User's vision: automated cron job running headless in cloud, periodic full re-fetch and diff, with the goal of exhaustive coverage.

### 2026-02-11 — Design Agreed

Decision: Build three components (force-refetch, discovery audit, quality gate) starting with force-refetch. HTTP-only Docker container for cron, add Playwright only when needed.
