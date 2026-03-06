# Bybit — Deep Discovery

## Documentation Sites
- **Main docs**: https://bybit-exchange.github.io/docs/ (Docusaurus)
- **V5 API**: https://bybit-exchange.github.io/docs/v5/intro
- **WebSocket docs**: https://bybit-exchange.github.io/docs/v5/ws/connect
- **FIX protocol**: None
- **Developer portal**: https://www.bybit.com/future-activity/en/developer
- **Platform**: Docusaurus (source: github.com/bybit-exchange/docs)

## Versioned APIs
- **Current**: V5 (unified spot/derivatives/options)
- **Legacy**: V3 via docs-legacy repo (Slate-based)
- **Migration notice**: https://announcements.bybit.com/article/important-api-update-transition-from-open-api-v3-to-open-api-v5-blt07c25e4e6f734fee/

## Changelogs & Updates
- **Changelog URL**: https://bybit-exchange.github.io/docs/changelog/v5
- **Format**: Date-stamped entries
- **RSS/Atom feed**: None (Telegram is real-time source)
- **Frequency**: Multiple/month
- **Telegram**: @bybit_api_announcements

## GitHub
- **Org**: https://github.com/bybit-exchange (15 repos)
- **Docs repo**: https://github.com/bybit-exchange/docs (Docusaurus source)
- **Legacy docs**: https://github.com/bybit-exchange/docs-legacy (Slate, pre-V5)
- **Swagger spec**: https://github.com/bybit-exchange/api-connectors/blob/master/swagger.json (~304KB, version 0.2.11 — POSSIBLY V3-ERA/OUTDATED)
- **SDKs**: bybit-exchange/bybit.go.api (Go); community SDKs for Python/JS/C#
- **Other repos**: pay-docs, usa-docs, api-usage-examples, merkle-proof, balance-checker
- **Commit feed**: https://github.com/bybit-exchange/docs/commits/main.atom

## Specs & Collections
- **OpenAPI**: swagger.json in api-connectors (possibly outdated V3)
- **Postman**: https://github.com/bybit-exchange/QuickStartWithPostman (V5 + Tax V3 collections)
- **GraphQL**: None

## Discovery Files
- **robots.txt**: 404 (GitHub Pages)
- **sitemap.xml**: https://bybit-exchange.github.io/docs/sitemap.xml (in registry)
- **Hidden paths**: pay-docs repo, usa-docs repo (regional)

## CCXT
- **ID**: `bybit`

## Status & Incidents
- **Status page**: NONE — bybit.statuspage.io is FRAUDULENT (phishing, lists Coinbase services)
- **API**: `GET /v5/system-status`; `GET /v5/announcements/index`; https://announcements.bybit.com

## Action Items
- [ ] Verify swagger.json version — may be V3-era, not covering V5
- [ ] Postman V5 collection — worth importing if not already done
- [ ] usa-docs, pay-docs repos — assess if worth crawling
