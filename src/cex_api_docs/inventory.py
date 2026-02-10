from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from .db import open_db
from .errors import CexApiDocsError
from .hashing import sha256_hex_text
from .httpfetch import fetch
from .lock import acquire_write_lock
from .sitemaps import SitemapParseResult, iter_unique, parse_sitemap_bytes
from .timeutil import now_iso_utc
from .urlcanon import canonicalize_url


@dataclass(frozen=True, slots=True)
class InventoryConfig:
    exchange_id: str
    section_id: str
    allowed_domains: list[str]
    seed_urls: list[str]
    scope_prefixes: list[str]
    timeout_s: float
    max_bytes: int
    max_redirects: int
    retries: int
    ignore_robots: bool


def _require_store_db(docs_dir: str) -> Path:
    db_path = Path(docs_dir) / "db" / "docs.db"
    if not db_path.exists():
        raise CexApiDocsError(code="ENOINIT", message="Store not initialized. Run `cex-api-docs init` first.", details={"docs_dir": docs_dir})
    return db_path


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


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
        resp = session.get(robots_url, timeout=float(timeout_s), allow_redirects=True, stream=False)
        text = resp.text or ""
    except Exception:
        return []
    finally:
        try:
            resp.close()  # type: ignore[name-defined]
        except Exception:
            pass

    out: list[str] = []
    for line in text.splitlines():
        # Allow arbitrary spacing/case.
        m = re.match(r"(?i)\\s*sitemap\\s*:\\s*(\\S+)\\s*$", line.strip())
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
                continue
            looks_xml = ("xml" in ctype) or (len(fr.body) > 0 and fr.body.lstrip().startswith(b"<"))
            if not looks_xml:
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
    max_redirects: int = 5,
    retries: int = 1,
    ignore_robots: bool = False,
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
    db_path = _require_store_db(docs_dir)
    lock_path = Path(docs_dir) / "db" / ".write.lock"
    session = requests.Session()

    allow = {d.lower() for d in (allowed_domains or []) if d}
    seeds = [s for s in (seed_urls or []) if s]
    scopes = scope_prefixes_from_seeds(seeds)

    cfg = InventoryConfig(
        exchange_id=exchange_id,
        section_id=section_id,
        allowed_domains=sorted(allow),
        seed_urls=seeds,
        scope_prefixes=scopes,
        timeout_s=float(timeout_s),
        max_bytes=int(max_bytes),
        max_redirects=int(max_redirects),
        retries=int(retries),
        ignore_robots=bool(ignore_robots),
    )

    generated_at = now_iso_utc()
    errors: list[dict[str, Any]] = []

    # 1) Discover sitemap candidates.
    robot_sitemaps: list[str] = []
    for s in seeds[:3]:
        # Only need one robots file per host; take first few seeds as hints.
        robot_sitemaps.extend(_robot_sitemaps(session, base_url=s, timeout_s=cfg.timeout_s))
    robot_sitemaps = iter_unique(robot_sitemaps)

    candidates = iter_unique(robot_sitemaps + _common_sitemap_candidates(seeds))

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
        if _in_scope(c, scope_prefixes=scopes):
            urls_canon.append(c)

    urls_final = sorted(iter_unique(urls_canon))
    inv_hash = sha256_hex_text("\\n".join(urls_final))

    sources = {
        "seeds": seeds,
        "scope_prefixes": scopes,
        "robot_sitemaps": robot_sitemaps,
        "sitemap_candidates": candidates,
        "visited_sitemaps": visited_sitemaps,
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
            "errors": len(errors),
        },
        errors=errors[:50],
        samples=samples,
    )


def latest_inventory_id(*, docs_dir: str, exchange_id: str, section_id: str) -> int | None:
    db_path = _require_store_db(docs_dir)
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
