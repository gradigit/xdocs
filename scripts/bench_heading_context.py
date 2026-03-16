#!/usr/bin/env python3
"""Simulate the impact of prepending heading breadcrumb context to chunks before embedding.

Compares cosine similarity rankings between original chunks and chunks with
"[{exchange} | {heading}]" prepended, across 10 API-docs-relevant queries.
"""

import json
import random
import sys
import time

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# 1. Load embedder and LanceDB
# ---------------------------------------------------------------------------
print("=" * 80)
print("HEADING CONTEXT EMBEDDING SIMULATION")
print("=" * 80)

print("\n[1/6] Loading Qwen3 embedding model via project embedder...")
t0 = time.monotonic()
from xdocs.embeddings import get_embedder

embedder = get_embedder()
ndims = embedder.ndims()
print(f"  Model loaded: {embedder.model_name} ({embedder.backend_name})")
print(f"  Dimensions: {ndims}")
print(f"  Load time: {time.monotonic() - t0:.1f}s")

# ---------------------------------------------------------------------------
# 2. Read 100 random chunks with non-empty headings from LanceDB
# ---------------------------------------------------------------------------
print("\n[2/6] Reading chunks from LanceDB...")
import lancedb

db = lancedb.connect(str(REPO_ROOT / "cex-docs" / "lancedb-index"))
table = db.open_table("pages")
total_rows = table.count_rows()
print(f"  Total rows in index: {total_rows:,}")

# Strategy: use vector search with a zero vector to get diverse chunks,
# filtered to non-empty headings with meaningful text (len > 50).
# We'll sample from multiple exchange-targeted queries to get diversity.
dummy_vec = np.zeros(ndims).tolist()

# Get a large sample, then randomly pick 100 with non-empty heading + text
print("  Fetching candidate chunks...")
candidates_df = (
    table.search(dummy_vec)
    .where('heading != "" AND length(text) > 50')
    .select(["text", "heading", "exchange", "domain", "url", "title", "page_id", "chunk_index"])
    .limit(2000)
    .to_pandas()
)
print(f"  Candidates with non-empty heading + text>50: {len(candidates_df)}")

# Filter further: ensure reasonable text lengths and exchange diversity
candidates_df = candidates_df[candidates_df["text"].str.len() > 80].copy()
candidates_df = candidates_df[candidates_df["text"].str.len() < 3000].copy()
print(f"  After length filter (80-3000 chars): {len(candidates_df)}")

# Sample 100 with exchange diversity
random.seed(42)
np.random.seed(42)

# Stratified sampling: try to get chunks from many exchanges
exchanges = candidates_df["exchange"].unique().tolist()
print(f"  Exchanges represented: {exchanges}")

sampled_indices = []
# First pass: sample up to 8 per exchange
per_exchange = max(2, 100 // len(exchanges))
for exch in exchanges:
    exch_df = candidates_df[candidates_df["exchange"] == exch]
    n_take = min(per_exchange, len(exch_df))
    sampled_indices.extend(exch_df.sample(n=n_take, random_state=42).index.tolist())

# Fill remaining from all candidates
remaining = 100 - len(sampled_indices)
if remaining > 0:
    remaining_pool = candidates_df[~candidates_df.index.isin(sampled_indices)]
    if len(remaining_pool) >= remaining:
        sampled_indices.extend(remaining_pool.sample(n=remaining, random_state=42).index.tolist())
    else:
        sampled_indices.extend(remaining_pool.index.tolist())

# Truncate to exactly 100
sampled_indices = sampled_indices[:100]
chunks_df = candidates_df.loc[sampled_indices].reset_index(drop=True)
print(f"  Selected {len(chunks_df)} chunks")
print(f"  Exchange distribution:")
for exch, cnt in chunks_df["exchange"].value_counts().items():
    print(f"    {exch}: {cnt}")

# ---------------------------------------------------------------------------
# 3. Create original and context-prepended versions
# ---------------------------------------------------------------------------
print("\n[3/6] Creating original and context-prepended chunk versions...")

original_texts = []
context_texts = []
chunk_metadata = []

for _, row in chunks_df.iterrows():
    orig = row["text"]
    exchange = row["exchange"]
    heading = row["heading"]
    # Clean heading: strip markdown # prefixes and zero-width spaces
    clean_heading = heading.lstrip("#").strip().replace("\u200b", "")

    context_prefix = f"[{exchange} | {clean_heading}]\n\n"
    ctx_text = context_prefix + orig

    original_texts.append(orig)
    context_texts.append(ctx_text)
    chunk_metadata.append({
        "exchange": exchange,
        "heading": heading,
        "clean_heading": clean_heading,
        "url": row["url"],
        "title": row["title"],
        "page_id": int(row["page_id"]),
        "chunk_index": int(row["chunk_index"]),
        "text_preview": orig[:120].replace("\n", " "),
        "text_len": len(orig),
    })

print(f"  Original texts: {len(original_texts)}")
print(f"  Context texts:  {len(context_texts)}")
print(f"  Avg original length: {np.mean([len(t) for t in original_texts]):.0f} chars")
print(f"  Avg context length:  {np.mean([len(t) for t in context_texts]):.0f} chars")

# ---------------------------------------------------------------------------
# 4. Define test queries
# ---------------------------------------------------------------------------
queries = [
    "Binance rate limit",
    "how to place an order on Bybit",
    "OKX funding rate",
    "KuCoin authentication",
    "account balance endpoint",
    "WebSocket connection",
    "error code -1002",
    "margin trading API",
    "withdrawal limits",
    "API key permissions",
]

print(f"\n[4/6] Defined {len(queries)} test queries:")
for i, q in enumerate(queries):
    print(f"  {i+1:2d}. {q}")

# ---------------------------------------------------------------------------
# 5. Embed everything
# ---------------------------------------------------------------------------
print("\n[5/6] Embedding all texts...")

# Embed queries
print("  Embedding queries...")
t0 = time.monotonic()
query_vectors = embedder.embed_texts(queries, is_query=True)
print(f"    {len(queries)} queries embedded in {time.monotonic() - t0:.2f}s")

# Embed original chunks (in batches)
print("  Embedding original chunks...")
t0 = time.monotonic()
batch_size = 32
orig_vectors = []
for i in range(0, len(original_texts), batch_size):
    batch = original_texts[i:i + batch_size]
    orig_vectors.extend(embedder.embed_texts(batch))
    if (i + batch_size) % 64 == 0 or i + batch_size >= len(original_texts):
        print(f"    Progress: {min(i + batch_size, len(original_texts))}/{len(original_texts)}")
print(f"    {len(orig_vectors)} original chunks embedded in {time.monotonic() - t0:.1f}s")

# Embed context-prepended chunks
print("  Embedding context-prepended chunks...")
t0 = time.monotonic()
ctx_vectors = []
for i in range(0, len(context_texts), batch_size):
    batch = context_texts[i:i + batch_size]
    ctx_vectors.extend(embedder.embed_texts(batch))
    if (i + batch_size) % 64 == 0 or i + batch_size >= len(context_texts):
        print(f"    Progress: {min(i + batch_size, len(context_texts))}/{len(context_texts)}")
print(f"    {len(ctx_vectors)} context chunks embedded in {time.monotonic() - t0:.1f}s")

# Convert to numpy arrays for fast cosine similarity
query_vecs = np.array(query_vectors)
orig_vecs = np.array(orig_vectors)
ctx_vecs = np.array(ctx_vectors)

# Normalize for cosine similarity
def normalize(vecs):
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms

query_vecs = normalize(query_vecs)
orig_vecs = normalize(orig_vecs)
ctx_vecs = normalize(ctx_vecs)

# ---------------------------------------------------------------------------
# 6. Compute similarity and compare rankings
# ---------------------------------------------------------------------------
print("\n[6/6] Computing cosine similarities and comparing rankings...\n")

# For each query, compute cosine similarity against all chunks
orig_sims = query_vecs @ orig_vecs.T   # (10, 100)
ctx_sims = query_vecs @ ctx_vecs.T     # (10, 100)

# Determine relevance: a chunk is "relevant" to a query if:
# - The query mentions an exchange name that matches the chunk's exchange
# - OR the chunk's heading/text is topically related to the query
# We'll use a combination: exchange match OR high original similarity as proxy

# Exchange keywords in queries
query_exchange_map = {
    0: ["binance"],        # "Binance rate limit"
    1: ["bybit"],          # "how to place an order on Bybit"
    2: ["okx"],            # "OKX funding rate"
    3: ["kucoin"],         # "KuCoin authentication"
    4: [],                 # "account balance endpoint" - generic
    5: [],                 # "WebSocket connection" - generic
    6: ["binance"],        # "error code -1002" - Binance-specific error
    7: [],                 # "margin trading API" - generic
    8: [],                 # "withdrawal limits" - generic
    9: [],                 # "API key permissions" - generic
}

# Topic keywords for heading matching
query_topic_keywords = {
    0: ["rate limit", "rate-limit", "ratelimit", "request weight", "throttl"],
    1: ["order", "place order", "new order", "create order", "trade"],
    2: ["funding", "funding rate", "fund"],
    3: ["auth", "authentication", "api key", "signature", "sign", "hmac"],
    4: ["balance", "account", "wallet", "asset"],
    5: ["websocket", "ws", "socket", "stream", "connection"],
    6: ["error", "-1002", "error code"],
    7: ["margin", "leverage", "cross", "isolated"],
    8: ["withdraw", "withdrawal", "transfer"],
    9: ["permission", "api key", "key", "auth", "scope"],
}


def is_relevant(query_idx: int, chunk_idx: int) -> tuple[bool, str]:
    """Determine if chunk is relevant to query. Returns (relevant, reason)."""
    meta = chunk_metadata[chunk_idx]
    exchange = meta["exchange"].lower()
    heading_lower = meta["clean_heading"].lower()
    text_lower = original_texts[chunk_idx][:500].lower()

    reasons = []

    # Check exchange match
    target_exchanges = query_exchange_map.get(query_idx, [])
    exchange_match = any(ex in exchange for ex in target_exchanges) if target_exchanges else False

    # Check topic match (heading OR text)
    topic_kws = query_topic_keywords.get(query_idx, [])
    heading_topic_match = any(kw in heading_lower for kw in topic_kws)
    text_topic_match = any(kw in text_lower for kw in topic_kws)

    if exchange_match and (heading_topic_match or text_topic_match):
        return True, "exchange+topic"
    if exchange_match and not target_exchanges:
        pass  # No exchange filter, skip exchange-only match
    if heading_topic_match:
        return True, "heading_topic"
    if text_topic_match and exchange_match:
        return True, "exchange+text_topic"

    return False, ""


# Build relevance matrix
relevance = np.zeros((len(queries), len(chunk_metadata)), dtype=bool)
relevance_reasons = {}
for qi in range(len(queries)):
    for ci in range(len(chunk_metadata)):
        rel, reason = is_relevant(qi, ci)
        relevance[qi, ci] = rel
        if rel:
            relevance_reasons[(qi, ci)] = reason

print("=" * 80)
print("RESULTS")
print("=" * 80)

# --- Summary statistics ---
print("\n--- Relevance Summary ---")
for qi, query in enumerate(queries):
    rel_count = relevance[qi].sum()
    rel_exchanges = set(chunk_metadata[ci]["exchange"] for ci in range(len(chunk_metadata)) if relevance[qi, ci])
    print(f"  Q{qi+1:2d} ({query}): {rel_count} relevant chunks | exchanges: {rel_exchanges or '{generic}'}")

# --- Per-query analysis ---
print("\n" + "=" * 80)
print("PER-QUERY RANKING ANALYSIS")
print("=" * 80)

all_rank_changes = []
all_sim_changes = []
top5_overlaps = []
context_helps_examples = []
context_hurts_examples = []

for qi, query in enumerate(queries):
    print(f"\n{'─' * 70}")
    print(f"Query {qi+1}: \"{query}\"")
    print(f"{'─' * 70}")

    # Get rankings (descending similarity)
    orig_ranking = np.argsort(-orig_sims[qi])   # chunk indices sorted by orig sim
    ctx_ranking = np.argsort(-ctx_sims[qi])      # chunk indices sorted by ctx sim

    # Build rank maps
    orig_rank_map = {idx: rank for rank, idx in enumerate(orig_ranking)}
    ctx_rank_map = {idx: rank for rank, idx in enumerate(ctx_ranking)}

    # Top-5 overlap
    orig_top5 = set(orig_ranking[:5].tolist())
    ctx_top5 = set(ctx_ranking[:5].tolist())
    overlap = len(orig_top5 & ctx_top5)
    top5_overlaps.append(overlap)

    print(f"\n  Top-5 overlap: {overlap}/5")

    # Show top-5 for each
    print(f"\n  Original Top-5:")
    for rank in range(5):
        ci = orig_ranking[rank]
        meta = chunk_metadata[ci]
        sim = orig_sims[qi, ci]
        rel = "***" if relevance[qi, ci] else "   "
        print(f"    {rel} #{rank+1} sim={sim:.4f} [{meta['exchange']}] {meta['clean_heading'][:50]}")

    print(f"\n  Context-Prepended Top-5:")
    for rank in range(5):
        ci = ctx_ranking[rank]
        meta = chunk_metadata[ci]
        sim = ctx_sims[qi, ci]
        rel = "***" if relevance[qi, ci] else "   "
        ctx_orig_rank = orig_rank_map[ci] + 1
        direction = "=" if ctx_orig_rank == rank + 1 else ("^" if ctx_orig_rank > rank + 1 else "v")
        print(f"    {rel} #{rank+1} sim={sim:.4f} [{meta['exchange']}] {meta['clean_heading'][:50]}  (was #{ctx_orig_rank} {direction})")

    # Analyze relevant chunks
    relevant_indices = [ci for ci in range(len(chunk_metadata)) if relevance[qi, ci]]

    if relevant_indices:
        print(f"\n  Relevant chunk rank changes ({len(relevant_indices)} chunks):")
        query_rank_changes = []
        query_sim_changes = []

        for ci in relevant_indices:
            orig_rank = orig_rank_map[ci] + 1
            ctx_rank = ctx_rank_map[ci] + 1
            rank_change = orig_rank - ctx_rank  # positive = improved (moved up)
            sim_change = ctx_sims[qi, ci] - orig_sims[qi, ci]

            query_rank_changes.append(rank_change)
            query_sim_changes.append(sim_change)
            all_rank_changes.append(rank_change)
            all_sim_changes.append(sim_change)

            meta = chunk_metadata[ci]
            reason = relevance_reasons.get((qi, ci), "")
            direction = "IMPROVED" if rank_change > 0 else ("WORSENED" if rank_change < 0 else "SAME")

            if abs(rank_change) >= 2:
                example = {
                    "query": query,
                    "exchange": meta["exchange"],
                    "heading": meta["clean_heading"],
                    "orig_rank": orig_rank,
                    "ctx_rank": ctx_rank,
                    "rank_change": rank_change,
                    "orig_sim": float(orig_sims[qi, ci]),
                    "ctx_sim": float(ctx_sims[qi, ci]),
                    "text_preview": meta["text_preview"][:100],
                }
                if rank_change > 0:
                    context_helps_examples.append(example)
                else:
                    context_hurts_examples.append(example)

            if len(relevant_indices) <= 10 or abs(rank_change) >= 3:
                print(f"    [{meta['exchange']}] \"{meta['clean_heading'][:40]}\"")
                print(f"      Rank: #{orig_rank} -> #{ctx_rank} ({'+' if rank_change>0 else ''}{rank_change}) {direction}")
                print(f"      Sim:  {orig_sims[qi,ci]:.4f} -> {ctx_sims[qi,ci]:.4f} ({'+' if sim_change>0 else ''}{sim_change:.4f})")
                print(f"      Match: {reason}")

        if query_rank_changes:
            mean_change = np.mean(query_rank_changes)
            print(f"\n  Summary: mean rank change = {'+' if mean_change>0 else ''}{mean_change:.1f} "
                  f"(positive = improved)")
            print(f"  Mean sim change: {'+' if np.mean(query_sim_changes)>0 else ''}{np.mean(query_sim_changes):.4f}")
    else:
        print(f"\n  No explicitly relevant chunks in sample for this query")
        # Still show top-5 similarity changes
        for rank in range(min(5, len(orig_ranking))):
            ci = orig_ranking[rank]
            orig_rank = rank + 1
            ctx_rank = ctx_rank_map[ci] + 1
            change = orig_rank - ctx_rank
            print(f"    Top-{rank+1} [{chunk_metadata[ci]['exchange']}] "
                  f"\"{chunk_metadata[ci]['clean_heading'][:40]}\" "
                  f"rank: #{orig_rank}->{ctx_rank} ({'+' if change>0 else ''}{change})")


# ---------------------------------------------------------------------------
# AGGREGATE ANALYSIS
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("AGGREGATE ANALYSIS")
print("=" * 80)

print(f"\n--- Rank Changes (across all relevant chunk-query pairs) ---")
if all_rank_changes:
    rc = np.array(all_rank_changes)
    print(f"  Total relevant (chunk, query) pairs: {len(rc)}")
    print(f"  Mean rank change:   {'+' if rc.mean()>0 else ''}{rc.mean():.2f} (positive = improved)")
    print(f"  Median rank change: {'+' if np.median(rc)>0 else ''}{np.median(rc):.1f}")
    print(f"  Std rank change:    {rc.std():.2f}")
    print(f"  Improved (rank went up):   {(rc > 0).sum()} ({(rc > 0).mean()*100:.1f}%)")
    print(f"  Same rank:                 {(rc == 0).sum()} ({(rc == 0).mean()*100:.1f}%)")
    print(f"  Worsened (rank went down): {(rc < 0).sum()} ({(rc < 0).mean()*100:.1f}%)")
    print(f"  Big improvements (>5):     {(rc > 5).sum()}")
    print(f"  Big regressions (<-5):     {(rc < -5).sum()}")

print(f"\n--- Similarity Changes ---")
if all_sim_changes:
    sc = np.array(all_sim_changes)
    print(f"  Mean sim change:   {'+' if sc.mean()>0 else ''}{sc.mean():.4f}")
    print(f"  Median sim change: {'+' if np.median(sc)>0 else ''}{np.median(sc):.4f}")
    print(f"  Sim increased: {(sc > 0).sum()} ({(sc > 0).mean()*100:.1f}%)")
    print(f"  Sim decreased: {(sc < 0).sum()} ({(sc < 0).mean()*100:.1f}%)")

print(f"\n--- Top-5 Overlap ---")
print(f"  Per-query top-5 overlap: {top5_overlaps}")
print(f"  Mean top-5 overlap: {np.mean(top5_overlaps):.2f}/5")
print(f"  This measures ranking stability — how much the top-5 changes with context")

# ---------------------------------------------------------------------------
# SPECIFIC EXAMPLES
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("EXAMPLES WHERE CONTEXT HELPS")
print("=" * 80)

# Sort by largest positive rank change
context_helps_examples.sort(key=lambda x: -x["rank_change"])
for ex in context_helps_examples[:10]:
    print(f"\n  Query: \"{ex['query']}\"")
    print(f"  Chunk: [{ex['exchange']}] \"{ex['heading']}\"")
    print(f"  Rank:  #{ex['orig_rank']} -> #{ex['ctx_rank']} (improved by {ex['rank_change']} positions)")
    print(f"  Sim:   {ex['orig_sim']:.4f} -> {ex['ctx_sim']:.4f}")
    print(f"  Text:  {ex['text_preview']}")

print("\n" + "=" * 80)
print("EXAMPLES WHERE CONTEXT HURTS")
print("=" * 80)

context_hurts_examples.sort(key=lambda x: x["rank_change"])
for ex in context_hurts_examples[:10]:
    print(f"\n  Query: \"{ex['query']}\"")
    print(f"  Chunk: [{ex['exchange']}] \"{ex['heading']}\"")
    print(f"  Rank:  #{ex['orig_rank']} -> #{ex['ctx_rank']} (worsened by {abs(ex['rank_change'])} positions)")
    print(f"  Sim:   {ex['orig_sim']:.4f} -> {ex['ctx_sim']:.4f}")
    print(f"  Text:  {ex['text_preview']}")

# ---------------------------------------------------------------------------
# EMBEDDING SPACE ANALYSIS
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("EMBEDDING SPACE ANALYSIS")
print("=" * 80)

# How much does context change the embedding?
diffs = ctx_vecs - orig_vecs
cosine_self_sims = np.sum(orig_vecs * ctx_vecs, axis=1)  # cosine sim between orig and ctx for same chunk

print(f"\n--- Original vs Context-Prepended (same chunk) ---")
print(f"  Mean cosine similarity:   {cosine_self_sims.mean():.4f}")
print(f"  Min cosine similarity:    {cosine_self_sims.min():.4f}")
print(f"  Max cosine similarity:    {cosine_self_sims.max():.4f}")
print(f"  Std cosine similarity:    {cosine_self_sims.std():.4f}")
print(f"  < 0.90 (large shift):     {(cosine_self_sims < 0.90).sum()}")
print(f"  < 0.95 (moderate shift):  {(cosine_self_sims < 0.95).sum()}")
print(f"  > 0.99 (minimal shift):   {(cosine_self_sims > 0.99).sum()}")

# Analyze shift by text length
text_lengths = np.array([len(t) for t in original_texts])
short_mask = text_lengths < 300
medium_mask = (text_lengths >= 300) & (text_lengths < 1000)
long_mask = text_lengths >= 1000

print(f"\n--- Embedding Shift by Chunk Length ---")
for label, mask in [("Short (<300)", short_mask), ("Medium (300-1000)", medium_mask), ("Long (>1000)", long_mask)]:
    if mask.sum() > 0:
        sims = cosine_self_sims[mask]
        print(f"  {label}: n={mask.sum()}, mean_cosine={sims.mean():.4f}, min={sims.min():.4f}")

# Analyze shift by exchange
print(f"\n--- Embedding Shift by Exchange ---")
for exch in sorted(set(m["exchange"] for m in chunk_metadata)):
    mask = np.array([m["exchange"] == exch for m in chunk_metadata])
    if mask.sum() > 0:
        sims = cosine_self_sims[mask]
        print(f"  {exch:20s}: n={mask.sum():3d}, mean_cosine={sims.mean():.4f}, min={sims.min():.4f}")

# ---------------------------------------------------------------------------
# CONCLUSION
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

if all_rank_changes:
    rc = np.array(all_rank_changes)
    improved_pct = (rc > 0).mean() * 100
    worsened_pct = (rc < 0).mean() * 100
    mean_change = rc.mean()
    mean_overlap = np.mean(top5_overlaps)
    mean_self_sim = cosine_self_sims.mean()

    print(f"""
  Context prepending ("[exchange | heading]\\n\\n" prefix) results:

  1. RANKING IMPACT:
     - {improved_pct:.0f}% of relevant chunks improved rank
     - {worsened_pct:.0f}% worsened
     - Mean rank change: {'+' if mean_change>0 else ''}{mean_change:.1f} positions

  2. TOP-5 STABILITY:
     - Mean overlap: {mean_overlap:.1f}/5 (5 = identical, 0 = completely different)

  3. EMBEDDING SHIFT:
     - Mean self-cosine: {mean_self_sim:.4f} (1.0 = no change)
     - Context prepending {'significantly' if mean_self_sim < 0.95 else 'moderately' if mean_self_sim < 0.98 else 'minimally'} shifts embeddings

  4. RECOMMENDATION:
""")

    if improved_pct > 60 and mean_change > 1:
        print("     STRONG BENEFIT: Context prepending consistently improves retrieval for")
        print("     exchange-specific and topic-specific queries. Recommended for production.")
    elif improved_pct > 50:
        print("     MODERATE BENEFIT: Context prepending helps more often than it hurts.")
        print("     Consider implementing with monitoring.")
    elif improved_pct > 40:
        print("     MIXED RESULTS: Context prepending has roughly equal positive and negative")
        print("     effects. Consider query-type-specific strategies instead.")
    else:
        print("     NOT RECOMMENDED: Context prepending worsens rankings more often than")
        print("     it helps for this embedding model and data distribution.")
else:
    print("  No relevant chunks found for analysis. Check relevance criteria.")

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)
