"""Markdown chunking for semantic search embedding.

Splits markdown documents at heading boundaries (H1/H2/H3) using mistune AST
parsing, then sub-splits oversized sections at paragraph boundaries with overlap.
Requires ``mistune>=3.0`` (part of the ``[semantic]`` extras).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Chunk:
    """A chunk of markdown text with provenance metadata."""

    text: str
    heading: str  # Nearest heading text (empty for preamble)
    heading_level: int  # 1/2/3/0 (0 = preamble before first heading)
    chunk_index: int  # 0-based sequential index
    char_start: int  # Character offset in original markdown
    char_end: int


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~3 chars per token (conservative for CJK)."""
    return len(text) // 3


def _find_heading_boundaries(ast_nodes: list[dict[str, Any]], md: str) -> list[tuple[str, int, int]]:
    """Walk the AST to find heading positions in the original markdown.

    Returns list of (heading_text, heading_level, char_position) sorted by position.
    """
    headings: list[tuple[str, int, int]] = []

    def _extract_text(node: dict[str, Any]) -> str:
        """Recursively extract plain text from an AST node."""
        if node.get("type") == "text":
            return node.get("raw", node.get("text", ""))
        children = node.get("children")
        if children:
            return "".join(_extract_text(c) for c in children)
        return node.get("raw", node.get("text", ""))

    search_start = 0
    for node in ast_nodes:
        if node.get("type") == "heading":
            level = node.get("attrs", {}).get("level", node.get("level", 1))
            text = _extract_text(node).strip()
            # Find this heading in the original markdown.
            # Look for the pattern: # text (with appropriate number of #s).
            prefix = "#" * level + " "
            idx = md.find(prefix + text, search_start)
            if idx == -1:
                # Try finding just the # prefix near any occurrence of the text.
                idx = md.find(prefix, search_start)
            if idx >= 0:
                headings.append((text, level, idx))
                search_start = idx + 1

    # Deduplicate and sort by position.
    seen: set[int] = set()
    unique: list[tuple[str, int, int]] = []
    for h in headings:
        if h[2] not in seen:
            seen.add(h[2])
            unique.append(h)
    unique.sort(key=lambda x: x[2])
    return unique


def _protect_fenced_blocks(paragraphs: list[str]) -> list[str]:
    """Merge paragraphs that fall inside code fences into single protected blocks.

    Tracks opening/closing ``` or ~~~ fences (with up to 3 leading spaces),
    matching by exact delimiter length.
    """
    import re

    fence_re = re.compile(r"^( {0,3})((`{3,})|(~{3,}))", re.MULTILINE)
    result: list[str] = []
    buf: list[str] = []
    fence_char: str | None = None
    fence_len: int = 0

    for para in paragraphs:
        if fence_char is None:
            # Not inside a fence — check if this paragraph opens one.
            m = fence_re.match(para)
            if m:
                fence_char = m.group(3)[0] if m.group(3) else m.group(4)[0]
                fence_len = len(m.group(3) or m.group(4))
                # Check if the same paragraph also closes the fence.
                lines = para.split("\n")
                if len(lines) > 1:
                    close_re = re.compile(r"^ {0,3}" + re.escape(fence_char) * fence_len + r"+\s*$")
                    if any(close_re.match(line) for line in lines[1:]):
                        # Self-closing block — emit as-is.
                        result.append(para)
                        fence_char = None
                        fence_len = 0
                        continue
                buf = [para]
            else:
                result.append(para)
        else:
            # Inside a fence — accumulate.
            buf.append(para)
            # Check if any line in this paragraph closes the fence.
            close_re = re.compile(r"^ {0,3}" + re.escape(fence_char) * fence_len + r"+\s*$")
            if any(close_re.match(line) for line in para.split("\n")):
                # Close the fence — merge all buffered paragraphs.
                result.append("\n\n".join(buf))
                buf = []
                fence_char = None
                fence_len = 0

    # If the fence was never closed, merge remaining buffer anyway.
    if buf:
        result.append("\n\n".join(buf))

    return result


def _merge_table_paragraphs(paragraphs: list[str]) -> list[str]:
    """Merge consecutive pipe-delimited table paragraphs to avoid splitting tables.

    Detects paragraphs where ALL non-blank lines match ``^\\|.*\\|$`` (pure table
    rows).  Consecutive table paragraphs are merged into a single paragraph so the
    downstream chunk splitter treats the table as an atomic unit.  Oversized merged
    tables still fall through to the character-based guardrail in ``_split_at_paragraphs``.
    """
    import re

    table_row_re = re.compile(r"^\|.*\|$")

    def _is_table_paragraph(text: str) -> bool:
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        return bool(lines) and all(table_row_re.match(line) for line in lines)

    result: list[str] = []
    table_buf: list[str] = []

    for para in paragraphs:
        if _is_table_paragraph(para):
            table_buf.append(para)
        else:
            if table_buf:
                result.append("\n\n".join(table_buf))
                table_buf = []
            result.append(para)

    if table_buf:
        result.append("\n\n".join(table_buf))

    return result


def _split_at_paragraphs(
    text: str,
    *,
    heading: str,
    heading_level: int,
    max_tokens: int,
    overlap_tokens: int,
    base_char_start: int,
    start_index: int,
) -> list[Chunk]:
    """Sub-split an oversized section at paragraph (``\\n\\n``) boundaries with overlap."""
    paragraphs = text.split("\n\n")

    # Protect code fences and merge table rows before splitting.
    paragraphs = _protect_fenced_blocks(paragraphs)
    paragraphs = _merge_table_paragraphs(paragraphs)

    # Guardrail: if a paragraph itself is huge (common in scraped/minified docs),
    # hard-split it into fixed-size windows so downstream embedding/index writes
    # never receive giant multi-GB buffers.
    expanded: list[str] = []
    max_chars = max_tokens * 3
    step_chars = max((max_tokens - overlap_tokens) * 3, 1)
    for para in paragraphs:
        if _estimate_tokens(para) <= max_tokens:
            expanded.append(para)
            continue
        start = 0
        while start < len(para):
            expanded.append(para[start : start + max_chars])
            if start + max_chars >= len(para):
                break
            start += step_chars
    paragraphs = expanded

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_len = 0
    chunk_char_start = 0
    char_pos = 0

    for i, para in enumerate(paragraphs):
        para_tokens = _estimate_tokens(para)

        if current_parts and current_len + para_tokens > max_tokens:
            # Emit current chunk.
            chunk_text = "\n\n".join(current_parts)
            chunks.append(Chunk(
                text=chunk_text,
                heading=heading,
                heading_level=heading_level,
                chunk_index=start_index + len(chunks),
                char_start=base_char_start + chunk_char_start,
                char_end=base_char_start + chunk_char_start + len(chunk_text),
            ))

            # Overlap: keep last paragraph(s) up to overlap_tokens.
            overlap_parts: list[str] = []
            overlap_len = 0
            for p in reversed(current_parts):
                p_tokens = _estimate_tokens(p)
                if overlap_len + p_tokens > overlap_tokens:
                    break
                overlap_parts.insert(0, p)
                overlap_len += p_tokens

            current_parts = overlap_parts
            current_len = overlap_len
            # Adjust char_start for the overlap.
            if overlap_parts:
                overlap_text = "\n\n".join(overlap_parts)
                chunk_char_start = char_pos - len(overlap_text)
            else:
                chunk_char_start = char_pos

        current_parts.append(para)
        current_len += para_tokens
        char_pos += len(para) + 2  # +2 for the \n\n separator

    # Emit remaining.
    if current_parts:
        chunk_text = "\n\n".join(current_parts)
        chunks.append(Chunk(
            text=chunk_text,
            heading=heading,
            heading_level=heading_level,
            chunk_index=start_index + len(chunks),
            char_start=base_char_start + chunk_char_start,
            char_end=base_char_start + chunk_char_start + len(chunk_text),
        ))

    return chunks


def chunk_markdown(
    md: str,
    *,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    """Split a markdown document into chunks for embedding.

    Strategy:
    1. Parse with ``mistune.create_markdown(renderer='ast')`` for heading detection.
    2. Split at H1/H2/H3 boundaries.
    3. Sub-split oversized sections at paragraph boundaries with overlap.
    4. Return a single chunk for small documents (< max_tokens).

    Args:
        md: Markdown text to chunk.
        max_tokens: Target max tokens per chunk (estimated as len/3).
        overlap_tokens: Token overlap between consecutive sub-split chunks.

    Returns:
        List of Chunk objects preserving document order.
    """
    if not md or not md.strip():
        return []

    # Small document: single chunk.
    if _estimate_tokens(md) <= max_tokens:
        return [Chunk(
            text=md,
            heading="",
            heading_level=0,
            chunk_index=0,
            char_start=0,
            char_end=len(md),
        )]

    # Parse AST for heading boundaries.
    try:
        import mistune
    except ImportError:
        # Fallback: return single truncated chunk if mistune not available.
        return [Chunk(
            text=md[:max_tokens * 3],
            heading="",
            heading_level=0,
            chunk_index=0,
            char_start=0,
            char_end=min(len(md), max_tokens * 3),
        )]

    parser = mistune.create_markdown(renderer="ast")
    ast_nodes = parser(md)

    headings = _find_heading_boundaries(ast_nodes, md)

    if not headings:
        # No headings found: split at paragraphs.
        return _split_at_paragraphs(
            md,
            heading="",
            heading_level=0,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            base_char_start=0,
            start_index=0,
        )

    # Build sections from heading boundaries.
    sections: list[tuple[str, int, int, int]] = []  # (heading, level, start, end)

    # Preamble before first heading.
    if headings[0][2] > 0:
        sections.append(("", 0, 0, headings[0][2]))

    for i, (text, level, pos) in enumerate(headings):
        end = headings[i + 1][2] if i + 1 < len(headings) else len(md)
        sections.append((text, level, pos, end))

    # Chunk each section.
    chunks: list[Chunk] = []
    for heading_text, heading_level, sec_start, sec_end in sections:
        section_text = md[sec_start:sec_end].rstrip()
        if not section_text.strip():
            continue

        if _estimate_tokens(section_text) <= max_tokens:
            chunks.append(Chunk(
                text=section_text,
                heading=heading_text,
                heading_level=heading_level,
                chunk_index=len(chunks),
                char_start=sec_start,
                char_end=sec_start + len(section_text),
            ))
        else:
            sub_chunks = _split_at_paragraphs(
                section_text,
                heading=heading_text,
                heading_level=heading_level,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
                base_char_start=sec_start,
                start_index=len(chunks),
            )
            chunks.extend(sub_chunks)

    # Re-index sequentially.
    return [
        Chunk(
            text=c.text,
            heading=c.heading,
            heading_level=c.heading_level,
            chunk_index=i,
            char_start=c.char_start,
            char_end=c.char_end,
        )
        for i, c in enumerate(chunks)
    ]
