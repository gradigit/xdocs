# Evaluation Scenarios — cex-api-query

## Scenario 1: Happy Path — Endpoint Lookup

**Input:** "What endpoint do I use to place a spot limit order on Binance?"

**Expected behavior:**
1. Agent runs `search-endpoints "place order" --exchange binance`
2. Finds `POST /api/v3/order` or similar
3. Gets full endpoint JSON — extracts parameters (symbol, side, type, price, quantity, timeInForce)
4. Reads the doc page for additional rules (e.g., LIMIT orders require timeInForce)
5. Presents: method, path, base_url, parameters table, key rules, source URL

**Success criteria:**
- Correct endpoint identified (POST /api/v3/order)
- Parameters listed with types and required flags
- At least one usage rule from the docs (e.g., timeInForce required for LIMIT)
- Source URL provided
- No hallucinated information

## Scenario 2: Edge Case — Single-Page Doc Site

**Input:** "How does OKX API request signing work? What headers do I need?"

**Expected behavior:**
1. Agent runs `search-pages "OKX sign request header"` or similar
2. Finds the OKX main docs page (single 292K-word page)
3. Does NOT try to print/read the entire page
4. Uses Grep to locate the authentication section within the file
5. Reads a targeted section (~100-200 lines) around the auth heading
6. Extracts: required headers (OK-ACCESS-KEY, OK-ACCESS-SIGN, OK-ACCESS-TIMESTAMP, OK-ACCESS-PASSPHRASE), signing procedure (HMAC-SHA256)
7. Presents the auth flow with source URL

**Success criteria:**
- Agent handles the large single-page doc without flooding context
- Authentication headers correctly identified
- Signing procedure described (not just header names)
- Source URL provided
- Agent does NOT say "not found" — the info IS in the store, just buried in a large page

## Scenario 3: Not Found — Exchange Missing or Topic Not Covered

**Input:** "What are the Kraken API rate limits?"

**Expected behavior:**
1. Agent runs `search-endpoints "rate limit" --exchange kraken` — no results
2. Agent runs `search-pages "Kraken rate limit"` — no results
3. Agent tells the user: Kraken is not in the store
4. Agent lists which exchanges ARE available

**Success criteria:**
- Agent does NOT hallucinate Kraken rate limits
- Agent clearly states Kraken is not in the store
- Agent provides the list of available exchanges
- Agent stops after 2-3 failed searches (doesn't keep trying variations endlessly)
