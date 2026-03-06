# Crypto.com — Deep Discovery

## Documentation Sites
- **Main docs**: https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html (single-page)
- **WebSocket docs**: Embedded in main page
- **Old v1 docs**: https://crypto.com/exchange-docs-v1 (labeled "[Old]")
- **OTC 2.0 API**: /exchange/v1/rest-ws/index_OTC2.html
- **Derivatives**: /derivatives/index.html
- **API landing**: https://crypto.com/exchange/api
- **Platform**: Custom (single-page HTML)

## Versioned APIs
- **Current**: Exchange API v1 (superset of old Derivatives v1)
- **Legacy**: exchange-docs-v1 preserved as "[Old]"

## Changelogs & Updates
- **Changelog**: Embedded in main doc page (scroll to changelog section)
- **Format**: Dated entries with descriptions
- **RSS**: None
- **Frequency**: Active — entries through at least 2025-12-17

## GitHub
- **Org**: https://github.com/crypto-com
- **Docs repo**: https://github.com/crypto-com/crypto-exchange (stub — README only)
- **SDKs**: None found in org

## Specs & Collections
- **OpenAPI**: None found (probes return 403/400)
- **Postman**: None found

## Discovery Files
- **robots.txt**: [BLOCKED] 403 (aggressive bot protection)
- **sitemap.xml**: [BLOCKED] 403

## CCXT
- **ID**: `cryptocom` (NOT `crypto_com` — codebase has this mapping at ccxt_xref.py:34)

## Status & Incidents
- **Status page**: https://status.crypto.com (Statuspage.io)

## Action Items
- [ ] Single-page doc with WAF — verify existing crawl captures full content
- [ ] OTC 2.0 API page (/index_OTC2.html) — check if crawled as separate section
- [ ] Derivatives docs (/derivatives/index.html) — check if in registry
