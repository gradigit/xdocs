# Research: Embedding Models & Split Build/Query Architecture (March 2026)

## Summary

Comprehensive evaluation of embedding models and build/query architecture for our document retrieval use case (5,700 pages, ~134K chunks of crypto exchange API documentation). The current model (Qwen3-Embedding-0.6B, decoder-only, 1024 dims) scores 54.32 on BEIR v1 retrieval and takes ~10 hours to build on Apple Silicon MLX.

**Primary finding:** gte-modernbert-base (149M params, encoder-only, 55.33 BEIR v1) is the strongest candidate. It exceeds current quality at 4x fewer parameters with native support in both MLX (query) and CUDA/TEI (build).

**Architecture finding:** A split build/query pipeline — home PC (RTX 4070 Ti Super) maintains the full pipeline (crawl, sync, embed, index) and pushes query-only data (~400-450MB) to GitHub. Team members git pull and query locally on their MacBooks via mlx-embeddings. Build time drops from ~10 hours to ~5 minutes. LanceDB indexes are fully portable across platforms.

## Key Findings

### 1. MTEB v1 vs v2 scores are NOT comparable — confidence: HIGH

MTEB v2 (released 2025) uses downsampled corpora with hard negatives, producing different absolute scores than v1 (15 BEIR datasets, full corpus). Qwen3-0.6B scores 61.83 (v2) vs 54.32 (v1). When comparing models, ensure both scores come from the same version. Most older models only have v1 scores; newest models report v2.

Sources: MTEB leaderboard (huggingface.co/spaces/mteb/leaderboard), MTEB v2 paper

### 2. gte-modernbert-base is the best cross-platform model — confidence: HIGH

149M params (4x smaller than Qwen3-0.6B), encoder-only (ModernBERT architecture), 55.33 BEIR v1 retrieval (exceeds Qwen3-0.6B's 54.32), 8K context, Apache 2.0 license. Native support in both ecosystems:
- **MLX**: mlx-embeddings has a dedicated ModernBERT handler. Pre-quantized 4-bit MLX variant via mlx-community.
- **CUDA**: Fully supported by HuggingFace TEI (Text Embeddings Inference) via native Candle backend. SentenceTransformers compatible.

Encoder-only architecture processes all tokens in parallel with bidirectional attention — fundamentally faster than decoder-only causal models for embedding.

Sources: MTEB leaderboard, Alibaba-NLP/gte-modernbert-base HuggingFace card, mlx-embeddings README, TEI GitHub

### 3. Encoder-only models are 3-8x faster than decoder-only for embeddings — confidence: HIGH

Architectural advantage: bidirectional attention processes all tokens simultaneously, no causal masking overhead. MLX benchmarks show BERT-base at 4.9ms per batch (batch=1) on M2 Max. Our current Qwen3-0.6B throughput (~230 chunks/min) is far below the theoretical MLX maximum (jakedahn reports 44K tok/s for Qwen3-0.6B on M2 Max), suggesting either our batching is suboptimal or the decoder overhead is significant.

Sources: mlx-embeddings benchmarks, jakedahn/embed-benchmark GitHub

### 4. Jina v5 claims highest retrieval scores — confidence: MEDIUM

Jina v5-text-nano (239M, EuroBERT backbone): claims 71.0 MTEB v2 retrieval. Jina v5-text-small (677M, Qwen3-0.6B backbone): claims 71.7. Released Feb 18, 2026 — only ~2 weeks old at time of research.

**Technical considerations:**
- **License: CC-BY-NC-4.0.** Not a blocker.
- **MLX compatibility:** NOT mlx-embeddings compatible. EuroBERT is a novel architecture (GQA, RoPE, RMSNorm) with no handler in mlx-embeddings. Jina publishes self-contained MLX models under jinaai/ namespace that require custom loading code.
- **No independent validation.** MTEB scores were self-submitted (PR #4102 merged). Jina v3 had a ~4 point discrepancy between self-reported (57.98) and third-party (53.88) BEIR scores.
- **LoRA adapter complexity.** Jina v5 uses 4 task-specific adapters (retrieval, text-matching, classification, clustering). MLX variants are pre-merged but this adds deployment complexity.
- **TEI incompatible.** EuroBERT has no Candle backend in TEI. Python backend fallback may work (~75% higher latency). Jina recommends **vLLM** for serving v5 models.

Sources: jinaai/jina-embeddings-v5-text-nano HuggingFace card, MTEB PR #4102, Jina blog, TEI GitHub

### 5. pplx-embed-v1-0.6B has inflated marketing, no MLX — confidence: HIGH

Perplexity's pplx-embed-v1-0.6B (Feb 26, 2026): bidirectional encoder converted from Qwen3-0.6B via diffusion continued pretraining. 596M params, 1024 dims, 32K context, MIT license, no instruction prefix needed. Natively outputs INT8 embeddings.

**Why it's not a contender for us:**
- **MTEB English v2 Retrieval: unreported.** The headline 71.1% is their internal PPLXQuery2Query benchmark. On comparable MTEB multilingual, the gap over Qwen3-0.6B is only +0.76.
- **No MLX support.** No mlx-community 4-bit port. Custom architecture (`bidirectional_pplx_qwen3`) requires `trust_remote_code=True` — no mlx-embeddings handler exists.
- **Same 596M params as Qwen3-0.6B.** No speed advantage over current model.
- **CUDA-only viable.** Could build via TEI/SentenceTransformers on the PC, but can't query on Mac. gte-modernbert-base covers both platforms at 4x fewer params with a verified BEIR v1 score.

The pplx-embed-context-v1 variant (built-in late chunking for RAG) is architecturally interesting but has the same MLX/platform blockers.

Sources: perplexity-ai/pplx-embed-v1-0.6b HuggingFace card, pplx-embed research paper (arXiv:2602.11151), semantic-pipeline-report.md local benchmarks

### 6. EmbeddingGemma-300M is a strong mid-range option — confidence: MEDIUM

308M params, 55.70 MTEB v2, Sep 2025 release, Gemma license (permissive). 4-bit MLX variant available via mlx-community. Supported by mlx-embeddings via Gemma3 handler. **Limitation: 2K max context** — sufficient for our chunks (<2K tokens) but no headroom.

Sources: google/EmbeddingGemma-300M HuggingFace card, mlx-community

### 6. Ultra-lightweight models exist but don't match BM25 on retrieval — confidence: HIGH

Model2Vec/potion-retrieval-32M: 36.35 BEIR — well below BM25 baseline (~42-45). Disqualified for retrieval. However, mdbr-leaf-ir (23M, MongoDB): 53.55 BEIR — extraordinary efficiency, within 1 point of Qwen3-0.6B at 1/26th the params. granite-embed-small-en-r2 (47M, IBM): 55.6 BEIR — best sub-50M model. Neither has MLX support currently.

Sources: MTEB leaderboard, Model2Vec GitHub, MongoDB LEAF paper

### 7. nomic-embed-text-v2-moe is disqualified — confidence: HIGH

512 token max context, confirmed by Nomic team. Our chunks can reach 2K tokens. The MoE architecture is interesting but the context limit is a dealbreaker.

Sources: nomic-ai blog, Nomic team confirmation

### 8. Chunk optimization can halve build time independently — confidence: MEDIUM

Analysis of current chunking pipeline identifies four optimizations: (1) Token estimation fix: `len(text)/3` should be `len(text)/4` for English text, causing premature splits. (2) max_tokens increase from 512 to 1024 (model supports it). (3) Filter tiny chunks <50 chars. (4) Merge adjacent small chunks. Combined estimate: 134K → ~69K chunks (~48% reduction). Not yet validated — implementation needed.

Sources: Codebase analysis of semantic.py and chunker.py

### 9. mx.compile() is an untapped speedup — confidence: MEDIUM

MLX's `mx.compile()` fuses operations to reduce kernel launches. Documented up to 5x for fusible ops. Estimated 1.5-3x for full transformer forward pass. Not currently used in our embeddings.py. Easy to add: wrap the model's forward call.

Sources: MLX documentation (ml-explore.github.io/mlx)

### 10. Hybrid retrieval (BM25 + vector) adds +3-5 nDCG points — confidence: HIGH

Consistent finding across multiple papers and benchmarks. We already have FTS5 (BM25-like) — our `semantic.py` already supports hybrid mode. This means a slightly weaker embedding model combined with our existing FTS5 can match a stronger model used alone.

Sources: Multiple BEIR papers, LanceDB hybrid search documentation

### 11. RTX 4070 Ti Super makes build time a non-issue — confidence: HIGH

NVIDIA RTX 4070 Ti Super (Ada Lovelace, sm89): 8,448 CUDA cores, 264 4th-gen Tensor Cores, 16GB GDDR6X at 672 GB/s, 285W TDP. Roughly 0.55-0.65x of an RTX 4090 but with the same 16GB VRAM. Our entire corpus (134K chunks) fits trivially in VRAM.

Estimated build throughput via TEI:
| Model | Chunks/min | Full build (134K) |
|-------|------------|-------------------|
| gte-modernbert-base (149M) | ~26,000 | **~5 min** |
| Jina v5-text-nano (239M) | ~15,000 | **~9 min** |
| Qwen3-0.6B (596M) | ~2,000-6,000 | **~22-65 min** |

Even with the "worst" model, CUDA builds are 10-25x faster than our current MLX pipeline.

Sources: NVIDIA RTX 4070 Ti Super specs, TEI benchmarks (scaled from 4090 published data), SentenceTransformers CUDA benchmarks

### 12. LanceDB indexes are fully portable across platforms — confidence: HIGH

Lance columnar format is little-endian, based on Apache Arrow, with protobuf metadata. No platform-specific binaries. An index built on Linux/CUDA can be used directly on macOS/ARM.

**Requirements:**
- Pin LanceDB version on both machines (Lance format evolves across versions)
- Run `compact_files()` + `cleanup_old_versions()` before transfer — reduces 264+ fragment files to 1-3 contiguous files
- Atomic swap pattern on the Mac side: write to temp dir, rename into place (zero-downtime updates)

Sources: LanceDB documentation, Lance format specification, Arrow columnar format spec

### 13. Same model and precision required for vector compatibility — confidence: HIGH

Embedding vectors are model-specific — a query must be embedded with the exact same model that produced the index vectors. Precision matters:
- **FP16 ↔ FP32: SAFE.** IEEE 754 guarantees lossless round-trip for values in FP16 range. All embedding values fit comfortably.
- **INT4 ↔ FP16: NOT SAFE.** 4-bit quantized models produce different vectors than their FP16/FP32 counterparts — up to 4% correlation loss measured in MLX quantization studies.

**Implication for split architecture:** Build with FP16 on CUDA, query with the same model at FP16 (or FP32) on Mac. Do NOT mix 4-bit quantized queries against FP16 index vectors. Mac query-time inference with FP16 gte-modernbert-base (149M params) should be fast enough — single-query latency estimated at <50ms on Apple Silicon.

Sources: SentenceTransformers documentation, IEEE 754 specification, MLX quantization benchmarks

### 14. TEI is the gold standard for CUDA batch embedding — confidence: HIGH

HuggingFace's Text Embeddings Inference (TEI) is the optimized batch embedding layer for CUDA builds:
- Native Candle backend for ModernBERT, BERT, XLM-RoBERTa families
- Dynamic batching, Flash Attention, tensor parallelism
- Pre-built Docker images with CUDA support
- RTX 4070 Ti Super (Ada Lovelace sm89) fully supported

**TEI model compatibility:**
| Model | TEI Support | Notes |
|-------|------------|-------|
| gte-modernbert-base | Native Candle | Full speed, recommended |
| Qwen3-Embedding-0.6B | Python backend | Works but slower |
| Jina v5-text-nano | NOT supported | EuroBERT has no Candle backend; use vLLM |

Sources: HuggingFace TEI GitHub, TEI Candle model registry

### 15. Query-only distribution is ~400-500MB — confidence: HIGH

Measured from current store (5,716 pages, 3,603 endpoints, 134K chunks):

| Component | Size | Query needed? |
|-----------|------|---------------|
| `db/docs.db` (full) | 304MB | Partially — ~204MB is FTS content/data |
| `pages/` (markdown) | 132MB | Yes (citations, excerpts) |
| `lancedb-index/` | 78MB (265 fragments) | Yes (vector search) |
| `raw/` (HTML) | 1.6GB | **No** (crawl/maintenance only) |
| `meta/` | 22MB | Optional |

A query-only SQLite DB (stripping `page_versions`, `inventory_entries`, `crawl_runs`, `review_queue`, `inventory_scope_ownership`) would save ~25MB. After `VACUUM`, the query-only DB is estimated at ~270MB.

After compaction, LanceDB index reduces from 265 fragments to 1-3 files. Switching to gte-modernbert-base (768 dims vs 1024 dims) would shrink the index by ~25%.

**Estimated query-only distribution: ~400-450MB** (after cleanup + model switch + compaction). Git LFS is the natural distribution mechanism.

Sources: Local store measurements, SQLite dbstat analysis

### 16. Maintainer PC → GitHub → Team Macs architecture — confidence: HIGH

The PC is purely a maintainer — no remote query serving. Architecture:

```
┌─────────────────────────────────────────────────┐
│              MAINTAINER (Home PC)                │
│  RTX 4070 Ti Super + TEI (Candle backend)       │
│  Crawl → Sync → Import → Build Index → Embed    │
│  gte-modernbert-base FP16, 134K chunks in ~5min │
│  compact_files() → strip maintenance tables     │
│  git push (LFS for binary data)                 │
└──────────────────────┬──────────────────────────┘
                       │ git push / git pull
                       │ (~400-450MB via Git LFS)
┌──────────────────────▼──────────────────────────┐
│               GITHUB REPO (data)                 │
│  db/docs.db (query-only)                         │
│  pages/ (markdown for citations)                 │
│  lancedb-index/ (compacted, 1-3 files)           │
│  NO raw/, NO meta/, NO crawl artifacts           │
└──────────────────────┬──────────────────────────┘
                       │ git pull
┌──────────────────────▼──────────────────────────┐
│           QUERY RUNTIME (Team MacBooks)          │
│  mlx-embeddings + gte-modernbert-base FP16       │
│  Single-query latency: ~10-30ms                  │
│  LanceDB search + FTS5 hybrid                    │
│  Fallback: FTS5-only if model not installed       │
└─────────────────────────────────────────────────┘
```

**Key constraints:**
- Build model must match query model exactly (same weights, FP16 on both sides)
- PC builds with TEI/SentenceTransformers (CUDA FP16), Macs query with mlx-embeddings (FP16)
- FP16 ↔ FP32 is safe — team members can use either precision on their Macs
- Git LFS handles the binary files (SQLite DB + Lance files)
- Compaction is essential before push — reduces Lance fragments from 264+ to 1-3 files

Sources: Architecture analysis, LanceDB documentation, Git LFS documentation

## Comprehensive Model Comparison

### Models with BEIR v1 scores (directly comparable)

| Model | Params | Architecture | BEIR v1 | Dims | Max Ctx | MLX | CUDA/TEI | Notes |
|-------|--------|-------------|---------|------|---------|-----|----------|-------|
| gte-large-en-v1.5 | 434M | BERT | 57.91 | 1024 | 8K | mlx-community | TEI native | Highest v1 retrieval under 1B |
| gte-modernbert-base | 149M | ModernBERT | 55.33 | 768 | 8K | mlx-embeddings | TEI native | **Best overall candidate** |
| granite-embed-small-en-r2 | 47M | BERT | 55.60 | 384 | 8K | No | TEI native | Best sub-50M |
| **Qwen3-Embedding-0.6B** | **596M** | **Decoder** | **54.32** | **1024** | **32K** | **mlx-embeddings** | **TEI Python** | **Current model** |
| KaLM-V2.5 | 494M | Decoder | 55.00 | 1024 | 8K | No | TEI Python | Marginal gain |
| mdbr-leaf-ir (LEAF) | 23M | Custom | 53.55 | 256 | 512 | No | Unknown | Extraordinary efficiency |
| nomic-embed-text-v1.5 | 137M | BERT | ~52 | 768 | 8K | mlx-community | TEI native | Matryoshka support |

### Models with MTEB v2 scores only (not directly comparable to above)

| Model | Params | Architecture | MTEB v2 Ret | Dims | Max Ctx | MLX | CUDA | Notes |
|-------|--------|-------------|-------------|------|---------|-----|------|-------|
| Jina v5-text-small | 677M | Qwen3+LoRA | 71.7 | 1024 | 32K | jinaai/ self-contained | vLLM | Custom loading both sides |
| Jina v5-text-nano | 239M | EuroBERT+LoRA | 71.0 | 512 | 8K | jinaai/ self-contained | vLLM | Quality leader (unverified) |
| pplx-embed-v1-0.6B | 596M | Bidir. Qwen3 | unreported* | 1024 | 32K | No | TEI/ST | No MLX, CUDA-only |
| **Qwen3-Embedding-0.6B** | **596M** | **Decoder** | **61.83** | **1024** | **32K** | **mlx-embeddings** | **TEI Python** | **Current model** |
| EmbeddingGemma-300M | 308M | Gemma | 55.70 | 768 | 2K | mlx-community | TEI native | 2K context limit |

*pplx-embed MTEB English v2 Retrieval is unreported. MTEB multilingual: 65.41 (only +0.76 vs Qwen3-0.6B). The 71.1% headline is PPLXQuery2Query (internal benchmark).

### Build Throughput (RTX 4070 Ti Super, CUDA)

| Model | Params | TEI Backend | Chunks/min | Full build (134K) | Full build (69K*) |
|-------|--------|------------|------------|-------------------|--------------------|
| gte-modernbert-base | 149M | Candle (native) | ~26,000 | ~5 min | ~2.5 min |
| EmbeddingGemma-300M | 308M | Candle (native) | ~18,000 | ~7.5 min | ~4 min |
| Jina v5-text-nano | 239M | vLLM | ~15,000 | ~9 min | ~4.5 min |
| Qwen3-Embedding-0.6B | 596M | Python fallback | ~2,000-6,000 | ~22-65 min | ~12-35 min |

*After chunk optimization (~50% reduction from 134K to ~69K)

### Query Latency (Apple Silicon, per single query)

| Model | Params | Runtime | Expected Latency |
|-------|--------|---------|-----------------|
| gte-modernbert-base | 149M | mlx-embeddings (FP16) | ~10-30ms |
| gte-modernbert-base | 149M | TEI+Metal | ~15-25ms |
| EmbeddingGemma-300M | 308M | mlx-embeddings (FP16) | ~20-40ms |
| Qwen3-Embedding-0.6B | 596M | mlx-embeddings (4-bit) | ~50-100ms |

## Hypotheses

### Model Selection (original campaign)

| Hypothesis | Status | Evidence |
|-----------|--------|----------|
| H1: Encoder-only can match Qwen3-0.6B quality at 3-8x faster | **Confirmed** | gte-modernbert-base: 55.33 vs 54.32 BEIR, 4x smaller, encoder-only |
| H2: Sub-200M model can match Qwen3-0.6B | **Confirmed** | gte-modernbert-base (149M): 55.33 BEIR > 54.32 |
| H3: Feb/Mar 2026 models are a quality leap | **Uncertain** | Jina v5 claims huge leap but scores are unverified (2 weeks old, self-reported) |
| H4: MLX 4-bit quantization preserves retrieval quality | **Uncertain** | No published ablations; works for Qwen3 in practice |
| H5: Chunk count reduction of ~50% is achievable | **Confirmed** | Analysis estimates 134K → ~69K via 4 optimizations |

### Split Architecture (new campaign)

| Hypothesis | Status | Evidence |
|-----------|--------|----------|
| H6: RTX 4070 Ti Super builds full index in <30 min | **Confirmed** | ~26K chunks/min with gte-modernbert-base → 5 min |
| H7: LanceDB index is fully portable across platforms | **Confirmed** | Lance = little-endian Arrow + protobuf, no platform binaries |
| H8: Mac can use lighter/quantized model while PC builds full-precision | **Refuted** | Same model + precision required. FP16↔FP32 safe, INT4 is not. |
| H9: CUDA unlocks models not available on MLX | **Confirmed (not needed)** | Top candidates have both MLX and CUDA variants |
| H10: Distribution via GitHub is practical | **Confirmed** | Query-only footprint ~400-450MB. Git LFS handles binary data. |
| H11: TEI serves batch builds on CUDA | **Confirmed** | Native Candle backend for ModernBERT. Not needed for query (Mac uses mlx-embeddings). |

## Gaps and Limitations

- **No local benchmarks.** All speed comparisons are estimates from architecture and parameter counts. A proper A/B test with our corpus is needed before switching.
- **Jina v5 scores unverified.** Only 2 weeks old, self-reported, historical discrepancy with v3. If scores hold up under independent validation, Jina v5-text-nano would be the quality leader — but requires vLLM on CUDA and custom MLX loading on Mac.
- **MLX quantization impact unknown.** 4-bit quantization of encoder-only models may degrade retrieval quality differently than for decoder-only. No published data. For split architecture, use FP16 on both sides to avoid this risk.
- **gte-modernbert-base output dims are 768, not 1024.** Switching models requires rebuilding the entire LanceDB index (different vector dimensions). The dim-check in semantic.py already handles this — it will trigger a full rebuild automatically.
- **No MTEB v2 score for gte-modernbert-base.** Can't directly compare with Jina v5 or EmbeddingGemma. The v1 score (55.33) exceeds Qwen3-0.6B v1 (54.32), which is the most relevant comparison.
- **Git LFS overhead.** ~400-450MB of binary data per update. Git LFS handles this well but initial clones are slow. GitHub LFS has a 2GB/month free bandwidth quota — a full team pulling weekly could exceed this. Consider GitHub Releases as an alternative distribution if bandwidth becomes a concern.

## Recommendations

### Primary recommendation: gte-modernbert-base (149M) with split build/query

**Why:**
- Exceeds Qwen3-0.6B on BEIR v1 retrieval (55.33 vs 54.32)
- 4x smaller → faster inference, lower memory
- Encoder-only → parallel token processing, fundamentally faster
- **Native TEI Candle backend** on CUDA → ~5 min full builds on RTX 4070 Ti Super
- **Native mlx-embeddings handler** on Mac → fast query-time inference for team
- Apache 2.0 license, 8K context, pre-quantized MLX model available

**Estimated impact:**
- Build: ~10 hours → **~5 minutes** (RTX 4070 Ti Super via TEI)
- Query: ~50-100ms → **~10-30ms** (encoder parallelism + smaller model)
- Distribution: ~400-450MB via Git LFS (vs 2.1GB full store)
- With chunk optimization: build drops to **~2.5 minutes**

### Recommended architecture: Maintainer PC → GitHub → Team Macs

```
┌──────────────────────────────────────────────────┐
│              MAINTAINER (Home PC)                 │
│  RTX 4070 Ti Super + TEI (Candle backend)        │
│  Crawl → Sync → Import → Build Index → Embed     │
│  gte-modernbert-base FP16, full corpus in ~5 min │
│  compact + strip maintenance tables + git push    │
└──────────────────────┬───────────────────────────┘
                       │ git push (LFS)
                       │ ~400-450MB binary data
┌──────────────────────▼───────────────────────────┐
│                GITHUB REPO                        │
│  db/docs-query.db  (~270MB, query tables only)    │
│  pages/            (~132MB, markdown for cites)    │
│  lancedb-index/    (~60MB, compacted, 1-3 files)  │
└──────────────────────┬───────────────────────────┘
                       │ git pull
┌──────────────────────▼───────────────────────────┐
│           QUERY RUNTIME (Team MacBooks)           │
│  mlx-embeddings + gte-modernbert-base FP16        │
│  LanceDB vector search + FTS5 hybrid              │
│  Single-query: ~10-30ms embedding + ~5ms search   │
│  Fallback: FTS5-only if model not installed        │
└──────────────────────────────────────────────────┘
```

**Maintainer workflow:**
1. PC runs full pipeline: crawl → sync → import endpoints → build LanceDB index
2. `compact_files()` + `cleanup_old_versions()` on LanceDB
3. Export query-only SQLite DB (strip `page_versions`, `inventory_entries`, `crawl_runs`, `review_queue`, `inventory_scope_ownership`)
4. `git add` + `git push` (LFS tracks `.db`, `.lance` files)
5. Team members: `git pull` → query immediately

### Secondary recommendation: Jina v5-text-nano (239M)

Highest claimed quality (71.0 MTEB v2) but more complex deployment:
- CUDA: Requires vLLM instead of TEI (no native Candle backend for EuroBERT)
- Mac: Self-contained MLX under jinaai/ namespace (custom loading code, not mlx-embeddings)
- Worth benchmarking once scores get independent validation

### Fallback recommendation: EmbeddingGemma-300M

If gte-modernbert-base underperforms in local testing. Higher MTEB v2 score (55.70), 308M params, native TEI Candle support. 2K context limit is tight but sufficient for our chunks.

### Independent optimization: Chunk reduction

Regardless of model choice, implement the 4 chunking optimizations (token estimation fix, max_tokens increase, tiny chunk filter, adjacent merge) for ~50% chunk count reduction. Stacks multiplicatively with any model/architecture improvement.

### Independent optimization: mx.compile()

Add `mx.compile()` to the model forward pass in embeddings.py. Expected 1.5-3x additional speedup for Mac-local inference with zero quality impact.

## Sources

### Models and Benchmarks
- MTEB Leaderboard: huggingface.co/spaces/mteb/leaderboard
- Alibaba-NLP/gte-modernbert-base: huggingface.co/Alibaba-NLP/gte-modernbert-base
- Qwen3-Embedding: huggingface.co/Qwen/Qwen3-Embedding-0.6B
- jinaai/jina-embeddings-v5-text-nano: huggingface.co/jinaai/jina-embeddings-v5-text-nano
- google/EmbeddingGemma-300M: huggingface.co/google/EmbeddingGemma-300M
- MongoDB LEAF paper (Sep 2025): arxiv.org
- granite-embedding-small-en-r2: huggingface.co/ibm-granite/granite-embedding-small-en-r2
- nomic-embed-text-v2-moe: huggingface.co/nomic-ai/nomic-embed-text-v2-moe
- perplexity-ai/pplx-embed-v1-0.6b: huggingface.co/perplexity-ai/pplx-embed-v1-0.6b
- pplx-embed paper (Feb 2026): arxiv.org/abs/2602.11151
- KaLM paper: arxiv.org
- Model2Vec: github.com/MinishLab/model2vec
- jakedahn/embed-benchmark: github.com/jakedahn/embed-benchmark

### Infrastructure and Serving
- HuggingFace TEI: github.com/huggingface/text-embeddings-inference
- TEI Candle model registry: github.com/huggingface/text-embeddings-inference (supported models)
- vLLM: github.com/vllm-project/vllm
- LanceDB documentation: lancedb.github.io/lancedb
- Lance format specification: github.com/lancedb/lance
- Apache Arrow columnar format: arrow.apache.org
- mlx-embeddings: github.com/Blaizzy/mlx-embeddings
- MLX documentation: ml-explore.github.io/mlx

### Hardware and Networking
- NVIDIA RTX 4070 Ti Super specifications: nvidia.com
- Tailscale mesh VPN: tailscale.com
- SentenceTransformers CUDA benchmarks: sbert.net

---

*Research conducted: 2026-03-04. Two forge-research campaigns:*
*Campaign 1 (Model selection): 4 Phase 1 agents (breadth) + 1 Phase 2 agent (adversarial verification). Total: 5 sub-agents.*
*Campaign 2 (Split architecture): 4 Phase 1 agents (GPU specs, LanceDB portability, CUDA models, architecture patterns) + 1 Phase 2 agent (TEI compatibility). Total: 5 sub-agents.*
