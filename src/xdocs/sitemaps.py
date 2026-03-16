from __future__ import annotations

import gzip
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterable

from .errors import XDocsError


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    loc: str
    lastmod: str | None = None
    changefreq: str | None = None
    priority: str | None = None


@dataclass(frozen=True, slots=True)
class SitemapParseResult:
    kind: str  # sitemap_index|urlset|unknown
    locs: list[str]
    entries: list[SitemapEntry] = field(default_factory=list)


def _maybe_gunzip(data: bytes) -> bytes:
    # Gzip magic header: 0x1f 0x8b
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        return gzip.decompress(data)
    return data


def _local(tag: str) -> str:
    """Strip namespace prefix from an XML tag."""
    idx = tag.rfind("}")
    if idx != -1:
        return tag[idx + 1:].lower()
    return tag.lower()


def _child_text(parent: ET.Element, local_name: str) -> str | None:
    """Get text of the first child element matching local_name (namespace-agnostic)."""
    for child in parent:
        if _local(child.tag) == local_name and child.text:
            t = child.text.strip()
            if t:
                return t
    return None


def parse_sitemap_bytes(*, data: bytes, url: str) -> SitemapParseResult:
    """
    Parse a sitemap document (xml or gzipped xml) and return loc entries
    with optional lastmod/changefreq/priority metadata.

    Backward compatible: callers using .locs still get a flat list of URLs.
    """
    raw = _maybe_gunzip(data)
    try:
        bio = io.BytesIO(raw)
        it = ET.iterparse(bio, events=("start", "end"))
        root_tag: str | None = None
        entries: list[SitemapEntry] = []
        locs: list[str] = []

        # Track parent elements: <url> and <sitemap> contain <loc>, <lastmod>, etc.
        entry_tags = frozenset(("url", "sitemap"))

        for event, elem in it:
            if event == "start" and root_tag is None:
                root_tag = str(elem.tag or "")

            if event == "end":
                local = _local(elem.tag)
                if local in entry_tags:
                    loc = _child_text(elem, "loc")
                    if loc:
                        entry = SitemapEntry(
                            loc=loc,
                            lastmod=_child_text(elem, "lastmod"),
                            changefreq=_child_text(elem, "changefreq"),
                            priority=_child_text(elem, "priority"),
                        )
                        entries.append(entry)
                        locs.append(loc)
                    # Keep memory bounded for large sitemaps.
                    elem.clear()

        # Fallback: if no <url>/<sitemap> parents found but bare <loc> tags exist,
        # do a second pass (handles malformed/unusual sitemaps).
        if not locs:
            bio2 = io.BytesIO(raw)
            for _event, elem2 in ET.iterparse(bio2, events=("end",)):
                if _local(elem2.tag) == "loc" and elem2.text:
                    t = elem2.text.strip()
                    if t:
                        locs.append(t)
                        entries.append(SitemapEntry(loc=t))
                elem2.clear()

        kind = "unknown"
        if root_tag:
            rt = root_tag.lower()
            if rt.endswith("sitemapindex"):
                kind = "sitemap_index"
            elif rt.endswith("urlset"):
                kind = "urlset"

        return SitemapParseResult(kind=kind, locs=locs, entries=entries)
    except XDocsError:
        raise
    except Exception as e:
        raise XDocsError(
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
