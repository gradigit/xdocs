# dYdX — Deep Discovery

## Documentation Sites
- **Main docs**: https://docs.dydx.xyz/ (GitBook)
- **Indexer API**: https://docs.dydx.exchange/developers/indexer/indexer_api
- **Indexer WebSocket**: https://docs.dydx.exchange/developers/indexer/indexer_websocket
- **v3 docs (legacy)**: https://dydxprotocol.github.io/v3-teacher/ (read-only reference)
- **Blog**: https://www.dydx.xyz/blog/
- **Platform**: GitBook + GitHub (v4-documentation, MDX)
- **Alternate domains**: docs.dydx.exchange, docs.dydx.trade (both point to v4 docs)

## Versioned APIs
- **Current**: v4 (Chain, Indexer API v1.0.0)
- **Legacy**: v3 sunset Oct 28, 2024 (read-only API kept ~1 year)
- **Base URL**: https://indexer.dydx.trade/v4 (mainnet)

## Changelogs & Updates
- **Changelog**: Via v4-chain GitHub releases + v4-documentation commits
- **RSS**: https://github.com/dydxprotocol/v4-chain/releases.atom
- **Frequency**: Very active — v4-chain updated through Mar 2026

## GitHub
- **Org**: https://github.com/dydxprotocol
- **Docs repo**: https://github.com/dydxprotocol/v4-documentation (MDX, updated Feb 2026)
- **Swagger spec**: https://github.com/dydxprotocol/v4-chain/blob/main/indexer/services/comlink/public/swagger.json (114,959 bytes, Swagger 2.0)
- **SDKs**: dydxprotocol/v4-clients (TypeScript), dydxprotocol/dydx-v3-python (legacy v3, still on PyPI)
- **Widdershins**: dydxprotocol/dydx-widdershins (OpenAPI-to-markdown converter)
- **Commit feeds**: https://github.com/dydxprotocol/v4-chain/commits.atom, https://github.com/dydxprotocol/v4-documentation/commits.atom

## Specs & Collections
- **Swagger**: https://github.com/dydxprotocol/v4-chain/blob/main/indexer/services/comlink/public/swagger.json (Swagger 2.0, ~115KB)
- **Postman**: None found

## CCXT
- **ID**: `dydx` (may need to be added to ccxt_xref.py)

## Status & Incidents
- **Status page (v4)**: https://status.dydx.trade/ (active)
- **Status page (v3)**: https://status.dydx.exchange/ (inactive/read-only)
- **Status page (testnet)**: https://status.v4testnet.dydx.exchange/
- **API**: Standard Statuspage.io APIs (Slack/Atom/RSS subscriptions)

## Action Items
- [ ] dYdX Indexer swagger.json (115KB) — importable, add to import pipeline
- [ ] Add dydx to ccxt_xref.py CCXT_EXCHANGE_MAP
- [ ] Monitor v4-chain releases.atom for API changes
