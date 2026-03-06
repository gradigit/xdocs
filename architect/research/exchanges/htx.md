# HTX (ex-Huobi) — Deep Discovery

## Documentation Sites
- **Legacy docs**: https://huobiapi.github.io/docs/spot/v1/en/ (GitHub Pages, still primary for content)
- **New portal**: https://www.htx.com/en-us/opend/newApiPages/ (custom portal)
- **WebSocket docs**: Embedded in each section (huobiapi.github.io/docs/spot/v1/en/#websocket-reference)
- **FIX**: https://github.com/huobiapi/huobi_fix
- **Platform**: GitHub Pages (legacy) + Custom portal (new)

## Versioned APIs
- **Current**: v1 (spot), v1 (derivatives)
- **Derivatives sections**: /docs/dm/v1/en/ (derivatives), /docs/coin_margined_swap/v1/en/, /docs/usdt_swap/v1/en/

## Changelogs & Updates
- **Changelog**: https://www.htx.com/en-us/opend/newApiPages/ (Updates section)
- **RSS**: None
- **Frequency**: Active (new portal updates visible)

## GitHub
- **Account**: https://github.com/huobiapi (user account, NOT an org — org endpoint 404s)
- **SDK org**: https://github.com/HuobiRDCenter
- **SDKs**: huobi_Python, huobi_Java, huobi_Golang, huobi_Cpp, huobi_CSharp + contract variants
- **Postman scripts**: HuobiRDCenter/Postman_PreRequest_Scripts (last updated 2020, stale)
- **Commit feed**: https://github.com/huobiapi/docs/commits.atom

## Specs & Collections
- **OpenAPI**: None found
- **Postman**: Pre-request scripts only (2020, stale)

## Discovery Files
- **Note**: GitHub Pages serves single-page docs per section; no sitemap needed

## CCXT
- **ID**: `htx`

## Status & Incidents
- **Status page**: https://status.huobigroup.com
- **API**: https://status.huobigroup.com/api/v2/summary.json, /api/v2/incidents.json, /api/v2/status.json

## Action Items
- [ ] New portal (htx.com/en-us/opend/) — evaluate if it replaces or supplements legacy GitHub Pages
- [ ] Dual-system docs (legacy vs new) may have content inconsistencies
- [ ] Base URLs still reference huobi.pro (spot) and hbdm.com (futures) domains
