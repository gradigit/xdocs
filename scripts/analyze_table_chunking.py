#!/usr/bin/env python3
"""Analyze how the chunker handles markdown tables and code blocks in LanceDB index.

Reads a sample of chunks from LanceDB, detects table/code-block content,
and reports on splitting quality.
"""
from __future__ import annotations

import re
import sqlite3
import textwrap
from collections import Counter, defaultdict
from pathlib import Path

import lancedb

DOCS_DIR = Path("cex-docs")
LANCE_DIR = DOCS_DIR / "lancedb-index"
DB_PATH = DOCS_DIR / "db" / "docs.db"
TABLE_NAME = "pages"
SAMPLE_SIZE = 5000

# ──────────────────── detection helpers ────────────────────

PIPE_ROW_RE = re.compile(r"^\s*\|.+\|", re.MULTILINE)
SEPARATOR_RE = re.compile(r"^\s*\|[\s\-:|]+\|", re.MULTILINE)
CODE_FENCE_RE = re.compile(r"^```", re.MULTILINE)


def has_pipe_rows(text: str) -> bool:
    return bool(PIPE_ROW_RE.search(text))


def has_separator(text: str) -> bool:
    return bool(SEPARATOR_RE.search(text))


def count_tables(text: str) -> int:
    """Count distinct markdown tables (each separator = one table)."""
    return len(SEPARATOR_RE.findall(text))


def is_only_table(text: str) -> bool:
    """True if the chunk is >90% pipe-delimited lines."""
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    pipe_lines = sum(1 for l in lines if l.strip().startswith("|"))
    return pipe_lines / len(lines) > 0.9


def table_at_boundary(text: str) -> dict[str, bool]:
    """Check if a table appears cut at the start or end of a chunk."""
    lines = text.splitlines()
    if not lines:
        return {"starts_mid_table": False, "ends_mid_table": False}

    # Starts mid-table: first non-empty line is a pipe row but there's no
    # separator in the first few lines (the header + separator should come before data)
    first_nonempty = next((l for l in lines if l.strip()), "")
    starts_mid = (
        first_nonempty.strip().startswith("|")
        and not SEPARATOR_RE.match(first_nonempty)
        and not any(SEPARATOR_RE.match(l) for l in lines[:3])
    )

    # Ends mid-table: last non-empty line is a pipe row AND there is no blank
    # line after the table before chunk end
    last_nonempty = next((l for l in reversed(lines) if l.strip()), "")
    ends_with_pipe = last_nonempty.strip().startswith("|")
    # Check if the table continues to the very end (no prose after last pipe row)
    ends_mid = ends_with_pipe and has_pipe_rows(text)

    return {"starts_mid_table": starts_mid, "ends_mid_table": ends_mid}


def count_code_fences(text: str) -> int:
    return len(CODE_FENCE_RE.findall(text))


def estimate_tokens(text: str) -> int:
    return len(text) // 4


# ──────────────────── main analysis ────────────────────

def main():
    print("=" * 80)
    print("CHUNKER TABLE & CODE-BLOCK ANALYSIS")
    print("=" * 80)

    # ── 1. Load chunks from LanceDB ──
    db = lancedb.connect(str(LANCE_DIR))
    table = db.open_table(TABLE_NAME)
    total_rows = table.count_rows()
    print(f"\nLanceDB table '{TABLE_NAME}': {total_rows:,} total chunks")

    sample_limit = min(SAMPLE_SIZE, total_rows)
    # Read ALL chunks for complete analysis
    print(f"Reading ALL {total_rows:,} chunks for complete analysis...")
    df = table.to_pandas()
    texts = df["text"].tolist()
    page_ids = df["page_id"].tolist()
    chunk_indices = df["chunk_index"].tolist()
    headings = df["heading"].tolist()
    exchanges = df["exchange"].tolist()
    urls = df["url"].tolist()

    n = len(texts)
    print(f"Loaded {n:,} chunks\n")

    # ── 2. Table content detection ──
    print("-" * 80)
    print("TABLE CONTENT ANALYSIS")
    print("-" * 80)

    table_chunks = []  # indices of chunks with any table content
    partial_table_chunks = []  # pipe rows but no separator
    only_table_chunks = []  # >90% pipe lines
    boundary_split_chunks = []  # table at start/end boundary
    starts_mid = []
    ends_mid = []

    table_char_sizes = []
    table_token_sizes = []
    nontable_char_sizes = []
    nontable_token_sizes = []

    tables_per_exchange = Counter()
    table_chunks_per_exchange = Counter()

    for i, text in enumerate(texts):
        has_pipes = has_pipe_rows(text)
        has_sep = has_separator(text)
        chars = len(text)
        tokens = estimate_tokens(text)

        if has_pipes:
            table_chunks.append(i)
            table_char_sizes.append(chars)
            table_token_sizes.append(tokens)
            tables_per_exchange[exchanges[i]] += 1

            if not has_sep:
                partial_table_chunks.append(i)

            if is_only_table(text):
                only_table_chunks.append(i)

            boundaries = table_at_boundary(text)
            if boundaries["starts_mid_table"] or boundaries["ends_mid_table"]:
                boundary_split_chunks.append(i)
            if boundaries["starts_mid_table"]:
                starts_mid.append(i)
            if boundaries["ends_mid_table"]:
                ends_mid.append(i)
        else:
            nontable_char_sizes.append(chars)
            nontable_token_sizes.append(tokens)

    print(f"\nChunks with table content:     {len(table_chunks):>6,} / {n:,}  ({100*len(table_chunks)/n:.1f}%)")
    print(f"Chunks with PARTIAL table:     {len(partial_table_chunks):>6,} / {n:,}  ({100*len(partial_table_chunks)/n:.1f}%)")
    print(f"  (has pipe rows but NO separator — likely split mid-table)")
    print(f"Chunks with ONLY table content:{len(only_table_chunks):>6,} / {n:,}  ({100*len(only_table_chunks)/n:.1f}%)")
    print(f"Chunks with table at boundary: {len(boundary_split_chunks):>6,} / {n:,}  ({100*len(boundary_split_chunks)/n:.1f}%)")
    print(f"  - Starts mid-table:          {len(starts_mid):>6,}")
    print(f"  - Ends mid-table:            {len(ends_mid):>6,}")

    # ── Size comparison ──
    print(f"\n{'Metric':<35} {'Table chunks':>15} {'Non-table chunks':>18}")
    print("-" * 70)
    if table_char_sizes:
        avg_tc = sum(table_char_sizes) / len(table_char_sizes)
        avg_tt = sum(table_token_sizes) / len(table_token_sizes)
    else:
        avg_tc = avg_tt = 0
    if nontable_char_sizes:
        avg_nc = sum(nontable_char_sizes) / len(nontable_char_sizes)
        avg_nt = sum(nontable_token_sizes) / len(nontable_token_sizes)
    else:
        avg_nc = avg_nt = 0

    print(f"{'Avg chars':<35} {avg_tc:>15,.0f} {avg_nc:>18,.0f}")
    print(f"{'Avg est. tokens':<35} {avg_tt:>15,.0f} {avg_nt:>18,.0f}")
    if table_char_sizes:
        print(f"{'Median chars':<35} {sorted(table_char_sizes)[len(table_char_sizes)//2]:>15,} {sorted(nontable_char_sizes)[len(nontable_char_sizes)//2] if nontable_char_sizes else 0:>18,}")
        print(f"{'Max chars':<35} {max(table_char_sizes):>15,} {max(nontable_char_sizes) if nontable_char_sizes else 0:>18,}")
        print(f"{'Min chars':<35} {min(table_char_sizes):>15,} {min(nontable_char_sizes) if nontable_char_sizes else 0:>18,}")

    # ── Table chunks by exchange ──
    print(f"\nTable chunks by exchange (top 15):")
    for exch, cnt in sorted(tables_per_exchange.items(), key=lambda x: -x[1])[:15]:
        print(f"  {exch:<25} {cnt:>6,}")

    # ── 3. Examples of boundary splits ──
    print("\n" + "-" * 80)
    print("EXAMPLES: CHUNKS WHERE TABLE IS SPLIT AT BOUNDARY")
    print("-" * 80)

    shown = 0
    for idx in starts_mid[:5]:
        shown += 1
        text = texts[idx]
        lines = text.splitlines()
        print(f"\n--- Example {shown}: chunk starts mid-table (page_id={page_ids[idx]}, chunk_index={chunk_indices[idx]}) ---")
        print(f"    Exchange: {exchanges[idx]}")
        print(f"    URL: {urls[idx]}")
        print(f"    Heading: {headings[idx]}")
        print(f"    First 8 lines:")
        for line in lines[:8]:
            print(f"      {line[:120]}")
        print(f"    ... ({len(lines)} lines total, {len(text)} chars)")

    for idx in ends_mid[:5]:
        if idx in starts_mid[:5]:
            continue
        shown += 1
        if shown > 8:
            break
        text = texts[idx]
        lines = text.splitlines()
        print(f"\n--- Example {shown}: chunk ends mid-table (page_id={page_ids[idx]}, chunk_index={chunk_indices[idx]}) ---")
        print(f"    Exchange: {exchanges[idx]}")
        print(f"    URL: {urls[idx]}")
        print(f"    Heading: {headings[idx]}")
        print(f"    Last 8 lines:")
        for line in lines[-8:]:
            print(f"      {line[:120]}")
        print(f"    ... ({len(lines)} lines total, {len(text)} chars)")

    # ── 4. Code block analysis ──
    print("\n" + "-" * 80)
    print("CODE BLOCK ANALYSIS")
    print("-" * 80)

    chunks_with_fences = 0
    unbalanced_fences = 0
    unbalanced_examples = []

    for i, text in enumerate(texts):
        fence_count = count_code_fences(text)
        if fence_count > 0:
            chunks_with_fences += 1
            if fence_count % 2 != 0:
                unbalanced_fences += 1
                if len(unbalanced_examples) < 5:
                    unbalanced_examples.append(i)

    print(f"\nChunks with ``` markers:        {chunks_with_fences:>6,} / {n:,}  ({100*chunks_with_fences/n:.1f}%)")
    print(f"Chunks with UNBALANCED fences:  {unbalanced_fences:>6,} / {n:,}  ({100*unbalanced_fences/n:.1f}%)")
    print(f"  (odd number of ``` markers — likely split mid-code-block)")

    if unbalanced_examples:
        print(f"\nExamples of unbalanced code fences:")
        for idx in unbalanced_examples[:3]:
            text = texts[idx]
            fences = count_code_fences(text)
            lines = text.splitlines()
            print(f"\n  chunk_index={chunk_indices[idx]}, page_id={page_ids[idx]}, exchange={exchanges[idx]}")
            print(f"  ``` count: {fences}, chars: {len(text)}")
            print(f"  Heading: {headings[idx]}")
            # Show lines around fence markers
            for li, line in enumerate(lines):
                if line.strip().startswith("```"):
                    start = max(0, li - 1)
                    end = min(len(lines), li + 2)
                    for sl in range(start, end):
                        prefix = ">>>" if sl == li else "   "
                        print(f"    {prefix} L{sl+1}: {lines[sl][:100]}")

    # ── 5. SQLite pages with most table content → LanceDB chunking ──
    print("\n" + "-" * 80)
    print("TOP 5 PAGES BY TABLE CONTENT → CHUNKING QUALITY")
    print("-" * 80)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, canonical_url, title, domain, word_count, markdown_path
        FROM pages
        WHERE word_count > 0 AND markdown_path IS NOT NULL
        ORDER BY word_count DESC
        LIMIT 2000
    """).fetchall()

    # Score each page by table content in its markdown file
    page_table_scores = []
    repo_root = DOCS_DIR.parent

    for row in rows:
        md_rel = row["markdown_path"]
        md_path = repo_root / md_rel if md_rel.startswith(DOCS_DIR.name) else DOCS_DIR / md_rel
        if not md_path.exists():
            continue
        try:
            md_text = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        n_tables = count_tables(md_text)
        n_pipe_lines = len(PIPE_ROW_RE.findall(md_text))
        if n_tables > 0:
            page_table_scores.append({
                "page_id": row["id"],
                "url": row["canonical_url"],
                "title": row["title"],
                "domain": row["domain"],
                "word_count": row["word_count"],
                "md_path": str(md_path),
                "n_tables": n_tables,
                "n_pipe_lines": n_pipe_lines,
                "md_len": len(md_text),
            })

    conn.close()

    page_table_scores.sort(key=lambda x: -x["n_pipe_lines"])

    # Build lookup: page_id → list of chunk indices in our loaded data
    page_to_chunks: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        page_to_chunks[page_ids[i]].append(i)

    for rank, page in enumerate(page_table_scores[:5], 1):
        pid = page["page_id"]
        chunk_idxs = page_to_chunks.get(pid, [])

        table_c = sum(1 for ci in chunk_idxs if has_pipe_rows(texts[ci]))
        partial_c = sum(1 for ci in chunk_idxs if has_pipe_rows(texts[ci]) and not has_separator(texts[ci]))
        boundary_c = 0
        starts_c = 0
        ends_c = 0
        for ci in chunk_idxs:
            bd = table_at_boundary(texts[ci])
            if bd["starts_mid_table"]:
                starts_c += 1
                boundary_c += 1
            if bd["ends_mid_table"]:
                ends_c += 1
                boundary_c += 1

        print(f"\n#{rank}: {page['title'] or page['url']}")
        print(f"  URL: {page['url']}")
        print(f"  Page ID: {pid}, Words: {page['word_count']:,}, MD size: {page['md_len']:,} chars")
        print(f"  Tables in source: {page['n_tables']}, Pipe lines: {page['n_pipe_lines']}")
        print(f"  Chunks in LanceDB: {len(chunk_idxs)}")
        print(f"    With table content:   {table_c}")
        print(f"    Partial (no sep):     {partial_c}")
        print(f"    Boundary splits:      {boundary_c} (starts={starts_c}, ends={ends_c})")

        if chunk_idxs and partial_c > 0:
            # Show one partial-table example from this page
            for ci in chunk_idxs:
                if has_pipe_rows(texts[ci]) and not has_separator(texts[ci]):
                    lines = texts[ci].splitlines()
                    pipe_lines = [l for l in lines if l.strip().startswith("|")]
                    print(f"    Example partial chunk (chunk_index={chunk_indices[ci]}):")
                    print(f"      First pipe line: {pipe_lines[0][:100] if pipe_lines else 'N/A'}")
                    print(f"      Pipe lines in chunk: {len(pipe_lines)} / {len([l for l in lines if l.strip()])}")
                    break

    # ── 6. Summary of the chunking strategy impact on tables ──
    print("\n" + "=" * 80)
    print("SUMMARY & ANALYSIS")
    print("=" * 80)

    print(f"""
The chunker splits markdown at:
  1) H1/H2/H3 heading boundaries (primary split)
  2) Paragraph boundaries (\\n\\n) for oversized sections (secondary split)

Max tokens per chunk: 512 (estimated at ~4 chars/token = ~2048 chars)
Overlap: 64 tokens (~256 chars)

KEY FINDINGS:

Tables in chunks:
  - {len(table_chunks):,} / {n:,} chunks ({100*len(table_chunks)/n:.1f}%) contain pipe-delimited table rows
  - {len(partial_table_chunks):,} chunks ({100*len(partial_table_chunks)/n:.1f}%) have pipe rows but NO separator
    (strong indicator of mid-table splitting via \\n\\n paragraph breaks)
  - {len(only_table_chunks):,} chunks ({100*len(only_table_chunks)/n:.1f}%) are >90% table content
  - {len(boundary_split_chunks):,} chunks show table at chunk boundaries

Code blocks:
  - {chunks_with_fences:,} chunks ({100*chunks_with_fences/n:.1f}%) contain triple-backtick markers
  - {unbalanced_fences:,} chunks ({100*unbalanced_fences/n:.1f}%) have unbalanced fences (split mid-block)

ROOT CAUSE:
  Tables rarely contain blank lines (\\n\\n), so the paragraph splitter treats
  the entire table as one "paragraph". However, large tables embedded within a
  section that exceeds max_tokens get split when the cumulative paragraph token
  count crosses the threshold — the table itself isn't split, but the context
  around it (heading, preceding prose) may land in a different chunk.

  Tables with blank lines between rows (common in some HTML→MD converters)
  WILL be split at those blank lines since the chunker treats \\n\\n as paragraph
  boundaries.

  The partial-table count ({len(partial_table_chunks):,}) represents chunks where the table
  header+separator ended up in a prior chunk, leaving only data rows.
""")


if __name__ == "__main__":
    main()
