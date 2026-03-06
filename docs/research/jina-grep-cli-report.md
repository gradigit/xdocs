# jina-grep-cli Research Report

**Date**: 2026-03-05
**Relevance**: We use the same MLX model-loading pattern in our `JinaMlxEmbedder` class.

## What It Is

A semantic grep CLI by Jina AI (authored entirely by Han Xiao, Jina CEO). Performs embedding-based file search using cosine similarity instead of regex. Released 2026-02-26, Apache-2.0 license, 150 stars. Apple Silicon only (MLX).

**Repo**: https://github.com/jina-ai/jina-grep-cli
**Not on PyPI** — install via `git clone` + `uv pip install -e .`

Use case: "Use `grep`/`rg` when you know what to search. Use `jina-grep` when you don't." Finds semantically related code even when no keyword overlap exists.

## Architecture

5 Python modules:

| Module | Role |
|--------|------|
| `cli.py` | Click CLI entrypoint (grep-compatible flags + semantic flags) |
| `client.py` | Search logic, file traversal, cosine similarity |
| `embedder.py` | MLX model loading + inference (the pattern we borrowed) |
| `server.py` | Optional FastAPI persistent server (localhost:8089) |
| `__init__.py` | Package init |

Two embedding backends:
1. **LocalEmbedder** — in-process MLX, loads model per invocation
2. **EmbeddingClient** — HTTP client to persistent FastAPI server (~10ms/query)

Auto-detects running server; falls back to local.

## The MLX Loading Pattern (What We Use)

This is the pattern our `JinaMlxEmbedder` follows. The model's Python architecture code is NOT bundled in the pip package — it ships with the weights on HuggingFace and is loaded dynamically at runtime.

### Step 1: Download (or use cached)

```python
def _snapshot_download(repo_id: str) -> str:
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(repo_id, local_files_only=True)  # offline-first
    except Exception:
        print("Downloading model for first time...", file=sys.stderr, flush=True)
        return snapshot_download(repo_id)
```

### Step 2: Dynamic import of utils.py from downloaded repo

```python
model_dir = _snapshot_download("jinaai/jina-embeddings-v5-text-nano-mlx")

import importlib.util
spec = importlib.util.spec_from_file_location(
    f"jina_mlx_utils_{model_name}",
    os.path.join(model_dir, "utils.py"),  # from HuggingFace cache
)
utils_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(utils_mod)

multi_model = utils_mod.load_model(model_dir)
```

### Step 3: utils.py internally loads model.py (second importlib)

Inside `utils.py` from the HuggingFace repo:

```python
def load_model(model_dir: str):
    spec = importlib.util.spec_from_file_location("model", os.path.join(model_dir, "model.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    model = mod.JinaEmbeddingModel(config)
    weights = mx.load(os.path.join(model_dir, "model.safetensors"))
    model.load_weights(list(weights.items()))
    # loads tokenizer + all 4 LoRA adapters
    return JinaMultiTaskModel(model, tokenizer, adapters)
```

### How Our Code Compares

Our `JinaMlxEmbedder._ensure_loaded()` in `embeddings.py` follows the identical pattern:

```python
model_dir = snapshot_download(self.repo_id, local_files_only=True, revision=revision)
spec = ilu.spec_from_file_location("jina_mlx_utils", os.path.join(model_dir, "utils.py"))
utils_mod = ilu.module_from_spec(spec)
spec.loader.exec_module(utils_mod)
multi_model = utils_mod.load_model(model_dir)
multi_model.switch_task("retrieval")
```

Differences from jina-grep-cli:
- We pin revision via `CEX_JINA_MLX_REVISION` env var (they use latest)
- We pass `max_length=512` to `encode()` (they use model default 8192)
- We clear MLX Metal cache every 50 calls (they don't — ephemeral CLI vs long-running indexer)
- We have SentenceTransformer fallback for non-Mac; they are Apple Silicon only

## LoRA Adapter Switching

The `JinaMultiTaskModel` supports 4 tasks via in-place LoRA weight arithmetic:

```python
def switch_task(self, task: str):
    if task == self._current_task:
        return
    self._apply_adapter(self.adapters[self._current_task], sign=-1.0)  # unmerge
    self._apply_adapter(self.adapters[task], sign=+1.0)  # merge
    self._current_task = task

def _apply_adapter(self, adapter, sign=1.0):
    scale = sign * adapter["config"]["lora_alpha"] / adapter["config"]["r"]
    # W' = W + scale * (B @ A)
```

- Config: r=32, alpha=32 (scale = +/-1.0)
- Switch time: ~20ms
- Memory: 456MB total for all 4 tasks (vs 1.6GB for 4 pre-merged repos)
- Tasks: retrieval, text-matching, clustering, classification

We call `multi_model.switch_task("retrieval")` once at load time and never switch.

## HuggingFace Repo Structure

`jinaai/jina-embeddings-v5-text-nano-mlx` (~495MB total):

```
config.json                            (378B — EuroBERT-210M config)
model.py                               (9.8KB — JinaEmbeddingModel MLX class)
model.safetensors                      (424MB — base weights, float16)
tokenizer.json                         (17.2MB)
utils.py                               (4.4KB — JinaMultiTaskModel + load_model)
adapters/retrieval/adapter_model.safetensors       (~13MB, LoRA r=32)
adapters/text-matching/adapter_model.safetensors
adapters/clustering/adapter_model.safetensors
adapters/classification/adapter_model.safetensors
```

Base architecture: EuroBERT-210M (12 layers, 768 hidden, 12 heads, rope_theta=1e6). Uses `mx.fast.scaled_dot_product_attention` and `mx.fast.rope`. Last-token pooling with L2 normalization.

## Model Mapping

```python
# In jina-grep-cli's embedder.py:
MLX_MODELS = {
    "jina-embeddings-v5-small": "jinaai/jina-embeddings-v5-text-small-mlx",
    "jina-embeddings-v5-nano": "jinaai/jina-embeddings-v5-text-nano-mlx",
}
CODE_MODELS_MAP = {
    "jina-code-embeddings-0.5b": "jinaai/jina-code-embeddings-0.5b-mlx",
    "jina-code-embeddings-1.5b": "jinaai/jina-code-embeddings-1.5b-mlx",
}
```

Code models use instruction prefixes (not LoRA) for task switching.

## CLI Features

Grep-compatible flags: `-r`, `-l`, `-L`, `-c`, `-n`, `-A`/`-B`/`-C`, `--include`, `--exclude`, `-v`, `-m`, `-q`

Semantic flags: `--threshold`, `--top-k`, `--model`, `--task`, `--granularity`

Modes:
- **Standalone search**: `jina-grep "error handling" src/`
- **Pipe reranking**: `grep -rn "error" src/ | jina-grep "error handling"`
- **Zero-shot classification**: `-e "bug" -e "feature" -e "docs"` classifies to best label
- **Code search**: `--model jina-code-embeddings-0.5b --task nl2code`
- **Server management**: `jina-grep serve start/stop/status`

Granularity: line, paragraph, sentence, token (default: token, ~512-token windows at line boundaries).

## Performance

Benchmarked on M3 Ultra (512GB):

| Model | Single query | Peak throughput |
|-------|-------------|-----------------|
| v5-nano (239M) | 3ms | 77K tok/s |
| v5-small | 7.5ms | 21.6K tok/s |
| code-1.5b | 14.6ms | 7.7K tok/s |

Cold start (model load): ~5-10s total wall clock. Persistent server avoids this for repeated queries.

## Dependencies

```toml
mlx>=0.20.0
tokenizers>=0.20.0
huggingface-hub>=0.24.0
fastapi>=0.110.0
uvicorn>=0.29.0
httpx>=0.27.0
numpy>=1.26.0
click>=8.1.0
```

No PyTorch, no transformers — pure MLX inference. Same minimal dependency footprint as our `semantic-query` extra.

## License Note

CLI: Apache-2.0 (permissive). Model weights: CC-BY-NC-4.0 (non-commercial). Same license situation as our project (we evaluate on technical merit per user preference, license is not a blocker).

## Key Takeaway

jina-grep-cli is the canonical reference implementation for loading Jina v5 MLX models. Our `JinaMlxEmbedder` follows the same proven pattern — `snapshot_download` + `importlib` dynamic import of `utils.py` from the HuggingFace repo. The only substantive differences are our revision pinning (supply chain safety) and Metal cache clearing (long-running indexer vs ephemeral CLI).
