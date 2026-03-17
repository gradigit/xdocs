# Suggestions

## New
<!-- Agent writes suggestions here. Human approves/rejects. -->

### [2026-03-09] ~~CRITICAL: Fix 3 answer pipeline bugs~~ FIXED
Fixed in this session. code_snippet MRR: 0.224→0.332 (+48%), nDCG@5: 1.322→1.335 (+1%).

### [2026-03-09] ~~Position-aware blend no-op~~ FIXED
Fixed: `retrieval_score_key="score"` passed in semantic.py. Was a no-op due to key mismatch.

### [2026-03-09] ~~HIGH: Code-syntax stopwords for code_snippet queries~~ IMPLEMENTED (M22 Step 4)
Implemented: ~40 CODE_STOPWORDS in fts_util.py. A/B: +18.1% code_snippet MRR, +28.6% code_snippet PFX. FTS+vector switch deferred (stopwords alone exceeded target).

### [2026-03-09] ~~HIGH: Operation-type inference for request payloads~~ IMPLEMENTED (M22 Step 5)
Implemented: 14-pattern `_PAYLOAD_ACTION_MAP` in answer.py. A/B: +14.1% payload PFX, +9.2% nDCG. Exchange signature expansion (8→16+) deferred.

### [2026-03-09] MEDIUM: Improved docs_url resolution (est +10-15% endpoint_path prefix hit)
**Source**: Query quality deep research, live traces
**Confidence**: high

4 of 10 endpoint_path misses are docs_url pointing to wrong page (FAQ, changelog, wrong operation). Fix: use HTTP method + description for disambiguation, extend changelog filter to FAQs, add fuzzy path matching with version-stripped suffix matching.

### [2026-03-09] LOW: Expand synonym map with API domain terms
**Source**: Query optimization research
**Confidence**: medium

Missing: futures/perpetual/perp/contract, leverage/margin, spot/cash, sandbox/testnet. Each addition needs validation against eval set.

### [2026-03-09] LOW: Deterministic PRF for question queries (est +3-5% MRR)
**Source**: Query quality deep research, academic references
**Confidence**: medium

Extract top TF-IDF terms from BM25 top-3 when matches are weak (`bm25_score < 0.5`), expand query, re-run FTS5. Addresses vocabulary mismatch without LLM. ~50ms/query cost.

### [2026-03-09] LOW: Run end-to-end reranker A/B test
**Source**: Reranker impact analysis
**Confidence**: medium

No pipeline-level comparison exists. Jina v3 +15.6% MRR in isolated benchmark; 57% of queries reach reranker, controlling 65% of final ranking for questions.

### [2026-03-09] LOW: Paradex URL drift — site restructured
**Source**: Spot check agent
**Confidence**: high

Paradex docs moved from `/docs/...` to `/releases/`, `/trading/`, etc. Stored URLs now 404. Need registry update + re-sync to capture new URL structure and 2 new releases.

### [2026-03-09] INFO: Content quality gaps
**Source**: Content analysis
- dYdX: 65% thin pages (183/283) — likely CSR issue
- Kraken futures: 49 pages averaging 487 words, almost all navigation links — Docusaurus CSR
- Bluefin: 26% thin (login-gated ReadMe.io pages)
- FlashRank provides zero benefit over CrossEncoder at 9x latency — consider removing from cascade

### [2026-03-10] ~~HIGH: RRF weight retuning after A/B test~~ FIXED
Post-hoc A/B test revealed endpoint_path [1.5,0.5] was net negative. Fixed: [0.7,1.3] (+5.2% endpoint_path MRR). Code_snippet removed from BM25 shortcut (+3.5% MRR). Combined: MRR 0.6199→0.6308 (+1.8%).

### [2026-03-10] MEDIUM: Score-aware linear fusion replacing RRF (est +3-5% nDCG)
**Source**: Web research (TopK benchmark, Elastic blog), architect/research/score-fusion.md
**Confidence**: high

TopK benchmark: score-aware linear fusion with MinMax normalization beats RRF by 4.58% nDCG@10 on BEIR. Pipeline already has per-type weights and 200 labeled queries. Migration: ~30 lines replacing rrf_fuse() with linear_fuse(). Key: preserves score magnitude information that RRF discards.

### [2026-03-10] ~~MEDIUM: Separate FTS query from semantic query~~ REJECTED (M22 Step 7)
A/B tested: stripping AND/OR from vector queries → -3.5% question MRR, -3.7% error_message PFX. AND tokens help focus embeddings. Do NOT implement.

### [2026-03-10] ~~MEDIUM: Lower auto-rerank threshold~~ IMPLEMENTED (M22 Step 1)
Lowered `_AUTO_RERANK_MIN_CANDIDATES` from 12 to 6. A/B: neutral (0% change). Kept as theoretically correct.

### [2026-03-10] LOW: Benchmark GTE-ModernBERT-base as code_snippet reranker
**Source**: Web research (HuggingFace model card, CoIR benchmark)
**Confidence**: medium

GTE-reranker-modernbert-base (149M, BEIR 56.73, CoIR 79.99) may outperform Jina v3 specifically for code-related queries. Trivial integration: `CrossEncoder("Alibaba-NLP/gte-reranker-modernbert-base")`. Pipeline A/B test on golden QA needed.

### [2026-03-10] ~~LOW: Add parameter names to endpoint FTS search_text~~ REJECTED (M22 Step 6)
A/B tested: adding param names to endpoint FTS search_text → -12.6% request_payload MRR. Common params (symbol, side, type) reduce BM25 discriminative power. Needs selective approach (discriminative params only), not blanket inclusion.

### [2026-03-10] LOW: Expand _PAYLOAD_EXCHANGE_SIGNATURES (8 → 16+ exchanges)
**Source**: Codebase analysis (Finding 9)
**Confidence**: high

Only 8/46 exchanges have payload signatures. Missing: deribit (instrument_name), coinbase (product_id + order_configuration), orderly (order_type + broker_id), mexc (mirrors binance), bitfinex, etc. Each addition improves exchange detection for request_payload queries.

## Approved
<!-- Move approved items here. Agent adds to milestones. -->

## Rejected
<!-- Move rejected items here with reason. -->
