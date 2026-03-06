# Semantic Search Pipeline: Exhaustive Research & Benchmark Report

**Date**: 2026-03-02
**Scope**: Embedding models, rerankers, chunking strategies, retrieval architecture
**Method**: 5-phase — deep research → independent validation → adversarial review → local benchmarks → synthesis

> **PARTIALLY SUPERSEDED (2026-03-04):** The model recommendation ("keep Qwen3-0.6B") is outdated — see `embedding-models-march-2026.md` which evaluates gte-modernbert-base and split build/query architecture with CUDA. The implementation-level findings below (chunking issues, retrieval architecture bugs, reranker evaluation, priority tiers) remain valid and are the primary reference for pipeline fixes.

---

## Executive Summary

The current pipeline (Qwen3-Embedding-0.6B + LanceDB hybrid + jina-reranker-v3-mlx) is architecturally sound but has **implementation-level issues** causing more retrieval quality loss than any model swap would fix.

**Measured baseline**: 45% Recall@1, 55% Recall@10 on golden QA (20 queries). When the system finds the right page, it's almost always rank 1. Failures are binary — it either gets it or misses entirely.

**Top 3 issues by impact** (all code-level, no model changes needed):

1. **22.8% of chunks are silently truncated** — `max_length=512` in the embedder cuts the tail off chunks that exceed 512 actual tokens, while the chunker's `len(text)//4` estimator underestimates by 12% on average.
2. **`answer.py` uses semantic search as fallback-only** — FTS5 must return zero results before semantic search fires. Natural language queries get poor FTS matches that block the semantic path.
3. **Hybrid fusion injects FTS noise** — vector-only search outperformed hybrid on Binance queries (MRR 0.267 vs 0.067). The FTS component displaces correct vector results.

**Model assessment**: Keep Qwen3-Embedding-0.6B and jina-reranker-v3-mlx. No model swap is justified until the implementation issues above are fixed and a new baseline measured.

---

## 1. Current Pipeline Architecture

```
Query → Classify → Route
                     ├→ FTS5 (answer.py primary) → semantic fallback if 0 results
                     ├→ semantic_search() → LanceDB hybrid (vector + FTS) → reranker
                     └→ endpoint lookup (SQL LIKE)

Index Build:
  Pages → chunk_markdown() → embed_texts() → LanceDB table
  5,716 pages → 133,605 chunks → 932 MB index
  Model: Qwen3-Embedding-0.6B-4bit-DWQ (MLX), 1024 dims
  Reranker: jina-reranker-v3-mlx (0.6B, CC-BY-NC)
```

---

## 2. Embedding Models

### Current: Qwen3-Embedding-0.6B (keep)

| Metric | Value |
|--------|-------|
| MTEB English v2 Retrieval | 61.83 |
| Parameters | 0.6B |
| MLX 4-bit size | 335 MB |
| Throughput (MLX) | ~44K tokens/sec |
| Index rebuild time | ~35 minutes |
| Maturity | 9 months, well-established |

### Evaluated Alternatives

| Model | Params | MTEB Retrieval | MLX Ready? | Verdict |
|-------|--------|---------------|------------|---------|
| **pplx-embed-v1-0.6B** | 0.6B | Not reported (MTEB-multi: 65.41) | F32 only (2.38GB), no 4-bit | **WAIT** — 4 days old, no 4-bit MLX, MTEB English unreported |
| pplx-embed-context-v1 | 0.6B | ConTEB: 76.53 | No | Interesting (native late chunking) but immature |
| Qwen3-Embedding-4B | 4B | 68.46 | Yes (2.3GB 4-bit) | Quality upgrade path when 0.6B ceiling is proven |
| Qwen3-Embedding-8B | 8B | 69.44 | Yes (4.5GB 4-bit) | Diminishing returns vs 4B |
| jina-embeddings-v5-text-small | 677M | 63.28 avg | No | Marginal gain, no MLX |
| EmbeddingGemma-300M | 300M | 47.4 retrieval | MLX available | Too weak for primary embedding |
| Snowflake Arctic Embed 2.0 | 568M | 56.13 | No | Below Qwen3 |
| IBM Granite-Small-R2 | 47M | Competitive for size | No MLX | Fast first-stage screener, not primary |
| F2LLM-1.7B | 1.7B | #1 in 1-2B range | No | Fine-tuning recipe reference |
| nomic-embed-text-v2-moe | 475M (305M active) | Competitive | No | Interesting MoE architecture |

### Key Findings

- **pplx-embed-v1-0.6B benchmark claims are inflated**: The headline 71.1% vs 55.1% comparison is on Perplexity's internal PPLXQuery2Query benchmark. On comparable standard benchmarks (MTEB Multilingual), the gap is only +0.76. MTEB English v2 Retrieval — the most relevant benchmark — is **unreported**.
- **No model swap is justified now**: Qwen3-Embedding-0.6B has the best MLX ecosystem support (335MB 4-bit, proven 44K tok/sec throughput, 9 months of production use). pplx-embed needs 3-6 months for MLX ecosystem maturity.
- **Quick win available**: We're not applying Qwen3's instruction prefix. Adding `"Instruct: Given a query, retrieve relevant passages\nQuery: "` could yield 1-5% improvement for free.
- **Fine-tuning is the highest-ROI model improvement**: Literature consistently shows 7-20% retrieval improvement from domain-specific fine-tuning. With 3,600 structured endpoints and golden QA data, synthetic training pair generation is straightforward.

---

## 3. Reranker

### Current: jina-reranker-v3-mlx (keep)

| Metric | Value |
|--------|-------|
| BEIR nDCG@10 (controlled) | 61.85 |
| Parameters | 0.6B |
| Context | 131K tokens |
| License | CC-BY-NC-4.0 |
| MLX port | Official, 100% parity, 1.2GB |

### Controlled Comparison (all evaluated with same first-stage retriever)

| Model | Params | BEIR nDCG@10 | MLX? | License |
|-------|--------|-------------|------|---------|
| **jina-reranker-v3** | **0.6B** | **61.85** | **Yes (official)** | CC-BY-NC |
| mxbai-rerank-large-v2 | 1.5B | 61.44 | No | Apache 2.0 |
| Qwen3-Reranker-4B | 4.0B | 61.16 | No | Apache 2.0 |
| mxbai-rerank-base-v2 | 0.5B | 58.40 | No | Apache 2.0 |
| Qwen3-Reranker-0.6B | 0.6B | 56.28 | No | Apache 2.0 |
| gte-reranker-modernbert-base | 149M | 56.73 | No | Apache 2.0 |
| zerank-2 | 4.0B | #1 Agentset ELO | No | CC-BY-NC |

### Key Findings

- **Qwen3-Reranker MTEB-R scores are inflated**: Self-reported 65.80 uses pre-filtered candidates from Qwen3-Embedding. Under standard BEIR evaluation, Qwen3-Reranker-0.6B drops to 56.28 — **5.6 points below** jina-reranker-v3.
- **jina-reranker-v3 is the best sub-1B reranker with MLX support**: Even Qwen3-Reranker-4B (8x larger) scores lower (61.16 vs 61.85).
- **Evaluation bias caveat**: The Jina paper uses jina-embeddings-v3 as first-stage retriever. Agentset leaderboard (independent methodology) ranks zerank-2 higher, but it's 4B with no MLX port.
- **Implementation fix**: `top_n=fetch_limit` wastes compute — reranker processes 30 candidates when 10-20 suffice.

---

## 4. Chunking

### Current Implementation (mostly keep, with fixes)

- Heading-aware splitting at H1/H2/H3 via mistune AST
- Paragraph sub-splitting at `\n\n` for oversized sections
- 512 max tokens (estimated as `len(text) // 4`), 64 token overlap
- Produces 133,605 chunks from 5,716 pages

### Benchmark Results

| Issue | Measured Impact | Fix |
|-------|----------------|-----|
| **Token estimation `//4` underestimates** | Mean 12% under, CJK 2x under | Change to `//3.7` or use tokenizer |
| **22.8% of chunks silently truncated** | ~30,000 chunks lose tail content | Increase `max_length` to 1024 |
| Orphaned data-row chunks | 959 (0.7%) — table rows without headers | Add table-aware splitting |
| Split code blocks | 1,157 (0.9%) — unbalanced fences | Add fence tracking |
| True cross-boundary table splits | 188 (0.14%) | Concentrated in mega-pages |
| Overlap at 64 tokens | Higher than research suggests necessary | Reduce to 32 for heading splits |

### Contextual Retrieval (heading prepend): REJECTED

**Benchmark result**: Net negative. 55% of relevant chunks worsened in rank vs 26% improved.

- Exchange-name prefix creates cross-domain interference in a multi-exchange corpus
- For generic queries, the prefix is pure noise
- The model already captures heading context from chunk body text
- **Query-time exchange filtering** (`where("exchange = '...'")`) achieves the same goal without distorting embeddings

### Research-Validated Assessment

- 512-token heading-aware splitting is empirically near-optimal for decoder-based embedding models (confirmed by multiple 2025-2026 papers)
- Semantic chunking is NOT better than structure-based splitting (NAACL 2025, ACL 2026)
- Late chunking yields only +1.9% absolute improvement — not worth the complexity
- Optimal overlap for heading-based splits: 0-32 tokens (Chroma 2024, multiple studies)

---

## 5. Hybrid Search & Retrieval Architecture

### Benchmark Results

| Configuration | Recall@1 | Recall@10 | MRR |
|--------------|----------|-----------|-----|
| Hybrid + exchange filter | **45.0%** | **55.0%** | **0.483** |
| Hybrid unfiltered | 30.0% | 55.0% | 0.383 |
| Vector-only + filter (5 queries) | **20.0%** | **40.0%** | **0.267** |
| FTS-only + filter (5 queries) | 0.0% | 20.0% | 0.025 |
| Hybrid + filter (5 queries) | 0.0% | 20.0% | 0.067 |

### Critical Finding: Vector-Only Beats Hybrid on Dense Exchanges

On the 5-query Binance sample, vector-only search (MRR 0.267) dramatically outperformed hybrid (MRR 0.067). The FTS component injects keyword-match noise that displaces semantically correct vector results. This is especially visible for exchanges with many pages (Binance: ~1,400 pages) where FTS matches are abundant but imprecise.

### Architecture Issues Found

| Issue | Severity | Location |
|-------|----------|----------|
| **Semantic search is fallback-only in answer.py** | Critical | `answer.py:136` — FTS5 must return 0 results before semantic fires |
| **No exchange filter passed to semantic fallback** | High | `answer.py:141` — searches all 35 exchanges, then discards by URL prefix |
| **Classifier exchange list is stale** | High | `classify.py:141-149` — missing 7+ new exchanges |
| No hybrid fusion weight tuning | Medium | LanceDB default RRF, no domain-specific bias |
| FTS query strips "api" as stopword | Medium | `answer.py:246` |
| Excerpt extraction ignores structure | Medium | `answer.py:48-62` — fixed 400-char window misses tables |
| Hard 10-claim cap | Low | `answer.py:297` — truncates multi-exchange answers |
| Reranker top_n wastes compute | Low | `semantic.py:493` — reranks 30 when 10-20 suffice |

### Failure Modes

Retrieval failures cluster into 3 patterns:
1. **Section confusion** (5/9 failures): Binance has 8+ sections; "account balance" matches spot, margin, futures, portfolio-margin. Need section-level filtering.
2. **URL migration** (2/9 failures): KuCoin migrated `/docs/` → `/docs-new/`. Golden QA URLs are stale. (False negatives in benchmark, not actual retrieval failures.)
3. **Language mismatch** (1/9 failures): Upbit English expected URL vs Korean indexed URL.

---

## 6. ColBERT / Multi-Vector: Not Recommended

| Factor | Assessment |
|--------|-----------|
| Storage | 7-14x current (6.7-13.3 GB vs 932 MB) |
| MLX support | None — would need PyTorch CPU/MPS |
| FTS5 overlap | ColBERT's token-level matching largely duplicates what FTS5 already provides |
| LanceDB support | Native MaxSim exists but requires schema-breaking change |
| Best model | GTE-ModernColBERT-v1 (54.67 BEIR, 150M params) |

**Verdict**: Not worth the complexity. FTS5 + dense vector + reranker already covers the retrieval spectrum. ColBERT would add a fourth signal with high storage cost and no MLX path.

---

## 7. Novel Techniques Evaluated

| Technique | Expected Impact | Practical? | Verdict |
|-----------|----------------|------------|---------|
| **HyPE** (index-time question gen) | +42pp precision (reported) | Yes — one-time batch LLM cost | Worth investigating after code fixes |
| SPLADE (IBM Granite-30m-Sparse) | Learned query expansion | No — LanceDB lacks sparse vector support | Blocked by infrastructure |
| Fine-tuning Qwen3 on domain data | 7-20% (literature) | Yes — 5-10K synthetic pairs | Highest-ROI model improvement |
| Query expansion (static synonyms) | Medium | Yes — zero cost | Easy win for keyword mismatch |
| HyDE (query-time) | +15% nDCG (reported) | Adds LLM latency per query | Only for "deep search" mode |
| Late chunking | +1.9% absolute | High complexity | Not worth it |
| Reasoning-based reranking | Quality + explainability | Adds inference cost | Future consideration |
| Two-stage reranking | Cost reduction | Not needed at current scale | Premature optimization |

---

## 8. Prioritized Recommendations

### Tier 0: Measure Before Changing (do first)

| # | Action | Effort |
|---|--------|--------|
| 0a | Fix golden QA stale URLs (KuCoin `/docs-new/`, Bybit wallet) | 30 min |
| 0b | Add more golden QA cases (error codes, endpoint paths, DEXes, Korean exchanges) | 2 hours |
| 0c | Re-run baseline after fixes to get accurate Recall@10 (~65% expected) | 10 min |

### Tier 1: High Impact, Low Effort (implementation fixes)

| # | Action | Expected Impact | Effort |
|---|--------|----------------|--------|
| 1a | Set `max_length=1024` in `MlxEmbedder` | Eliminates 22.8% truncation | 1 line |
| 1b | Change token estimator from `//4` to `//3.7` | Reduces chunk oversizing | 1 line |
| 1c | Make semantic search primary in `answer.py` (not FTS5-fallback-only) | Major recall improvement | ~50 lines |
| 1d | Pass exchange filter to semantic search in answer.py | Reduces cross-exchange noise | ~5 lines |
| 1e | Update classifier exchange list (or load dynamically from registry) | Fixes routing for 7+ exchanges | ~10 lines |
| 1f | Fix reranker `top_n` from `fetch_limit` to `min(limit*2, len(results))` | Reduces reranker compute waste | 1 line |

### Tier 2: Medium Impact, Moderate Effort

| # | Action | Expected Impact | Effort |
|---|--------|----------------|--------|
| 2a | Add table-aware chunking (keep tables intact, repeat header on split) | Fixes 959 orphaned data-rows | 1 day |
| 2b | Add code-fence tracking to chunker | Fixes 1,157 split code blocks | 4 hours |
| 2c | Add Qwen3 instruction prefix to query embeddings | 1-5% retrieval improvement | 30 min |
| 2d | Add static query expansion dictionary for API terms | Helps keyword mismatch cases | 1 day |
| 2e | Add section-level filtering for multi-section exchanges (Binance) | Fixes 5/9 Binance failures | 1 day |
| 2f | Tune hybrid fusion: increase vector weight vs FTS | Fixes FTS noise on dense exchanges | 4 hours |

### Tier 3: High Impact, High Effort (future investments)

| # | Action | Expected Impact | Effort |
|---|--------|----------------|--------|
| 3a | Fine-tune Qwen3-Embedding-0.6B on synthetic API doc pairs | 7-20% retrieval improvement | 2-3 days |
| 3b | Evaluate pplx-embed-v1-0.6B via SentenceTransformers A/B test | Potentially significant | 4 hours + rebuild |
| 3c | Implement HyPE (index-time question generation) | Major precision improvement | 2-3 days |
| 3d | Programmatic classify-then-route pipeline | Removes agent-level routing dependency | 1 day |

### Not Recommended

| Action | Reason |
|--------|--------|
| Switch to pplx-embed now | 4 days old, no 4-bit MLX, MTEB English unreported |
| Add ColBERT/multi-vector | 7-14x storage, no MLX, FTS5 already covers exact matching |
| Heading breadcrumb prepending | Benchmark showed net negative (-0.6 rank positions) |
| Switch reranker from jina-v3 | Still highest BEIR at 0.6B with only production MLX port |
| SPLADE integration | LanceDB lacks native sparse vector support |
| Late chunking | +1.9% absolute for high implementation complexity |
| Semantic chunking | Outperformed by structure-based splitting (ACL 2026) |

---

## 9. Expected Outcomes

Implementing Tier 0 + Tier 1 fixes (estimated 1-2 days of work):

| Metric | Current | Expected After |
|--------|---------|---------------|
| Recall@1 (filtered) | 45% | ~60-65% |
| Recall@10 (filtered) | 55% | ~75-80% |
| Chunks truncated | 22.8% | <2% |
| Answer pathway | FTS5-primary | Semantic-primary |

Adding Tier 2 fixes (estimated 1 additional week):

| Metric | Expected |
|--------|----------|
| Recall@1 | ~70-75% |
| Recall@10 | ~85-90% |
| Orphaned table chunks | ~0% |
| Split code blocks | ~0% |

---

## 10. Research Sources

### Models Evaluated (HuggingFace)
- [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [pplx-embed-v1-0.6b](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b) — Released Feb 26, 2026
- [jina-reranker-v3-mlx](https://huggingface.co/jinaai/jina-reranker-v3-mlx)
- [GTE-ModernColBERT-v1](https://huggingface.co/lightonai/GTE-ModernColBERT-v1)
- [IBM Granite-Embedding-Small-R2](https://huggingface.co/ibm-granite/granite-embedding-small-english-r2)
- [IBM Granite-30m-Sparse](https://huggingface.co/ibm-granite/granite-embedding-30m-sparse)

### Papers Cited
- "Beyond Chunk-Then-Embed" (ACL Findings, Feb 2026) — arXiv:2602.16974
- "Rethinking Chunk Size for Long-Document Retrieval" (May 2025) — arXiv:2505.21700
- "Late Chunking" (NAACL 2025) — arXiv:2409.04701
- "Diffusion-Pretrained Embeddings" (pplx-embed paper, Feb 2026) — arXiv:2602.11151
- Jina Reranker v3 (Sep 2025) — arXiv:2509.25085
- Qwen3 Embedding (Jun 2025) — arXiv:2506.05176
- Evaluating Chunking Strategies (Chroma, Jul 2024)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) (Sep 2024)

### Benchmarks Run Locally
- Token estimation accuracy: 1,000 chunks, Qwen3 tokenizer vs `len//4`
- Semantic search quality: 20 golden QA queries across 13 exchanges
- Table/code chunking analysis: 5,000+ chunks
- Heading context simulation: 100 chunks × 10 queries, cosine similarity comparison
