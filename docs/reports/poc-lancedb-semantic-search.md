# POC: LanceDB Semantic Search vs SQLite FTS5

Date: 2026-02-12
Corpus: 3,815 pages, 4.5M words across 16 exchanges

## Build Performance

| Metric | Value |
|--------|-------|
| Pages embedded | 3,815 |
| Build time | 43.4s |
| Model | all-MiniLM-L6-v2 (384 dims, 80MB) |
| Index size | ~6 MB vectors + FTS |
| Embedding rate | ~88 pages/sec |

## Query Latency (20 queries, top-5 results each)

| Engine | Avg Latency |
|--------|-------------|
| SQLite FTS5 | 6.2ms |
| LanceDB Vector | 6.7ms |
| LanceDB Hybrid | 7.6ms |

All sub-10ms. No perceptible difference.

## Key Findings

### 1. Vector search finds pages FTS5 misses entirely

FTS5 returned nothing for 10 of 20 queries. Vector search returned results for 18 of 20.

Examples where vector search succeeds and FTS5 fails:
- "How do I check my account balance?" → `/docs/wallet/account/api-key-permission`
- "What are the rate limits for trading?" → `/docs/v5/broker/exchange-broker/rate-limit/introduction`
- "broker sub-account management" → `/managed-sub-account/Query-Managed-Sub-Account-Transfer-Log`
- "websocket real-time order updates" → `/reference/ws-auth-input` (Bitfinex)

### 2. Semantic matching bridges synonym gaps

| Query | FTS5 Result | Vector/Hybrid Result |
|-------|-------------|---------------------|
| "withdraw funds" | Gate.io index page (broad) | `enable-fast-withdraw-switch` (specific) |
| "candlestick chart data klines" | web-socket-streams (broad) | `Continuous-Contract-Kline-Candlestick-Streams` (exact) |
| "futures perpetual swap funding rate" | OKX docs-v5 (entire page) | `Get-Funding-Rate-History-of-Perpetual-Futures` (exact) |
| "copy trading follower endpoints" | error-code page | `copytrading/follower/Cancel-Trader` (relevant) |

### 3. Hybrid search combines the best of both

Hybrid found the exact Bybit `/v5/market/tickers` page for the query "/v5/market/tickers" — while vector search alone returned a different Bybit page (adl-alert) and FTS5 returned nothing.

### 4. Low overlap confirms complementarity

- Average FTS5/Vector overlap: 0.1/5 results
- Average FTS5/Hybrid overlap: 0.2/5 results
- This means FTS5 and vector search are finding almost completely different pages — they're complementary, not redundant.

### 5. FTS5 still has edge cases where it wins

- "margin trading leverage API" → Both FTS5 and Hybrid found the same page (Adjust-Cross-Margin-Max-Leverage). FTS5's exact keyword match was reliable here.
- "authentication HMAC signature" → FTS5 found the websocket request-security page directly; vector found a mini-program signature page.

## Verdict

**LanceDB adds clear value as a supplementary semantic index.** The POC validates the hypothesis from the research report:

1. **For natural language questions**: Vector/hybrid search provides results where FTS5 returns nothing (50% of queries).
2. **For concept/synonym queries**: Vector search bridges vocabulary gaps ("withdraw" → "fast-withdraw-switch", "klines" → "Candlestick-Streams").
3. **For exact lookups**: FTS5 remains the right tool when queries contain exact API paths.
4. **Performance is equivalent**: Sub-10ms for all three engines. No latency penalty.
5. **Build cost is low**: 43 seconds to embed 3,815 pages with a lightweight model on a laptop.

## Recommendation

Proceed with integrating LanceDB as an optional `[semantic]` dependency:
1. Add `build-index` and `semantic-search` CLI commands.
2. Add hybrid search as a fallback in the `answer` command when FTS5 returns no results.
3. Keep SQLite FTS5 as the primary search (battle-tested, zero dependencies).
4. Rebuild the LanceDB index post-sync via the `build-index` command.

## Architecture

```
User Query
    |
    v
SQLite FTS5 (primary, keyword)
    |
    +--> Results found? --> Return cited answer
    |
    +--> No results? --> LanceDB Vector (fallback, semantic)
                              |
                              v
                         Return cited answer
```

Alternatively, always run both and merge with RRF (higher quality, slightly more complex).
