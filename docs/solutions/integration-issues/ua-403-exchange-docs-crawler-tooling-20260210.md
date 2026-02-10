---
module: Tooling
date: 2026-02-10
problem_type: integration_issue
component: tooling
symptoms:
  - "cex-api-docs validate-registry intermittently failed with http_status=403 for some exchange doc seeds"
  - "Some doc sites returned 403 for User-Agent=cex-api-docs but 200 for python-requests (and vice versa)"
  - "Registry seeds/allowlists drifted (Gate docs moved to gate.com; HTX spot docs best seed on huobiapi.github.io)"
  - "Binance wow query (clarification=binance:portfolio_margin) returned missing required_permissions until the correct source page was crawled"
root_cause: missing_tooling
resolution_type: tooling_addition
severity: high
tags: [user-agent, 403, validate-registry, seed-drift, exchange-docs, base-urls, binance, cite-only]
---

# Troubleshooting: UA-Dependent 403s and Registry Seed Drift for Exchange Docs

## Problem

The `cex-api-docs` crawler and registry validator were unreliable because multiple exchange documentation sites vary access rules by `User-Agent` (returning 403 for some UAs), and a few registry `seed_urls`/`allowed_domains` had drifted due to doc host moves. This broke `validate-registry` and made the cite-only Binance MVP query miss `required_permissions` evidence until the right doc page was included.

## Environment

- Module: Tooling (`cex-api-docs` CLI + crawler)
- Date: 2026-02-10
- Store: local filesystem + SQLite FTS5 (`./cex-docs/`)

## Symptoms

- `cex-api-docs validate-registry` reported `counts.errors > 0` with one or more results showing `http_status: 403` and `ok: false`.
- A given doc URL would return 403 for one UA but 200 for another, causing flakiness:
  - Example pattern:
    - `User-Agent: cex-api-docs` -> 403 on `www.gate.com`
    - requests default UA (no UA header) -> 200 on `www.gate.com`
    - `User-Agent: cex-api-docs` -> 200 on `www.bitget.com`
    - requests default UA (no UA header) -> 403 on `www.bitget.com`
- Registry drift:
  - Gate docs seed moved to `www.gate.com` and would not validate reliably with old hosts.
  - HTX spot docs are crawlable from `huobiapi.github.io` (GitHub Pages).
- The Binance MVP “wow query” returned `missing: ["required_permissions"]` until the relevant Binance permissions page was crawled and the answer assembler searched a broader prefix.

## What Didn't Work

**Attempted Solution 1:** Use a single identifying UA (`cex-api-docs`) everywhere.
- **Why it failed:** Some doc hosts explicitly block unknown UA strings (403), so fetches fail even though the content is public.

**Attempted Solution 2:** Use only requests’ default UA (python-requests).
- **Why it failed:** Some doc hosts block python-requests (403), while allowing a custom or browser-like UA.

**Attempted Solution 3:** Keep registry seeds fixed “as-is”.
- **Why it failed:** Docs hostnames change (Gate) and some seeds are JS-only or redirect in ways that break strict allowlists. Seed drift must be treated as expected operational reality.

**Attempted Solution 4:** Search for Binance `required_permissions` only inside the Portfolio Margin seed prefix.
- **Why it failed:** The best citeable statement for “API key restrictions / Enable Reading” lives on Binance derivatives “Quick Start” docs, which may not be inside the Portfolio Margin subtree.

## Solution

### 1) Update registry seeds/allowlists for Gate and HTX

`data/exchanges.yaml` was updated so seeds are crawlable and `allowed_domains` matches where the docs actually live:

```yaml
# data/exchanges.yaml
- exchange_id: gateio
  allowed_domains:
    - www.gate.com
  sections:
    - section_id: v4
      seed_urls: ["https://www.gate.com/docs/apiv4/index.html"]

- exchange_id: htx
  allowed_domains:
    - huobiapi.github.io
  sections:
    - section_id: spot
      seed_urls: ["https://huobiapi.github.io/docs/spot/v1/en/"]
```

### 2) Add robust UA fallback on HTTP 403 for public docs fetches

HTTP fetching now retries 403s in a deliberate order to satisfy WAF differences across doc sites:

- First: identifying UA `cex-api-docs`
- Second: requests default UA (no `User-Agent` header)
- Third: browser-like UA (Chrome-style)

```python
# src/cex_api_docs/httpfetch.py (conceptual)
resp = _get(..., user_agent=USER_AGENT)
if resp.status_code == 403:
    resp = _get(..., user_agent=None)          # python-requests default UA
if resp.status_code == 403:
    resp = _get(..., user_agent=_BROWSER_UA)   # browser-like UA
```

The same 403 retry strategy is applied to robots fetching so RFC9309 parsing isn’t blocked by UA-only 403s:

```python
# src/cex_api_docs/robots.py (conceptual)
resp = GET(robots_url, UA=cex-api-docs)
if 403: resp = GET(robots_url)                 # default UA
if 403: resp = GET(robots_url, UA=browser)     # browser UA
```

### 3) Add `validate-base-urls` to reconfirm API domains/endpoints

New CLI command:

```bash
cex-api-docs validate-base-urls
```

Behavior:
- `http/https` base URLs: make an unauthenticated GET and treat “any HTTP response” as reachable.
- `ws/wss` base URLs: DNS-only (no websocket handshake).

Implementation:
- `src/cex_api_docs/base_urls_validate.py`
- wired in `src/cex_api_docs/cli.py`

### 4) Ensure the Binance wow query can cite API key permissions

The answer assembler now recognizes and sources “Enable Reading” / “enable withdrawals” language from Binance docs even when outside the `portfolio_margin` seed prefix:

- `src/cex_api_docs/answer.py` broadened permissions search prefixes and keywords.
- Runbook-safe approach: explicitly crawl the Binance derivatives quick-start page into the local store when reproducing the wow query:

```bash
cex-api-docs crawl --url "https://developers.binance.com/docs/derivatives/quick-start" \
  --domain-scope developers.binance.com --docs-dir ./cex-docs --max-depth 0 --max-pages 5
```

## Why This Works

1. **Docs are public but WAF rules differ**: A multi-UA retry strategy turns “UA-specific 403” into a robust fetch of the same public content without weakening domain allowlists or adding any authenticated exchange calls.
2. **Seed drift is inevitable**: Keeping registry seeds accurate (and validated) prevents redirect-to-disallowed-host failures and prevents empty/JS-only doc seeds from slipping in unnoticed.
3. **Cite-only requires evidence coverage**: For permissions, if the relevant page isn’t crawled, we must return `unknown`/`undocumented`. Broadening the permissions source search and ensuring the right source page is in-store turns “missing” into “cite-backed”.
4. **Dedicated `base_urls` reconfirmation**: `validate-base-urls` provides a fast way to check that API endpoint domains are reachable without hitting any private endpoints.

## Prevention

- Run these two commands after any registry change:
  - `cex-api-docs validate-registry`
  - `cex-api-docs validate-base-urls`
- Treat `validate-registry` as a stability check: run it multiple times if you suspect WAF flakiness and compare `counts` outputs.
- Prefer seeds that are:
  - crawlable via plain HTTP (non-JS or server-rendered)
  - stable hostnames (often GitHub Pages for long-lived reference docs)
  - non-empty extractions (the validator requires `word_count > 0` and 2xx)
- Add tests that simulate UA-dependent 403 using a local HTTP handler:
  - first request 403 if `User-Agent=cex-api-docs`, second request 200 if UA omitted (and vice versa)
  - assert `httpfetch.fetch()` returns 200 and stores the terminal response
- Keep the MVP wow query reproducible by ensuring the runbook includes every required source page (especially when “permissions” live outside the target section subtree).

## Related Docs

- Plan/spec: `docs/plans/2026-02-09-feat-cex-api-docs-cite-only-knowledge-base-plan.md`
- Runbook: `docs/runbooks/binance-wow-query.md`
- Smoke report (sample run outputs): `docs/reports/2026-02-10-cex-api-docs-smoke-report.md`
- Agent workflow: `skills/cex-api-docs/SKILL.md`

