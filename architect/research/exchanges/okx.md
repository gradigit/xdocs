# OKX — Deep Discovery

## Documentation Sites
- **Main docs**: https://www.okx.com/docs-v5/en/ (single-page SPA, 224K words)
- **Broker docs**: https://www.okx.com/docs-v5/broker_en/
- **WebSocket docs**: Same page, #websocket-api section
- **FIX protocol**: None publicly documented
- **Developer portal**: https://www.okx.com/okx-api (tutorials, sample bots, demo environment)
- **Platform**: Custom (single-page SPA)

## Versioned APIs
- **Current**: V5
- **Legacy**: V3 docs removed; V5 is current
- **Deprecation notices**: Embedded in changelog

## Changelogs & Updates
- **Changelog URL**: https://www.okx.com/docs-v5/log_en/
- **Format**: Date-stamped reverse-chronological (latest 2026-03-04)
- **RSS/Atom feed**: None
- **Frequency**: 5+ entries/month
- **API Announcements**: https://www.okx.com/help/section/announcements-api
- **Web3/WaaS changelog**: https://www.okx.com/web3/build/docs/waas/changelog

## GitHub
- **Orgs**: https://github.com/okx (30+ repos, infra/Web3) and https://github.com/okxapi (API SDKs)
- **Docs repo**: None (hosted on okx.com)
- **OpenAPI spec**: None publicly available
- **SDKs**: okxapi/python-okx (804 stars); okx/okx-dex-sdk (DEX)
- **Commit feed**: https://github.com/okxapi/python-okx/commits/master.atom

## Specs & Collections
- **OpenAPI**: None
- **Postman**: None official
- **GraphQL**: None

## Discovery Files
- **robots.txt**: 7 sitemaps (default-index, learn-index, convert-index, help-center-index, landingpage-index, markets-index, text-docs-index); allows /llms.txt
- **sitemap.xml**: text-docs-index.xml → text-docs001.xml (only llms.txt URL)
- **llms.txt**: https://www.okx.com/llms.txt (LLM-readable site info)
- **Hidden paths**: /docs-v5/broker_en/, /web3/build/docs/waas/changelog

## CCXT
- **ID**: `okx`

## Status & Incidents
- **Status page**: https://www.okx.com/status (deposit/withdrawal status, maintenance)
- **API**: `GET /api/v5/system/status`; `GET /api/v5/support/announcements`

## Action Items
- [ ] llms.txt — potentially useful as a structured doc source
- [ ] Web3/WaaS changelog — separate crawl target if Web3 coverage needed
- [ ] No machine-readable spec — endpoint extraction relies on page content only
