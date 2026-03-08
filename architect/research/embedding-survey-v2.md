# Embedding Model Survey v2 — March 2026

## Summary

Current jina-v5-text-nano (239M, 768d) is #1 under 500M on MMTEB. Upgrade paths: jina-v5-text-small (677M, 1024d, +6% MTEB) or Qwen3-Embedding-0.6B. LanceDB now natively supports ColBERT multi-vector search (MaxSim) — answerai-colbert-small (33M) provides +6-10% OOD improvement. SPLADE blocked by LanceDB. RaBitQ binary quantization available (15-20x compression).

## Competitive Landscape: Under 500M Params

| Model | Params | Dims | Context | Backbone | MTEB Rank |
|-------|--------|------|---------|----------|-----------|
| jina-v5-text-nano (current) | 239M | 768 | 8192 | EuroBERT | #1 MMTEB multilingual (Feb 2026) |
| EmbeddingGemma-300M | 308M | 768 (MRL) | 2048 | Gemma 3 | #1 MTEB multilingual (Sep 2025) |
| granite-embedding-english-r2 | 149M | 768 | 8192 | ModernBERT | #1 MTEB English retrieval (Oct 2025) |
| snowflake-arctic-embed-m-v2.0 | 113M | 768 | 8192 | Unknown | Strong, smallest footprint |
| nomic-embed-text-v2-moe | 475M (305M active) | 768 (MRL) | 512 | MoE | Strong multilingual |

## Upgrade Tier: 500M–1B Params

| Model | Params | Dims | Context | License | MTEB |
|-------|--------|------|---------|---------|------|
| jina-v5-text-small | 677M | 1024 | 32768 | Apache 2.0 | 71.7 English |
| Qwen3-Embedding-0.6B | 600M | 1024 (MRL) | 8192 | Apache 2.0 | Strong |
| BGE-M3 | 568M | 1024 | 8192 | MIT | Dense+sparse+multi-vec |
| jina-embeddings-v3 | 570M | 1024 (MRL 32-1024) | 8192 | CC-BY-NC | 5 LoRA adapters |

## Max Quality: >1B Params

| Model | Params | Dims | Context | MTEB |
|-------|--------|------|---------|------|
| Qwen3-Embedding-8B | 8B | 1024 | 32K | 70.58 MMTEB |
| llama-embed-nemotron-8b | 7.5B | 4096 | 32K | #1 MMTEB (Oct 2025) |
| NV-Embed-v2 | 7.5B | 384-1024 | 2048 | 72.31 MTEB overall |
| Stella en 1.5B v5 | 1.5B | 512-8192 | 8192 | High, English only |
| Qwen3-Embedding-4B | 4B | 1024 | 32K | Between 0.6B and 8B |

## Alternative Architectures

### ColBERT (Late Interaction)
- LanceDB supports multi-vector search natively (MaxSim, cosine only)
- +6-10% improvement on out-of-domain tasks vs single-vector
- Storage: 50-100x more than single-vector (512 tokens * 128 dims/token = 262KB/doc vs 3KB)

| ColBERT Model | Params | Dims/Token | Languages | License |
|---------------|--------|-----------|-----------|---------|
| answerai-colbert-small-v1 | 33M | 96 | English | MIT |
| ColBERTv2 (Stanford) | 110M | 128 | English | MIT |
| jina-colbert-v2 | 560M | 128/96/64 | 89 languages | CC-BY-NC |

### SPLADE (Learned Sparse)
- NOT supported by LanceDB (no sparse vector storage)
- Existing FTS5 + BM25 partially covers this role
- BGE-M3 can output sparse vectors but nowhere to store them

### Hybrid Dense+Sparse
- BGE-M3 outputs dense + sparse + multi-vector simultaneously
- Only dense and multi-vector usable with LanceDB

## Storage Optimization

| Config | Dims | Precision | Per-Vector | Index Est. | Recall Impact |
|--------|------|-----------|-----------|------------|---------------|
| Current (v5-nano) | 768 | float32 | 3,072B | 908MB | baseline |
| RaBitQ quantized | 768 | 1-bit | ~100B | ~50MB | <5% loss |
| MRL 384 + float32 | 384 | float32 | 1,536B | ~460MB | ~1% loss |
| v5-small 1024d | 1024 | float32 | 4,096B | ~1.2GB | quality gain |

## Jina Family Complete Catalog

| Model | Params | Dims | Context | Formats | License |
|-------|--------|------|---------|---------|---------|
| jina-v2-small-en | 33M | 512 | 8192 | PyTorch | Apache 2.0 |
| jina-v2-base-en | 137M | 768 | 8192 | PyTorch | Apache 2.0 |
| jina-v3 | 570M | 1024 (MRL) | 8192 | PyTorch, ONNX | CC-BY-NC |
| jina-v4 | 3.8B | 2048+128/token | 32K | PyTorch, GGUF | CC-BY-NC |
| jina-v5-text-nano | 239M | 768 | 8192 | MLX, GGUF, ONNX | Apache 2.0 |
| jina-v5-text-small | 677M | 1024 | 32K | MLX, GGUF, ONNX | Apache 2.0 |
| jina-colbert-v2 | 560M | 128/token | 8192 | PyTorch | CC-BY-NC |

## Recommendation

1. **Keep jina-v5-text-nano** as default — it's #1 in class, dual-format (MLX+ONNX+GGUF)
2. **Evaluate jina-v5-text-small** (677M, 1024d) — same family, +6% MTEB, 32K context
3. **Investigate ColBERT** via answerai-colbert-small (33M, MIT) + LanceDB MaxSim — potential +6-10% OOD
4. **Apply RaBitQ quantization** to existing index — 15-20x storage reduction, <5% recall loss
5. **Defer 7-8B models** — impractical for CPU-only Linux (14-17s cold-start already at 239M)

## Sources

- Elastic blog (jina-v5), HuggingFace model cards, Jina AI model pages
- MTEB/MMTEB leaderboard, BEIR benchmark results
- LanceDB docs (multivector-search, quantization), GitHub issue #1930 (sparse vectors)
- Google Dev blog (EmbeddingGemma), IBM (granite-r2), Snowflake (arctic-embed)
- Answer.AI blog (answerai-colbert-small), Sease (ColBERT in practice)
- Qwen blog (Qwen3-Embedding), NVIDIA (NV-Embed-v2, llama-embed-nemotron)
