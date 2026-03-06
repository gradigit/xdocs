# KuCoin — Deep Discovery

## Documentation Sites
- **Main docs**: https://www.kucoin.com/docs-new/introduction (custom platform, opaque URL IDs)
- **Legacy docs**: https://docs.kucoin.com (Slate-based, older)
- **WebSocket docs**: Integrated into main docs
- **FIX protocol**: None
- **Developer portal**: https://www.kucoin.com/api (landing page)
- **Platform**: Custom (opaque URL IDs like /docs-new/338210m0)

## Versioned APIs
- **Current**: V1 (REST), V2 (some broker endpoints); Unified Trading Account API (Sept 2025)
- **Legacy**: docs.kucoin.com (Slate); deprecated futures docs in Kucoin/Docs-Deprecated repo
- **UTA announcement**: https://www.kucoin.com/announcement/en-kucoin-unified-api-announcement

## Changelogs & Updates
- **Changelog URL**: https://www.kucoin.com/docs-new/change-log
- **Format**: Date-stamped entries
- **RSS/Atom feed**: None
- **Frequency**: Multiple/month
- **Telegram**: t.me/KuCoin_API

## GitHub
- **Org**: https://github.com/Kucoin (28 repos)
- **Docs repos**: kucoin-api-docs (Slate, spot), kucoin-futures-api-docs (futures)
- **OpenAPI specs**: https://github.com/Kucoin/kucoin-universal-sdk/tree/main/spec/rest/api — **23 granular JSON spec files**:
  - Account: account, deposit, fee, subaccount, transfer, withdrawal
  - Affiliate: affiliate
  - Broker: apibroker, ndbroker
  - Copy Trading: futures
  - Earn: earn
  - Futures: fundingfees, market, order, positions
  - Margin: credit, debit, market, order, risklimit
  - Spot: market, order
  - VIP Lending: viplending
- **Entry-point specs**: 9 consolidated specs in `spec/rest/entry/`
- **SDKs**: kucoin-universal-sdk (multi-lang), kucoin-python-sdk, kucoin-go-sdk, kucoin-java-sdk, kucoin-php-sdk, kucoin-node-sdk, futures variants
- **Commit feed**: https://github.com/Kucoin/kucoin-universal-sdk/commits/main.atom

## Specs & Collections
- **OpenAPI**: 23 JSON files in kucoin-universal-sdk/spec/rest/api/ (comprehensive coverage)
- **Postman**: https://www.postman.com/kucoin-api/kucoin-api/overview (official workspace)
- **GraphQL**: None

## Discovery Files
- **robots.txt**: Disallows /assets/, /earn-account/order, /order/, /account/; sitemap referenced
- **sitemap.xml**: https://www.kucoin.com/sitemap.xml
- **Hidden paths**: /docs/broker/api-broker/instructions; mining docs in kucoin-mining-docs repo

## CCXT
- **ID**: `kucoin` (also `kucoinfutures`)

## Status & Incidents
- **Status page**: None (no dedicated web page)
- **API**: `GET /api/v1/status` (open/close/cancelonly)
- **Announcements**: https://www.kucoin.com/announcement/maintenance-updates

## Action Items
- [x] OpenAPI specs exist — 23 files in kucoin-universal-sdk repo (MAJOR FIND)
- [ ] Import all 23 OpenAPI specs (currently only spot + futures imported from older source)
- [ ] Postman workspace — additional import source
- [ ] kucoin-mining-docs — assess if relevant
