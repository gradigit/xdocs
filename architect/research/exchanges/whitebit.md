# WhiteBIT — Deep Discovery

## Documentation Sites
- **Main docs**: https://docs.whitebit.com/ (Docusaurus/Next.js)
- **WebSocket**: Integrated (market + account streams)
- **Blog**: https://blog.whitebit.com/
- **Platform**: Docusaurus (source on GitHub)

## Versioned APIs
- **Current**: V4 (primary), V2 (legacy public endpoints still documented)
- **Legacy**: V1, V2 under /public/http-v1/, /public/http-v2/
- **Note**: 110 CCXT endpoints, 0 in our DB — largest gap

## Changelogs & Updates
- **Changelog**: https://docs.whitebit.com/changelog/ (Feb-Sep 2025 entries)
- **Structured data**: `public/data/changelog.json` in GitHub repo
- **RSS**: None
- **Frequency**: Monthly

## GitHub
- **Org**: https://github.com/whitebit-exchange (13 repos)
- **Docs repo**: https://github.com/whitebit-exchange/api-docs (Next.js/Docusaurus source)
- **SDKs**: go-sdk, python-sdk, php-sdk
- **Examples**: api-quickstart (Python, Node.js, PHP, Go, Java)
- **Other**: wbt, docs, extensions
- **Commit feed**: https://github.com/whitebit-exchange/api-docs/commits/main.atom

## Specs & Collections
- **OpenAPI**: None (searched all repos)
- **Postman**: None

## Discovery Files
- **robots.txt**: Disallows /cdn-cgi/. Sitemap: https://docs.whitebit.com/sitemap.xml
- **sitemap.xml**: 141 URLs (account-wallet 34, spot 18, collateral 17, sub-accounts 17, websocket 22, market-data 14, oauth 9, convert 3, guides 6, platform 5)
- **Hidden paths**: /guides/ai-context-menu, /guides/ai-ide-setup (AI integration guides)

## CCXT
- **ID**: `whitebit`
- **Gap**: 110 CCXT endpoints, 0 in our DB

## Status & Incidents
- **Status page**: https://status.whitebit.com/ (OpenStatus)
- **Monitored**: Frontend, Public API, Blog

## Action Items
- [!] Largest endpoint gap — needs manual extraction from 161 stored pages (95K words) or OpenAPI spec discovery
- [ ] changelog.json — structured changelog data for automated monitoring
- [ ] Sitemap already has 141 URLs — verify our 161 pages match
