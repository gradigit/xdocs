# Kraken — Deep Discovery

## Documentation Sites
- **Main docs**: https://docs.kraken.com/ (Docusaurus)
- **Spot REST**: https://docs.kraken.com/api/docs/guides/spot-rest-intro/
- **Futures REST/WS/FIX**: https://docs.kraken.com/api/docs/futures-api/
- **WebSocket v2**: https://docs.kraken.com/api/docs/websocket-v2/status/
- **Spot FIX**: https://docs.kraken.com/api/docs/guides/spot-fix/
- **Embed REST API**: https://docs.kraken.com/api/docs/guides/embed-rest/ (B2B partners, new Feb 2026)
- **Platform**: Docusaurus

## Versioned APIs
- **Current**: Spot REST (unversioned), WS v2 (current), FIX (spot + futures)
- **Legacy**: WS v1.9.x (documented alongside v2), docs.futures.kraken.com redirects to docs.kraken.com

## Changelogs & Updates
- **Changelog**: https://docs.kraken.com/api/docs/change-log/
- **Format**: Dated entries grouped by year, tagged by API type (Spot REST/WS/FIX, Derivatives, Embed, Custody)
- **RSS**: None (Docusaurus changelog, no RSS)
- **Frequency**: Very active — multiple entries per month, 100+ entries from 2018–2026
- **Demo env**: demo-futures.kraken.com (Futures testing)

## GitHub
- **Org**: https://github.com/krakenfx
- **API specs repo**: https://github.com/krakenfx/api-specs — EXISTS but EMPTY (README only, last updated 2025-11-17). Description promises "OpenAPI and AsyncAPI standards" but no specs published yet.
- **Commit feed**: https://github.com/krakenfx/api-specs/commits.atom (monitor for when specs are published)

## Specs & Collections
- **OpenAPI (official)**: None published yet (api-specs repo is empty)
- **OpenAPI (community)**: kanekoshoyu/exchange-collection/asset/krakenfutures_rest_openapi.yaml (148KB, Futures only)
- **Postman**: Referenced in docs as available from Client Engagement team (no public URL)

## Discovery Files
- **robots.txt**: Allows all, sitemap at docs.kraken.com/sitemap.xml
- **sitemap.xml**: https://docs.kraken.com/sitemap.xml

## CCXT
- **IDs**: `kraken` (spot), `krakenfutures` (futures) — separate CCXT classes

## Status & Incidents
- **Status page**: https://status.kraken.com/
- **API**: https://status.kraken.com/api/v2/status.json, /api/v2/summary.json, /api/v2/components.json

## Action Items
- [ ] Monitor krakenfx/api-specs repo — official specs coming (commit feed set up)
- [ ] Kraken Embed REST API — check if registered as separate section
- [ ] Community Futures OpenAPI spec (148KB) — assess for import viability
