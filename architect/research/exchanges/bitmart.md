# BitMart — Deep Discovery

## Documentation Sites
- **Main docs**: https://developer-pro.bitmart.com/ (Custom SPA)
- **Spot API**: https://developer-pro.bitmart.com/en/spot/
- **Futures V2**: https://developer-pro.bitmart.com/en/futuresv2/
- **Alternate domain**: https://openapi-doc.bitmart.com/en/spot/ [HTTP 525 SSL ERROR]
- **API landing**: https://www.bitmart.com/en-US/bitmart-api
- **WebSocket**: Integrated into main docs
- **Platform**: Custom SPA (single-page per section)

## Versioned APIs
- **Current**: Spot API + Futures V2
- **Legacy**: Futures V1 discontinued 2024-11-30
- **Note**: Demo trading environment for V2 Futures only

## Changelogs & Updates
- **Changelog**: Inline at developer-pro.bitmart.com/en/spot/#changelog (2025 entries)
- **Format**: Dated entries with [New], [Update] tags
- **RSS**: None
- **Frequency**: Monthly

## GitHub
- **Org**: https://github.com/bitmartexchange
- **Postman repo**: https://github.com/bitmartexchange/bitmart-postman-api
  - **Spot collection**: collections/Spot.postman_collection.json (45KB)
  - **Futures collection**: collections/Futures.postman_collection.json (49KB)
- **SDKs**: bitmart-{python,java,go,php,node}-sdk-api
- **Other**: bitmart-smart-contract, bitmart-us-api-docs

## Specs & Collections
- **OpenAPI**: None (openapi-doc.bitmart.com domain exists but SSL broken)
- **Postman**: Official — Spot (45KB) + Futures (49KB) collections
- **GraphQL**: None

## CCXT
- **ID**: `bitmart`

## Status & Incidents
- **Status page**: None (has /system/service API endpoint)

## Action Items
- [!] Import Postman collections — BitMart has 73K words, 0 endpoints. This is the most urgent extraction target.
- [ ] openapi-doc.bitmart.com — SSL cert issue, may have OpenAPI spec behind it
