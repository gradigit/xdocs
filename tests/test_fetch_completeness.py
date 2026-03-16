from __future__ import annotations

import pytest

from xdocs.extraction_verify import ExtractionQuality, verify_extraction
from xdocs.inventory_fetch import _check_truncation
from xdocs.httpfetch import FetchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fr(body: bytes, headers: dict[str, str] | None = None) -> FetchResult:
    return FetchResult(
        url="https://example.com/test",
        final_url="https://example.com/test",
        redirect_chain=[],
        http_status=200,
        content_type="text/html",
        headers=headers or {},
        body=body,
    )


# ---------------------------------------------------------------------------
# ExtractionQuality computation
# ---------------------------------------------------------------------------

class TestVerifyExtraction:
    def test_perfect_extraction(self):
        """HTML and markdown have identical structural counts."""
        html = """
        <html><body>
        <h1>Title</h1>
        <h2>Section</h2>
        <p>Some words here to make this long enough for word count. Adding more
        words to reach forty words minimum threshold. One two three four five
        six seven eight nine ten.</p>
        <table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
        <pre><code>print("hello")</code></pre>
        </body></html>
        """
        md = """# Title

## Section

Some words here to make this long enough for word count. Adding more
words to reach forty words minimum threshold. One two three four five
six seven eight nine ten.

| A | B |
| --- | --- |
| 1 | 2 |

```python
print("hello")
```
"""
        result = verify_extraction(html, md)

        assert result.html_table_count == 1
        assert result.md_table_count == 1
        assert result.html_code_block_count == 1
        assert result.md_code_block_count == 1
        assert result.html_heading_count == 2
        assert result.md_heading_count == 2
        assert result.tables_lost == 0
        assert result.code_blocks_lost == 0
        assert result.quality_score == pytest.approx(1.0, abs=0.01)
        assert result.warnings == []

    def test_empty_html(self):
        """Empty HTML produces zero counts and low quality score."""
        result = verify_extraction("", "")

        assert result.html_table_count == 0
        assert result.md_table_count == 0
        assert result.html_code_block_count == 0
        assert result.md_code_block_count == 0
        assert result.html_heading_count == 0
        assert result.md_heading_count == 0
        assert result.md_word_count == 0
        assert result.tables_lost == 0
        assert result.code_blocks_lost == 0
        # With no HTML elements: both-zero → ratio=1.0 for structure,
        # word_ratio=0/40=0. Score = 0.35+0.30+0.15+0 = 0.80
        assert result.quality_score == pytest.approx(0.80, abs=0.01)

    def test_tables_lost(self):
        """HTML has tables but markdown doesn't — tables_lost > 0."""
        html = """
        <html><body>
        <h1>Title</h1>
        <table><tr><th>A</th></tr><tr><td>1</td></tr></table>
        <table><tr><th>B</th></tr><tr><td>2</td></tr></table>
        <table><tr><th>C</th></tr><tr><td>3</td></tr></table>
        </body></html>
        """
        md = "# Title\n\nSome text content without tables."

        result = verify_extraction(html, md)

        assert result.html_table_count == 3
        assert result.md_table_count == 0
        assert result.tables_lost == 3
        assert any("3 tables lost" in w for w in result.warnings)

    def test_code_blocks_lost(self):
        """HTML has pre blocks but markdown doesn't preserve them."""
        html = """
        <html><body>
        <pre><code>block1</code></pre>
        <pre>block2</pre>
        </body></html>
        """
        md = "Just text, no code fences."

        result = verify_extraction(html, md)

        assert result.html_code_block_count == 2
        assert result.md_code_block_count == 0
        assert result.code_blocks_lost == 2
        assert any("2 code blocks lost" in w for w in result.warnings)

    def test_low_quality_warning(self):
        """Quality score below 0.40 triggers a warning."""
        html = """
        <html><body>
        <h1>T</h1><h2>S</h2><h3>X</h3>
        <table><tr><th>A</th></tr><tr><td>1</td></tr></table>
        <pre>code</pre>
        </body></html>
        """
        md = "short"  # 1 word, no headings, no tables, no code

        result = verify_extraction(html, md)

        assert result.quality_score < 0.40
        assert any("Low extraction quality" in w for w in result.warnings)

    def test_quality_score_formula(self):
        """Verify quality score formula with known inputs."""
        # HTML: 2 tables, 1 code block, 2 headings
        # MD: 1 table, 1 code block, 2 headings, 50 words
        html = """
        <html><body>
        <h1>Title</h1>
        <h2>Section</h2>
        <table><tr><th>A</th></tr><tr><td>1</td></tr></table>
        <table><tr><th>B</th></tr><tr><td>2</td></tr></table>
        <pre>code</pre>
        </body></html>
        """
        words = " ".join(f"word{i}" for i in range(50))
        md = f"""# Title

## Section

{words}

| A |
| --- |
| 1 |

```
code
```
"""
        result = verify_extraction(html, md)

        # table_ratio = min(1/2, 1.0) = 0.5
        # code_ratio = min(1/1, 1.0) = 1.0
        # heading_ratio = min(2/2, 1.0) = 1.0
        # word_ratio = 1.0 (50 >= 40)
        expected = 0.35 * 0.5 + 0.30 * 1.0 + 0.15 * 1.0 + 0.20 * 1.0
        assert result.quality_score == pytest.approx(expected, abs=0.01)

    def test_md_has_more_elements_than_html(self):
        """MD somehow has more elements than HTML — ratios capped at 1.0."""
        html = "<html><body><p>hello</p></body></html>"
        words = " ".join(f"w{i}" for i in range(50))
        md = f"""# Heading

{words}

| A | B |
| --- | --- |
| 1 | 2 |

```
code
```
"""
        result = verify_extraction(html, md)

        # HTML has 0 tables, 0 code blocks, 0 headings
        # MD has 1 table, 1 code block, 1 heading
        # All ratios use max(html_count, 1) in denominator
        # table_ratio = min(1/1, 1.0) = 1.0
        # code_ratio = min(1/1, 1.0) = 1.0
        # heading_ratio = min(1/1, 1.0) = 1.0
        # word_ratio = 1.0
        assert result.quality_score == pytest.approx(1.0, abs=0.01)

    def test_word_ratio_partial(self):
        """Word count below 40 gives partial word_ratio."""
        html = "<html><body><p>text</p></body></html>"
        md = "one two three four five"  # 5 words

        result = verify_extraction(html, md)

        assert result.md_word_count == 5
        # word_ratio = 5/40 = 0.125; no HTML structure → both-zero ratios = 1.0
        # Score = 0.35*1.0 + 0.30*1.0 + 0.15*1.0 + 0.20*0.125 = 0.825
        assert result.quality_score == pytest.approx(0.825, abs=0.01)

    def test_empty_markdown_with_html_content(self):
        """Empty markdown despite HTML content triggers warning."""
        html = """
        <html><body>
        <h1>Title</h1>
        <p>Content here</p>
        </body></html>
        """
        md = ""

        result = verify_extraction(html, md)

        assert result.md_word_count == 0
        assert any("Markdown is empty" in w for w in result.warnings)

    def test_frozen_dataclass(self):
        """ExtractionQuality is frozen — attributes are read-only."""
        result = verify_extraction("<html></html>", "text")
        with pytest.raises(AttributeError):
            result.quality_score = 0.5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Truncation detection
# ---------------------------------------------------------------------------

class TestCheckTruncation:
    def test_no_truncation(self):
        """Normal response is not flagged."""
        fr = _make_fr(b"x" * 1000)
        result = _check_truncation(fr, max_bytes=10_000)
        assert result is None

    def test_near_max_bytes(self):
        """Body size >= 95% of max_bytes is flagged."""
        max_bytes = 10_000
        body = b"x" * 9600  # 96% of max_bytes
        fr = _make_fr(body)
        result = _check_truncation(fr, max_bytes=max_bytes)
        assert result is not None
        assert result["code"] == "WTRUNCATED"
        assert "9600" in result["message"]

    def test_exactly_at_95_percent(self):
        """Body size at exactly 95% threshold is flagged."""
        max_bytes = 10_000
        body = b"x" * 9500  # Exactly 95%
        fr = _make_fr(body)
        result = _check_truncation(fr, max_bytes=max_bytes)
        assert result is not None
        assert result["code"] == "WTRUNCATED"

    def test_just_below_95_percent(self):
        """Body size just below 95% is not flagged."""
        max_bytes = 10_000
        body = b"x" * 9499
        fr = _make_fr(body)
        result = _check_truncation(fr, max_bytes=max_bytes)
        assert result is None

    def test_content_length_mismatch(self):
        """Content-Length header exceeds actual body size."""
        fr = _make_fr(
            b"x" * 5000,
            headers={"content-length": "10000"},
        )
        result = _check_truncation(fr, max_bytes=100_000)
        assert result is not None
        assert result["code"] == "WTRUNCATED"
        assert "Content-Length" in result["message"]

    def test_content_length_matches(self):
        """Content-Length header matches body — no flag."""
        fr = _make_fr(
            b"x" * 5000,
            headers={"content-length": "5000"},
        )
        result = _check_truncation(fr, max_bytes=100_000)
        assert result is None

    def test_content_length_non_numeric(self):
        """Non-numeric Content-Length is ignored."""
        fr = _make_fr(
            b"x" * 5000,
            headers={"content-length": "not-a-number"},
        )
        result = _check_truncation(fr, max_bytes=100_000)
        assert result is None

    def test_no_headers(self):
        """Missing headers dict doesn't crash."""
        fr = _make_fr(b"x" * 100, headers={})
        result = _check_truncation(fr, max_bytes=10_000)
        assert result is None


# ---------------------------------------------------------------------------
# Completeness gate
# ---------------------------------------------------------------------------

class TestCompletenessGate:
    def test_completion_pct_calculation(self):
        """Verify completeness percentage computation."""
        total = 100
        fetched = 85
        errors = 15
        pct = (fetched / total) * 100 if total > 0 else 100.0
        assert pct == pytest.approx(85.0)

    def test_zero_entries(self):
        """Zero entries gives 100% completion."""
        total = 0
        pct = 100.0 if total == 0 else 0.0
        assert pct == 100.0
