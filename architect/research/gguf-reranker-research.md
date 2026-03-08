# GGUF Reranker Research — March 2026

## Key Findings

### llama-cpp-python Has NO Reranking API
- Python bindings lack `rerank()` method (issue #1794 open, PR #1820 not merged)
- C++ llama.cpp supports `LLAMA_POOLING_TYPE_RANK` (PR #9510) but Python doesn't expose it
- Workaround: `llama-server --rerank` HTTP endpoint, or subprocess calls

### Qwen3-Reranker-0.6B GGUF
- **Only ggml-org conversion works**: `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF` (639MB)
- Community conversions (Mungert, QuantFactory) produce wrong scores
- Scoring: yes/no token logit extraction + softmax
- MTEB-R: 65.80 (vs FlashRank ~57 BEIR, MiniLM-L12 ~57 BEIR)

### Jina Reranker v3 GGUF — NOT Viable
- Requires Hanxiao's custom llama.cpp fork (not mainline)
- Uses subprocess calls to `llama-embedding` binary + separate `projector.safetensors`
- Too fragile for production. PyTorch path (`_load_jina_v3()`) is simpler and works on CUDA.

### RECOMMENDED: Qwen3-Reranker-0.6B seq-cls Conversion
- `tomaarsen/Qwen3-Reranker-0.6B-seq-cls` — loads via `sentence_transformers.CrossEncoder`
- **Zero new dependencies** (sentence-transformers 5.2.3 already installed)
- Mathematically equivalent: `classifier_weight = yes_vector - no_vector`
- Conversion by Tom Aarsen (sentence-transformers maintainer)
- Requires specific prompt template with `<|im_start|>` markers

### Integration Code
```python
from sentence_transformers import CrossEncoder

model = CrossEncoder("tomaarsen/Qwen3-Reranker-0.6B-seq-cls")

def format_query(query):
    prefix = ('<|im_start|>system\nJudge whether the Document meets the '
              'requirements based on the Query and the Instruct provided. '
              'Note that the answer can only be "yes" or "no".<|im_end|>\n'
              '<|im_start|>user\n')
    instruction = "Given a web search query, retrieve relevant passages that answer the query"
    return f"{prefix}<Instruct>: {instruction}\n<Query>: {query}\n"

def format_document(doc):
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    return f"<Document>: {doc}{suffix}"

pairs = [[format_query(q), format_document(d)] for q, d in zip(queries, docs)]
scores = model.predict(pairs)
```

### Performance Expectations (RTX 4070 Ti SUPER)
- PyTorch CrossEncoder (0.6B, batch=20): ~50-100ms
- GGUF llama-server (0.6B, Q8_0): ~100-200ms
- FlashRank ONNX (33M, CPU): ~80-300ms

## Conclusion
Skip GGUF for now — the seq-cls conversion gives us a 600M Qwen3 reranker via the
existing CrossEncoder infrastructure. No new deps, CUDA-accelerated, quality leader
(MTEB-R 65.80). Benchmark it head-to-head against MiniLM-L12 and FlashRank on 180 queries.

## Sources
- llama-cpp-python issue #1794 (no rerank API)
- ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF (HuggingFace)
- tomaarsen/Qwen3-Reranker-0.6B-seq-cls (HuggingFace)
- Qwen3-Reranker conversion discussion (HF discussions/3)
- llama.cpp issue #16407 (GGUF bug fix)
- llama.cpp issue #17189 (Jina v3 not supported in mainline)
