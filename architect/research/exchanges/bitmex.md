# BitMEX — Deep Discovery

## Documentation Sites
- **Main docs**: https://docs.bitmex.com/ (Docusaurus)
- **API Explorer**: https://docs.bitmex.com/api-explorer (interactive Swagger UI)
- **Legacy explorer**: https://www.bitmex.com/api/explorer/
- **WebSocket**: Integrated into Docusaurus docs
- **FIX protocol**: References FIX Spec for field definitions but no public FIX API docs (likely institutional-only)
- **Blog**: https://www.bitmex.com/blog/
- **Platform**: Docusaurus

## Versioned APIs
- **Current**: v1 (REST base: bitmex.com/api/v1), spec version 1.2.0
- **Legacy**: None separate

## Changelogs & Updates
- **Changelog**: https://www.bitmex.com/app/apiChangelog (static HTML, entries up to ~Jan 2023 visible)
- **API RSS**: https://www.bitmex.com/api_announcement/feed (HTTP 200)
- **Status feeds**: https://status.bitmex.com/history.atom and https://status.bitmex.com/history.rss
- **Maintenance**: Every Tuesday and Thursday, 06:00-09:00 UTC

## GitHub
- **Org**: https://github.com/BitMEX (9 repos)
- **Docs repo**: https://github.com/BitMEX/api-connectors (API connectors + swagger.json)
- **Live Swagger**: https://www.bitmex.com/api/explorer/swagger.json (183KB, Swagger 2.0)
- **GitHub Swagger**: https://raw.githubusercontent.com/BitMEX/api-connectors/master/swagger.json (272KB)
- **SDKs**: api-connectors (auto-generated multi-lang), sample-market-maker
- **Other**: bitmex-local-proxy, easy-data-scripts, proof-of-reserves-liabilities
- **Commit feed**: https://github.com/BitMEX/api-connectors/commits/master.atom
- **Sitemap**: https://docs.bitmex.com/sitemap.xml (148 URLs)

## Specs & Collections
- **OpenAPI (live)**: https://www.bitmex.com/api/explorer/swagger.json (183KB)
- **OpenAPI (GitHub)**: swagger.json in api-connectors (272KB — larger, may include more detail)
- **Postman**: None
- **GraphQL**: None

## CCXT
- **ID**: `bitmex`

## Status & Incidents
- **Status page**: https://status.bitmex.com/ (Atlassian Statuspage)
- **Monitored**: REST API, WebSocket API, Web Frontend, Mobile App, Trading Engine, Options, Deposits/Withdrawals, Testnet variants
- **Feeds**: Atom at /history.atom, RSS at /history.rss

## Action Items
- [ ] Compare live vs GitHub swagger.json for drift detection
- [ ] API announcement RSS feed — automated monitoring
- [ ] Status page feeds — automated monitoring
- [ ] FIX API — may be available to institutional clients, investigate further
