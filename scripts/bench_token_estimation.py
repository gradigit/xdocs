#!/usr/bin/env python3
"""Benchmark: measure accuracy of len(text)//4 token estimation vs Qwen3 tokenizer.

Loads 1000 chunks from LanceDB index, tokenizes each with the Qwen3 tokenizer,
and reports statistics on the ratio of actual tokens to estimated tokens.
"""

import sys
import statistics
import random

# ---------- 1. Load tokenizer ----------
print("Loading Qwen3 tokenizer (Qwen/Qwen3-Embedding-0.6B)...")
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-Embedding-0.6B")
print(f"  Tokenizer loaded. Vocab size: {tokenizer.vocab_size}")

# ---------- 2. Open LanceDB and read chunks ----------
import lancedb

LANCE_DIR = "/Users/aaaaa/Projects/cex-api-docs/cex-docs/lancedb-index"
SAMPLE_SIZE = 1000

print(f"\nOpening LanceDB at {LANCE_DIR}...")
db = lancedb.connect(LANCE_DIR)
table = db.open_table("pages")
total_rows = table.count_rows()
print(f"  Total rows in 'pages' table: {total_rows:,}")

# Read a sample. LanceDB doesn't have RANDOM(), so read all text fields and sample.
print(f"  Reading {SAMPLE_SIZE} chunks (random sample from {total_rows:,})...")

# Read all texts efficiently — just the text column via search API
df = table.search().select(["text"]).limit(total_rows).to_pandas()
texts = df["text"].tolist()

if len(texts) > SAMPLE_SIZE:
    random.seed(42)
    sample_indices = random.sample(range(len(texts)), SAMPLE_SIZE)
    sample_texts = [texts[i] for i in sample_indices]
else:
    sample_texts = texts

print(f"  Sampled {len(sample_texts)} chunks for analysis.")

# ---------- 3. Compute estimated vs actual tokens ----------
print("\nTokenizing chunks with Qwen3 tokenizer...")

results = []
for i, text in enumerate(sample_texts):
    estimated = len(text) // 4
    # Tokenize without truncation to get true count
    tokens = tokenizer.encode(text, add_special_tokens=False)
    actual = len(tokens)
    ratio = actual / estimated if estimated > 0 else float('inf')
    results.append({
        "text": text,
        "char_len": len(text),
        "estimated": estimated,
        "actual": actual,
        "ratio": ratio,
        "error_pct": (actual - estimated) / estimated * 100 if estimated > 0 else float('inf'),
    })
    if (i + 1) % 200 == 0:
        print(f"  Tokenized {i+1}/{len(sample_texts)}...")

print(f"  Done. Tokenized all {len(results)} chunks.")

# ---------- 4. Statistics ----------
ratios = [r["ratio"] for r in results if r["ratio"] != float('inf')]
error_pcts = [r["error_pct"] for r in results if r["error_pct"] != float('inf')]
actual_counts = [r["actual"] for r in results]
estimated_counts = [r["estimated"] for r in results]
char_lens = [r["char_len"] for r in results]

ratios_sorted = sorted(ratios)
n = len(ratios_sorted)

def percentile(data, p):
    k = (len(data) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(data):
        return data[-1]
    return data[f] + (k - f) * (data[c] - data[f])

print("\n" + "=" * 70)
print("TOKEN ESTIMATION ACCURACY BENCHMARK")
print("=" * 70)
print(f"Estimator:   len(text) // 4")
print(f"Tokenizer:   Qwen/Qwen3-Embedding-0.6B")
print(f"Sample size: {len(results)} chunks from LanceDB index")
print(f"Total index: {total_rows:,} chunks")

print("\n--- Ratio: actual_tokens / estimated_tokens ---")
print(f"  Mean:   {statistics.mean(ratios):.4f}")
print(f"  Median: {statistics.median(ratios):.4f}")
print(f"  StdDev: {statistics.stdev(ratios):.4f}")
print(f"  p5:     {percentile(ratios_sorted, 5):.4f}")
print(f"  p25:    {percentile(ratios_sorted, 25):.4f}")
print(f"  p75:    {percentile(ratios_sorted, 75):.4f}")
print(f"  p95:    {percentile(ratios_sorted, 95):.4f}")
print(f"  Min:    {min(ratios):.4f}")
print(f"  Max:    {max(ratios):.4f}")

print("\n--- Estimation Error (%) ---")
print(f"  Mean error:   {statistics.mean(error_pcts):+.1f}%")
print(f"  Median error: {statistics.median(error_pcts):+.1f}%")
# Positive = underestimate (actual > estimated), Negative = overestimate

underestimates = sum(1 for r in ratios if r > 1.0)
overestimates = sum(1 for r in ratios if r < 1.0)
exact = sum(1 for r in ratios if r == 1.0)
print(f"\n  Underestimates (actual > estimated): {underestimates} ({underestimates/n*100:.1f}%)")
print(f"  Overestimates  (actual < estimated): {overestimates} ({overestimates/n*100:.1f}%)")
print(f"  Exact matches:                       {exact} ({exact/n*100:.1f}%)")

print("\n--- Actual Token Count Distribution ---")
print(f"  Mean:   {statistics.mean(actual_counts):.0f}")
print(f"  Median: {statistics.median(actual_counts):.0f}")
print(f"  Min:    {min(actual_counts)}")
print(f"  Max:    {max(actual_counts)}")

# Truncation analysis (max_length=512 in embedder)
over_512 = sum(1 for a in actual_counts if a > 512)
over_384 = sum(1 for a in actual_counts if a > 384)
over_256 = sum(1 for a in actual_counts if a > 256)
print(f"\n--- Truncation Risk (embedding max_length=512) ---")
print(f"  Chunks with actual tokens > 512: {over_512} ({over_512/n*100:.1f}%) <- TRUNCATED")
print(f"  Chunks with actual tokens > 384: {over_384} ({over_384/n*100:.1f}%) <- >75% of limit")
print(f"  Chunks with actual tokens > 256: {over_256} ({over_256/n*100:.1f}%) <- >50% of limit")

# Histogram of actual token counts
print("\n--- Histogram of Actual Token Counts ---")
buckets = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 512, 600, 800, 1000, float('inf')]
for i in range(len(buckets) - 1):
    lo, hi = buckets[i], buckets[i+1]
    count = sum(1 for a in actual_counts if lo <= a < hi)
    bar = "#" * (count * 50 // n) if n > 0 else ""
    hi_label = f"{hi:.0f}" if hi != float('inf') else "+"
    print(f"  [{lo:>5} - {hi_label:>5}): {count:>4} ({count/n*100:5.1f}%) {bar}")

# Histogram of char lengths
print("\n--- Histogram of Character Lengths ---")
char_buckets = [0, 200, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000, float('inf')]
for i in range(len(char_buckets) - 1):
    lo, hi = char_buckets[i], char_buckets[i+1]
    count = sum(1 for c in char_lens if lo <= c < hi)
    bar = "#" * (count * 50 // n) if n > 0 else ""
    hi_label = f"{hi:.0f}" if hi != float('inf') else "+"
    print(f"  [{lo:>5} - {hi_label:>5}): {count:>4} ({count/n*100:5.1f}%) {bar}")

# ---------- 5. Worst cases ----------
print("\n--- Top 10 WORST Underestimates (actual >> estimated) ---")
print("  (Chunks where len//4 badly underestimates real tokens)")
worst_under = sorted(results, key=lambda r: -r["ratio"])[:10]
for i, r in enumerate(worst_under):
    snippet = r["text"][:80].replace("\n", "\\n")
    print(f"  {i+1}. ratio={r['ratio']:.2f} est={r['estimated']} actual={r['actual']} "
          f"chars={r['char_len']} | {snippet}...")

print("\n--- Top 10 WORST Overestimates (actual << estimated) ---")
print("  (Chunks where len//4 badly overestimates real tokens)")
worst_over = sorted(results, key=lambda r: r["ratio"])[:10]
for i, r in enumerate(worst_over):
    snippet = r["text"][:80].replace("\n", "\\n")
    print(f"  {i+1}. ratio={r['ratio']:.2f} est={r['estimated']} actual={r['actual']} "
          f"chars={r['char_len']} | {snippet}...")

# ---------- 6. Content-type breakdown ----------
print("\n--- Ratio by Content Type (heuristic) ---")

def classify_chunk(text):
    """Rough content classification."""
    lines = text.strip().split("\n")
    code_lines = sum(1 for l in lines if l.startswith("  ") or l.startswith("\t") or l.startswith("```"))
    table_lines = sum(1 for l in lines if "|" in l and l.count("|") >= 2)
    url_count = text.count("http://") + text.count("https://")

    if code_lines / max(len(lines), 1) > 0.5:
        return "code_heavy"
    if table_lines / max(len(lines), 1) > 0.3:
        return "table_heavy"
    if url_count > 3:
        return "url_heavy"
    # Check for CJK characters (Korean/Chinese/Japanese)
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\uac00' <= c <= '\ud7af' or '\u3040' <= c <= '\u30ff')
    if cjk_count > len(text) * 0.1:
        return "cjk_text"
    return "prose"

type_ratios = {}
for r in results:
    ctype = classify_chunk(r["text"])
    type_ratios.setdefault(ctype, []).append(r["ratio"])

for ctype in sorted(type_ratios.keys()):
    vals = type_ratios[ctype]
    vals_sorted = sorted(vals)
    print(f"  {ctype:>12}: n={len(vals):>4}  mean={statistics.mean(vals):.3f}  "
          f"median={statistics.median(vals):.3f}  "
          f"p5={percentile(vals_sorted, 5):.3f}  p95={percentile(vals_sorted, 95):.3f}")

# ---------- 7. Suggested correction factor ----------
print("\n--- Suggested Correction ---")
optimal_divisor = statistics.mean([r["char_len"] / r["actual"] for r in results if r["actual"] > 0])
print(f"  Current divisor:   4 (len(text) // 4)")
print(f"  Optimal divisor:   {optimal_divisor:.2f} (len(text) // {optimal_divisor:.2f})")
print(f"  Using {optimal_divisor:.1f} would center the ratio at ~1.0")

# What if we used the optimal divisor?
optimal_ratios = [r["actual"] / (r["char_len"] / optimal_divisor) for r in results if r["char_len"] > 0]
optimal_sorted = sorted(optimal_ratios)
print(f"\n  With divisor={optimal_divisor:.2f}:")
print(f"    Mean ratio:   {statistics.mean(optimal_ratios):.4f}")
print(f"    Median ratio: {statistics.median(optimal_ratios):.4f}")
print(f"    p5-p95 range: {percentile(optimal_sorted, 5):.4f} - {percentile(optimal_sorted, 95):.4f}")

# How many chunks would be truncated with the corrected estimator?
corrected_over_512 = sum(1 for r in results if r["char_len"] / optimal_divisor > 512 and r["actual"] <= 512)
print(f"\n  False negatives avoided (est>512 but actual<=512 with corrected divisor): "
      f"{corrected_over_512}")

print("\n" + "=" * 70)
print("BENCHMARK COMPLETE")
print("=" * 70)
