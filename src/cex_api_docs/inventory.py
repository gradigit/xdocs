from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from .db import open_db
from .errors import CexApiDocsError
from .hashing import sha256_hex_text
from .httpfetch import fetch
from .lock import acquire_write_lock
from .playwrightfetch import PlaywrightFetcher
from .robots import fetch_robots_policy
from .registry import DocSource, InventoryPolicy
from .sitemaps import SitemapParseResult, iter_unique, parse_sitemap_bytes
from .url_sanitize import sanitize_url
from .store import require_store_db
from .timeutil import now_iso_utc
from .urlcanon import canonicalize_url
from .urlutil import url_host as _host


@dataclass(frozen=True, slots=True)
class InventoryConfig:
    exchange_id: str
    section_id: str
    allowed_domains: list[str]
    seed_urls: list[str]
    doc_sources: list[dict[str, Any]]
    inventory_policy: dict[str, Any]
    link_follow_max_pages_override: int | None
    scope_prefixes: list[str]
    timeout_s: float
    max_bytes: int
    link_follow_max_bytes: int
    max_redirects: int
    retries: int
    ignore_robots: bool
    delay_s: float
    default_render_mode: str


def _robot_sitemaps(session: requests.Session, *, base_url: str, timeout_s: float) -> list[str]:
    """
    Parse `Sitemap:` directives from robots.txt.
    This intentionally does NOT apply robots allow/deny rules (robots doesn't restrict sitemaps).
    """
    parsed = urlsplit(base_url)
    scheme = (parsed.scheme or "https").lower()
    host = parsed.hostname or ""
    if not host:
        return []
    netloc = host.lower()
    if parsed.port:
        netloc = f"{netloc}:{int(parsed.port)}"
    robots_url = urlunsplit((scheme, netloc, "/robots.txt", "", ""))

    try:
        # Use the shared HTTP fetcher so we get the same UA fallback behavior that
        # makes registry validation/crawling robust (some sites 403 python-requests).
        fr = fetch(
            session,
            url=robots_url,
            timeout_s=float(timeout_s),
            max_bytes=1_000_000,
            max_redirects=3,
            retries=0,
            allowed_domains=None,
        )
        text = (fr.body or b"").decode("utf-8", errors="replace")
    except Exception:
        return []

    out: list[str] = []
    for line in text.splitlines():
        # Allow arbitrary spacing/case.
        m = re.match(r"(?i)\s*sitemap\s*:\s*(\S+)\s*$", line.strip())
        if not m:
            continue
        out.append(m.group(1).strip())
    return iter_unique(out)


def _common_sitemap_candidates(seed_urls: list[str]) -> list[str]:
    """
    Heuristic candidate sitemap URLs for a seed host.
    Includes root-level and seed-path-level candidates.
    """
    out: list[str] = []
    for u in seed_urls:
        p = urlsplit(u)
        scheme = (p.scheme or "https").lower()
        host = p.hostname or ""
        if not host:
            continue
        netloc = host.lower()
        if p.port:
            netloc = f"{netloc}:{int(p.port)}"

        for path in (
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/sitemap-index.xml",
            "/sitemap.xml.gz",
            "/sitemap_index.xml.gz",
            "/sitemap-index.xml.gz",
        ):
            out.append(urlunsplit((scheme, netloc, path, "", "")))

        # Also try under the seed directory and a few ancestors.
        # Example: Docusaurus sites often host sitemap at their baseUrl (e.g. /docs/sitemap.xml),
        # while section seeds look like /docs/<section>/...
        seed_dir = p.path or "/"
        if not seed_dir.endswith("/"):
            seed_dir = seed_dir.rsplit("/", 1)[0] + "/"
        seed_dir = seed_dir if seed_dir.startswith("/") else "/" + seed_dir

        ancestors: list[str] = []
        cur = seed_dir
        for _i in range(0, 3):
            ancestors.append(cur)
            if cur == "/":
                break
            cur = cur.rstrip("/")
            cur = cur.rsplit("/", 1)[0] + "/"
            if not cur.startswith("/"):
                cur = "/" + cur

        for a in iter_unique(ancestors):
            for name in ("sitemap.xml", "sitemap.xml.gz", "sitemap_index.xml", "sitemap-index.xml"):
                out.append(urlunsplit((scheme, netloc, a + name, "", "")))

    return iter_unique(out)


def scope_prefixes_from_seeds(seed_urls: list[str]) -> list[str]:
    """
    Derive section "scope" prefixes from seed URLs:
    - canonicalize
    - take directory prefix (ensure trailing slash) to avoid excluding sibling pages
    """
    prefixes: list[str] = []
    for u in seed_urls:
        if not u:
            continue
        c = canonicalize_url(u)
        parsed = urlsplit(c)
        path = parsed.path or "/"
        if not path.endswith("/"):
            path = path.rsplit("/", 1)[0] + "/"
        prefixes.append(urlunsplit((parsed.scheme, parsed.netloc, path, "", "")))
    return sorted(iter_unique(prefixes))


def _in_scope(url: str, *, scope_prefixes: list[str]) -> bool:
    if not scope_prefixes:
        return True
    for p in scope_prefixes:
        if url.startswith(p):
            return True
    return False


def _extract_links(html: str, *, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href or not isinstance(href, str):
            continue
        u = urljoin(base_url, href)
        if u.startswith("http://") or u.startswith("https://"):
            sr = sanitize_url(u)
            if sr.accepted:
                out.append(u)
    return out


def _decode_html(body: bytes) -> str:
    # Inventory link extraction is best-effort; prefer "replace" over hard failure.
    try:
        return body.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover
        return str(body)


def _scope_prefix_from_path(prefix: str, *, seed_urls: list[str]) -> str | None:
    """
    Convert a scope prefix that may be:
    - full URL prefix (https://host/path/)
    - absolute path (/docs/...)
    into a canonical URL prefix.
    """
    s = (prefix or "").strip()
    if not s:
        return None
    if s.startswith("http://") or s.startswith("https://"):
        try:
            c = canonicalize_url(s)
        except Exception:
            return None
        if not c.endswith("/") and (urlsplit(c).path or "/") not in ("", "/"):
            c += "/"
        return c
    if s.startswith("/") and seed_urls:
        try:
            base = canonicalize_url(seed_urls[0])
        except Exception:
            return None
        p = urlsplit(base)
        full = urlunsplit((p.scheme, p.netloc, s, "", ""))
        if not full.endswith("/") and (urlsplit(full).path or "/") not in ("", "/"):
            full += "/"
        return full
    return None


@dataclass(frozen=True, slots=True)
class InventoryResult:
    inventory_id: int
    generated_at: str
    url_count: int
    inventory_hash: str
    sources: dict[str, Any]
    counts: dict[str, Any]
    errors: list[dict[str, Any]]
    samples: dict[str, Any]


def _walk_sitemaps(
    session: requests.Session,
    *,
    sitemap_urls: list[str],
    allowed_domains: set[str],
    timeout_s: float,
    max_bytes: int,
    max_redirects: int,
    retries: int,
    max_sitemaps: int = 250,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """
    Returns (visited_sitemaps, page_urls, errors).
    """
    q: list[str] = list(sitemap_urls)
    seen: set[str] = set()
    visited: list[str] = []
    urls: list[str] = []
    errors: list[dict[str, Any]] = []

    while q and len(visited) < int(max_sitemaps):
        sm = q.pop(0)
        sm_c = canonicalize_url(sm)
        if sm_c in seen:
            continue
        seen.add(sm_c)

        try:
            fr = fetch(
                session,
                url=sm,
                timeout_s=float(timeout_s),
                max_bytes=int(max_bytes),
                max_redirects=int(max_redirects),
                retries=int(retries),
                allowed_domains=allowed_domains,
            )
            # Only attempt to parse sitemaps when they look like XML and succeeded.
            status = int(fr.http_status)
            ctype = (fr.content_type or "").lower()
            if status < 200 or status >= 300:
                errors.append({
                    "url": sm,
                    "error": {
                        "code": "ESITEMAPHTTP",
                        "message": f"Sitemap returned HTTP {status}.",
                        "details": {"url": sm, "http_status": status},
                    },
                })
                continue
            looks_xml = ("xml" in ctype) or (len(fr.body) > 0 and fr.body.lstrip().startswith(b"<"))
            if not looks_xml:
                errors.append({
                    "url": sm,
                    "error": {
                        "code": "ESITEMAPFORMAT",
                        "message": "Sitemap response is not XML.",
                        "details": {"url": sm, "content_type": ctype},
                    },
                })
                continue

            parsed: SitemapParseResult = parse_sitemap_bytes(data=fr.body, url=fr.final_url)
            visited.append(fr.final_url)

            # Filter obvious non-URLs early.
            locs = [l for l in parsed.locs if l.startswith("http://") or l.startswith("https://")]

            if parsed.kind == "sitemap_index":
                # Enqueue nested sitemaps.
                for child in locs:
                    q.append(child)
            else:
                urls.extend(locs)
        except CexApiDocsError as e:
            errors.append({"url": sm, "error": e.to_json()})
        except Exception as e:  # pragma: no cover
            errors.append({"url": sm, "error": {"code": "ESITEMAP", "message": "Unexpected sitemap fetch error", "details": {"error": f"{type(e).__name__}: {e}"}}})

    return visited, urls, errors


def create_inventory(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    exchange_id: str,
    section_id: str,
    allowed_domains: list[str],
    seed_urls: list[str],
    timeout_s: float = 20.0,
    max_bytes: int = 50_000_000,
    link_follow_max_bytes: int | None = None,
    max_redirects: int = 5,
    retries: int = 1,
    ignore_robots: bool = False,
    delay_s: float = 0.25,
    default_render_mode: str = "http",
    doc_sources: list[DocSource] | None = None,
    inventory_policy: InventoryPolicy | None = None,
    link_follow_max_pages_override: int | None = None,
    include_urls: bool = False,
    sample_limit: int = 20,
) -> InventoryResult:
    """
    Deterministically enumerate URLs for a section and persist the inventory into the store DB.

    Current deterministic sources:
    - robots.txt Sitemap directives
    - common sitemap locations
    - seed-derived scope prefixes to keep section inventories bounded
    """
    db_path = require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"
    session = requests.Session()

    allow = {d.lower() for d in (allowed_domains or []) if d}
    seeds = [s for s in (seed_urls or []) if s]
    ds_list = list(doc_sources or [])
    pol = inventory_policy or InventoryPolicy()

    derived_scopes = scope_prefixes_from_seeds(seeds)
    explicit_scopes: list[str] = []

    # Optional explicit scope prefixes from policy and per-source scope constraints.
    for sp in pol.scope_prefixes:
        p = _scope_prefix_from_path(sp, seed_urls=seeds)
        if p:
            explicit_scopes.append(p)
    for ds in ds_list:
        if ds.scope:
            p = _scope_prefix_from_path(ds.scope, seed_urls=seeds)
            if p:
                explicit_scopes.append(p)

    scopes = explicit_scopes if explicit_scopes else derived_scopes
    scopes = sorted(iter_unique(scopes))

    cfg = InventoryConfig(
        exchange_id=exchange_id,
        section_id=section_id,
        allowed_domains=sorted(allow),
        seed_urls=seeds,
        doc_sources=[asdict(ds) for ds in ds_list],
        inventory_policy=asdict(pol),
        link_follow_max_pages_override=None if link_follow_max_pages_override is None else max(1, int(link_follow_max_pages_override)),
        scope_prefixes=scopes,
        timeout_s=float(timeout_s),
        max_bytes=int(max_bytes),
        link_follow_max_bytes=int(link_follow_max_bytes) if link_follow_max_bytes is not None else min(int(max_bytes), 5_000_000),
        max_redirects=int(max_redirects),
        retries=int(retries),
        ignore_robots=bool(ignore_robots),
        delay_s=float(delay_s),
        default_render_mode=str(default_render_mode),
    )

    generated_at = now_iso_utc()
    errors: list[dict[str, Any]] = []

    visited_sitemaps: list[str] = []
    urls: list[str] = []
    robot_sitemaps: list[str] = []
    candidates: list[str] = []

    if pol.mode not in ("inventory", "link_follow"):
        raise CexApiDocsError(code="EBADARG", message="Invalid inventory_policy.mode.", details={"mode": pol.mode})

    if pol.mode == "inventory":
        # 1) Discover sitemap candidates.
        for s in seeds[:3]:
            # Only need one robots file per host; take first few seeds as hints.
            robot_sitemaps.extend(_robot_sitemaps(session, base_url=s, timeout_s=cfg.timeout_s))
        robot_sitemaps = iter_unique(robot_sitemaps)

        ds_sitemaps = [ds.url for ds in ds_list if ds.kind == "sitemap" and ds.url]
        candidates = iter_unique(robot_sitemaps + ds_sitemaps + _common_sitemap_candidates(seeds))

        # 2) Walk sitemap graph to get URLs (best-effort).
        visited_sitemaps, urls, sitemap_errors = _walk_sitemaps(
            session,
            sitemap_urls=candidates,
            allowed_domains=allow,
            timeout_s=cfg.timeout_s,
            max_bytes=cfg.max_bytes,
            max_redirects=cfg.max_redirects,
            retries=cfg.retries,
        )
        errors.extend(sitemap_errors)

        # Auto link-follow fallback: if sitemaps produced < 5 URLs, supplement
        # with one-hop link extraction from seed pages.
        if len(urls) < 5:
            import logging

            _log = logging.getLogger(__name__)
            _log.warning(
                "Sitemaps yielded only %d URLs for %s/%s; running link-follow fallback from seeds.",
                len(urls),
                exchange_id,
                section_id,
            )
            for seed_url in seeds:
                try:
                    fr = fetch(
                        session,
                        url=seed_url,
                        timeout_s=float(cfg.timeout_s),
                        max_bytes=int(cfg.link_follow_max_bytes),
                        max_redirects=int(cfg.max_redirects),
                        retries=int(cfg.retries),
                        allowed_domains=allow,
                    )
                    if 200 <= int(fr.http_status) < 300:
                        html = _decode_html(fr.body)
                        seed_links = _extract_links(html, base_url=fr.final_url)
                        urls.extend(seed_links)
                except Exception:
                    # Best-effort fallback; failures don't abort inventory.
                    continue

    # 3) Canonicalize + filter by allowlist and scope prefixes.
    urls_canon: list[str] = []
    for u in urls:
        try:
            c = canonicalize_url(u)
        except Exception:
            continue
        h = _host(c)
        if allow and h and not (h in allow or any(h.endswith("." + d) for d in allow)):
            continue
        if not _in_scope(c, scope_prefixes=scopes):
            continue
        urls_canon.append(c)

    # Always include the canonicalized seeds.
    for s in seeds:
        try:
            c = canonicalize_url(s)
        except Exception:
            continue
        urls_canon.append(c)

    urls_final = sorted(iter_unique(urls_canon))

    link_follow_visited = 0
    link_follow_discovered = 0
    link_follow_skipped_robots = 0
    link_follow_queue_max = 0
    link_follow_queue_dropped = 0
    link_follow_max_queue = 0

    if pol.mode == "link_follow":
        # Deterministic link-follow inventory (fallback for docs without usable sitemaps).
        max_pages = int(pol.max_pages) if pol.max_pages is not None else 5000
        if max_pages <= 0:
            max_pages = 1
        if cfg.link_follow_max_pages_override is not None:
            max_pages = min(max_pages, int(cfg.link_follow_max_pages_override))

        render_mode = (pol.render_mode or cfg.default_render_mode or "http").strip()
        if render_mode not in ("http", "playwright", "auto"):
            raise CexApiDocsError(code="EBADARG", message="Invalid inventory_policy.render_mode.", details={"render_mode": render_mode})

        import heapq

        pw: PlaywrightFetcher | None = None
        robots_cache: dict[str, Any] = {}
        seen: set[str] = set()
        queued: set[str] = set()
        heap: list[str] = []

        for u in urls_final:
            queued.add(u)
            heapq.heappush(heap, u)

        def robots_can_fetch(u: str) -> bool:
            if cfg.ignore_robots:
                return True
            h = _host(u)
            if not h:
                return False
            if h not in robots_cache:
                robots_cache[h] = fetch_robots_policy(session, url=u, timeout_s=cfg.timeout_s)
            can_fetch_fn, _decision = robots_cache[h]
            return bool(can_fetch_fn(u))

        def _needs_pw(status: int, links0: list[str]) -> bool:
            if status >= 400:
                return True
            if not links0:
                return True
            return False

        max_queue = max_pages * 20
        if max_queue < max_pages:
            max_queue = max_pages
        if max_queue > 200_000:
            max_queue = 200_000
        link_follow_max_queue = int(max_queue)
        link_follow_queue_max = len(queued)

        while heap and len(seen) < max_pages:
            cur = heapq.heappop(heap)
            if cur in seen:
                continue
            seen.add(cur)
            link_follow_visited += 1

            try:
                if not robots_can_fetch(cur):
                    link_follow_skipped_robots += 1
                    continue

                fr = None
                links: list[str] = []

                if render_mode in ("http", "auto"):
                    fr = fetch(
                        session,
                        url=cur,
                        timeout_s=float(cfg.timeout_s),
                        max_bytes=int(cfg.link_follow_max_bytes),
                        max_redirects=int(cfg.max_redirects),
                        retries=int(cfg.retries),
                        allowed_domains=allow,
                    )
                    html = _decode_html(fr.body)
                    links = _extract_links(html, base_url=fr.final_url)

                if render_mode in ("playwright", "auto"):
                    do_pw = render_mode == "playwright"
                    if fr is not None and render_mode == "auto":
                        do_pw = _needs_pw(int(fr.http_status), links)
                    if do_pw:
                        try:
                            if pw is None:
                                pw = PlaywrightFetcher(allowed_domains=allow).open()
                            fr_pw = pw.fetch(url=cur, timeout_s=float(cfg.timeout_s), max_bytes=int(cfg.link_follow_max_bytes), retries=int(cfg.retries))
                            html_pw = _decode_html(fr_pw.body)
                            links_pw = _extract_links(html_pw, base_url=fr_pw.final_url)
                            if fr is None or _needs_pw(int(fr.http_status), links) or len(links_pw) > len(links):
                                fr = fr_pw
                                links = links_pw
                        except CexApiDocsError:
                            # If Playwright is unavailable or fails, keep the HTTP result.
                            pass

                # Canonicalize + filter discovered links.
                new_links: list[str] = []
                for u in links:
                    try:
                        c = canonicalize_url(u)
                    except Exception:
                        continue
                    h = _host(c)
                    if allow and h and not (h in allow or any(h.endswith("." + d) for d in allow)):
                        continue
                    if not _in_scope(c, scope_prefixes=scopes):
                        continue
                    if c in seen or c in queued:
                        continue
                    if len(queued) >= int(max_queue):
                        link_follow_queue_dropped += 1
                        continue
                    queued.add(c)
                    new_links.append(c)

                link_follow_discovered += len(new_links)
                for nl in sorted(iter_unique(new_links)):
                    heapq.heappush(heap, nl)
            except Exception:
                # Best-effort; keep the URL in inventory but don't fail the whole run.
                continue
            finally:
                link_follow_queue_max = max(link_follow_queue_max, len(queued))
                if cfg.delay_s > 0:
                    time.sleep(float(cfg.delay_s))

        if pw is not None:
            pw.close()

        # Include all discovered URLs, not only those we managed to visit before hitting `max_pages`.
        # This keeps inventories closer to "all reachable from the seeds" while still bounding
        # request volume during inventory generation.
        urls_final = sorted(iter_unique(urls_final + sorted(queued)))

    inv_hash = sha256_hex_text("\\n".join(urls_final))

    sources = {
        "seeds": seeds,
        "scope_prefixes": scopes,
        "doc_sources": [asdict(ds) for ds in ds_list],
        "inventory_policy": asdict(pol),
        "robot_sitemaps": robot_sitemaps,
        "sitemap_candidates": candidates,
        "visited_sitemaps": visited_sitemaps,
        "link_follow": {
            "visited": link_follow_visited,
            "discovered": link_follow_discovered,
            "skipped_robots": link_follow_skipped_robots,
            "queue_max": link_follow_queue_max,
            "queue_dropped": link_follow_queue_dropped,
            "max_queue": link_follow_max_queue,
        },
        "config": asdict(cfg),
    }

    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn = open_db(db_path)
        try:
            with conn:
                cur = conn.execute(
                    """
INSERT INTO inventories (exchange_id, section_id, generated_at, sources_json, url_count, inventory_hash)
VALUES (?, ?, ?, ?, ?, ?);
""",
                    (exchange_id, section_id, generated_at, json.dumps(sources, sort_keys=True, ensure_ascii=False), len(urls_final), inv_hash),
                )
                inventory_id = int(cur.lastrowid)

                for u in urls_final:
                    conn.execute(
                        """
INSERT OR IGNORE INTO inventory_entries (inventory_id, canonical_url, status)
VALUES (?, ?, 'pending');
""",
                        (inventory_id, u),
                    )
            conn.commit()
        finally:
            conn.close()

    samples: dict[str, Any] = {
        "urls": urls_final[: int(sample_limit)],
        "sitemaps": visited_sitemaps[:10],
    }
    if include_urls:
        samples["urls_all"] = urls_final

    return InventoryResult(
        inventory_id=inventory_id,
        generated_at=generated_at,
        url_count=len(urls_final),
        inventory_hash=inv_hash,
        sources=sources,
        counts={
            "seed_urls": len(seeds),
            "scope_prefixes": len(scopes),
            "robot_sitemaps": len(robot_sitemaps),
            "sitemap_candidates": len(candidates),
            "visited_sitemaps": len(visited_sitemaps),
            "urls_in_sitemaps": len(urls),
            "urls_in_scope": len(urls_final),
            "link_follow_visited": link_follow_visited,
            "link_follow_discovered": link_follow_discovered,
            "link_follow_skipped_robots": link_follow_skipped_robots,
            "link_follow_queue_max": link_follow_queue_max,
            "link_follow_queue_dropped": link_follow_queue_dropped,
            "errors": len(errors),
        },
        errors=errors[:50],
        samples=samples,
    )


def latest_inventory_id(*, docs_dir: str, exchange_id: str, section_id: str) -> int | None:
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        row = conn.execute(
            """
SELECT id
FROM inventories
WHERE exchange_id = ? AND section_id = ?
ORDER BY generated_at DESC, id DESC
LIMIT 1;
""",
            (exchange_id, section_id),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()
