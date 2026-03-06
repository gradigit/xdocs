# QMD Codebase Analysis

Source: github.com/tobi/qmd (cloned and fully read, 9,722 lines TypeScript)
Author: Tobi Lutke (Shopify CEO)

## Architecture Overview

~10K-line TypeScript app. 8 core files:
- `store.ts` (3,391 lines) — schema, chunking, RRF fusion, hybrid query
- `llm.ts` (1,420 lines) — embedding, reranking, query expansion via node-llama-cpp
- `qmd.ts` (2,900 lines) — CLI entry point
- `mcp.ts` (738 lines) — MCP server with structured search API
- `collections.ts` (450 lines) — YAML config
- `formatter.ts` (429 lines) — output formatting
- `db.ts` (54 lines) — SQLite compatibility layer

## Three-Model Architecture

| Model | Purpose | Size | Format |
|-------|---------|------|--------|
| embeddinggemma-300M-Q8_0 | Embeddings | ~300MB | GGUF |
| qwen3-reranker-0.6b-q8_0 | Cross-encoder reranking | ~640MB | GGUF |
| qmd-query-expansion-1.7B-q4_k_m | Query expansion (fine-tuned) | ~1.1GB | GGUF |

## Key Design Decisions

### 1. Single SQLite DB (FTS5 + sqlite-vec)
No LanceDB — vectors stored in same DB via sqlite-vec extension. Simpler than our dual-DB approach. Known sqlite-vec bug: virtual tables hang on JOINs, requires two-step queries.

### 2. Scored Break-Point Chunking (900 tokens, 15% overlap)
Scan document for break points with base scores (H1:100, H2:90, code fence:80, blank line:20, list item:5, line break:1). At the 900-token target, search 200-token window with squared distance decay:
```
finalScore = baseScore * (1 - (distance/window)^2 * 0.7)
```
Code fences protected from splitting. Two-pass tokenization (estimate then validate).

### 3. Hybrid Query Pipeline (8 steps)
1. BM25 probe — if top score >= 0.85 with gap >= 0.15, skip expansion
2. Query expansion — typed variants: `lex` (BM25), `vec` (semantic), `hyde` (hypothetical doc)
3. Type-routed search — lex→FTS5, vec/hyde→sqlite-vec
4. RRF fusion — k=60, original query 2x weight, top-rank bonus (+0.05 for #1, +0.02 for #2-3)
5. Chunk selection — pick chunk with most keyword overlap for each candidate
6. LLM reranking — Qwen3-Reranker scores each chunk
7. Position-aware blending — rank 1-3: 75% RRF / 25% reranker; rank 4-10: 60/40; rank 11+: 40/60
8. Dedup and filter

### 4. BM25 Score Normalization
```
score = |x| / (1 + |x|)
```
Maps: strong(-10)→0.91, medium(-2)→0.67, weak(-0.5)→0.33, none(0)→0. Monotonic, bounded [0,1), no parameters.

### 5. MCP Structured Search API
Lets capable LLMs (Claude, GPT-4) bypass local query expansion by submitting pre-typed sub-queries directly. Elegant — recognizes LLMs generate better query variations than a 1.7B model.

### 6. FTS5 Tokenizer
Uses `porter unicode61` — stemming enabled. Query strategy: exact phrase OR NEAR proximity OR individual OR terms.

### 7. Content-Addressable Storage
SHA-256 hashes for deduplication. Identical content shares storage and embeddings.

### 8. LLM Resource Lifecycle
Models stay loaded, contexts disposed after 5 min inactivity. Reranker context uses 2048 tokens with flash attention (20x VRAM reduction from 11.6GB to 568MB).

## Lessons for cex-api-docs

### Adopt
- **Qwen3-Reranker-0.6B in GGUF** — runs on CPU via llama-cpp-python, ~640MB, great quality
- **BM25 normalization** `|x|/(1+|x|)` — use for score fusion with vector results
- **Position-aware blending** — don't apply flat reranker weight across all ranks
- **RRF fusion** with top-rank bonus — better than raw RRF
- **BM25 strong signal detection** — skip expensive vector search when FTS5 has a clear winner
- **FTS5 porter tokenizer** — we should add stemming
- **Chunk keyword overlap for reranker input** — avoid reranking full docs, select best chunk

### Consider
- **sqlite-vec** — eliminates LanceDB dependency, but has JOIN bugs and less mature than LanceDB
- **Typed query routing** (lex/vec/hyde) — complex but high-quality; our classify.py could evolve toward this
- **Query expansion model** — overkill for our use case but interesting pattern

### Skip
- **GGUF models via node-llama-cpp** — we're Python, use llama-cpp-python or sentence-transformers instead
- **Content-addressable storage** — we track by URL, not content hash; different access pattern
- **Custom fine-tuned expansion model** — too much investment for our scope

## Our Advantages Over QMD
- Exhaustive coverage mandate (46 exchanges, 78 sections)
- Structured endpoint extraction with citation verification (byte-exact provenance)
- Multi-source cross-referencing (OpenAPI, Postman, CCXT, page content)
- Crawl cascade for JS-heavy sites
- Exchange-specific error code search
- Input classification for query routing
