from __future__ import annotations

import gzip
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

from .errors import CexApiDocsError


@dataclass(frozen=True, slots=True)
class SitemapParseResult:
    kind: str  # sitemap_index|urlset|unknown
    locs: list[str]


def _maybe_gunzip(data: bytes) -> bytes:
    # Gzip magic header: 0x1f 0x8b
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        return gzip.decompress(data)
    return data


def parse_sitemap_bytes(*, data: bytes, url: str) -> SitemapParseResult:
    """
    Parse a sitemap document (xml or gzipped xml) and return loc entries.

    This intentionally does not attempt to validate the schema beyond:
    - determine root kind (sitemapindex vs urlset) when possible
    - collect all <loc> values
    """
    raw = _maybe_gunzip(data)
    try:
        bio = io.BytesIO(raw)
        it = ET.iterparse(bio, events=("start", "end"))
        root_tag: str | None = None
        locs: list[str] = []

        for event, elem in it:
            if event == "start" and root_tag is None:
                root_tag = str(elem.tag or "")

            if event == "end":
                tag = str(elem.tag or "")
                if tag.lower().endswith("loc") and elem.text:
                    t = elem.text.strip()
                    if t:
                        locs.append(t)
                # Keep memory bounded for large sitemaps.
                elem.clear()

        kind = "unknown"
        if root_tag:
            rt = root_tag.lower()
            if rt.endswith("sitemapindex"):
                kind = "sitemap_index"
            elif rt.endswith("urlset"):
                kind = "urlset"

        return SitemapParseResult(kind=kind, locs=locs)
    except CexApiDocsError:
        raise
    except Exception as e:
        raise CexApiDocsError(
            code="ESITEMAP",
            message="Failed parsing sitemap XML.",
            details={"url": url, "error": f"{type(e).__name__}: {e}"},
        ) from e


def iter_unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if not it:
            continue
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out

