---
name: cex-discovery
description: >
  Exhaustive crawl target discovery for cryptocurrency exchanges. Discovers all API documentation,
  sitemaps, OpenAPI/AsyncAPI/Postman specs, changelogs, status pages, GitHub repos, FIX protocol docs,
  and community sources for a given exchange. Produces a bible entry and exchanges.yaml config for
  registration. Activates when user asks to "add exchange", "discover docs", "find API sources",
  "research exchange API", "new crawl target", or wants comprehensive documentation discovery for
  any exchange (CEX, DEX, or aggregator).
---

# CEX Discovery — Exhaustive Crawl Target Discovery

## Core Rule: Exhaustive

Every discoverable source must be found. If a source type exists for the exchange, it must be in the output. "I didn't check" is not acceptable — every probe in the checklist (bottom of this file) must be executed and its result recorded. Mark confirmed non-existent sources explicitly as "None found (probed: {method})" so future agents don't re-search.

## When To Use

- Adding a new exchange to the registry
- Auditing an existing exchange for missing sources (periodic refresh)
- User provides an exchange name or docs URL and wants full discovery
- Bible refresh — re-validating existing entries for drift

## Prerequisites

- Active Python venv with `cex-api-docs` installed
- Web access for URL probing and search
- `crawl4ai`, `cloudscraper`, Playwright installed for crawl testing
- CCXT installed for cross-reference (`pip install ccxt`)
- Read `docs/crawl-targets-bible.md` in full before starting — check if the exchange already has a bible entry or is listed in Section 6 (Missing Exchanges) or Section 11 (Confirmed Non-Existent Sources)

## Workflow

### Step 1: Gather Input

Collect from user or infer:

- **Exchange name** (e.g., "MEXC", "BingX", "Deribit")
- **Known docs URL** (if any)
- **Known API base URL** (if any)
- **Type**: CEX / DEX-REST / DEX-CONTRACT / DEX-SDK / Aggregator

Check the bible first:
- If the exchange is in Section 6 (Missing Exchanges), use that research as starting point
- If the exchange is in Section 3-5 (registered), this is an audit/refresh — compare against stored entry
- If the exchange is in Section 7 (Tier 2 DEX), use that research as starting point

### Step 2: Domain & URL Discovery

#### 2a. Find all documentation domains

Run web searches (use WebSearch tool):

```
"{exchange_name} API documentation"
"{exchange_name} developer API reference"
"{exchange_name} REST API docs"
"site:github.com {exchange_name} API docs"
```

Record every unique domain that hosts documentation. Common patterns:

| Pattern | Example |
|---------|---------|
| `docs.{exchange}.com` | docs.deribit.com |
| `developers.{exchange}.com` | developers.binance.com |
| `developer-pro.{exchange}.com` | developer-pro.bitmart.com |
| `api-docs.{exchange}.com` | api-docs.pro.apex.exchange |
| `{exchange}.github.io/docs/` | bybit-exchange.github.io/docs/ |
| `{exchange}-docs.{domain}` | exchange-docs.crypto.com |
| `www.{exchange}.com/docs/` | www.kucoin.com/docs/ |
| `www.{exchange}.com/api-doc/` | www.bitget.com/api-doc/ |

Also probe adjacent domains:

```bash
for prefix in docs developers developer api api-docs dev; do
  domain="${prefix}.EXCHANGE.com"
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "https://${domain}/" 2>/dev/null)
  echo "$code https://${domain}/"
done
```

#### 2b. Probe each documentation domain for discovery files

For EVERY documentation domain found, probe ALL of these URLs:

```bash
DOMAIN="https://docs.example.com"

# Robots & sitemaps
for path in /robots.txt /sitemap.xml /sitemap-pages.xml /sitemap-0.xml; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "${DOMAIN}${path}" 2>/dev/null)
  echo "$code ${DOMAIN}${path}"
done

# LLM discovery files
for path in /llms.txt /llms-full.txt; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "${DOMAIN}${path}" 2>/dev/null)
  echo "$code ${DOMAIN}${path}"
done

# Spec files (docs domain)
for path in /openapi.json /openapi.yaml /swagger.json /swagger.yaml /api-docs /api-docs.json; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "${DOMAIN}${path}" 2>/dev/null)
  echo "$code ${DOMAIN}${path}"
done

# Versioned spec paths
for ver in v1 v2 v3 v4 v5; do
  for ext in openapi.json openapi.yaml swagger.json; do
    code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "${DOMAIN}/${ver}/${ext}" 2>/dev/null)
    [ "$code" = "200" ] && echo "$code ${DOMAIN}/${ver}/${ext}"
  done
done
```

Also probe the API base domain (if different):

```bash
API="https://api.example.com"
for path in /openapi.json /openapi.yaml /swagger.json /swagger/doc.json /v1/openapi.yaml /api-docs; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "${API}${path}" 2>/dev/null)
  [ "$code" = "200" ] && echo "$code ${API}${path}"
done
```

#### 2c. Parse sitemap (if found)

```bash
# Count and categorize URLs
curl -sL "${DOMAIN}/sitemap.xml" | grep '<loc>' | sed 's/.*<loc>//;s/<\/loc>.*//' | sort | head -50
echo "---"
curl -sL "${DOMAIN}/sitemap.xml" | grep -c '<loc>'
```

Count by path prefix to identify sections (REST, WebSocket, FIX, changelogs, etc.).

#### 2d. Parse robots.txt (if found)

Look for:
- Additional `Sitemap:` directives
- `Disallow:` paths that reveal hidden doc sections
- `Crawl-delay:` directives

#### 2e. Parse llms.txt (if found)

Extract:
- Document structure and section links
- Spec file URLs (WhiteBIT's llms.txt exposed 7 OpenAPI + 19 AsyncAPI specs)
- Changelog URLs
- Section hierarchy

#### 2f. Check Wayback Machine CDX (for historical/missing pages)

```bash
# Check what URLs Wayback has archived for this domain
curl -sL "http://web.archive.org/cdx/search/cdx?url=${DOMAIN}/*&output=text&fl=original&collapse=urlkey&limit=100" | sort -u | head -50
```

### Step 3: GitHub & Repository Discovery

#### 3a. Find official GitHub organization

Search for official org. Common patterns:
- `github.com/{exchange}`
- `github.com/{exchange}api`
- `github.com/{exchange}-exchange`
- `github.com/{exchange}com`

Record: organization URL, repo count, notable repos.

#### 3b. Search for spec files in repos

Within the org, search for:

```
filename:openapi extension:json OR extension:yaml
filename:swagger extension:json
filename:postman_collection extension:json
filename:asyncapi extension:json OR extension:yaml
```

For each spec file found, record:
- Full raw.githubusercontent.com URL
- File size (bytes)
- Format (OpenAPI 3.x / Swagger 2.0 / AsyncAPI 2.x/3.0 / Postman v2.1)
- Number of paths/operations
- Has `servers[]` field? (needed for `--base-url` decision)
- Last commit date

#### 3c. Check for Postman collections

- Search `postman.com` for official workspace
- Check GitHub repos for `.postman_collection.json` files
- Check if Postman URL is direct-downloadable or requires auth

#### 3d. Check for FIX protocol repos

- Search within org for FIX protocol implementations
- Look for QuickFIX XML dictionaries
- Check for FIX connection guides in docs

#### 3e. Check community spec repositories

Always check these:

| Repo | Content |
|------|---------|
| `openxapi/openxapi` | Community OpenAPI + AsyncAPI for major exchanges |
| `kanekoshoyu/exchange-collection` | Community swagger specs |
| `ujhin/upbit-client` | Upbit community OpenAPI |
| `metalocal/coinbase-exchange-api` | Coinbase Exchange community spec |

Search: `site:github.com "{exchange_name}" openapi OR swagger OR "api spec"`

### Step 4: Spec Validation

For each discovered spec file, download and validate:

```bash
curl -sL "$SPEC_URL" | python3 -c "
import sys, json
try:
    import yaml
except ImportError:
    yaml = None
data = sys.stdin.read()
try:
    spec = json.loads(data)
except:
    if yaml:
        spec = yaml.safe_load(data)
    else:
        print('YAML spec but no pyyaml installed'); sys.exit(1)
version = spec.get('openapi', spec.get('swagger', spec.get('asyncapi', 'unknown')))
paths = len(spec.get('paths', {}))
ops = sum(len([m for m in methods if m in ('get','post','put','delete','patch')])
          for methods in spec.get('paths', {}).values() if isinstance(methods, dict))
info = spec.get('info', {})
servers = spec.get('servers', [])
host = spec.get('host', '')
print(f'Format: {version}')
print(f'Title: {info.get(\"title\", \"N/A\")}')
print(f'Spec version: {info.get(\"version\", \"N/A\")}')
print(f'Paths: {paths}, Operations: {ops}')
print(f'Servers: {[s.get(\"url\") for s in servers] if servers else host or \"NONE — needs --base-url\"}')
print(f'Size: {len(data):,} bytes')
"
```

Record: format, path count, operation count, whether `--base-url` is needed.

### Step 5: Platform Detection & Crawl Method Testing

#### 5a. Detect documentation platform

Visit the main docs URL and identify the platform:

| Platform | Detection Signals | Crawl Implications |
|----------|------------------|--------------------|
| ReadMe.io | `readme-docs` class, `.readme.io`, `/reference/` paths | Auto-generates llms.txt and changelog RSS |
| Docusaurus | `docusaurus` in meta, structured `/docs/` paths | Good sitemap, static HTML works |
| GitBook | `.gitbook.io` domain, GitBook meta tags | Good sitemap, may need `--render auto` |
| Swagger UI | `swagger-ui` in HTML, `/swagger-ui/` path | Import spec directly, don't crawl HTML |
| Redoc | `redoc` in HTML, single-page reference | Single page, use spec import |
| Mintlify | `mintlify` in HTML, `.mintlify.dev` | Good sitemap, static usually works |
| Custom SPA | None of the above | Likely needs `--render auto` or `playwright` |
| GitHub Pages | `.github.io` domain | Static HTML, `requests` works |
| GitHub Markdown | `github.com/{org}/{repo}` paths | Use raw.githubusercontent for markdown |

#### 5b. Test crawl methods

Test the main docs URL with ALL four methods:

```bash
# Method 1: requests
python3 -c "
import requests
r = requests.get('DOCS_URL', timeout=30, headers={'User-Agent': 'Mozilla/5.0 (compatible)'})
print(f'requests: status={r.status_code}, length={len(r.text)}, words={len(r.text.split())}')"

# Method 2: cloudscraper
python3 -c "
import cloudscraper
s = cloudscraper.create_scraper()
r = s.get('DOCS_URL')
print(f'cloudscraper: status={r.status_code}, length={len(r.text)}, words={len(r.text.split())}')"

# Method 3: crawl4ai (primary validation tool)
python3 -c "
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
async def test():
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as c:
        r = await c.arun(url='DOCS_URL', config=CrawlerRunConfig())
        md = r.markdown or ''
        print(f'crawl4ai: success={r.success}, md_length={len(md)}, words={len(md.split())}')
asyncio.run(test())"
```

Compare results:
- If `requests` word count is >80% of `crawl4ai` → `render_mode: http` (static site)
- If `requests` is thin but `crawl4ai` gets full content → `render_mode: auto`
- If only Playwright/crawl4ai works → `render_mode: auto` or `playwright`
- If nothing works (CAPTCHA, login-gated) → document and escalate

#### 5c. Record crawl method matrix

| Method | Status | Content Length | Words | Usable? |
|--------|--------|---------------|-------|---------|
| requests | ___ | ___ | ___ | ___ |
| cloudscraper | ___ | ___ | ___ | ___ |
| crawl4ai | ___ | ___ | ___ | ___ |

### Step 6: CCXT Cross-Reference

```bash
source .venv/bin/activate && python3 -c "
import ccxt
# Try common ID formats (lowercase, no spaces/hyphens)
for eid in ['EXCHANGE_ID', 'EXCHANGE_ALT_ID']:
    try:
        ex = getattr(ccxt, eid)()
        desc = ex.describe()
        print(f'CCXT ID: {eid}')
        print(f'Name: {desc.get(\"name\")}')
        urls = desc.get('urls', {})
        print(f'API URLs: {urls.get(\"api\", \"N/A\")}')
        print(f'Doc URL: {urls.get(\"doc\", \"N/A\")}')
        print(f'Certified: {desc.get(\"certified\", False)}')
        api = desc.get('api', {})
        total = 0
        for section in api.values():
            if isinstance(section, dict):
                for method_paths in section.values():
                    if isinstance(method_paths, dict):
                        total += len(method_paths)
                    elif isinstance(method_paths, list):
                        total += len(method_paths)
        print(f'CCXT endpoint count: {total}')
        break
    except AttributeError:
        print(f'No CCXT class: {eid}')
"
```

If CCXT class exists, record: ID, endpoint count, certified status, doc URL.

### Step 7: Changelogs, Status Pages, RSS Feeds

#### 7a. Changelog discovery

Probe these paths on each docs domain:

```bash
DOMAIN="https://docs.example.com"
for path in /changelog /changelog/ /docs/changelog /api-changelog /change-log \
  /api/docs/change-log/ /docs/change-log/ /reference/changelog; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "${DOMAIN}${path}" 2>/dev/null)
  [ "$code" = "200" ] && echo "$code ${DOMAIN}${path}"
done
```

#### 7b. Status page discovery

```bash
EXCHANGE="example"
for url in "https://status.${EXCHANGE}.com" "https://${EXCHANGE}.statuspage.io" \
  "https://${EXCHANGE}.status.io" "https://status.${EXCHANGE}.io"; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null)
  [ "$code" = "200" ] && echo "$code $url"
done
```

#### 7c. RSS/Atom feed discovery

```bash
DOMAIN="https://docs.example.com"
for path in /changelog.rss /changelog.atom /feed.xml /rss.xml /atom.xml; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 10 "${DOMAIN}${path}" 2>/dev/null)
  [ "$code" = "200" ] && echo "$code ${DOMAIN}${path}"
done
```

For GitHub repos, check `/releases.atom` and `/commits/{branch}.atom`.

### Step 8: Additional Documentation Types

Check for these and record findings:

- [ ] **WebSocket docs** — separate section or embedded in REST docs? Dedicated WS base URLs?
- [ ] **FIX protocol docs** — separate section? FIX version (4.2/4.4/5.0)?
- [ ] **Sandbox/testnet docs** — separate API base? Test key setup guide?
- [ ] **SDK documentation** — official SDKs? Which languages? Embedded specs?
- [ ] **Multiple API versions** — v1/v2/v3? Which is current? Legacy still documented?
- [ ] **Broker/affiliate docs** — separate section or restricted access?
- [ ] **gRPC/protobuf** — any gRPC endpoints? Protobuf definitions?
- [ ] **GraphQL** — any GraphQL API? (rare for CEX, more common in DeFi indexers)

### Step 9: Compile Bible Entry

Generate a bible entry matching the format in `docs/crawl-targets-bible.md` Sections 3-5:

```markdown
### {Exchange Name}

| Field | Value |
|-------|-------|
| **Docs URL** | {main_docs_url} |
| **Platform** | {platform} |
| **Sections** | {N} ({section_list}) |
| **Pages/Words/Endpoints** | TBD (pre-sync estimate: {sitemap_count} URLs) |
| **CCXT endpoints** | {count} (ID: {ccxt_id}) / No CCXT class |
| **OpenAPI** | {spec_url} ({size}, {paths} paths) / None found |
| **Postman** | {collection_url} ({eps} endpoints) / None found |
| **AsyncAPI** | {spec_url} / None found |
| **Sitemap** | {sitemap_url} ({count} URLs) / None (404) |
| **Changelog** | {changelog_url} / None found |
| **RSS** | {rss_url} / None |
| **Status** | {status_url} / None found |
| **GitHub** | {github_org_url} ({repo_count} repos) |
| **FIX docs** | {fix_url} / None |
| **WebSocket docs** | {ws_docs_url} / Embedded in REST docs / None |
| **llms.txt** | {llms_url} / 404 |
| **Render mode** | {http/auto/playwright} (based on crawl test results) |
| **Crawl notes** | {any special handling needed} |
```

Also include a "Confirmed Non-Existent Sources" subsection:

```markdown
**Confirmed non-existent (probed {date}):** OpenAPI spec (probed {domain}/openapi.json, /swagger.json — 404), Postman (searched github.com and postman.com — none), AsyncAPI (probed — none), llms.txt (404), RSS feed (404).
```

### Step 10: Generate Registry Entry

Generate a `data/exchanges.yaml` entry:

```yaml
  - exchange_id: {id}  # lowercase, no hyphens
    display_name: {Display Name}
    allowed_domains:
      - {docs_domain}
      # - {additional_domain}  # if docs span multiple domains
    sections:
      - section_id: {section}  # e.g., rest, v5, spot, api
        base_urls: ["{api_base_url}"]
        seed_urls: ["{best_entry_point_url}"]
        doc_sources:
          - kind: sitemap
            url: {sitemap_url}  # only if sitemap exists and is trustworthy
        inventory_policy:
          mode: link_follow  # if no sitemap or sitemap is unreliable
          render_mode: {auto/http/playwright}
          max_pages: {estimate * 1.5}  # generous ceiling
          scope_prefixes:
            - "{url_prefix}"  # if domain is shared with non-API content
```

Include comments explaining any non-obvious choices (scope_priority, render_mode, etc.).

### Step 11: Present, Register & Validate

1. Present the bible entry and registry entry to the user for review
2. After approval:
   - Add registry entry to `data/exchanges.yaml`
   - Add bible entry to `docs/crawl-targets-bible.md`:
     - New CEX → Section 3 (alphabetical)
     - New DEX-REST → Section 4, DEX-REST subsection
     - New DEX-CONTRACT/SDK → Section 4, appropriate subsection
     - Update Section 2a coverage table with a placeholder row
     - Update Section 2c/2d/2e/2f if specs/AsyncAPI/Postman/llms.txt found
   - If the exchange was in Section 6 (Missing Exchanges), move it out
   - Run initial sync:
     ```bash
     cex-api-docs sync --exchange {id} --docs-dir ./cex-docs --render {mode}
     ```
   - Validate:
     ```bash
     cex-api-docs validate-crawl-targets --exchange {id} --enable-nav --docs-dir ./cex-docs
     cex-api-docs quality-check --docs-dir ./cex-docs
     ```
   - Import any discovered specs (use `cex-api-docs import-openapi`/`import-postman`)
   - Run `cex-api-docs ccxt-xref --exchange {id} --docs-dir ./cex-docs`
   - Update all docs per "Updating Skills & Documentation" in `cex-api-docs` SKILL.md

## Exhaustive Discovery Checklist

**Every discovery run MUST execute ALL of these probes.** Check off each item with its result. Present the completed checklist in the discovery report.

### URL Probes (per documentation domain)

- [ ] `{domain}/robots.txt` → ___
- [ ] `{domain}/sitemap.xml` → ___
- [ ] `{domain}/sitemap-pages.xml` → ___
- [ ] `{domain}/llms.txt` → ___
- [ ] `{domain}/llms-full.txt` → ___
- [ ] `{domain}/openapi.json` → ___
- [ ] `{domain}/openapi.yaml` → ___
- [ ] `{domain}/swagger.json` → ___
- [ ] `{domain}/swagger.yaml` → ___
- [ ] `{domain}/api-docs` → ___
- [ ] `{domain}/api-docs.json` → ___
- [ ] `{domain}/v1/openapi.yaml` → ___
- [ ] `{domain}/v2/openapi.yaml` → ___
- [ ] `{domain}/.well-known/` → ___

### API Base Domain Probes (if different from docs domain)

- [ ] `{api}/openapi.json` → ___
- [ ] `{api}/openapi.yaml` → ___
- [ ] `{api}/swagger.json` → ___
- [ ] `{api}/swagger/doc.json` → ___
- [ ] `{api}/v1/openapi.yaml` → ___
- [ ] `{api}/api-docs` → ___

### Domain Variants

- [ ] `docs.{exchange}.com` → ___
- [ ] `developers.{exchange}.com` → ___
- [ ] `developer.{exchange}.com` → ___
- [ ] `developer-pro.{exchange}.com` → ___
- [ ] `api.{exchange}.com` → ___
- [ ] `api-docs.{exchange}.com` → ___
- [ ] `{exchange}.github.io` → ___
- [ ] `{exchange}-exchange.github.io` → ___
- [ ] `{exchange}-api.github.io` → ___

### GitHub / Repository

- [ ] Official GitHub org found → ___
- [ ] Repos searched for: openapi, swagger, postman, asyncapi → ___
- [ ] FIX protocol repos checked → ___
- [ ] SDK repos checked for embedded specs → ___
- [ ] Community repos checked (openxapi, exchange-collection) → ___

### Specs Discovered

- [ ] OpenAPI/Swagger → ___ (URL, size, paths, has servers[]?)
- [ ] AsyncAPI → ___ (URL, channels)
- [ ] Postman collection → ___ (URL, endpoint count)
- [ ] FIX dictionary/spec → ___

### Platform & Crawl Testing

- [ ] Platform detected → ___
- [ ] `requests` test → status: ___, words: ___
- [ ] `cloudscraper` test → status: ___, words: ___
- [ ] `crawl4ai` test → success: ___, words: ___
- [ ] Render mode determined → ___

### CCXT

- [ ] CCXT class exists? → ___ (ID: ___)
- [ ] CCXT endpoint count → ___
- [ ] Certified exchange? → ___

### Changelogs & Feeds

- [ ] Changelog URL → ___
- [ ] RSS/Atom feed → ___
- [ ] Status page → ___

### Additional Documentation

- [ ] WebSocket docs → ___
- [ ] FIX protocol docs → ___
- [ ] Sandbox/testnet docs → ___
- [ ] Multiple API versions → ___
- [ ] Broker/affiliate docs → ___

## Output Artifacts

Every discovery run produces three artifacts:

1. **Bible entry** — full markdown table matching `docs/crawl-targets-bible.md` format, placed in the appropriate section
2. **Registry entry** — YAML for `data/exchanges.yaml` with comments
3. **Discovery report** — completed checklist above with all probe results, including confirmed non-existent sources

## Gotchas

- Some exchanges have multiple doc domains (OKX has okx.com + okxapi GitHub). Probe ALL of them.
- GitHub org names don't always match exchange names (HTX = huobiapi + HuobiRDCenter, OKX = okx + okxapi).
- CCXT exchange IDs may differ from our exchange_id (crypto_com vs cryptocom, mercadobitcoin vs mercado).
- Community specs may be stale — always check last commit date before recommending import.
- Postman collections on postman.com may require authentication to download; prefer GitHub-hosted copies.
- Some exchanges (Deribit) use JSON-RPC instead of REST — still documentable but note the difference.
- ReadMe.io and GitBook auto-generate llms.txt — content quality varies but URLs are valuable.
- Single-page SPAs (OKX, Gate.io, HTX) produce 1 page with 200K+ words — this is correct behavior.
- Swagger UI sites (MercadoBitcoin) cannot be crawled for content — import the spec instead.
- Localize.js sites (Bithumb EN) require Playwright to render translated content.
- Rate limiting may prevent testing all methods in rapid succession — add delays between crawl tests.
