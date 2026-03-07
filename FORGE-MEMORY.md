# Forge Memory

Cross-session learnings. Minimum-signal gate: "Will a future agent act better knowing this?"
Keep under 3,000 tokens via aggressive deduplication.

## Architectural Decisions
- [2026-03-06] CCXT describe() data is cross-reference only — cite-only constraint prevents generating synthetic docs. Use ccxt_xref.py for validation, not doc generation.
- [2026-03-06] Single-page doc sites are correct behavior, not bugs: OKX (224K words), Gate.io (256K), HTX (325K across 4), BitMart (38K+34K), Crypto.com (35K), Bitstamp (22K), Korbit (25K).
- [2026-03-06] KuCoin uses opaque URL IDs (/docs-new/338210m0) — can't separate spot/futures by URL path. Merged into one section.

## Failed Approaches
- [2026-03-06] Generic crawl target prompt assumed 12 exchanges and suggested impractical sources (Discord, Wayback, forums, Google cache). These don't work for a deterministic crawl pipeline.

## Patterns Learned
- [2026-03-06] Scope_prefixes are critical for exchanges sharing one sitemap (Binance 9 sections, Coinbase 4 sections, Bitget 5 sections). Without them, URLs get claimed by the first section and skipped by the rest.
- [2026-03-06] render_mode: auto needed for JS-heavy doc sites (Coinbase, BitMart, most DEXes). Without it, link-follow only finds the seed page.
- [2026-03-06] 29 of 61 sections have 0 structured endpoints — potential OpenAPI/Postman import targets.
- [2026-03-06] CCXT describe() paths are relative to urls.api base, not absolute. Our DB stores full paths. Suffix-based matching (stripping /api/vN/ prefixes) is needed for cross-reference.
- [2026-03-06] Postman imports store {{url}}/{{host}} variable prefixes in endpoint paths. _normalize_path must strip all {{...}} patterns, not just {{url}}.
- [2026-03-06] NodePlaywrightFetcher.__init__ doesn't validate Node.js availability — cascade must call _find_node_pw_module() at selection time.
- [2026-03-06] revalidated_unchanged check in inventory_fetch.py short-circuits Playwright fallback — empty pages with matching hash won't get re-rendered.
- [2026-03-06] crawl4ai IS Playwright (hard dependency). cloudscraper can't render JS. No lightweight JS rendering alternative exists.
- [2026-03-06] LanceDB compaction: `compact_files()` + deprecated `cleanup_old_versions()` doesn't reduce fragments. Use `table.optimize(cleanup_older_than=timedelta(days=0))` instead — combines compact + prune + index optimize in one call. Reduced 3,568 → 9 fragments, 2.4GB → 908MB.
