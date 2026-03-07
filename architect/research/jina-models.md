# Jina Reranker Model Survey — HuggingFace

## Summary

9 official Jina reranker models exist. None beats FlashRank MiniLM-L12 under our constraints.

## Model Comparison

| Model | Params | Size (ONNX int8) | BEIR nDCG@10 | License | Linux CPU | Context |
|-------|--------|-------------------|--------------|---------|-----------|---------|
| v1-tiny | 33M | 31.9MB | 48.54 | Apache 2.0 | Yes | 8,192 |
| v1-turbo | 37.8M | 36.5MB | 49.60 | Apache 2.0 | Yes | 8,192 |
| v1-base | 137M | API-only | 52.45 | Apache 2.0 | No (API) | 8,192 |
| v2-base | 278M | 267MB | 57.06 | CC-BY-NC | Yes | 1,024 |
| v3 | 597M | No ONNX (GGUF only) | 61.94 | CC-BY-NC | GGUF only | 131K |
| v3-MLX | 597M | N/A | 61.94 | CC-BY-NC | macOS only | 131K |
| m0 | 2.4B | No ONNX | 58.95 | CC-BY-NC | No | vision |
| **FlashRank MiniLM-L12** | **33M** | **34MB** | **~57 est.** | **Apache 2.0** | **Yes** | **512** |

## Key Findings

1. **v1 models (Apache 2.0)**: Official ONNX exports with 7 quantization variants each. Quality is lower than FlashRank (BEIR 48-50 vs ~57).
2. **v2/v3 (higher quality)**: All CC-BY-NC-4.0 — non-commercial restriction. v2 is 267MB ONNX int8. v3 has no ONNX, only GGUF via custom llama.cpp fork (397MB-1.2GB).
3. **v3 architecture**: Decoder-only (Qwen3-0.6B backbone), listwise reranking (64 docs simultaneously). Innovative but complex integration.
4. **Community conversions**: GGUF versions exist for v1/v2 (mradermacher, gpustack). No community ONNX for v2/v3.
5. **v1 requires trust_remote_code=True** for PyTorch loading (custom JinaBERT with ALiBi attention).

## Recommendation

**Keep FlashRank ms-marco-MiniLM-L-12-v2.** No Jina model is strictly better under all constraints:
- v1: lower quality (BEIR 48-50 vs ~57)
- v2: CC-BY-NC license, 267MB
- v3: CC-BY-NC, no ONNX, 640MB+ GGUF, custom llama.cpp fork required

The only scenario to revisit: if Jina releases v4 under Apache 2.0 with ONNX support.
