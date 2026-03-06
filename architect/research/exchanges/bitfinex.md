# Bitfinex — Deep Discovery

## Documentation Sites
- **Main docs**: https://docs.bitfinex.com/ (ReadMe.io)
- **API reference**: https://docs.bitfinex.com/reference/rest-public-platform-status
- **WebSocket docs**: https://docs.bitfinex.com/docs/ws-general
- **FIX gateway**: https://github.com/bitfinexcom/bfxfixgw (repo, not hosted docs)
- **Platform**: ReadMe.io

## Versioned APIs
- **Current**: v2
- **Legacy**: v1 (still accessible at /v1/ path prefix on ReadMe.io)

## Changelogs & Updates
- **Changelog**: https://docs.bitfinex.com/docs/changelog
- **Format**: Dated entries (ReadMe.io format)
- **RSS**: [DEAD] https://docs.bitfinex.com/changelog.rss (404)
- **Frequency**: Very sparse — 8 entries across 2017–2024, latest 2024-10-16

## GitHub
- **Org**: https://github.com/bitfinexcom
- **SDKs**: bitfinex-api-py (Python, 214 stars), bitfinex-api-node, bitfinex-api-go, bitfinex-api-rb
- **FIX**: bfxfixgw (FIX 4.2 Gateway)
- **Note**: As of Mar 2025, some repos marked "no longer maintained" (archival only)
- **Commit feed**: https://github.com/bitfinexcom/bitfinex-api-py/commits.atom

## Specs & Collections
- **OpenAPI**: None found
- **Postman**: https://www.postman.com/antoanpopoff/crypto-apis/documentation/wk3dduc/bitfinex (community, not official)

## Discovery Files
- **robots.txt**: Disallows /edit/, /cdn-cgi/, /login, /logout, /suggested-edits/, /*/api-next
- **sitemap.xml**: [DEAD] 404

## CCXT
- **ID**: `bitfinex` (also `bitfinex2` for v2)

## Status & Incidents
- **Status page**: https://bitfinex.statuspage.io/
- **API**: https://bitfinex.statuspage.io/api/v2/status.json + REST endpoint GET /v2/platform/status

## Action Items
- [ ] ReadMe.io changelog RSS is dead — need HTML scraping for changelog monitoring
- [ ] v1 docs still accessible — decide whether to crawl legacy endpoints
- [ ] FIX gateway repo may contain useful API protocol docs
