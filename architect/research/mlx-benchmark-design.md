# MLX Benchmark Design — March 2026

## Models to Test

| Model | Type | Params | Dims | Size | Repo |
|-------|------|--------|------|------|------|
| jina-v5-text-small-mlx | Embedding | 677M | 1024 | 1.3GB | jinaai/jina-embeddings-v5-text-small-mlx |
| jina-v5-text-nano-mlx | Embedding | 200M | 768 | ~400MB | jinaai/jina-embeddings-v5-text-nano-mlx |
| jina-reranker-v3-mlx | Reranker | 0.6B | N/A | 1.2GB | jinaai/jina-reranker-v3-mlx |

No other MLX rerankers exist. Jina v3 MLX is the only one.

## Benchmark Phases

1. **Embedding quality**: 180 queries via `semantic_search(query_type="vector", rerank=False)`
2. **Embedding throughput**: Batch size sweep (1, 16, 32, 64), measure embeddings/sec
3. **Reranker quality**: Top-30 candidates → rerank → compare nDCG@5 lift
4. **Memory profile**: `mx.metal.get_active_memory()`, `get_peak_memory()`, `get_cache_memory()`

## MLX-Specific Protocol

- **Warm-up**: 3 semantic_search calls before timing (shader compilation)
- **10 warm-up iterations** for raw throughput measurement
- **`mx.eval()` synchronization** after each operation for accurate timing
- **`mx.clear_cache()`** before each phase, not between queries
- **Memory monitoring**: `mx.metal.reset_peak_memory()` before each phase

## Output Format
JSON report with `embedding_quality`, `embedding_throughput`, `reranker_quality`,
`memory_profile` sections. Compatible with Linux benchmark for cross-platform comparison.

## Script Design
Self-contained `scripts/benchmark_mlx.py`:
- Checks `platform.system() == "Darwin"` and MLX availability
- Uses existing project APIs (get_embedder, semantic_search, rerank)
- `--docs-dir`, `--json`, `--skip-reranker`, `--compare`, `--batch-sizes` flags
- Includes pip install instructions in docstring

## Sources
- MLX compilation docs (warm-up guidance)
- MLX Metal memory API docs
- mlx issue #2254 (Metal cache bloat)
- jinaai/jina-embeddings-v5-text-small-mlx HuggingFace
- jinaai/jina-reranker-v3-mlx HuggingFace
