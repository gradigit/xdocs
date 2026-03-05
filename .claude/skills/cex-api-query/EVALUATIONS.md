# Evaluation Scenarios — cex-api-query

## Scenario 1: Happy Path — Endpoint Lookup

**Input:** "What endpoint do I use to place a spot limit order on Binance?"

**Expected behavior:**
1. Agent runs `semantic-search "place spot limit order params timeInForce" --exchange binance --mode hybrid --rerank-policy auto`
2. Finds `POST /api/v3/order` or similar
3. Gets full endpoint JSON — extracts parameters (symbol, side, type, price, quantity, timeInForce)
4. Reads the doc page for additional rules (e.g., LIMIT orders require timeInForce)
5. Presents: method, path, base_url, parameters table, key rules, source URL

**Success criteria:**
- Correct endpoint identified (POST /api/v3/order)
- Parameters listed with types and required flags
- At least one usage rule from the docs (e.g., timeInForce required for LIMIT)
- Source URL provided as OSC-8 hyperlink (full URL destination)
- Retrieval audit includes `search_mode=semantic/hybrid`, `rerank_policy`, `rerank_applied`, and `rerank_reason`
- No hallucinated information

## Scenario 2: Edge Case — Single-Page Doc Site

**Input:** "How does OKX API request signing work? What headers do I need?"

**Expected behavior:**
1. Agent runs `semantic-search "OKX sign request header HMAC timestamp passphrase" --exchange okx --mode hybrid --rerank-policy auto`
2. Finds the OKX main docs page (single 292K-word page)
3. Does NOT try to print/read the entire page
4. Uses `get-page` for the winning URL and only then targeted Grep within that one markdown file
5. Reads a targeted section (~100-200 lines) around auth heading
6. Extracts: required headers (OK-ACCESS-KEY, OK-ACCESS-SIGN, OK-ACCESS-TIMESTAMP, OK-ACCESS-PASSPHRASE), signing procedure (HMAC-SHA256)
7. Presents the auth flow with source URL

**Success criteria:**
- Agent handles the large single-page doc without flooding context
- Authentication headers correctly identified
- Signing procedure described (not just header names)
- Source URL provided as OSC-8 hyperlink (full URL destination)
- Retrieval audit shows raw scan was bounded and targeted
- Agent does NOT say "not found" — the info IS in the store, just buried in a large page

## Scenario 3: Not Found — Exchange Missing or Topic Not Covered

**Input:** "What are the Kraken API rate limits?"

**Expected behavior:**
1. Agent runs `semantic-search "Kraken rate limit private API" --exchange kraken --mode hybrid --rerank-policy auto` — no results
2. Agent runs one bounded fallback (`search-endpoints` or `search-pages`) — no results
3. Agent tells the user: Kraken is not in the store
4. Agent lists which exchanges ARE available

**Success criteria:**
- Agent does NOT hallucinate Kraken rate limits
- Agent clearly states Kraken is not in the store
- Agent provides the list of available exchanges
- Agent stops after 2-3 failed searches (doesn't keep trying variations endlessly)
- Retrieval audit explicitly shows fallback attempts

## Scenario 4: Stress — Cross-Exchange Comparison with Strict Citations

**Input:**  
"I need least-privilege subaccount balance endpoints across Binance/OKX/Bybit/Bitget/Upbit/Bithumb with auth, permissions, rate limits, failure codes, conflict audit, and rollout recommendation."

**Expected behavior:**
1. Agent gathers evidence per exchange via `semantic-search --mode hybrid --rerank-policy auto`, then validates with targeted endpoint/page fetch.
2. Agent outputs a comparison table with citation IDs per material cell (or `unknown`/`undocumented`/`conflict`).
3. Agent outputs a Citation Ledger mapping each ID to source URL and evidence note.
4. Any unresolved/ambiguous field is fail-closed (`unknown`/`undocumented`) instead of inferred.

**Success criteria:**
- Every non-trivial table cell has citation ID(s) OR explicit `unknown`/`undocumented`/`conflict`.
- Conflict audit cites both conflicting sources explicitly.
- No unsupported claims in permission/rate-limit/auth/error columns.
- Source URLs are rendered as OSC-8 hyperlinks with full URL destinations.
- Retrieval audit confirms semantic/hybrid retrieval and auto-rerank decision.

## Scenario 5: Ambiguous Multi-Exchange Query Routing

**Input:**  
"For account balances, what’s the private endpoint and auth header format for Binance, OKX, and Bybit?"

**Expected behavior:**
1. Agent runs semantic-first retrieval for each requested exchange (bounded calls).
2. Agent avoids conflating similarly named endpoints across exchanges.
3. Agent outputs exchange-separated rows with claim-level citations and explicit unknowns where fields are missing.

**Success criteria:**
- No cross-exchange field leakage (e.g., Binance header names shown for OKX).
- Every exchange row has endpoint + auth evidence citation(s).
- Source URLs are OSC-8 full-destination links.
- Retrieval audit shows bounded semantic/fallback counts.

## Scenario 6: Error-Code Remediation Path

**Input:**  
"Binance returns `-1002` for Convert quote. What should I check and how do I fix it?"

**Expected behavior:**
1. Agent classifies input as `error_message`.
2. Agent runs `search-error -- -1002 --exchange binance`, then targeted endpoint/page fetch.
3. Agent provides remediation checklist (permission toggles, questionnaire/access gating, key validation steps), each with citation.

**Success criteria:**
- Error meaning/remediation steps are directly supported by cited docs.
- If remediation detail is missing, answer uses `unknown`/`undocumented` rather than guessing.
- Output includes Source Docs OSC-8 links and retrieval audit block.
