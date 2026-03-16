from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from xdocs.discover_sources import discover_sources
from tests.http_server import serve_directory


class TestDiscoverSources(unittest.TestCase):
    def test_discovers_spec_links_from_seed_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir(parents=True, exist_ok=True)

            (site / "index.html").write_text(
                "<html><body><a href=\"/openapi.yaml\">OpenAPI</a></body></html>\n",
                encoding="utf-8",
            )
            (site / "openapi.yaml").write_text("openapi: 3.0.0\ninfo:\n  title: x\n  version: 1\npaths: {}\n", encoding="utf-8")

            with serve_directory(site) as base_url:
                seed = f"{base_url}/index.html"
                r = discover_sources(
                    exchange="binance",
                    section="spot",
                    seed_urls=[seed],
                    allowed_domains=["127.0.0.1"],
                    timeout_s=5.0,
                    max_bytes=1_000_000,
                    max_redirects=2,
                    retries=0,
                )

            urls = {s["url"]: set(s["kinds"]) for s in r["sources"]}
            self.assertIn(f"{base_url}/openapi.yaml", urls)
            self.assertTrue("openapi" in urls[f"{base_url}/openapi.yaml"] or "spec_candidate" in urls[f"{base_url}/openapi.yaml"])


if __name__ == "__main__":
    unittest.main()
