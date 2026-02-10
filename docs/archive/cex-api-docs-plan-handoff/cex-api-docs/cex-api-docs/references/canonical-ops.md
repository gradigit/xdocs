# Canonical Operations

Canonical operations provide a **normalized vocabulary** for cross-exchange comparison. These are
**additive metadata** \u2014 the original exchange terminology is always preserved alongside.

Bootstrapped from CCXT's unified API methods, extended with operations CCXT doesn't cover.

## Mapping Rules

1. Every exchange endpoint gets tagged with zero or more canonical operations
2. One endpoint may map to multiple canonical ops (e.g., a "get account" endpoint that returns
   both balances and positions)
3. If no canonical op fits, tag as `unmapped` with a suggested new canonical name
4. Canonical names use snake_case: `{verb}_{noun}`

## Market Data (Public)

| Canonical Operation | Description | CCXT Method |
|---|---|---|
| `get_ticker` | Current price/24h stats for a symbol | `fetchTicker` |
| `get_tickers` | All tickers | `fetchTickers` |
| `get_orderbook` | Order book (bids/asks) | `fetchOrderBook` |
| `get_trades` | Recent trades | `fetchTrades` |
| `get_ohlcv` | Candlestick/kline data | `fetchOHLCV` |
| `get_funding_rate` | Current funding rate (perps) | `fetchFundingRate` |
| `get_funding_rate_history` | Historical funding rates | `fetchFundingRateHistory` |
| `get_open_interest` | Open interest for a symbol | `fetchOpenInterest` |
| `get_mark_price` | Mark price (derivatives) | `fetchMarkPrice` |
| `get_index_price` | Index price | \u2014 |
| `get_markets` | List all trading pairs/instruments | `fetchMarkets` |
| `get_currencies` | List all currencies | `fetchCurrencies` |
| `get_exchange_info` | Exchange-level config (limits, etc.) | \u2014 |
| `get_server_time` | Server timestamp | \u2014 |

## Trading (Private)

| Canonical Operation | Description | CCXT Method |
|---|---|---|
| `place_order` | Create new order | `createOrder` |
| `place_orders_batch` | Create multiple orders | `createOrders` |
| `cancel_order` | Cancel single order | `cancelOrder` |
| `cancel_orders_batch` | Cancel multiple orders | `cancelOrders` |
| `cancel_all_orders` | Cancel all open orders | `cancelAllOrders` |
| `edit_order` | Modify existing order | `editOrder` |
| `get_order` | Get single order by ID | `fetchOrder` |
| `get_open_orders` | All open/active orders | `fetchOpenOrders` |
| `get_closed_orders` | Completed/cancelled orders | `fetchClosedOrders` |
| `get_order_history` | Full order history | `fetchOrders` |
| `get_my_trades` | User's trade/fill history | `fetchMyTrades` |

## Account (Private)

| Canonical Operation | Description | CCXT Method |
|---|---|---|
| `get_balance` | Account balances | `fetchBalance` |
| `get_positions` | Open positions (derivatives) | `fetchPositions` |
| `get_position` | Single position | `fetchPosition` |
| `set_leverage` | Set leverage for a symbol | `setLeverage` |
| `set_margin_mode` | Set cross/isolated margin | `setMarginMode` |
| `get_account_info` | Account configuration | \u2014 |
| `get_fee_rate` | Trading fee schedule | `fetchTradingFee` |
| `get_deposit_address` | Get deposit address | `fetchDepositAddress` |
| `get_deposits` | Deposit history | `fetchDeposits` |
| `get_withdrawals` | Withdrawal history | `fetchWithdrawals` |
| `withdraw` | Create withdrawal | `withdraw` |
| `transfer` | Internal transfer between accounts | `transfer` |

## Sub-Account (Private)

| Canonical Operation | Description | CCXT Method |
|---|---|---|
| `get_sub_accounts` | List sub-accounts | \u2014 |
| `create_sub_account` | Create sub-account | \u2014 |
| `get_sub_balance` | Sub-account balance | \u2014 |
| `sub_transfer` | Transfer between main/sub | \u2014 |
| `get_sub_deposit_address` | Sub-account deposit addr | \u2014 |

## Funding / Earn (Private)

| Canonical Operation | Description | CCXT Method |
|---|---|---|
| `get_funding_balance` | Funding/wallet balance | \u2014 |
| `get_lending_rates` | Current lending rates | \u2014 |
| `subscribe_lending` | Lend assets | \u2014 |
| `redeem_lending` | Redeem lent assets | \u2014 |
| `get_staking_products` | Available staking | \u2014 |
| `stake` | Stake assets | \u2014 |
| `unstake` | Unstake assets | \u2014 |

## WebSocket

| Canonical Operation | Description | CCXT WS |
|---|---|---|
| `ws_subscribe_ticker` | Real-time ticker | `watchTicker` |
| `ws_subscribe_orderbook` | Real-time order book | `watchOrderBook` |
| `ws_subscribe_trades` | Real-time trades | `watchTrades` |
| `ws_subscribe_ohlcv` | Real-time candles | `watchOHLCV` |
| `ws_subscribe_orders` | Order updates | `watchOrders` |
| `ws_subscribe_balance` | Balance updates | `watchBalance` |
| `ws_subscribe_positions` | Position updates | `watchPositions` |
| `ws_authenticate` | WS authentication | \u2014 |
| `ws_ping` | Keep-alive | \u2014 |
