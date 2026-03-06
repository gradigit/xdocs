# Reranker Survey

## Top 3 Recommendations

### 1. FlashRank + ms-marco-MiniLM-L-12-v2 (PRIMARY)
- 34MB model, ~80ms for 20 docs, ~200ms for 50 docs
- Zero PyTorch dependency (onnxruntime + tokenizers only)
- NDCG@10=74.31 on TREC DL 2019
- Apache 2.0 license
- Total install: ~134MB (onnxruntime + model)

### 2. sentence-transformers CrossEncoder + ONNX (ALTERNATIVE)
- Already have sentence-transformers via [semantic] extra
- ms-marco-MiniLM-L6-v2 with ONNX backend: 91MB, ~50ms for 20 docs
- mxbai-rerank-xsmall-v1 for better out-of-domain: 142MB, ~150ms
- int8 quantization: ~3x CPU speedup, halves model size

### 3. Backend-agnostic with env var (FUTURE)
- Mirror embeddings.py pattern: CEX_RERANKER_BACKEND env var
- Default FlashRank on Linux, sentence-transformers fallback
- CEX_RERANKER_MODEL for model selection

## Comparison Table

| Model | Params | Size | Score | CPU 20 docs | License | PyTorch |
|-------|--------|------|-------|-------------|---------|---------|
| FlashRank TinyBERT-L2 | 4.4M | 4MB | 69.84 TREC | ~20ms | Apache 2.0 | No |
| FlashRank MiniLM-L12 | 33M | 34MB | 74.31 TREC | ~80ms | Apache 2.0 | No |
| CE MiniLM-L6-v2 | 22.7M | 91MB | 74.30 TREC | ~50ms | Apache 2.0 | Yes |
| mxbai-rerank-xsmall | 70.8M | 142MB | 43.9 BEIR | ~150ms | Apache 2.0 | Yes |
| bge-reranker-v2-m3 | 568M | 1.1GB | 84 custom | 200-400ms | Apache 2.0 | Yes |
| Qwen3-Reranker-0.6B | 600M | 1.2GB | 65.80 MTEB-R | ~380ms | Apache 2.0 | Yes |
| jina-reranker-v2 | 278M | 560MB | 53.17 BEIR | ~200ms | CC-BY-NC | Yes |

## Key Insight from QMD
QMD uses Qwen3-Reranker-0.6B in GGUF format (~640MB) via node-llama-cpp. They specifically reduced context to 2048 tokens for 20x memory savings. If we go GGUF route, llama-cpp-python is the Python equivalent. But FlashRank is simpler and sufficient.

## Integration Plan
Replace `reranker.py` entirely. Current implementation is MLX-only (macOS). New implementation:
- Lazy-load FlashRank Ranker
- Same `rerank()` signature
- Update pyproject.toml [reranker] extra: `flashrank>=0.2.9`
- Remove mlx, mlx-lm, huggingface_hub from [reranker] deps

## Rejected Options
- **jina-reranker-v2-base**: CC-BY-NC-4.0 license (non-commercial)
- **bge-reranker-v2-m3**: 568M params, 1.1GB, exceeds size/latency budget
- **Qwen3-Reranker-0.6B**: Highest quality but 380ms CPU, complex integration (causal LM, special formatting)
- **Cohere rerank**: API-only, violates local-only constraint
