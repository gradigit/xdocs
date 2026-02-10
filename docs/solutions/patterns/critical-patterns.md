# Critical Patterns (Required Reading)

These patterns are non-obvious and must be followed consistently. They exist to prevent recurring failures in foundational tooling and workflows.

## 1. Handle UA-Dependent 403s When Fetching Public Exchange Docs (ALWAYS REQUIRED)

### ❌ WRONG (Will cause flaky `validate-registry` failures)
```python
import requests

# Single User-Agent strategy (will be blocked by some doc sites).
resp = requests.get(url, headers={"User-Agent": "cex-api-docs"}, timeout=20)
resp.raise_for_status()
```

### ✅ CORRECT
```python
# src/cex_api_docs/httpfetch.py (conceptual)
resp = get(url, user_agent="cex-api-docs")
if resp.status_code == 403:
    resp = get(url, user_agent=None)  # requests default UA
if resp.status_code == 403:
    resp = get(url, user_agent="Mozilla/5.0 ... Chrome/122 ...")
```

**Why:** public doc sites commonly sit behind WAFs that allow/deny content based on `User-Agent`. Without a deterministic fallback order, registry validation and crawling becomes flaky even though the content is public.

**Placement/Context:** applies to all public documentation fetches (crawl + validate + robots). This does not weaken host allowlists and does not imply any authenticated exchange API calls.

**Documented in:** `docs/solutions/integration-issues/ua-403-exchange-docs-crawler-tooling-20260210.md`

