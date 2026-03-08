# Reranker Survey v2 — March 2026

## Summary

The reranking landscape has undergone a generational shift since the M1 survey. Multiple models exceed our FlashRank baseline by 5-12 nDCG points on BEIR. The strongest self-hostable upgrades are Qwen3-Reranker-0.6B (Apache 2.0, GGUF+ONNX, MTEB-R 65.80) and Jina Reranker v3 (GGUF+MLX, BEIR 61.94). LLM-based listwise rerankers show best OOD generalization (8% degradation vs 12-15% for cross-encoders).

## Tier 1: Highest Quality Self-Hostable

| Model | Params | BEIR nDCG@10 | MTEB-R | Formats | License |
|-------|--------|-------------|--------|---------|---------|
| Qwen3-Reranker-8B | 8B | - | 69.02 | GGUF | Apache 2.0 |
| Qwen3-Reranker-4B | 4B | - | 69.76 | GGUF, ONNX | Apache 2.0 |
| Qwen3-Reranker-0.6B | 0.6B | - | 65.80 | GGUF, ONNX, PyTorch | Apache 2.0 |
| Jina Reranker v3 | 597M | 61.94 | - | GGUF, MLX, PyTorch | CC-BY-NC |
| Contextual AI Rerank v2 6B | 6B | - | - | PyTorch, NVFP4 | CC-BY-NC |
| Contextual AI Rerank v2 2B | 2B | - | - | PyTorch, NVFP4 | CC-BY-NC |
| BGE-reranker-v2.5-gemma2 | 9B | 63.67 | - | PyTorch | Gemma |
| mxbai-rerank-large-v2 | 1.5B | 57.49 | - | PyTorch | Unknown |
| Zerank-2 | 4B | - | - | PyTorch | CC-BY-NC |
| Zerank-1-small | 1.7B | - | ELO 1539 | PyTorch | Apache 2.0 |

## Tier 2: Good Quality

| Model | Params | BEIR nDCG@10 | Formats | License |
|-------|--------|-------------|---------|---------|
| BGE-reranker-v2-m3 | 568M | ~56.5 | PyTorch | Apache 2.0 |
| mxbai-rerank-base-v2 | 0.5B | 55.57 | PyTorch | Unknown |
| GTE-multilingual-reranker-base | 0.3B | ~53 | PyTorch, GGUF | Apache 2.0 |
| Jina Reranker v2 | 278M | 57.06 | PyTorch, ONNX | CC-BY-NC |
| NVIDIA nv-rerankqa-1b-v2 | 1B | - | PyTorch | Open commercial |

## Tier 3: Current Baseline

| Model | Params | TREC DL19 | BEIR est. | Formats |
|-------|--------|-----------|----------|---------|
| FlashRank MiniLM-L12 (current) | 33M | 70.80 | ~57 | ONNX |

## Format Availability Matrix (for our dual deployment)

| Model | macOS MLX | Linux GGUF | Linux ONNX | Linux PyTorch |
|-------|-----------|-----------|------------|---------------|
| Jina Reranker v3 | Official | Official | No | Yes |
| Qwen3-Reranker-0.6B | No | Community | Community | Yes |
| Qwen3-Reranker-4B | No | Community | Community | Yes |

## Reranking Architecture Taxonomy

| Architecture | Quality | Speed | Examples |
|-------------|---------|-------|----------|
| Cross-encoder (BERT) | Good (TREC ~70-74) | Fast | MiniLM, BGE-v2-m3, mxbai |
| Decoder-only pointwise | Better (TREC ~71-73) | Medium | MonoT5, Qwen3-Reranker |
| Decoder-only listwise | Best generalizing (8% OOD) | Medium | RankZephyr, Jina v3 |
| Reasoning-augmented | Highest | Slow | Rank1, Rank-K, REARANK |

## Recommendation

**macOS runtime**: Keep Jina Reranker v3 MLX (already chosen, official MLX weights, 61.94 BEIR).

**Linux maintainer**: Deploy Qwen3-Reranker-0.6B via GGUF (llama-cpp-python) or ONNX. It scores higher on MTEB-R (65.80 vs Jina's 61.94 BEIR — different benchmarks but Qwen3 is consistently rated higher). Has sentence-transformers seq-cls conversion (tomaarsen/Qwen3-Reranker-0.6B-seq-cls) for easy integration.

**Backend-agnostic pattern**: Mirror embeddings.py with CEX_RERANKER_BACKEND env var. Default: Jina MLX on macOS, Qwen3 GGUF/ONNX on Linux.

## Integration Libraries

| Library | Supports Qwen3 | Supports Jina v3 | Notes |
|---------|----------------|-------------------|-------|
| sentence-transformers v4+ | Via seq-cls conversion | No | ONNX/OpenVINO backends |
| FlashRank | No | No | ONNX only, limited models |
| rerankers (AnswerDotAI) | Via CrossEncoder | Via CrossEncoder | Unified API |
| llama-cpp-python | GGUF natively | GGUF natively | CPU + CUDA |

## Sources

- HuggingFace model cards: Qwen3-Reranker-0.6B, jinaai/jina-reranker-v3, mixedbread-ai/mxbai-rerank-large-v2
- EMNLP 2025 empirical study (arxiv 2508.16757): 22 methods, 40 variants
- Agentset reranker leaderboard (Feb 2026)
- ZeroEntropy guide (zerank-1, zerank-2, zELO training)
- Contextual AI Rerank v2 blog
- FlashRank GitHub, rank-llm GitHub, rerankers GitHub
