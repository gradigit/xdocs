from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cex_api_docs.db import open_db
from cex_api_docs.httpfetch import FetchResult
from cex_api_docs.markdown import apply_quality_fallback, extract_block_metadata, extractor_info_v1, normalize_markdown
from cex_api_docs.page_store import extract_page_markdown, store_page
from cex_api_docs.store import init_store


class TestMarkdownPipeline(unittest.TestCase):
    def test_normalize_converts_code_tags_to_fences(self) -> None:
        md = "before\n\n[code]\nprint('x')\n[/code]\n\nafter\n"
        out = normalize_markdown(md)
        self.assertIn("```text", out)
        self.assertIn("print('x')", out)
        self.assertNotIn("[code]", out.lower())
        self.assertNotIn("[/code]", out.lower())

    def test_normalize_appends_table_fallback(self) -> None:
        html = """
<html><body>
  <h1>Sample</h1>
  <table>
    <tr><th>Name</th><th>Value</th></tr>
    <tr><td>rate</td><td>10</td></tr>
  </table>
</body></html>
"""
        out = normalize_markdown("# Sample\n", html=html)
        self.assertIn("## Extracted Tables", out)
        self.assertIn("| Name | Value |", out)
        self.assertIn("| rate | 10 |", out)

    def test_quality_fallback_adds_structural_extract(self) -> None:
        html = """
<html><body>
  <pre>curl -X GET /api/v1/test</pre>
  <table><tr><td>a</td><td>b</td></tr></table>
</body></html>
"""
        base = "short"
        out = apply_quality_fallback(base, html=html)
        self.assertIn("Structured Fallback Extract", out)
        self.assertIn("```text", out)
        self.assertIn("curl -X GET /api/v1/test", out)

    def test_extract_block_metadata_detects_blocks(self) -> None:
        md = """# Heading

```text
hello
```

| a | b |
| --- | --- |
| 1 | 2 |
"""
        meta = extract_block_metadata(md)
        self.assertEqual(meta["counts"]["headings"], 1)
        self.assertEqual(meta["counts"]["code_blocks"], 1)
        self.assertEqual(meta["counts"]["table_blocks"], 1)

    def test_extract_block_metadata_ignores_heading_and_table_inside_code(self) -> None:
        md = """# Outside

```text
# inside code
| a | b |
| --- | --- |
| 1 | 2 |
```
"""
        meta = extract_block_metadata(md)
        self.assertEqual(meta["counts"]["headings"], 1)
        self.assertEqual(meta["counts"]["code_blocks"], 1)
        self.assertEqual(meta["counts"]["table_blocks"], 0)

    def test_extract_block_metadata_supports_tilde_fences(self) -> None:
        md = """~~~bash
echo hi
~~~
"""
        meta = extract_block_metadata(md)
        self.assertEqual(meta["counts"]["code_blocks"], 1)

    def test_extract_page_markdown_uses_pipeline(self) -> None:
        html = (
            "<html><head><title>T</title></head><body>"
            "<h1>T</h1><pre>echo hi</pre>"
            "<table><tr><th>x</th><th>y</th></tr><tr><td>1</td><td>2</td></tr></table>"
            "</body></html>"
        )
        fr = FetchResult(
            url="https://example.com/docs",
            final_url="https://example.com/docs",
            redirect_chain=[],
            http_status=200,
            content_type="text/html; charset=utf-8",
            headers={},
            body=html.encode("utf-8"),
        )
        _html, _title, md, wc = extract_page_markdown(fr=fr)
        self.assertIn("```text", md)
        self.assertIn("Extracted Tables", md)
        self.assertGreater(wc, 0)

    def test_store_page_writes_blocks_sidecar_metadata(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (
            "<html><head><title>T</title></head><body>"
            "<h1>T</h1><pre>echo hi</pre>"
            "<table><tr><th>x</th><th>y</th></tr><tr><td>1</td><td>2</td></tr></table>"
            "</body></html>"
        )
        fr = FetchResult(
            url="https://example.com/docs",
            final_url="https://example.com/docs",
            redirect_chain=[],
            http_status=200,
            content_type="text/html; charset=utf-8",
            headers={},
            body=html.encode("utf-8"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=repo_root / "schema" / "schema.sql", lock_timeout_s=1.0)
            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                with conn:
                    cur = conn.execute(
                        "INSERT INTO crawl_runs (started_at, ended_at, config_json) VALUES (?, ?, ?);",
                        ("2026-02-26T00:00:00Z", None, "{}"),
                    )
                    crawl_run_id = int(cur.lastrowid)

                rec = store_page(
                    conn=conn,
                    docs_root=docs_dir,
                    crawl_run_id=crawl_run_id,
                    url=fr.url,
                    fr=fr,
                    render_mode="http",
                    extractor=extractor_info_v1(),
                )
            finally:
                conn.close()

            blocks_path = Path(str(rec["paths"]["blocks_path"]))
            self.assertTrue(blocks_path.exists())
            payload = json.loads(blocks_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(int(payload["counts"]["code_blocks"]), 1)


if __name__ == "__main__":
    unittest.main()
