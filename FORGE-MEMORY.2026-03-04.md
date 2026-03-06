# Forge Memory

Cross-session learnings. Minimum-signal gate: "Will a future agent act better knowing this?"
Keep under 3,000 tokens via aggressive deduplication.

## Architectural Decisions
- [2026-03-04] Qwen3-Embedding-0.6B selected over 4B — benchmark showed no meaningful quality difference on our API docs corpus (64% vs 64% no-rerank). 0.6B is 6x faster query, 3x faster build, doesn't cause swap pressure on 24GB Mac.
- [2026-03-04] Chunk size stays at 512 tokens — API endpoint descriptions are typically 200-500 tokens, 512 keeps one chunk ≈ one endpoint for cite-only provenance.
- [2026-03-04] Batch size increase to 128 — no quality impact, ~1.3x throughput gain.
- [2026-03-04] Heading context injection: prepend `[Page Title > Section Heading]` to chunk text before embedding. Disambiguates chunks from sibling pages across exchange sections.

## Failed Approaches
- [2026-03-04] Qwen3-4B full build on 24GB Mac → swap death spiral after 13+ hours at 60%. MLX memory-mapped weights + stale Playwright/Claude sessions exhausted RAM. Don't attempt full 4B builds without closing all other processes first.

## Patterns Learned
- [2026-03-04] Golden QA exact URL matching is too strict for multi-section exchanges. Binance has 15+ pages about "balance" across spot/wallet/derivatives/pay. Need prefix and domain matching alongside exact.
- [2026-03-04] Most "retrieval misses" are right-exchange-wrong-page (16/17 in benchmark). The retrieval pipeline finds relevant content but from sibling pages. Root cause: chunks lose page-level heading context → fixed with heading context injection.
- [2026-03-04] Crypto.com exchange ID in `_DOMAIN_MAP` must be `cryptocom` (not `crypto_com`) — must match registry `exchanges.yaml`. Mismatch causes exchange filter to find zero results.
- [2026-03-04] `_norm()` URL normalization: split fragment FIRST, then strip trailing slash. Reversed order leaves slash on URLs like `https://a.com/p/#s`.
- [2026-03-04] Percent-encoded URLs (Korean characters like `%EC%9D%B8%EC%A6%9D`) must be decoded with `unquote()` before comparison. Bithumb's golden QA URLs needed this fix.
