# Registry Updates — Recommended Changes to exchanges.yaml

**Date**: 2026-03-06
**Source**: Crawl Targets Bible research (M1–M3)

## 1. New Exchange Registrations

### Orderly Network (RECOMMEND ADD)
```yaml
orderly:
  display_name: "Orderly Network"
  type: dex
  sections:
    evm:
      seeds:
        - https://docs.orderly.network/
      allowed_domains:
        - docs.orderly.network
      doc_sources:
        - type: openapi
          url: https://raw.githubusercontent.com/OrderlyNetwork/.../evm.openapi.yaml
```
- **Rationale**: 461KB OpenAPI spec, active protocol, powers multiple frontends (WOOFi Pro, LogX)
- **Action**: Locate exact GitHub raw URL for evm.openapi.yaml

### Bluefin (RECOMMEND ADD)
```yaml
bluefin:
  display_name: "Bluefin"
  type: dex
  sections:
    api:
      seeds:
        - https://bluefin-exchange.readme.io/
      allowed_domains:
        - bluefin-exchange.readme.io
      render_mode: auto
```
- **Rationale**: ReadMe.io platform, ~22 REST endpoints, active Sui-based protocol
- **Note**: GitHub org is fireflyprotocol (previous name was Firefly)

### Nado (RECOMMEND ADD)
```yaml
nado:
  display_name: "Nado"
  type: dex
  sections:
    api:
      seeds:
        - https://docs.nado.trade/
      allowed_domains:
        - docs.nado.trade
```
- **Rationale**: Active changelog, 3 SDK languages, growing protocol

## 2. Remove / Mark Defunct

### Perpetual Protocol (REMOVE)
- **Current**: `perp` in registry with 36 pages, 43K words
- **Finding**: docs.perp.com DNS is dead (NXDOMAIN), token delisted
- **Action**: Remove from registry or add `status: defunct` field
- **Note**: 36 stored pages are historical only — no longer updatable

## 3. New Sections for Existing Exchanges

### Binance — FIX API
```yaml
binance:
  sections:
    fix:
      seeds:
        - https://developers.binance.com/docs/binance-spot-api-docs/fix-api
      allowed_domains:
        - developers.binance.com
      scope_prefixes:
        - /docs/binance-spot-api-docs/fix-api
```
- **Rationale**: FIX 4.4 protocol docs exist, not currently crawled

### Bitstamp — FIX v2
```yaml
bitstamp:
  sections:
    fix:
      seeds:
        - https://www.bitstamp.net/fix/v2/
      allowed_domains:
        - www.bitstamp.net
```
- **Rationale**: FIX v2 docs at /fix/v2/, not currently crawled

### Bitstamp — WebSocket v2
```yaml
bitstamp:
  sections:
    websocket:
      seeds:
        - https://www.bitstamp.net/websocket/v2/
      allowed_domains:
        - www.bitstamp.net
```

### Bitstamp — PSD2 / Open Banking
```yaml
bitstamp:
  sections:
    psd2:
      seeds:
        - https://www.bitstamp.net/api-psd2/
      allowed_domains:
        - www.bitstamp.net
```
- **Rationale**: PSD2/Open Banking API docs exist at /api-psd2/

### Kraken — Embed REST API
- **Finding**: docs.kraken.com/api/docs/guides/embed-rest/ (B2B partners, new Feb 2026)
- **Action**: Evaluate whether this warrants a separate section or is covered by existing spot crawl

## 4. New doc_sources (OpenAPI/Postman Imports)

### KuCoin — 23 OpenAPI Spec Files
```yaml
kucoin:
  sections:
    spot:
      doc_sources:
        - type: openapi
          url: https://raw.githubusercontent.com/Kucoin/kucoin-universal-sdk/main/spec/rest/entry/spot.json
        - type: openapi
          url: https://raw.githubusercontent.com/Kucoin/kucoin-universal-sdk/main/spec/rest/entry/futures.json
        - type: openapi
          url: https://raw.githubusercontent.com/Kucoin/kucoin-universal-sdk/main/spec/rest/entry/margin.json
        - type: openapi
          url: https://raw.githubusercontent.com/Kucoin/kucoin-universal-sdk/main/spec/rest/entry/account.json
        # ... 9 entry-point specs total
```
- **Note**: Use entry-point specs (9 consolidated files in spec/rest/entry/) rather than 23 granular files
- **Priority**: HIGH — currently only 70 endpoints despite 1M+ words of docs

### GRVT — OpenAPI Import
```yaml
grvt:
  sections:
    api:
      doc_sources:
        - type: openapi
          url: https://raw.githubusercontent.com/gravity-technologies/api-spec/main/apispec.json
```

### Paradex — OpenAPI Import
```yaml
paradex:
  sections:
    api:
      doc_sources:
        - type: openapi
          url: https://api.prod.paradex.trade/swagger/doc.json
```

### Lighter — OpenAPI Import
```yaml
lighter:
  sections:
    docs:
      doc_sources:
        - type: openapi
          url: https://raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json
```

### Coinbase Prime — OpenAPI Import
```yaml
coinbase:
  sections:
    prime:
      doc_sources:
        - type: openapi
          url: https://api.prime.coinbase.com/v1/openapi.yaml
```

### dYdX — Swagger Import
```yaml
dydx:
  sections:
    docs:
      doc_sources:
        - type: openapi
          url: https://raw.githubusercontent.com/dydxprotocol/v4-chain/main/indexer/services/comlink/public/swagger.json
```

### BitMart — Postman Import
```yaml
bitmart:
  sections:
    spot:
      doc_sources:
        - type: postman
          url: https://raw.githubusercontent.com/bitmartexchange/bitmart-postman-api/master/collections/Spot.postman_collection.json
    futures:
      doc_sources:
        - type: postman
          url: https://raw.githubusercontent.com/bitmartexchange/bitmart-postman-api/master/collections/Futures.postman_collection.json
```
- **Priority**: HIGH — 73K words, 0 endpoints

## 5. Metadata Updates

### Add Changelog URLs
For structured changelog monitoring, add `changelog_url` fields where discovered:

| Exchange | Changelog URL |
|----------|--------------|
| Kraken | https://docs.kraken.com/api/docs/change-log/ |
| Coinbase | 6 separate URLs (see Bible) |
| Bitfinex | https://docs.bitfinex.com/docs/changelog |
| WhiteBIT | https://docs.whitebit.com/changelog/ |

### Add RSS Feed URLs
For automated changelog monitoring:

| Exchange | Feed URL |
|----------|----------|
| Upbit (EN) | https://global-docs.upbit.com/changelog.rss |
| Upbit (KR) | https://docs.upbit.com/kr/changelog.rss |
| Bithumb | https://apidocs.bithumb.com/changelog.rss |
| Coinone | https://docs.coinone.co.kr/changelog.rss |
| BitMEX | https://www.bitmex.com/api_announcement/feed |

### Add Status Page URLs
For automated health monitoring:

| Exchange | Status URL |
|----------|-----------|
| Bitfinex | https://bitfinex.statuspage.io/ |
| Kraken | https://status.kraken.com/ |
| BitMEX | https://status.bitmex.com/ |
| HTX | https://status.huobigroup.com/ |
| Crypto.com | https://status.crypto.com/ |
| Coinbase | https://status.coinbase.com/ |
| dYdX | https://status.dydx.trade/ |
| Korbit | https://status.korbit.co.kr/ |
| WhiteBIT | https://status.whitebit.com/ |
| MercadoBitcoin | https://status.mercadobitcoin.com.br/ |

## 6. CCXT Cross-Reference Updates

### Add to CCXT_EXCHANGE_MAP (ccxt_xref.py)
```python
# Currently missing:
"hyperliquid": "hyperliquid",  # Module exists, not mapped
"dydx": "dydx",               # DEX, has CCXT class
```

### Fix dict-of-dicts Extraction Bug
- **Bug**: `_extract_ccxt_endpoints()` only handles list-based API trees, not dict-of-dicts
- **Impact**: 15/20 exchanges return 0 CCXT endpoints
- **Priority**: HIGH — blocks meaningful cross-reference data

## 7. Sitemap Updates

### Add Sitemaps Where Discovered
| Exchange | Sitemap URL |
|----------|-----------|
| Bitstamp | https://www.bitstamp.net/sitemap.xml |
| BitMEX | https://docs.bitmex.com/sitemap.xml (148 URLs) |

## 8. Summary of Changes

| Category | Count | Est. Impact |
|----------|------:|-------------|
| New exchanges to add | 3 | +3 exchanges, ~500+ endpoints |
| Exchanges to remove/defunct | 1 | Cleanup |
| New sections for existing exchanges | 4 | Better FIX/WS/PSD2 coverage |
| New OpenAPI/Postman imports | 7 | ~660+ new endpoints |
| Community specs to evaluate | 4 | ~220 potential endpoints |
| Changelog/RSS feeds to monitor | 10 | Drift detection |
| Status pages to monitor | 10 | Health monitoring |
| CCXT map additions | 2 | Better cross-reference |
| CCXT bug fix | 1 | Unblocks 15/20 exchange xrefs |

**Total estimated new endpoints from spec imports alone: ~660+**
