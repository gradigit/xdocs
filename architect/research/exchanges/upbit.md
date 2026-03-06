# Upbit — Deep Discovery

## Documentation Sites
- **Main docs (EN)**: https://global-docs.upbit.com/
- **Main docs (KR)**: https://docs.upbit.com/
- **API reference (EN)**: https://global-docs.upbit.com/reference
- **API reference (KR)**: https://docs.upbit.com/ko/reference
- **WebSocket**: Integrated into main docs
- **Platform**: ReadMe.io
- **llms.txt**: https://global-docs.upbit.com/llms.txt (structured index for AI navigation)

## Versioned APIs
- **Current**: v1 (REST base: api.upbit.com/v1)
- **Legacy**: None
- **Note**: Korean docs are more up-to-date than English (~3 minor versions ahead)

## Changelogs & Updates
- **Changelog (EN)**: https://global-docs.upbit.com/changelog (61 entries, 7 pages)
- **Changelog (KR)**: https://docs.upbit.com/ko/changelog
- **RSS (EN)**: https://global-docs.upbit.com/changelog.rss (57 items, 2019-2025)
- **RSS (KR)**: https://docs.upbit.com/kr/changelog.rss (79 items)
- **Frequency**: Monthly (more frequent in Korean)

## GitHub
- **Org**: https://github.com/upbit-exchange (5 repos)
- **SDKs**: upbit-exchange/client, upbit-exchange/python-client
- **Community OpenAPI**: https://github.com/uJhin/upbit-client (swg_generated/go/api/swagger.yaml, 92KB)
- **Community docs**: https://ujhin.github.io/upbit-client-docs/

## Specs & Collections
- **OpenAPI**: Community only (swagger.yaml in ujhin/upbit-client)
- **Postman**: None
- **GraphQL**: None

## Discovery Files
- **robots.txt**: Blocks /*/api-next, /cdn-cgi/, /edit/, /login, /logout. No sitemap.
- **Hidden paths**: /llms.txt

## CCXT
- **ID**: `upbit`

## Status & Incidents
- **Status page**: None (has /v1/status/wallet for deposit/withdrawal status)

## Action Items
- [ ] RSS feeds for automated changelog monitoring (both EN and KR)
- [ ] Community OpenAPI spec — assess for import viability
- [ ] llms.txt — potentially useful as structured doc source
