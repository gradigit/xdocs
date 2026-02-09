# Binance Wow Query Runbook (Cite-Only Demo)

Goal: reproduce the MVP wow query end-to-end using only locally stored sources and cite-only output.

Query:

> What’s the rate limit difference between Binance unified trading endpoint and the Binance spot endpoint? And in order to look up the balance of our Binance subaccount in Portfolio Margin mode, what permissions does the API key need?

## 1) Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cex-api-docs init --docs-dir ./cex-docs
```

## 2) Crawl Binance Docs (Spot + Portfolio Margin)

```bash
cex-api-docs crawl --exchange binance --section spot --docs-dir ./cex-docs
cex-api-docs crawl --exchange binance --section portfolio_margin --docs-dir ./cex-docs
```

If the user’s meaning of “unified trading” requires additional sections, crawl them only after clarification.

## 3) Locate Sources (Rate Limits + Permissions)

```bash
cex-api-docs search-pages --query "rate limit" --docs-dir ./cex-docs
cex-api-docs search-pages --query "portfolio margin" --docs-dir ./cex-docs
cex-api-docs search-pages --query "API key permission" --docs-dir ./cex-docs
```

## 4) Agent Extraction (Endpoint JSON)

The agent reads the stored pages and produces endpoint JSON records matching:
- `schemas/endpoint.schema.json`

Critical:
- For `required_permissions`, `rate_limit`, `error_codes`, include citations with verbatim excerpts and offsets.
- If docs do not explicitly state required permissions, set `undocumented` for that field and enqueue review via the ingest path.

## 5) Ingest Endpoints

```bash
cex-api-docs save-endpoint --file ./endpoint.json --docs-dir ./cex-docs
```

## 6) Produce Cite-Only Answer

```bash
cex-api-docs answer --question "<wow query text>" --docs-dir ./cex-docs
```

Expected behavior:
- Returns `needs_clarification` for “unified trading endpoint” unless a specific Binance section is stated.
- After clarification, returns cite-only claims.
- Any numeric “difference” is `[DERIVED]` and links to cited input claims.
- Missing facts return `unknown` / `undocumented` / `conflict` with citations to what was searched.

