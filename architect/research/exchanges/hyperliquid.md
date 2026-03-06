# Hyperliquid — Deep Discovery

**Note**: Hyperliquid is technically a DEX (decentralized perpetual futures, fully on-chain CLOB), not a CEX. Listed as CEX in our registry. Classification is contested (few validators, team-held supermajority stake).

## Documentation Sites
- **Main docs**: https://hyperliquid.gitbook.io/hyperliquid-docs/ (GitBook)
- **API reference**: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
- **WebSocket**: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket
- **Builder tools**: https://hyperliquid.gitbook.io/hyperliquid-docs/builder-tools/
- **App API settings**: https://app.hyperliquid.xyz/API
- **Platform**: GitBook

## Versioned APIs
- **Current**: No versioning (single API at api.hyperliquid.xyz)
- **Testnet**: api.hyperliquid-testnet.xyz

## Changelogs & Updates
- **Changelog**: None official
- **SDK releases**: Serve as informal changelog (Python SDK uses Release Drafter)

## GitHub
- **Org**: https://github.com/hyperliquid-dex (11 repos)
- **SDKs**: hyperliquid-python-sdk, hyperliquid-rust-sdk
- **Other**: ts-examples, node, contracts, historical_data, hyperliquid-stats, order_book_server
- **Community OpenAPI**: https://github.com/bowen31337/hyperliquid-openapi
  - openapi.yaml (38KB, OpenAPI 3.1.0)
  - websocket-api.yaml (22KB, AsyncAPI 3.0.0)
- **Community TypeScript SDKs**: nktkas/hyperliquid, nomeida/hyperliquid
- **Commit feed**: https://github.com/hyperliquid-dex/hyperliquid-python-sdk/commits/master.atom

## Specs & Collections
- **OpenAPI (community)**: https://github.com/bowen31337/hyperliquid-openapi/blob/main/openapi.yaml
- **AsyncAPI (community)**: https://github.com/bowen31337/hyperliquid-openapi/blob/main/websocket-api.yaml
- **Postman**: None

## Discovery Files
- **sitemap.xml**: https://hyperliquid.gitbook.io/hyperliquid-docs/sitemap.xml (3 sub-sitemaps: main, builder-tools, support)

## CCXT
- **ID**: `hyperliquid` (Python module exists but NOT in project's CCXT_EXCHANGE_MAP)
- **Auth**: Uses private key auth instead of API key/secret; API wallets for delegation

## Status & Incidents
- **Status page**: None

## Action Items
- [ ] Community OpenAPI spec — assess for import viability (38KB, 75 endpoints already in DB)
- [ ] Add to CCXT_EXCHANGE_MAP in ccxt_xref.py
- [ ] Consider reclassifying as DEX in registry
