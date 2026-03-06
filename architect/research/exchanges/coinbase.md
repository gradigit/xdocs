# Coinbase — Deep Discovery

## Documentation Sites
- **Main docs**: https://docs.cdp.coinbase.com/ (Custom — Coinbase Developer Platform)
- **Advanced Trade**: https://docs.cdp.coinbase.com/advanced-trade/docs/welcome
- **Exchange**: https://docs.cdp.coinbase.com/exchange/introduction/welcome
- **INTX**: https://docs.cdp.coinbase.com/intx/docs/welcome
- **Prime**: https://docs.cdp.coinbase.com/prime/docs/welcome
- **FIX (Exchange)**: https://docs.cdp.coinbase.com/exchange/docs/fix-overview (FIX 5, replaced FIX 4.2 deprecated June 2025)
- **FIX (INTX)**: https://docs.cdp.coinbase.com/intx/docs/fix-overview
- **Developer portal**: https://developers.coinbase.com/
- **Platform**: Custom (Coinbase Developer Platform)

## Versioned APIs
- **Current**: Advanced Trade, Exchange, INTX, Prime (all current)
- **Legacy**: docs.cloud.coinbase.com (old URLs redirect/mirror)

## Changelogs & Updates
- **App/Advanced Trade**: https://docs.cdp.coinbase.com/coinbase-app/introduction/changelog
- **Exchange**: https://docs.cdp.coinbase.com/exchange/changes/changelog
- **INTX**: https://docs.cdp.coinbase.com/international-exchange/changes/changelog
- **Prime Broker**: https://docs.cdp.coinbase.com/prime/changes/changelog
- **Prime FIX**: https://docs.cdp.coinbase.com/prime/docs/fix-changelog
- **Platform**: https://docs.cdp.coinbase.com/get-started/changelog
- **Upcoming changes**: /exchange/changes/upcoming-changes, /prime/changes/upcoming-changes
- **RSS**: None
- **Frequency**: Active — entries through Sep–Oct 2025

## GitHub
- **Org**: https://github.com/coinbase
- **SDKs**: coinbase-advanced-py (Python Advanced Trade SDK)
- **Community specs**: CoinFabrik/coinbase-api-swagger (API v2), metalocal/coinbase-exchange-api (Exchange REST)
- **Commit feed**: https://github.com/coinbase/coinbase-advanced-py/commits.atom

## Specs & Collections
- **OpenAPI (Prime)**: https://api.prime.coinbase.com/v1/openapi.yaml (LIVE, OpenAPI 3.0.1, 89 paths, 98 ops)
- **OpenAPI (INTX)**: [DEAD] api.international.coinbase.com/v1/openapi.yaml (404) — already imported to store via other means
- **OpenAPI (Advanced Trade)**: None published
- **OpenAPI (Exchange, community)**: metalocal/coinbase-exchange-api (39 paths)
- **Postman (community)**: https://www.postman.com/api-evangelist/blockchain/documentation/omutjt6/coinbase-api

## Discovery Files
- **sitemap.xml**: https://docs.cdp.coinbase.com/sitemap.xml (shared across all 4 sections, uses scope_prefixes)

## CCXT
- **IDs**: `coinbase` (Advanced Trade default), `coinbaseexchange` (Exchange), `coinbaseinternational` (INTX)

## Status & Incidents
- **Status pages**: https://status.coinbase.com/, https://cdpstatus.coinbase.com/, https://status.exchange.coinbase.com/
- **API**: Standard Statuspage.io APIs

## Action Items
- [ ] 6 separate changelogs — structured extraction for drift detection
- [ ] Prime OpenAPI already identified in importable-specs.md — verify import status
- [ ] Monitor for Advanced Trade or Exchange OpenAPI spec publication
