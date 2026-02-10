from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .errors import CexApiDocsError
from .httpfetch import fetch


SPEC_HINT_RE = re.compile(r"(openapi|swagger|postman|collection|asyncapi)", flags=re.IGNORECASE)
SPEC_EXT_RE = re.compile(r"\.(json|ya?ml)$", flags=re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DiscoverConfig:
    exchange: str
    section: str
    seed_urls: list[str]
    allowed_domains: list[str]
    timeout_s: float
    max_bytes: int
    max_redirects: int
    retries: int


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _is_http_url(url: str) -> bool:
    return urlsplit(url).scheme in ("http", "https")


def _host_allowed(host: str, allowed: set[str]) -> bool:
    h = host.lower()
    for d in allowed:
        dd = d.lower()
        if h == dd or h.endswith("." + dd):
            return True
    return False


def _extract_links(html: str, *, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for tag in soup.find_all(["a", "link", "script"]):
        attr = "href" if tag.name in ("a", "link") else "src"
        v = tag.get(attr)
        if not v:
            continue
        if not isinstance(v, str):
            continue
        u = urljoin(base_url, v)
        if _is_http_url(u):
            out.append(u)
    return out


def _classify(url: str) -> str | None:
    u = url.lower()
    if "sitemap" in u and (u.endswith(".xml") or u.endswith(".xml.gz")):
        return "sitemap"
    if SPEC_HINT_RE.search(u) and SPEC_EXT_RE.search(u):
        if "postman" in u or "collection" in u:
            return "postman"
        if "asyncapi" in u:
            return "asyncapi"
        return "openapi"
    # Allow extension-only detection for common spec formats.
    if SPEC_EXT_RE.search(u):
        return "spec_candidate"
    return None


def discover_sources(
    *,
    exchange: str,
    section: str,
    seed_urls: list[str],
    allowed_domains: list[str],
    timeout_s: float = 20.0,
    max_bytes: int = 10_000_000,
    max_redirects: int = 5,
    retries: int = 1,
) -> dict[str, Any]:
    if not exchange or not section:
        raise CexApiDocsError(code="EBADARG", message="Missing exchange/section.")
    seeds = [s for s in (seed_urls or []) if s]
    if not seeds:
        raise CexApiDocsError(code="EBADARG", message="No seed_urls provided.", details={"exchange": exchange, "section": section})

    allowed = {d.lower() for d in allowed_domains if d}
    cfg = DiscoverConfig(
        exchange=str(exchange),
        section=str(section),
        seed_urls=seeds,
        allowed_domains=sorted(allowed),
        timeout_s=float(timeout_s),
        max_bytes=int(max_bytes),
        max_redirects=int(max_redirects),
        retries=int(retries),
    )

    session = requests.Session()
    candidates: dict[str, dict[str, Any]] = {}

    # Robots.txt sitemap hints.
    for s in seeds[:3]:
        h = _host(s)
        if not h:
            continue
        if allowed and not _host_allowed(h, allowed):
            continue
        robots_url = f"https://{h}/robots.txt"
        resp = None
        try:
            resp = session.get(robots_url, timeout=float(cfg.timeout_s), allow_redirects=True, stream=False)
            text = resp.text or ""
            for line in text.splitlines():
                m = re.match(r"(?i)\\s*sitemap\\s*:\\s*(\\S+)\\s*$", line.strip())
                if not m:
                    continue
                sm = m.group(1).strip()
                if not _is_http_url(sm):
                    continue
                candidates.setdefault(sm, {"url": sm, "kinds": set(), "evidence": []})
                candidates[sm]["kinds"].add("sitemap")
                candidates[sm]["evidence"].append({"from": "robots.txt", "robots_url": robots_url})
        except Exception:
            # Discovery is best-effort; ignore.
            pass
        finally:
            try:
                if resp is not None:
                    resp.close()
            except Exception:
                pass

    # Seed page link mining.
    for s in seeds[:5]:
        try:
            fr = fetch(
                session,
                url=s,
                timeout_s=cfg.timeout_s,
                max_bytes=cfg.max_bytes,
                max_redirects=cfg.max_redirects,
                retries=cfg.retries,
                allowed_domains=allowed if allowed else None,
            )
            html = fr.body.decode("utf-8", errors="replace")
            for u in _extract_links(html, base_url=fr.final_url):
                k = _classify(u)
                if k is None:
                    continue
                candidates.setdefault(u, {"url": u, "kinds": set(), "evidence": []})
                candidates[u]["kinds"].add(k)
                candidates[u]["evidence"].append({"from": "seed_page", "seed_url": s})
        except Exception:
            continue

    out_sources: list[dict[str, Any]] = []
    for u, rec in sorted(candidates.items(), key=lambda x: x[0]):
        kinds = sorted({str(k) for k in rec.get("kinds", set()) if k})
        if not kinds:
            continue
        out_sources.append({"url": u, "kinds": kinds, "evidence": rec.get("evidence", [])[:5]})

    return {"cmd": "discover-sources", "schema_version": "v1", "config": asdict(cfg), "sources": out_sources}
