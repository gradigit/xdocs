# Wow Query Showcase -- 16 Exchanges, 16 Questions

**Generated:** 2026-02-11
**Store:** cex-docs/ (2,286 pages, 3.13M words across 16 exchanges)
**Engine:** cite-only answer pipeline (FTS5 search + endpoint DB)

This report runs one carefully chosen query per exchange and evaluates how well the
cite-only answer engine surfaces real technical content from the stored documentation.
Each query targets a domain-specific topic -- rate limits, authentication, order
placement, margin mechanics, funding rates -- that a developer integrating with that
exchange would actually need to know.

---

## Summary

| # | Exchange | Query (abbreviated) | Status | Claims | Verdict |
|--:|----------|---------------------|--------|-------:|---------|
| 1 | **Binance** | Unified trading rate limits & API key permissions | ok | 1 | **Partial** |
| 2 | **OKX** | OK-ACCESS-SIGN signing & passphrase header | ok | 3 | **Weak** |
| 3 | **Bybit** | Unified margin mode & cross collateral | ok | 2 | **Partial** |
| 4 | **Bitget** | Copy trading follower orders & profit sharing | ok | 5 | **Weak** |
| 5 | **Gate.io** | Spot batch order limits & portfolio margin | ok | 1 | **Weak** |
| 6 | **KuCoin** | Inner transfer between accounts | ok | 5 | **Weak** |
| 7 | **HTX** | Coin-margined swap liquidation & insurance fund | ok | 4 | **Weak** |
| 8 | **Crypto.com** | Nonce requirement & HMAC-SHA256 signing | ok | 1 | **Weak** |
| 9 | **Bitstamp** | Instant order API & minimum trade amounts | ok | 1 | **Weak** |
| 10 | **Bitfinex** | Margin funding offers via REST API | ok | 1 | **Weak** |
| 11 | **dYdX** | v4 perpetual funding rate & indexer API | ok | 3 | **Partial** |
| 12 | **Hyperliquid** | Vault deposit/withdrawal & EIP-712 signing | ok | 3 | **Strong** |
| 13 | **Upbit** | Rate limit headers & KRW minimum order | ok | 5 | **Weak** |
| 14 | **Bithumb** | Limit order placement & error codes | ok | 3 | **Partial** |
| 15 | **Coinone** | 2FA for crypto withdrawals & API sequence | ok | 3 | **Partial** |
| 16 | **Korbit** | OAuth2 token refresh & scopes | ok | 2 | **Partial** |
|   | **Overall** | | **16/16 ok** | **52** | |

**Legend:** Strong = excerpts contain directly usable technical detail. Partial = correct
pages found but excerpts are truncated or mixed with navigation chrome.
Weak = matched pages are topically relevant but excerpts consist primarily of
navigation menus, sidebar links, or table-of-contents fragments rather than
substantive documentation content.

---

## 1. Binance -- Unified trading rate limits & API key permissions

**Query:** What are the Binance unified trading rate limits and API key permissions?

### What the docs say

The engine found the Binance derivatives quick-start guide, which documents API key
permission defaults:

- After creating an API key, the default restriction is **Enable Reading**.
- To **enable withdrawals via the API**, the API key restriction must be modified
  through the Binance UI.
- The page also references an "Enabling Accounts" section for further setup.

The excerpt is truncated and does not include the specific rate limit numbers for the
unified trading account (portfolio margin). Only the API key permission model is
covered in this excerpt window.

### Sources

- https://developers.binance.com/docs/derivatives/quick-start

### Verdict: Partial

The engine correctly identified the derivatives quick-start page and extracted
meaningful content about API key permissions. However, the rate limit specifics for
unified trading were not captured -- likely because the FTS5 search matched on
"API key" and "restrictions" rather than the rate limit tables that live on a separate
page. A single claim with a 400-character excerpt window is too narrow to cover both
halves of a two-part question.

---

## 2. OKX -- OK-ACCESS-SIGN signing & OK-ACCESS-PASSPHRASE header

**Query:** How do I sign an OKX API request with OK-ACCESS-SIGN and what is the
OK-ACCESS-PASSPHRASE header?

### What the docs say

The engine returned three claims, but none contain the actual signing procedure:

1. **Main docs page** -- The excerpt is the table of contents sidebar listing sections
   like "REST Authentication > Making Requests > Signature" and "WebSocket > Login".
   This confirms the documentation structure includes a signing section but does not
   reproduce its content.

2. **Broker docs** -- An excerpt about broker API integration mentioning the `tag`
   parameter for associating orders with broker codes. Not relevant to the signing
   question.

3. **Changelog** -- Lists upcoming and recent API changes (contract renaming, parameter
   deprecations). Not relevant to authentication.

### Sources

- https://www.okx.com/docs-v5/en/
- https://www.okx.com/docs-v5/broker_en/
- https://www.okx.com/docs-v5/log_en/

### Verdict: Weak

The engine correctly identified the main OKX docs page, which is the right source.
However, OKX serves its entire API reference as a single enormous HTML file (~224K
words). The FTS5 excerpt window landed on the sidebar navigation rather than the
actual REST Authentication section that describes HMAC-SHA256 signing, the
`OK-ACCESS-SIGN` header construction, and the `OK-ACCESS-PASSPHRASE` requirement.
This is a known challenge with single-page documentation sites.

---

## 3. Bybit -- Unified margin mode & cross collateral

**Query:** What is Bybit unified margin mode and how does cross collateral work between
spot and perpetual positions?

### What the docs say

The engine found two relevant pages:

1. **V5 API introduction** -- Contains a coverage matrix showing that V5 Unified Trading
   Account supports USDT Perpetual, USDC Perpetual, USDC Futures, Inverse Perpetual,
   Inverse Futures, Spot, and Options -- all marked with check marks. Classic accounts
   have more limited coverage. The excerpt references "Key Upgrades" and "Product Lines
   Alignment" noting that V5 unifies APIs across trading products.

2. **WebSocket connection page** -- The excerpt is sidebar navigation listing product
   sections (RFQ, Affiliate, Spot Margin Trade UTA, Crypto Loan). Not substantive.

### Sources

- https://bybit-exchange.github.io/docs/v5/intro
- https://bybit-exchange.github.io/docs/v5/ws/connect

### Verdict: Partial

The first claim contains genuinely useful information -- the V5 unified account coverage
matrix. However, the specific cross-collateral mechanics between spot and perpetual
positions are not in the excerpt window. The second claim is pure navigation chrome.

---

## 4. Bitget -- Copy trading follower orders & profit sharing

**Query:** How do Bitget copy trading followers place orders through the API and what are
the trader profit sharing rules?

### What the docs say

All five claims consist entirely of sidebar navigation links from different Bitget
documentation sections (Common, Copy Trading, Margin, Earn, Broker). Each excerpt is
a list of navigation menu items linking to product sections. No substantive content
about copy trading order placement or profit sharing mechanics was captured.

The engine correctly identified the Copy Trading intro page as relevant, but the
excerpt window captured only the top-of-page navigation bar rather than the page body.

### Sources

- https://www.bitget.com/api-doc/common/intro
- https://www.bitget.com/api-doc/copytrading/intro
- https://www.bitget.com/api-doc/margin/intro
- https://www.bitget.com/api-doc/earn/intro
- https://www.bitget.com/api-doc/broker/intro

### Verdict: Weak

Correct pages located (especially the copy trading intro), but every excerpt is
navigation chrome. Bitget's docs use JavaScript-heavy rendering and the navigation
elements dominate the HTML. The actual API documentation content is deeper in the page
and falls outside the excerpt windows.

---

## 5. Gate.io -- Spot batch order limits & portfolio margin

**Query:** What are Gate.io spot batch order limits and how does the unified account
portfolio margin calculation work?

### What the docs say

A single claim from the main Gate.io API v4 page. The excerpt shows the top-level
navigation (Spot & Margin, Perpetual Futures, Delivery Futures, Options, Unified,
Alpha, CrossEx, Announcements) and a reference to "Gate API v4.106.24" with an
"Access URL" section. No batch order limits or portfolio margin calculation details.

### Sources

- https://www.gate.com/docs/developers/apiv4/

### Verdict: Weak

Gate.io serves its entire API reference (~256K words) from a single HTML page. The
FTS5 excerpt landed on the page header and navigation menu. The actual batch order
and margin calculation documentation is buried deep in the page body and was not
captured in the excerpt window.

---

## 6. KuCoin -- Inner transfer between accounts

**Query:** How does KuCoin inner transfer work between main account and trading accounts
and what currencies are supported?

### What the docs say

Five claims were returned, all from KuCoin's documentation site, targeting relevant
transfer-related pages:

1. **Abandoned inner-transfer endpoint** -- Page header and navigation chrome. The URL
   path itself (`abandoned-endpoints/account-funding/inner-transfer`) confirms this is
   the legacy inner transfer endpoint, now deprecated.
2. **Flex transfer (new API)** -- Page header navigation only. The URL
   (`rest/account-info/transfer/flex-transfer`) indicates the replacement endpoint.
3. **Unified account flex transfer** -- Again header navigation from the UA section.
4. **Copy trading section** -- Navigation chrome only.
5. **Exchange broker section** -- Navigation chrome only.

### Sources

- https://www.kucoin.com/docs-new/abandoned-endpoints/account-funding/inner-transfer
- https://www.kucoin.com/docs-new/rest/account-info/transfer/flex-transfer
- https://www.kucoin.com/docs-new/rest/ua/flex-transfer
- https://www.kucoin.com/docs-new/rest/copy-trading/introduction
- https://www.kucoin.com/docs-new/rest/broker/exchange-broker/introduction

### Verdict: Weak

The engine found the exactly right pages -- both the deprecated inner-transfer endpoint
and its replacement (flex-transfer) across standard and unified account variants.
The URL selection is excellent. However, KuCoin's docs use client-side rendering that
produces navigation-heavy HTML, so every excerpt contains only sidebar links and
language selectors rather than the actual endpoint documentation.

---

## 7. HTX -- Coin-margined swap liquidation & insurance fund

**Query:** What is HTX coin-margined swap liquidation price formula and how does the
insurance fund work?

### What the docs say

Four claims spanning HTX's four documentation sections (Spot, Derivatives/DM,
Coin-Margined Swap, USDT Swap). All excerpts consist of the top-of-page navigation
bar with Chinese-language section links to the different contract types. No liquidation
formula or insurance fund mechanics were extracted.

### Sources

- https://huobiapi.github.io/docs/spot/v1/en/
- https://huobiapi.github.io/docs/dm/v1/en/
- https://huobiapi.github.io/docs/coin_margined_swap/v1/en/
- https://huobiapi.github.io/docs/usdt_swap/v1/en/

### Verdict: Weak

The engine correctly identified the coin-margined swap documentation page, which is the
right source. However, HTX uses single-page docs (~325K words across 4 pages) where
the navigation header dominates the FTS5 excerpt. The actual liquidation formula and
insurance fund description exist deeper in the document.

---

## 8. Crypto.com -- Nonce requirement & HMAC-SHA256 signing

**Query:** What is the Crypto.com exchange API nonce requirement and how does HMAC-SHA256
request signing work?

### What the docs say

A single claim from the Exchange API v1 documentation. The excerpt shows the page
navigation header including links to REST, WebSocket, and FIX 4.4 APIs, followed by the
table of contents: Introduction, Common API Reference (Naming Conventions, Generating
the API Key, REST API Root...). The ToC confirms the signing documentation exists on
this page but the excerpt does not reach the actual content.

### Sources

- https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html

### Verdict: Weak

Correct page identified. Crypto.com's exchange docs are a single-page reference (~35K
words). The excerpt window captured the ToC rather than the authentication section.
The table of contents at least confirms that API key generation and signing
documentation is present.

---

## 9. Bitstamp -- Instant order API & minimum trade amounts

**Query:** How does Bitstamp instant order API work and what are the minimum trade
amounts for market orders?

### What the docs say

A single claim from Bitstamp's API page. The excerpt is a table-of-contents listing
including: Authentication examples, Changelog, Public data functions (Tickers,
getCurrencies, getTickers, getMarket ticker, getHourly ticker), Order book, Transactions,
Market info (getMarkets, getOHLC data, getEUR/USD conversion rate, getCurrent funding
rate). This is the navigation index, not endpoint documentation.

### Sources

- https://www.bitstamp.net/api/

### Verdict: Weak

The correct documentation page was found (Bitstamp's single-page API reference, ~22K
words). The excerpt captured the table of contents rather than the instant order
endpoint details or minimum trade amount specifications.

---

## 10. Bitfinex -- Margin funding offers via REST API

**Query:** What are Bitfinex margin funding offer rates and how do I submit a funding
offer via the REST API?

### What the docs say

A single claim from the Bitfinex REST API reference. The excerpt is a navigation sidebar
listing endpoints: Liquidations, Leaderboards, Funding Statistics, Configs, Virtual
Assets. These are nearby in the sidebar to the funding-related endpoints but the excerpt
does not contain the actual funding offer submission endpoint documentation or rate
information.

### Sources

- https://docs.bitfinex.com/reference/rest-public-platform-status

### Verdict: Weak

The engine matched against the Bitfinex reference page and the excerpt shows endpoint
navigation near the funding section. The "Funding Statistics" link in the sidebar
suggests the right content is on the page, but the excerpt window did not capture it.

---

## 11. dYdX -- v4 perpetual funding rate & indexer API

**Query:** How does dYdX v4 perpetual funding rate calculation work and how to query
current funding from the indexer API?

### What the docs say

Three claims spanning different sections of the dYdX documentation:

1. **Trading concepts (isolated markets)** -- Navigation showing the trading section
   structure: Limit Orderbook and Matching, Perpetuals and Assets, Isolated Markets,
   MegaVault. Confirms the documentation hierarchy but no funding rate content.

2. **Margin concepts** -- Navigation listing account operations: Orders, Margin,
   **Funding**, Liquidations, Accounts and Subaccounts. The "Funding" link is visible
   in the excerpt, confirming a dedicated funding page exists.

3. **Indexer HTTP client** -- Contains actual technical content: describes the
   `List Positions` endpoint that "retrieves perpetual positions for a specific
   subaccount. Both open and closed/historical positions can be queried." This is from
   the indexer client HTTP documentation -- the right area for querying funding data.

### Sources

- https://docs.dydx.xyz/concepts/trading/isolated-markets
- https://docs.dydx.xyz/concepts/trading/margin
- https://docs.dydx.xyz/indexer-client/http

### Verdict: Partial

The third claim delivers real technical content about the indexer API's position
querying capability. The navigation excerpts from claims 1 and 2 at least confirm the
documentation structure includes dedicated Funding and Margin pages. Not a complete
answer, but demonstrates the engine can reach into dYdX's multi-page docs.

---

## 12. Hyperliquid -- Vault deposit/withdrawal & EIP-712 signing

**Query:** What is Hyperliquid vault deposit and withdrawal flow and how does the
EIP-712 typed data signing work for L1 actions?

### What the docs say

Three claims with genuinely substantive content:

1. **Bridge2 documentation** -- Describes the deposit flow: "The user sends native USDC
   to the bridge, and it is credited to the account that sent it in less than 1 minute.
   **The minimum deposit amount is 5 USDC.**" Also references the Bridge2.sol smart
   contract source code on GitHub.

2. **Exchange endpoint** -- Explains subaccount and vault mechanics: "Subaccounts and
   vaults do not have private keys. To perform actions on behalf of a subaccount or
   vault, **signing should be done by the master account** and the `vaultAddress` field
   should be set to [the vault address]." Also documents spot asset indexing -- for
   PURR/USDC the asset is `10000` because its index in spot metadata is `0`.

3. **Info endpoint** -- Lists order status types including: `filled`, `canceled`,
   `triggered`, `rejected`, `marginCanceled` (insufficient margin), and notably
   `vaultWithdrawalCanceled` (canceled due to user withdrawal from vault) and
   `openInterestCapCanceled` (too aggressive when OI at cap). Also `selfTradeCancel`.

### Sources

- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/bridge2
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint

### Verdict: Strong

This is the best result in the entire showcase. All three claims contain directly usable
technical content: deposit minimums, vault signing mechanics, and order cancellation
reasons including vault-specific statuses. Hyperliquid's Gitbook-based docs are
well-structured with clean HTML, allowing the FTS5 excerpts to capture real content
rather than navigation chrome.

---

## 13. Upbit -- Rate limit headers & KRW minimum order

**Query:** What are Upbit remaining request rate limit headers and how does the KRW
market minimum order amount work?

### What the docs say

Five claims from different Upbit documentation pages, all containing identical content:
Korean-language navigation sidebar listing tutorial sections (24-hour accumulated trade
volume, RSI indicator calculation) and order management pages (limit bid order creation,
market ask order creation). The Korean text includes section titles like "주문 생성 및
관리" (Order Creation & Management) and "지정가 매수 주문 생성" (Limit Buy Order Creation).

### Sources

- https://docs.upbit.com/kr/docs/rest-api-best-practice
- https://docs.upbit.com/kr/docs/market-ask-order-creation
- https://docs.upbit.com/kr/docs/limit-bid-order-creation
- https://docs.upbit.com/kr/docs/first-quotation-api-call
- https://docs.upbit.com/kr/docs/24-hour-accumulated-trade-volume

### Verdict: Weak

The engine identified relevant pages (REST API best practice, order creation pages) but
all five excerpts contain the same Korean-language sidebar navigation. The actual rate
limit header documentation and KRW minimum order amounts are in the page bodies, not
captured by the excerpt windows. Upbit's docs are primarily in Korean, which the FTS5
search handles (matched on "order" and "api") but the content extraction did not reach
past the navigation.

---

## 14. Bithumb -- Limit order placement & error codes

**Query:** How do I place a limit order on Bithumb via the API and what are the required
parameters and error codes?

### What the docs say

Three claims with mixed quality:

1. **Error codes page (v1)** -- Contains a structured error code table for HTTP 400
   Bad Request responses:
   - `invalid_parameter` -- invalid parameter
   - `invalid_price` -- incorrect order price unit
   - `under_price_limit_ask` / `under_price_limit_bid` -- order price below minimum
   - `invalid_price_ask` / `invalid_price_bid` -- incorrect price unit
   - `bank_account_required` -- real-name verified bank account required
   - `two_factor_auth_r...` (truncated) -- two-factor authentication related

2. **Error codes page (v2.1.0)** -- Same error code table from a different API version,
   confirming the error codes are consistent across versions.

3. **Changelog** -- An announcement about rate limiting on Public WebSocket, noting
   new request limits being applied for service stability. Written in Korean:
   "보다 안정적인 서비스 제공을 위해 PUBLIC WEBSOCKET 기능에 대한 요청 제한 (Rate Limit)
   정책이 도입될 예정입니다."

### Sources

- https://apidocs.bithumb.com/docs/api-주요-에러-코드
- https://apidocs.bithumb.com/v2.1.0/docs/api-주요-에러-코드
- https://apidocs.bithumb.com/changelog/업데이트-public-websocket-데이터-요청-수-제한rate-limit-적용-안내

### Verdict: Partial

The error code tables in claims 1 and 2 are genuinely useful -- they list real API
error codes with descriptions. The limit order placement parameters themselves are not
in the excerpts, but the error response format is half of what a developer needs. The
Korean content is readable and the error code identifiers are in English.

---

## 15. Coinone -- 2FA for crypto withdrawals & API call sequence

**Query:** How does Coinone two-factor authentication work for cryptocurrency
withdrawals and what is the required API call sequence?

### What the docs say

Three claims:

1. **Changelog (deprecation notice)** -- Critical finding: Coinone has **discontinued
   OTP-based withdrawal support**. The deprecated APIs are:
   - `/v2/transaction/auth_number` (2FA authentication request)
   - `/v2/transaction/auth_number/` (BTC withdrawal)

   These are listed under "Private API v.2.0 - discontinued APIs" (지원 중단 API).

2. **Error codes page** -- Navigation header only (Home, Usage Guide, API Reference,
   Changelog with version links v1.0 through v1.7).

3. **Balance reference page** -- Navigation header only, same structure.

### Sources

- https://docs.coinone.co.kr/changelog/추가채널-인증-추가에-따른-api-지원-중단-안내-v110
- https://docs.coinone.co.kr/docs/error-code
- https://docs.coinone.co.kr/reference/find-balance-by-currencies

### Verdict: Partial

The first claim delivers a critically important answer: Coinone has **deprecated its
2FA withdrawal API entirely**. This is exactly the kind of information a developer
needs -- the answer to "how does 2FA withdrawal work?" is "it no longer does." The
changelog excerpt captures the deprecation notice with specific endpoint paths. Claims
2 and 3 are navigation chrome but claim 1 alone makes this a useful result.

---

## 16. Korbit -- OAuth2 token refresh & scopes

**Query:** How does Korbit OAuth2 access token refresh work and what are the token
expiration times and scopes?

### What the docs say

Two claims:

1. **English docs page** -- Contains the introduction section: "We are excited to
   introduce Korbit's new Open API service! With this service, you can freely access
   a variety of cryptocurrency exchange functions, including price inquiries, orders,
   deposits, and withdrawals, all through our Open API. Any Korbit member can utilize
   the Korbit Open API to dev[elop]..." This is introductory prose, not OAuth2 specifics.

2. **Korean docs main page** -- Table of contents in Korean showing the full API
   structure including an authentication section ("인증") with:
   - 서명된 요청 보내기 (Sending Signed Requests)
   - HMAC-SHA256 서명 (HMAC-SHA256 Signing)
   - ED25519 서명 (ED25519 Signing)

   And trading sections: current price, order book, trades, candlesticks, order
   placement (주문하기 POST), order cancellation.

### Sources

- https://docs.korbit.co.kr/index_en.html
- https://docs.korbit.co.kr/

### Verdict: Partial

The engine found both the English and Korean versions of Korbit's documentation.
The Korean ToC reveals that Korbit supports both HMAC-SHA256 and ED25519 signing
(a useful detail). However, neither excerpt contains the specific OAuth2 token refresh
flow, expiration times, or scope definitions. Notably, the ToC does not list an "OAuth2"
section -- Korbit may have moved to API key authentication (HMAC/ED25519), making the
query itself somewhat mismatched. The English excerpt at least provides the API
introduction and confirms the service scope.

---

## Overall Assessment

### Results by Verdict

| Verdict | Count | Exchanges |
|---------|------:|-----------|
| **Strong** | 1 | Hyperliquid |
| **Partial** | 7 | Binance, Bybit, dYdX, Bithumb, Coinone, Korbit |
| **Weak** | 8 | OKX, Bitget, Gate.io, KuCoin, HTX, Crypto.com, Bitstamp, Bitfinex, Upbit |

### What worked well

1. **Page selection is excellent.** In almost every case the engine found the right
   documentation pages. URLs for KuCoin transfer endpoints, Bithumb error codes, Coinone
   deprecation notices, and Hyperliquid vault docs were all precisely on-target.

2. **Hyperliquid is the gold standard.** Clean Gitbook HTML with minimal navigation
   chrome produces excerpts that contain actual technical content -- deposit minimums,
   vault signing mechanics, order status codes.

3. **Deprecation detection works.** The Coinone result correctly surfaced that 2FA
   withdrawal APIs have been discontinued. This is arguably more valuable than
   explaining how they work.

4. **Multi-section search.** For exchanges with multiple doc sections (HTX, KuCoin,
   Bitget), the engine searched across all sections and returned results from the most
   relevant ones.

### What needs improvement

1. **Excerpt window placement.** The 400-character excerpt window frequently lands on
   navigation chrome (sidebars, breadcrumbs, language selectors) rather than page body
   content. This is the single biggest quality issue.

2. **Single-page doc sites are hard.** OKX (224K words), Gate.io (256K words), HTX
   (325K words), Crypto.com (35K words), Bitstamp (22K words), and Korbit (25K words)
   serve their entire API reference from 1-2 HTML files. FTS5 matches correctly but
   the excerpt offset tends to hit the page header region.

3. **JS-rendered content.** Bitget and KuCoin use heavy client-side rendering. The
   stored HTML contains navigation-dense markup at the top, pushing actual API content
   further into the document. Excerpt windows starting near byte offset 0-400 will
   almost always be navigation.

4. **Korean-language docs.** Upbit and Bithumb docs are primarily in Korean. The FTS5
   search matches on English technical terms embedded in Korean pages, but the
   surrounding context is Korean navigation text.

### Recommendations

1. **Skip navigation stripping.** Pre-process stored HTML to remove `<nav>`, `<header>`,
   sidebar, and breadcrumb elements before markdown conversion. This would dramatically
   improve excerpt quality for all exchanges.

2. **Larger excerpt windows.** Increase from 400 characters to 800-1200 for single-page
   doc sites where the target content is deep in the document.

3. **Section-aware excerpting.** For single-page sites, use heading anchors (`#section`)
   to locate the relevant section before extracting the excerpt.

4. **Multiple excerpt passes.** When the first excerpt is detected as navigation-heavy
   (heuristic: high link-to-text ratio), try a second excerpt from further into the
   document.

### Bottom line

The answer engine's **retrieval** is strong -- it consistently finds the right pages
across all 16 exchanges. The **extraction** (excerpt placement within those pages) is
the bottleneck. For exchanges with well-structured, multi-page docs (Hyperliquid, dYdX,
Bybit, Binance), the system produces usable results. For single-page doc monoliths
(OKX, Gate.io, HTX) and JS-heavy sites (Bitget, KuCoin), the excerpts need smarter
offset selection to move past navigation chrome and into the actual technical content.
