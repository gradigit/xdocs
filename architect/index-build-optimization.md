# Index Build Optimization

## Problem

Full LanceDB index rebuild took **15+ hours** on RTX 4070 Ti SUPER (16 GB VRAM). Previous build was ~140 min. The regression is caused by OOM cascading: the last ~4,000 longest chunks (sorted ascending by length) all fail at batch_size=64 and fall back to batch_size=1, where each chunk takes ~0.5s individually.

## Current Architecture

- Model: `jina-embeddings-v5-text-small` (Qwen3-0.6B backbone, 1024 dims)
- VRAM usage: ~15.6 GB of 16 GB (barely fits)
- Chunks: ~337K total, max_tokens=512 (~1,536 chars), actual max ~1,735 chars
- Sort: ascending by text length (short chunks first, long last)
- Outer batch: 64 chunks passed to `embed_texts()`
- Inner batch: SentenceTransformers `encode(batch_size=128)` — processes all 64 at once
- VRAM clear: every 3,200 chunks (`batch_size * 50`)
- OOM handling: catch error, `torch.cuda.empty_cache()`, retry each chunk individually

## Why 15 Hours

1. **Batch_size=64 is too large for long chunks.** A batch of 64 chunks at 1,500+ chars each tokenizes to ~64 × 500 tokens. The attention matrix + intermediate states for 500-token sequences is ~3x larger than for 170-token (average) sequences. This pushes VRAM over 16 GB.

2. **OOM retry is all-or-nothing.** When 1 chunk in a batch of 64 causes OOM, all 64 are retried individually. The 63 short-enough chunks get embedded one at a time instead of in a batch.

3. **VRAM fragmentation.** `torch.cuda.empty_cache()` releases cached blocks but doesn't defragment. After 10+ hours, the allocator has thousands of small free blocks that can't be coalesced into one large allocation.

4. **Inner batch_size=128 fights outer batch_size=64.** SentenceTransformers' encode() with batch_size=128 processes all 64 texts in one GPU pass (64 < 128), maximizing VRAM pressure.

## Fixes (ranked by impact)

### Fix 1: Dynamic Batch Sizing (HIGH impact, LOW effort)

Replace fixed `batch_size=64` with length-adaptive batching:

```python
def _adaptive_batch_size(text_len: int) -> int:
    """Batch size based on chunk character length."""
    if text_len < 600:    return 64   # short chunks: full batch
    if text_len < 1000:   return 32   # medium chunks
    if text_len < 1400:   return 16   # long chunks
    return 4                           # extreme chunks

# In build_index(), replace fixed batching:
i = 0
while i < len(all_chunks):
    text_len = len(all_chunks[i]["text"])
    bs = _adaptive_batch_size(text_len)
    batch = all_chunks[i : i + bs]
    _embed_batch(batch)
    i += len(batch)
```

**Expected impact:** Eliminates all OOM retries. Long chunks get small batches that fit in VRAM. Short chunks still get full batch throughput.

### Fix 2: Lower Inner Batch Size (MEDIUM impact, TRIVIAL effort)

In `embeddings.py`, SentenceTransformersEmbedder.embed_texts():

```python
# Change line 166:
arr = model.encode(texts, ..., batch_size=128)
# To:
arr = model.encode(texts, ..., batch_size=32)
```

Forces SentenceTransformers to process texts in sub-batches of 32, reducing peak VRAM per encode() call. Combined with outer batch_size=64, this means at most 32 texts in GPU memory at once.

### Fix 3: More Frequent VRAM Clear (MEDIUM impact, TRIVIAL effort)

```python
# Change line 510:
if _has_cuda and chunks_embedded % (batch_size * 50) < batch_size:
# To:
if _has_cuda and chunks_embedded % 500 < batch_size:
```

Clears VRAM cache every 500 chunks instead of 3,200. Reduces fragmentation accumulation.

### Fix 4: Smart Incremental Rebuild (HUGE impact, MEDIUM effort)

Current `--incremental` only adds new/changed pages. A "smart full rebuild" would:

1. Read all existing chunk content_hashes from LanceDB
2. Chunk all pages
3. Skip chunks whose content_hash + chunk_index already exist in the index
4. Only embed truly new/changed chunks
5. Delete chunks for removed pages

For routine maintenance (weekly sync finds 50 new pages), this turns a 2-hour build into a 2-minute incremental update. The current `--incremental` already does most of this — the gap is that `build-index` (without `--incremental`) drops the entire table and rebuilds from scratch. There's no "rebuild but keep unchanged chunks" mode.

**Implementation:** In `build_index()`, when not incremental, instead of `lance_db.drop_table()`, open the existing table, compute the set of (page_id, content_hash) pairs that need updating, delete stale rows, and only embed the delta.

### Fix 5: Cap Max Chunk Size (LOW impact, LOW effort)

Reduce `max_tokens` from 512 to 384 in `chunker.py`. This caps chunks at ~1,152 chars instead of 1,536. Fewer long chunks = less OOM pressure. Risk: slight quality reduction on retrieval for long sections.

### Fix 6: Quantized Model (LARGE impact, MEDIUM effort)

Use float16 or int8 quantization for the embedding model. Halves VRAM usage, roughly doubles throughput. SentenceTransformers supports this via `model.half()` or `torch.quantization`. Needs quality validation on the golden QA benchmark.

## Recommended Implementation Order

1. **Now:** Fix 1 (dynamic batch) + Fix 2 (inner batch=32) + Fix 3 (clear every 500)
   - Expected: 15 hours → ~90 minutes
   - Zero quality impact, pure efficiency

2. **Next milestone:** Fix 4 (smart incremental)
   - Expected: routine rebuilds from ~90 min → ~2-5 min
   - Biggest long-term win

3. **If needed:** Fix 6 (quantization) for further speedup
   - Only if 90 min is still too slow

## Benchmark Data

From the 2026-04-07 build (15h 8m):
- 337,225 chunks from 11,471 pages
- 20 pages >50K words producing ~25K chunks in the long tail
- 14 OOM events, each retrying 64 chunks individually
- Top 5 pages by chunk count: OKX (3,494), Gate.io (2,550), openxapi (1,788), HTX-swap (1,367), HTX-dm (1,353)
- Chunks >1,500 chars: 2,319 (all in the OOM danger zone at batch_size=64)

Previous build (2026-03-08, same hardware): ~100 min embed + 40 min OOM retries = 140 min total.
Difference: the store grew from 339K → 337K chunks (fewer chunks!) but OOM retries cascaded worse due to VRAM fragmentation over the longer run.
