# Binance — Deep Discovery

## Documentation Sites
- **Main docs**: https://developers.binance.com/docs/binance-spot-api-docs/
- **API reference**: https://developers.binance.com/docs/binance-spot-api-docs/rest-api
- **WebSocket docs**: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- **FIX protocol docs**: https://developers.binance.com/docs/binance-spot-api-docs/fix-api (FIX 4.4)
- **Developer portal**: https://dev.binance.vision/ (Discourse forum, RSS: /latest.rss)
- **Platform**: Custom (React/Docusaurus-like)

## Versioned APIs
- **Current**: v3 (REST), v1 (WebSocket), FIX 4.4
- **Legacy**: v1 endpoints still live; Testnet docs separate
- **Deprecation notices**: Embedded in CHANGELOG

## Changelogs & Updates
- **Changelog URL**: https://developers.binance.com/docs/binance-spot-api-docs/CHANGELOG (spot); https://developers.binance.com/docs/derivatives/change-log (derivatives)
- **Format**: Reverse-chronological dated entries (H3 headers by date)
- **RSS/Atom feed**: https://dev.binance.vision/latest.rss (forum topics, not API changelog)
- **Frequency**: 2-4 entries/month (2026)
- **Telegram**: @binance_api_announcements (6.39K subscribers)

## GitHub
- **Org**: https://github.com/binance (45+ repos)
- **Docs repo**: https://github.com/binance/binance-spot-api-docs
- **OpenAPI spec**: https://github.com/binance/binance-api-swagger/blob/master/spot_api.yaml (~999KB, spot only — no futures/options)
- **Swagger UI**: https://binance.github.io/binance-api-swagger/
- **SDKs**: binance-connector-{python,js,java,go,rust,dotnet,php,ruby,typescript}, binance-fix-connector-python
- **Commit feed**: https://github.com/binance/binance-spot-api-docs/commits/master.atom

## Specs & Collections
- **OpenAPI**: spot_api.yaml (spot only)
- **Postman**: https://github.com/binance/binance-api-postman (25 collections: Spot, Futures USDS/COIN, Options, Portfolio Margin, Margin Trading, Wallet, Copy Trading, Pay, Convert, more)
- **GraphQL**: None

## Discovery Files
- **robots.txt**: 404
- **sitemap.xml**: 404 (documented gotcha; pipeline uses link-follow)
- **Hidden paths**: /docs/binance-pay, /docs/convert/quick-start, /docs/wallet, /docs/copy_trading

## CCXT
- **ID**: `binance` (also `binanceusdm`, `binancecoinm`)

## Status & Incidents
- **Status page**: None (Binance.US has binance.us/status — different entity)
- **API**: `GET /sapi/v1/system/status` (0=normal, 1=maintenance)

## Action Items
- [ ] FIX API docs — not currently crawled, add as new section?
- [ ] Verify Swagger spot_api.yaml is current vs existing OpenAPI import
- [ ] dev.binance.vision RSS for changelog drift detection
