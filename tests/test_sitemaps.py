from __future__ import annotations

import gzip
import unittest

from cex_api_docs.sitemaps import parse_sitemap_bytes


class TestSitemaps(unittest.TestCase):
    def test_parse_urlset(self) -> None:
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/docs/a</loc></url>
  <url><loc>https://example.com/docs/b</loc></url>
</urlset>
"""
        r = parse_sitemap_bytes(data=xml, url="https://example.com/sitemap.xml")
        self.assertEqual(r.kind, "urlset")
        self.assertEqual(r.locs, ["https://example.com/docs/a", "https://example.com/docs/b"])

    def test_parse_sitemap_index(self) -> None:
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>
</sitemapindex>
"""
        r = parse_sitemap_bytes(data=xml, url="https://example.com/sitemap_index.xml")
        self.assertEqual(r.kind, "sitemap_index")
        self.assertEqual(r.locs, ["https://example.com/sitemap-1.xml", "https://example.com/sitemap-2.xml"])

    def test_parse_gz(self) -> None:
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/docs/a</loc></url>
</urlset>
"""
        gz = gzip.compress(xml)
        r = parse_sitemap_bytes(data=gz, url="https://example.com/sitemap.xml.gz")
        self.assertEqual(r.kind, "urlset")
        self.assertEqual(r.locs, ["https://example.com/docs/a"])


if __name__ == "__main__":
    unittest.main()

