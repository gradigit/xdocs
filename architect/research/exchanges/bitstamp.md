# Bitstamp — Deep Discovery

## Documentation Sites
- **Main docs**: https://www.bitstamp.net/api/ (Redoc, rendered from inline OpenAPI 3.0.3)
- **WebSocket v2**: https://www.bitstamp.net/websocket/v2/
- **FIX v2**: https://www.bitstamp.net/fix/v2/
- **PSD2/Open Banking**: https://www.bitstamp.net/api-psd2/
- **Blog**: https://blog.bitstamp.net/
- **Platform**: Redoc (OpenAPI 3.0.3 rendered inline)

## Versioned APIs
- **Current**: v2
- **Legacy**: /api/v2/trading-pairs-info/ deprecated Dec 31, 2024 (replaced by /api/v2/markets/)

## Changelogs & Updates
- **Changelog**: None separate — inline notices within endpoint documentation
- **RSS**: None
- **Frequency**: Low — last notable public changes 2023–2024

## GitHub
- **Org**: None official
- **SDKs**: None official

## Specs & Collections
- **OpenAPI**: Inline in page source (OpenAPI 3.0.3). Download link exists (`download="openapi.json"`) but direct URL /openapi.json is blocked by Incapsula WAF. Must be obtained via browser download button.
- **Postman**: None found

## Discovery Files
- **sitemap.xml**: https://www.bitstamp.net/sitemap.xml (returns 200)

## CCXT
- **ID**: `bitstamp`

## Status & Incidents
- **Status page**: None found

## Action Items
- [!] OpenAPI spec extraction — spec exists inline but WAF blocks direct download. Use Playwright to click download button and capture the blob.
- [ ] PSD2 API (/api-psd2/) — check if in registry as separate section
- [ ] FIX v2 docs — check if crawled
