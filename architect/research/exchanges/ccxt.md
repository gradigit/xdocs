# CCXT — Deep Discovery

Reference library — unified API for 100+ cryptocurrency exchanges.

## Documentation Sites
- **Main docs**: https://docs.ccxt.com/ (primary)
- **ReadTheDocs**: https://ccxt.readthedocs.io/ (additional source, potentially stale)
- **Wiki**: https://github.com/ccxt/ccxt/wiki
- **Wiki source**: https://github.com/ccxt/ccxt/blob/master/wiki/ (raw Markdown)
- **Platform**: Custom (docs.ccxt.com) + GitHub Wiki + ReadTheDocs

## Versioned APIs
- **Current**: CCXT 4.x (major version)
- **Breaking changes**: Track via CHANGELOG.md and releases

## Changelogs & Updates
- **Changelog**: https://github.com/ccxt/ccxt/blob/master/CHANGELOG.md
- **Releases**: https://github.com/ccxt/ccxt/releases
- **RSS**: https://github.com/ccxt/ccxt/releases.atom
- **Frequency**: Very active — near-daily releases

## GitHub
- **Org**: https://github.com/ccxt
- **Main repo**: https://github.com/ccxt/ccxt (33K+ stars)
- **Exchange implementations**: ts/src/{exchange}.ts (TypeScript, primary), python/ccxt/{exchange}.py (auto-generated)
- **Abstract API surface**: ts/src/abstract/{exchange}.ts (auto-generated, contains all endpoint mappings)
- **Exchange metadata**: exchanges.json (master list with URLs, API versions, capabilities)
- **Commit feeds**: https://github.com/ccxt/ccxt/commits.atom

## Key Files for Our Use Case
- **exchanges.json**: Master exchange registry with API URLs, capabilities, has-flags
- **ts/src/{exchange}.ts**: describe() method maps every endpoint; contains rate limits, error codes, quirks
- **ts/src/abstract/{exchange}.ts**: Auto-generated API surface (all REST paths)
- **wiki/**: Documentation in Markdown (already synced — 188 pages in store)

## Cross-Reference Status
- **ccxt_xref.py**: Maps 20/21 CEXes (korbit has no CCXT class, mercadobitcoin remaps to `mercado`)
- **Bug**: `_extract_ccxt_endpoints()` only handles list-based API trees, not dict-of-dicts (affects 15/20 exchanges)
- **Fix needed**: Support dict-of-dicts format in extraction to get meaningful xref data

## Action Items
- [ ] Fix dict-of-dicts extraction bug in ccxt_xref.py — blocks meaningful cross-reference for 15/20 exchanges
- [ ] ccxt.readthedocs.io — check freshness vs docs.ccxt.com, add if different content
- [ ] exchanges.json — mine for API version metadata and capability flags
- [ ] Monitor releases.atom for breaking changes affecting our exchange mappings
