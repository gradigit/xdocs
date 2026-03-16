"""Tests for markdown chunking (src/xdocs/chunker.py)."""

from __future__ import annotations

import unittest


def _require_mistune():
    try:
        import mistune  # noqa: F401
        return True
    except ImportError:
        return False


HAS_MISTUNE = _require_mistune()


@unittest.skipUnless(HAS_MISTUNE, "mistune not installed (optional dependency)")
class TestChunker(unittest.TestCase):
    def test_single_section(self) -> None:
        """A small document with one heading should produce a single chunk."""
        from xdocs.chunker import chunk_markdown

        md = "# Title\n\nShort paragraph here."
        chunks = chunk_markdown(md)
        # Small doc: returned as single chunk without heading parsing.
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].char_start, 0)
        self.assertEqual(chunks[0].char_end, len(md))

        # When forced to split, heading should be detected.
        chunks2 = chunk_markdown(md, max_tokens=5)
        self.assertGreaterEqual(len(chunks2), 1)
        self.assertEqual(chunks2[0].heading, "Title")
        self.assertEqual(chunks2[0].heading_level, 1)

    def test_multiple_h2_sections(self) -> None:
        """Multiple H2 sections should produce one chunk per section."""
        from xdocs.chunker import chunk_markdown

        md = "## Section A\n\nContent A.\n\n## Section B\n\nContent B.\n\n## Section C\n\nContent C."
        chunks = chunk_markdown(md, max_tokens=10)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].heading, "Section A")
        self.assertEqual(chunks[1].heading, "Section B")
        self.assertEqual(chunks[2].heading, "Section C")
        # Indices should be sequential.
        self.assertEqual([c.chunk_index for c in chunks], [0, 1, 2])
        # Heading levels should all be 2.
        self.assertTrue(all(c.heading_level == 2 for c in chunks))

    def test_oversized_section_splits(self) -> None:
        """A section exceeding max_tokens should be split at paragraph boundaries."""
        from xdocs.chunker import chunk_markdown

        # Create a large section: ~800 tokens worth (3200 chars).
        paragraphs = [f"Paragraph {i}. " + "word " * 80 for i in range(10)]
        md = "## Big Section\n\n" + "\n\n".join(paragraphs)
        chunks = chunk_markdown(md, max_tokens=200, overlap_tokens=32)
        self.assertGreater(len(chunks), 1)
        # All chunks should reference the same heading.
        for c in chunks:
            self.assertEqual(c.heading, "Big Section")
            self.assertEqual(c.heading_level, 2)

    def test_code_blocks_with_hash(self) -> None:
        """Code blocks containing # should not be treated as headings."""
        from xdocs.chunker import chunk_markdown

        md = "## API Guide\n\n```python\n# This is a comment\nprint('hello')\n```\n\nSome text after code."
        chunks = chunk_markdown(md)
        # Small doc: single chunk (code block # is not a heading, and doc fits in one chunk).
        self.assertEqual(len(chunks), 1)
        # When forced to split, the code block # should not create an extra heading section.
        chunks2 = chunk_markdown(md, max_tokens=10)
        headings_found = [c.heading for c in chunks2]
        # "This is a comment" should NOT appear as a heading (it's inside a code block).
        self.assertNotIn("This is a comment", headings_found)

    def test_empty_input(self) -> None:
        """Empty or whitespace-only input should return no chunks."""
        from xdocs.chunker import chunk_markdown

        self.assertEqual(chunk_markdown(""), [])
        self.assertEqual(chunk_markdown("   \n\n  "), [])

    def test_char_offset_coverage(self) -> None:
        """Char offsets should cover the document without gaps in non-overlap case."""
        from xdocs.chunker import chunk_markdown

        # Use max_tokens=10 to force splitting on this small document.
        md = "## First\n\nContent one.\n\n## Second\n\nContent two."
        chunks = chunk_markdown(md, max_tokens=10)
        self.assertEqual(len(chunks), 2)
        # First chunk starts at 0.
        self.assertEqual(chunks[0].char_start, 0)
        # Second chunk starts where second heading begins.
        second_pos = md.index("## Second")
        self.assertEqual(chunks[1].char_start, second_pos)
        # char_end should be within the document.
        for c in chunks:
            self.assertLessEqual(c.char_end, len(md))
            self.assertGreater(c.char_end, c.char_start)

    def test_preamble_before_first_heading(self) -> None:
        """Text before the first heading should be in its own chunk with heading_level=0."""
        from xdocs.chunker import chunk_markdown

        md = "Some preamble text here.\n\n## Heading\n\nContent."
        chunks = chunk_markdown(md, max_tokens=10)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].heading, "")
        self.assertEqual(chunks[0].heading_level, 0)
        self.assertEqual(chunks[1].heading, "Heading")
        self.assertEqual(chunks[1].heading_level, 2)


if __name__ == "__main__":
    unittest.main()
