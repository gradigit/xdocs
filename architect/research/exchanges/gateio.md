# Gate.io — Deep Discovery

## Documentation Sites
- **Main docs**: https://www.gate.com/docs/developers/apiv4/ (single-page, 256K words, Swagger-rendered)
- **WebSocket docs**: https://www.gate.com/docs/developers/apiv4/ws/en/
- **FIX protocol**: None
- **Developer portal**: https://www.gate.com/gate-api (landing page)
- **Platform**: Custom (Swagger UI-based, OpenAPI-generated)

## Versioned APIs
- **Current**: APIv4 (v4.106.32 as of 2026-03-05)
- **Legacy**: APIv2 at gate.com/api2 (parallel, older)
- **Deprecation notices**: Embedded in announcements

## Changelogs & Updates
- **Changelog**: Embedded in docs page; announcements at https://www.gate.com/announcements/apiupdates
- **Format**: Version-tagged entries (v4.106.32, etc.) with model/endpoint changes
- **RSS/Atom feed**: None
- **Frequency**: Very frequent — multiple releases/week (12 PyPI releases in Jan-Feb 2026)
- **Telegram**: Gate_API_Announcements, Gate_API

## GitHub
- **Org**: https://github.com/gateio (15 repos, org name "gateio" not "gate")
- **Docs repo**: https://github.com/gateio/rest-v4 (README only, v4.22.0 overview)
- **OpenAPI spec**: NOT publicly hosted — internal to SDK generation pipeline. All probed URLs returned 404/403.
- **SDKs**: gateapi-{python,go,java,csharp,php,js,nodejs} (all auto-generated from OpenAPI spec)
- **SDK versioning**: Python v7.2.26 on PyPI (Feb 2026)
- **Other repos**: rest-v2, gatews, proof-of-reserves, WebSocket-API
- **Commit feed**: https://github.com/gateio/gateapi-python/commits/master.atom

## Specs & Collections
- **OpenAPI**: Architecture is OpenAPI-first (all SDKs auto-generated), but raw spec file is NOT publicly downloadable
- **Postman**: None
- **GraphQL**: None

## Discovery Files
- **robots.txt**: Blocks /data/, /admin/, /api/, /dashboard/; allows Twitterbot full access; sitemap at gate.com/sitemap.xml
- **sitemap.xml**: https://www.gate.com/sitemap.xml
- **Hidden paths**: gate.com/api2 (legacy APIv2); separate WebSocket at /apiv4/ws/en/

## CCXT
- **ID**: `gateio`

## Status & Incidents
- **Status page**: None (only unofficial monitoring)
- **API**: None found

## Action Items
- [ ] OpenAPI spec extraction — could potentially extract from auto-generated SDK repos (spec embedded in generated code comments?)
- [ ] gate.com/api2 legacy docs — assess if worth crawling for completeness
- [ ] Rate-limiting: 403 after sync — documented gotcha, needs longer delays or --render auto
