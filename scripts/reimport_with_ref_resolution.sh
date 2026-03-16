#!/usr/bin/env bash
# Re-import all OpenAPI specs to resolve $ref pointers.
# The $ref resolver was added in commit f82f018.
# This replaces 2,213 endpoints with unresolved $ref schemas.
set -euo pipefail

DOCS_DIR="${DOCS_DIR:-./cex-docs}"
CMD="xdocs import-openapi --docs-dir $DOCS_DIR --continue-on-error"
TOTAL=0
FAILED=0

reimport() {
    local exchange="$1" section="$2" url="$3" base_url="${4:-}"
    echo ">>> $exchange/$section: $url"
    local extra=""
    if [ -n "$base_url" ]; then
        extra="--base-url $base_url"
    fi
    if $CMD --exchange "$exchange" --section "$section" --url "$url" $extra > /dev/null 2>&1; then
        echo "    OK"
        TOTAL=$((TOTAL + 1))
    else
        echo "    FAILED"
        FAILED=$((FAILED + 1))
    fi
}

# Binance
reimport binance spot "https://raw.githubusercontent.com/binance/binance-api-swagger/master/spot_api.yaml" ""
reimport binance futures_usdm "https://raw.githubusercontent.com/openxapi/openxapi/main/specs/binance/openapi/umfutures.yaml" ""
reimport binance futures_coinm "https://raw.githubusercontent.com/openxapi/openxapi/main/specs/binance/openapi/cmfutures.yaml" ""
reimport binance options "https://raw.githubusercontent.com/openxapi/openxapi/main/specs/binance/openapi/options.yaml" ""
reimport binance portfolio_margin "https://raw.githubusercontent.com/openxapi/openxapi/main/specs/binance/openapi/pmargin.yaml" ""

# OKX
reimport okx rest "https://raw.githubusercontent.com/openxapi/openxapi/main/specs/okx/openapi/rest.yaml" ""

# Orderly
reimport orderly docs "https://raw.githubusercontent.com/OrderlyNetwork/documentation-public/main/evm.openapi.yaml" "https://api.orderly.org"

# Deribit
reimport deribit api "https://docs.deribit.com/specifications/deribit_openapi.json" ""

# WhiteBIT (6 specs)
reimport whitebit v4 "https://docs.whitebit.com/openapi/public/http-v4.yaml" ""
reimport whitebit v4 "https://docs.whitebit.com/openapi/public/http-v2.yaml" ""
reimport whitebit v4 "https://docs.whitebit.com/openapi/public/http-v1.yaml" ""
reimport whitebit v4 "https://docs.whitebit.com/openapi/private/main_api_v4.yaml" ""
reimport whitebit v4 "https://docs.whitebit.com/openapi/private/http-trade-v4.yaml" ""
reimport whitebit v4 "https://docs.whitebit.com/openapi/private/http-trade-v1.yaml" ""

# Coinbase
reimport coinbase prime "https://api.prime.coinbase.com/v1/openapi.yaml" ""
reimport coinbase exchange "https://raw.githubusercontent.com/metalocal/coinbase-exchange-api/main/api.oas3.json" ""
reimport coinbase intx "https://docs.cdp.coinbase.com/derivatives/downloads/cde-public-api-spec.json" ""

# BitMEX
reimport bitmex rest "https://raw.githubusercontent.com/BitMEX/api-connectors/master/swagger.json" ""

# Paradex
reimport paradex api "https://api.prod.paradex.trade/swagger/doc.json" "https://api.prod.paradex.trade/v1"

# Bitget
reimport bitget v2 "https://raw.githubusercontent.com/kanekoshoyu/exchange-collection/main/asset/bitget_rest_openapi.yaml" "https://api.bitget.com/api/v2"

# Backpack
reimport backpack api "https://raw.githubusercontent.com/CKS-Systems/backpack-client/main/openapi.json" "https://api.backpack.exchange"

# dYdX
reimport dydx docs "https://raw.githubusercontent.com/dydxprotocol/v4-chain/main/indexer/services/comlink/public/swagger.json" "https://indexer.dydx.trade/v4"

# Lighter
reimport lighter docs "https://raw.githubusercontent.com/elliottech/lighter-python/main/openapi.json" "https://api.lighter.xyz"

# Kraken
reimport kraken spot "https://raw.githubusercontent.com/Roukii/kraken-go/master/openapi/kraken.openapi.json" ""

# MercadoBitcoin
reimport mercadobitcoin v4 "https://api.mercadobitcoin.net/api/v4/docs/swagger.yaml" ""

# Bitstamp — skipped (spec was from localhost)

echo ""
echo "Done: $TOTAL succeeded, $FAILED failed"
