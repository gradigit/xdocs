# Exchange Registry

Each exchange entry below defines the crawl targets and API structure. The `doc_urls` are the
**official** entry points for crawling. `api_base_urls` map purpose labels to base URLs.

When crawling, start from `doc_urls` and follow links within the domain scope.

## Tier 1: Major Global Exchanges

### Binance

```yaml
id: binance
ccxt_id: binance
language: en
doc_urls:
  spot: https://binance-docs.github.io/apidocs/spot/en/
  futures_usdm: https://binance-docs.github.io/apidocs/futures/en/
  futures_coinm: https://binance-docs.github.io/apidocs/delivery/en/
  portfolio_margin: https://binance-docs.github.io/apidocs/pm/en/
  websocket_spot: https://binance-docs.github.io/apidocs/spot/en/#websocket-market-streams
  websocket_futures: https://binance-docs.github.io/apidocs/futures/en/#websocket-market-streams
api_base_urls:
  spot: https://api.binance.com
  sapi: https://api.binance.com/sapi
  futures_usdm: https://fapi.binance.com
  futures_coinm: https://dapi.binance.com
  portfolio_margin: https://papi.binance.com
  websocket_spot: wss://stream.binance.com:9443
  websocket_futures: wss://fstream.binance.com
domain_scope: binance-docs.github.io
api_versions:
  spot: v3
  futures: v1,v2
  sapi: v1,v2,v3
notes: |
  - sapi endpoints are for margin, savings, staking, sub-accounts, etc.
  - papi is portfolio margin (unified account)
  - fapi is USD-M futures, dapi is COIN-M futures
  - Rate limits: IP-based + order-based, varies by endpoint weight
  - Some endpoints have different weights depending on parameters
changelog_url: https://binance-docs.github.io/apidocs/spot/en/#change-log
```

### OKX

```yaml
id: okx
ccxt_id: okx
language: en
doc_urls:
  rest: https://www.okx.com/docs-v5/en/
  websocket: https://www.okx.com/docs-v5/en/#websocket-api
api_base_urls:
  rest: https://www.okx.com
  websocket_public: wss://ws.okx.com:8443/ws/v5/public
  websocket_private: wss://ws.okx.com:8443/ws/v5/private
  websocket_business: wss://ws.okx.com:8443/ws/v5/business
  demo: https://www.okx.com (header: x-simulated-trading: 1)
domain_scope: www.okx.com
api_versions:
  current: v5
notes: |
  - Unified account model \u2014 single API for spot/margin/futures/perps/options
  - All endpoints under /api/v5/
  - Sections: trade, market, account, asset, sub-account, earn, etc.
  - Rate limits per endpoint, some per user-ID, some per IP
changelog_url: https://www.okx.com/docs-v5/log_en/
```

### Bybit

```yaml
id: bybit
ccxt_id: bybit
language: en
doc_urls:
  v5: https://bybit-exchange.github.io/docs/v5/intro
  websocket: https://bybit-exchange.github.io/docs/v5/ws/connect
api_base_urls:
  rest: https://api.bybit.com
  websocket_public: wss://stream.bybit.com/v5/public
  websocket_private: wss://stream.bybit.com/v5/private
domain_scope: bybit-exchange.github.io
api_versions:
  current: v5
  legacy: v3 (deprecated)
notes: |
  - Unified v5 API covers spot, linear, inverse, option
  - Category parameter determines product type
  - Rate limits vary by endpoint and VIP level
changelog_url: https://bybit-exchange.github.io/docs/changelog/v5
```

### Bitget

```yaml
id: bitget
ccxt_id: bitget
language: en
doc_urls:
  v2: https://www.bitget.com/api-doc/common/intro
api_base_urls:
  rest: https://api.bitget.com
  websocket_public: wss://ws.bitget.com/v2/ws/public
  websocket_private: wss://ws.bitget.com/v2/ws/private
domain_scope: www.bitget.com
api_versions:
  current: v2
  legacy: v1
notes: |
  - Sections: spot, mix (futures), margin, earn, broker, tax, convert
  - v2 is current, v1 still works but deprecated
```

### Gate.io

```yaml
id: gateio
ccxt_id: gateio
language: en
doc_urls:
  v4: https://www.gate.io/docs/developers/apiv4/
api_base_urls:
  rest: https://api.gateio.ws/api/v4
  websocket_spot: wss://api.gateio.ws/ws/v4/
  websocket_futures: wss://fx-ws.gateio.ws/v4/ws/
domain_scope: www.gate.io
api_versions:
  current: v4
```

### KuCoin

```yaml
id: kucoin
ccxt_id: kucoin
language: en
doc_urls:
  spot: https://www.kucoin.com/docs/rest/spot-trading/spot-hf-trade-pro-account/place-hf-order
  futures: https://www.kucoin.com/docs/rest/futures-trading/orders/place-order
api_base_urls:
  spot: https://api.kucoin.com
  futures: https://api-futures.kucoin.com
domain_scope: www.kucoin.com
api_versions:
  spot: v1,v2,v3
  futures: v1
notes: |
  - Separate spot and futures APIs
  - WebSocket requires getting a token via REST first
  - HF (high-frequency) endpoints for spot
```

### HTX (Huobi)

```yaml
id: htx
ccxt_id: htx
language: en
doc_urls:
  spot: https://www.htx.com/en-us/opend/newApiPages/
api_base_urls:
  spot: https://api.huobi.pro
  futures: https://api.hbdm.com
domain_scope: www.htx.com
api_versions:
  spot: v1,v2
  futures: v1
notes: |
  - Rebranded from Huobi to HTX
  - Old API URLs (huobi.pro, hbdm.com) may still work
  - Separate APIs for spot, futures (linear/inverse), options
```

### Crypto.com

```yaml
id: cryptocom
ccxt_id: cryptocom
language: en
doc_urls:
  exchange: https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html
api_base_urls:
  rest: https://api.crypto.com/exchange/v1
  websocket: wss://stream.crypto.com/exchange/v1/market
domain_scope: exchange-docs.crypto.com
api_versions:
  current: v1
```

### Bitstamp

```yaml
id: bitstamp
ccxt_id: bitstamp
language: en
doc_urls:
  rest: https://www.bitstamp.net/api/
api_base_urls:
  rest: https://www.bitstamp.net/api
  websocket: wss://ws.bitstamp.net
domain_scope: www.bitstamp.net
api_versions:
  current: v2
```

### Bitfinex

```yaml
id: bitfinex
ccxt_id: bitfinex2
language: en
doc_urls:
  v2: https://docs.bitfinex.com/reference/rest-public-platform-status
api_base_urls:
  rest: https://api-pub.bitfinex.com/v2
  websocket: wss://api-pub.bitfinex.com/ws/2
domain_scope: docs.bitfinex.com
api_versions:
  current: v2
  legacy: v1 (deprecated)
```

## Tier 1: DEXs / DEX-like

### dYdX

```yaml
id: dydx
ccxt_id: dydx
language: en
doc_urls:
  v4: https://docs.dydx.exchange/
  api: https://docs.dydx.exchange/api_integration-indexer/indexer_api
api_base_urls:
  indexer: https://indexer.dydx.trade/v4
  websocket: wss://indexer.dydx.trade/v4/ws
domain_scope: docs.dydx.exchange
api_versions:
  current: v4
notes: |
  - v4 is the decentralized version (Cosmos-based)
  - Indexer API for reading, chain for writing
  - gRPC available for validators
```

### Hyperliquid

```yaml
id: hyperliquid
ccxt_id: hyperliquid
language: en
doc_urls:
  rest: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
api_base_urls:
  rest: https://api.hyperliquid.xyz
  websocket: wss://api.hyperliquid.xyz/ws
domain_scope: hyperliquid.gitbook.io
api_versions:
  current: v1 (unversioned)
notes: |
  - L1 DEX \u2014 perpetuals only (no spot)
  - All POST to /info (read) and /exchange (write)
  - Custom JSON-RPC-like format, not REST
```

## Tier 1: Korean Exchanges

### Upbit

```yaml
id: upbit
ccxt_id: upbit
language: ko,en
doc_urls:
  rest: https://docs.upbit.com/reference
  rest_ko: https://docs.upbit.com/ko/reference
api_base_urls:
  rest: https://api.upbit.com/v1
  websocket: wss://api.upbit.com/websocket/v1
domain_scope: docs.upbit.com
api_versions:
  current: v1
notes: |
  - Korean exchange, docs available in Korean and English
  - Crawl BOTH /ko/ and /en/ paths
  - Korean version may have more detail or be more up to date
  - KRW pairs only (no USDT)
```

### Bithumb

```yaml
id: bithumb
ccxt_id: bithumb
language: ko,en
doc_urls:
  rest: https://apidocs.bithumb.com/
api_base_urls:
  rest: https://api.bithumb.com
  websocket: wss://pubwss.bithumb.com/pub/ws
domain_scope: apidocs.bithumb.com
api_versions:
  current: (unversioned)
notes: |
  - Primarily Korean, some English docs
  - Store bilingual \u2014 original Korean + English translation
```

### Coinone

```yaml
id: coinone
ccxt_id: coinone
language: ko
doc_urls:
  rest: https://docs.coinone.co.kr/
api_base_urls:
  rest: https://api.coinone.co.kr
domain_scope: docs.coinone.co.kr
api_versions:
  current: v2
notes: |
  - Korean only \u2014 always store original + translation
```

### Korbit

```yaml
id: korbit
ccxt_id: korbit
language: ko,en
doc_urls:
  rest: https://apidocs.korbit.co.kr/
api_base_urls:
  rest: https://api.korbit.co.kr/v1
domain_scope: apidocs.korbit.co.kr
api_versions:
  current: v1
```

## Adding New Exchanges

To add a new exchange, add an entry following the schema above with:
1. Official doc URLs (entry points for crawling)
2. API base URLs with purpose labels
3. Domain scope for the crawler
4. Known API versions
5. Any exchange-specific notes or quirks

Then run: `python3 scripts/cex_crawl.py --exchange <id> --output-dir ./cex-docs`
