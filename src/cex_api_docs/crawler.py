from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .db import open_db
from .errors import CexApiDocsError
from .fs import atomic_write_bytes, atomic_write_text
from .hashing import sha256_hex_bytes, sha256_hex_text
from .httpfetch import FetchResult, fetch
from .lock import acquire_write_lock
from .markdown import extractor_info_v1, html_to_markdown, normalize_markdown
from .playwrightfetch import PlaywrightFetcher
from .robots import fetch_robots_policy
from .timeutil import now_iso_utc
from .urlcanon import canonicalize_url
from .urlutil import url_host as _host


DEFAULT_TIMEOUT_S = 20.0
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_DELAY_S = 1.0
DEFAULT_RETRIES = 2


def _parse_charset(content_type: str) -> str | None:
    # e.g. "text/html; charset=utf-8"
    m = re.search(r"charset=([\w\-]+)", content_type, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def _decode_body(body: bytes, content_type: str) -> str:
    charset = _parse_charset(content_type) or "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _extract_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        return t or None
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(" ", strip=True)
        return t or None
    return None


def _extract_links(html: str, *, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if not href:
            continue
        out.append(urljoin(base_url, href))
    return out


def _is_http_url(url: str) -> bool:
    s = urlsplit(url)
    return s.scheme in ("http", "https")


def _write_crawl_log(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False))
        f.write("\n")


@dataclass(frozen=True, slots=True)
class CrawlConfig:
    seeds: list[str]
    allowed_domains: list[str]
    max_depth: int
    max_pages: int
    delay_s: float
    timeout_s: float
    max_bytes: int
    max_redirects: int
    retries: int
    ignore_robots: bool
    render_mode: str  # http|playwright|auto


def crawl_store(
    *,
    docs_dir: str,
    schema_version: str,
    lock_timeout_s: float,
    seeds: list[str],
    allowed_domains: list[str],
    max_depth: int = 2,
    max_pages: int = 200,
    delay_s: float = DEFAULT_DELAY_S,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    retries: int = DEFAULT_RETRIES,
    ignore_robots: bool = False,
    render_mode: str = "http",
) -> dict[str, Any]:
    if render_mode not in ("http", "playwright", "auto"):
        raise CexApiDocsError(code="EBADARG", message="Invalid render_mode.", details={"render_mode": render_mode})

    root = Path(docs_dir)
    db_path = root / "db" / "docs.db"
    if not db_path.exists():
        raise CexApiDocsError(code="ENOINIT", message="Store not initialized. Run `cex-api-docs init` first.", details={"docs_dir": docs_dir})

    lock_path = root / "db" / ".write.lock"

    cfg = CrawlConfig(
        seeds=seeds,
        allowed_domains=allowed_domains,
        max_depth=int(max_depth),
        max_pages=int(max_pages),
        delay_s=float(delay_s),
        timeout_s=float(timeout_s),
        max_bytes=int(max_bytes),
        max_redirects=int(max_redirects),
        retries=int(retries),
        ignore_robots=bool(ignore_robots),
        render_mode=render_mode,
    )

    started_at = now_iso_utc()
    extractor = extractor_info_v1()

    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn = open_db(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO crawl_runs (started_at, ended_at, config_json) VALUES (?, ?, ?);",
                (started_at, None, json.dumps(asdict(cfg), sort_keys=True)),
            )
            crawl_run_id = int(cur.lastrowid)
            conn.commit()

            session = requests.Session()
            allow_hosts = {d.lower() for d in allowed_domains}
            pw: PlaywrightFetcher | None = None

            robots_cache: dict[str, Any] = {}

            def robots_can_fetch(u: str) -> bool:
                if cfg.ignore_robots:
                    return True
                h = _host(u)
                if h not in robots_cache:
                    robots_cache[h] = fetch_robots_policy(session, url=u, timeout_s=cfg.timeout_s)
                can_fetch_fn, _decision = robots_cache[h]
                return bool(can_fetch_fn(u))

            q: deque[tuple[str, int]] = deque()
            seen: set[str] = set()

            for s in seeds:
                if not _is_http_url(s):
                    continue
                if _host(s) not in allow_hosts:
                    continue
                q.append((s, 0))
                seen.add(canonicalize_url(s))

            stored = 0
            fetched = 0
            skipped = 0
            errors: list[dict[str, Any]] = []

            while q and stored < cfg.max_pages:
                url, depth = q.popleft()
                if depth > cfg.max_depth:
                    skipped += 1
                    continue
                if not _is_http_url(url):
                    skipped += 1
                    continue
                if _host(url) not in allow_hosts:
                    skipped += 1
                    continue
                if not robots_can_fetch(url):
                    skipped += 1
                    continue

                try:
                    fr: FetchResult | None = None
                    used_render_mode = "http"

                    def extract(fr0: FetchResult) -> tuple[str, str | None, str, int]:
                        html0 = _decode_body(fr0.body, fr0.content_type)
                        title0 = _extract_title(html0)

                        md_norm0 = ""
                        if "text/html" in fr0.content_type.lower() or fr0.content_type.lower().startswith("text/"):
                            md_raw0 = html_to_markdown(html0, base_url=fr0.final_url)
                            md_norm0 = normalize_markdown(md_raw0)

                        wc0 = len(md_norm0.split())
                        return html0, title0, md_norm0, wc0

                    def needs_playwright(fr0: FetchResult, md_norm0: str, wc0: int) -> bool:
                        # Heuristics: JS-heavy doc pages often return empty markdown in HTTP mode.
                        if int(fr0.http_status) >= 400:
                            return True
                        if wc0 <= 0 or not md_norm0.strip():
                            return True
                        return False

                    html = ""
                    title = None
                    markdown_norm = ""
                    word_count = 0

                    if cfg.render_mode in ("http", "auto"):
                        fr = fetch(
                            session,
                            url=url,
                            timeout_s=cfg.timeout_s,
                            max_bytes=cfg.max_bytes,
                            max_redirects=cfg.max_redirects,
                            retries=cfg.retries,
                            allowed_domains=allow_hosts,
                        )
                        used_render_mode = "http"
                        html, title, markdown_norm, word_count = extract(fr)

                    if cfg.render_mode in ("playwright", "auto"):
                        # Always use Playwright when explicitly requested.
                        do_pw = cfg.render_mode == "playwright"
                        if fr is not None and cfg.render_mode == "auto":
                            do_pw = needs_playwright(fr, markdown_norm, word_count)

                        if do_pw:
                            if pw is None:
                                pw = PlaywrightFetcher(allowed_domains=allow_hosts).open()
                            fr_pw = pw.fetch(
                                url=url,
                                timeout_s=cfg.timeout_s,
                                max_bytes=cfg.max_bytes,
                                retries=cfg.retries,
                            )
                            html_pw, title_pw, md_pw, wc_pw = extract(fr_pw)

                            # Prefer the rendered result when it produced more content or when HTTP fetch errored.
                            if fr is None or int(fr.http_status) >= 400 or wc_pw > word_count:
                                fr = fr_pw
                                used_render_mode = "playwright"
                                html, title, markdown_norm, word_count = html_pw, title_pw, md_pw, wc_pw

                    if fr is None:  # pragma: no cover
                        raise CexApiDocsError(code="ENET", message="No fetch result produced.", details={"url": url})
                except CexApiDocsError as e:
                    errors.append({"url": url, "error": e.to_json()})
                    continue

                fetched += 1

                final_url = fr.final_url
                canonical_url = canonicalize_url(final_url)
                domain = _host(final_url)
                path_hash = sha256_hex_text(canonical_url)
                crawled_at = now_iso_utc()
                raw_hash = sha256_hex_bytes(fr.body)
                # html/title/markdown_norm/word_count extracted during fetch.
                content_hash = sha256_hex_text(markdown_norm)

                raw_path = root / "raw" / domain / f"{path_hash}.bin"
                md_path = root / "pages" / domain / f"{path_hash}.md"
                meta_path = root / "meta" / domain / f"{path_hash}.json"

                prev_content_hash: str | None = None
                # Upsert in a per-page transaction after writing files.
                atomic_write_bytes(raw_path, fr.body)
                if markdown_norm:
                    atomic_write_text(md_path, markdown_norm)

                meta: dict[str, Any] = {
                    "url": url,
                    "final_url": final_url,
                    "canonical_url": canonical_url,
                    "redirect_chain": fr.redirect_chain,
                    "crawled_at": crawled_at,
                    "http_status": fr.http_status,
                    "content_type": fr.content_type,
                    "raw_hash": raw_hash,
                    "content_hash": content_hash,
                    "prev_content_hash": None,
                    "path_hash": path_hash,
                    "render_mode": used_render_mode,
                    "title": title,
                    "word_count": word_count,
                    "headers": fr.headers,
                    "extractor": {
                        "name": extractor.name,
                        "version": extractor.version,
                        "config": extractor.config,
                        "config_hash": extractor.config_hash,
                    },
                }

                # DB write: upsert pages + insert page_versions + update pages_fts.
                with conn:
                    existing = conn.execute(
                        "SELECT id, content_hash FROM pages WHERE canonical_url = ?;",
                        (canonical_url,),
                    ).fetchone()
                    if existing is not None:
                        page_id = int(existing["id"])
                        prev_content_hash = str(existing["content_hash"]) if existing["content_hash"] else None
                        conn.execute(
                            """
UPDATE pages
SET url = ?, final_url = ?, domain = ?, path_hash = ?, title = ?, http_status = ?, content_type = ?,
    render_mode = ?, raw_hash = ?, content_hash = ?, prev_content_hash = ?, crawled_at = ?,
    raw_path = ?, markdown_path = ?, meta_path = ?, word_count = ?,
    extractor_name = ?, extractor_version = ?, extractor_config_json = ?, extractor_config_hash = ?,
    last_crawl_run_id = ?
WHERE id = ?;
""",
                            (
                                url,
                                final_url,
                                domain,
                                path_hash,
                                title,
                                fr.http_status,
                                fr.content_type,
                                used_render_mode,
                                raw_hash,
                                content_hash,
                                prev_content_hash,
                                crawled_at,
                                str(raw_path),
                                str(md_path) if markdown_norm else None,
                                str(meta_path),
                                word_count,
                                extractor.name,
                                extractor.version,
                                json.dumps(extractor.config, sort_keys=True),
                                extractor.config_hash,
                                crawl_run_id,
                                page_id,
                            ),
                        )

                        # If the page content changed, enqueue re-review for endpoints citing the prior content hash.
                        if prev_content_hash and prev_content_hash != content_hash:
                            impacted = conn.execute(
                                """
SELECT DISTINCT endpoint_id, field_name
FROM endpoint_sources
WHERE page_canonical_url = ? AND page_content_hash = ?;
""",
                                (canonical_url, prev_content_hash),
                            ).fetchall()
                            for imp in impacted:
                                conn.execute(
                                    """
INSERT INTO review_queue (
  kind, endpoint_id, field_name, reason, status, created_at, details_json
) VALUES (?, ?, ?, ?, 'open', ?, ?);
""",
                                    (
                                        "source_changed",
                                        imp["endpoint_id"],
                                        imp["field_name"],
                                        "Source page changed; re-review required",
                                        crawled_at,
                                        json.dumps(
                                            {
                                                "page_canonical_url": canonical_url,
                                                "old_content_hash": prev_content_hash,
                                                "new_content_hash": content_hash,
                                                "crawl_run_id": crawl_run_id,
                                            },
                                            sort_keys=True,
                                        ),
                                    ),
                                )
                    else:
                        cur2 = conn.execute(
                            """
INSERT INTO pages (
  canonical_url, url, final_url, domain, path_hash, title,
  http_status, content_type, render_mode,
  raw_hash, content_hash, prev_content_hash,
  crawled_at, raw_path, markdown_path, meta_path, word_count,
  extractor_name, extractor_version, extractor_config_json, extractor_config_hash,
  last_crawl_run_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                            (
                                canonical_url,
                                url,
                                final_url,
                                domain,
                                path_hash,
                                title,
                                fr.http_status,
                                fr.content_type,
                                used_render_mode,
                                raw_hash,
                                content_hash,
                                None,
                                crawled_at,
                                str(raw_path),
                                str(md_path) if markdown_norm else None,
                                str(meta_path),
                                word_count,
                                extractor.name,
                                extractor.version,
                                json.dumps(extractor.config, sort_keys=True),
                                extractor.config_hash,
                                crawl_run_id,
                            ),
                        )
                        page_id = int(cur2.lastrowid)

                    meta["prev_content_hash"] = prev_content_hash
                    atomic_write_text(meta_path, json.dumps(meta, sort_keys=True, ensure_ascii=False, indent=2) + "\n")

                    conn.execute(
                        """
INSERT INTO page_versions (
  page_id, crawl_run_id, crawled_at, http_status, content_type,
  raw_hash, content_hash, raw_path, markdown_path, meta_path
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                        (
                            page_id,
                            crawl_run_id,
                            crawled_at,
                            fr.http_status,
                            fr.content_type,
                            raw_hash,
                            content_hash,
                            str(raw_path),
                            str(md_path) if markdown_norm else None,
                            str(meta_path),
                        ),
                    )

                    if markdown_norm:
                        conn.execute("DELETE FROM pages_fts WHERE rowid = ?;", (page_id,))
                        conn.execute(
                            "INSERT INTO pages_fts (rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);",
                            (page_id, canonical_url, title or "", markdown_norm),
                        )

                _write_crawl_log(
                    root / "crawl-log.jsonl",
                    {
                        "ts": crawled_at,
                        "crawl_run_id": crawl_run_id,
                        "url": url,
                        "final_url": final_url,
                        "canonical_url": canonical_url,
                        "path_hash": path_hash,
                        "http_status": fr.http_status,
                        "content_hash": content_hash,
                    },
                )

                stored += 1

                # Link discovery (only when HTML).
                if markdown_norm and depth < cfg.max_depth:
                    for link in _extract_links(html, base_url=final_url):
                        if not _is_http_url(link):
                            continue
                        if _host(link) not in allow_hosts:
                            continue
                        c = canonicalize_url(link)
                        if c in seen:
                            continue
                        seen.add(c)
                        q.append((link, depth + 1))

                time.sleep(cfg.delay_s)

            ended_at = now_iso_utc()
            conn.execute("UPDATE crawl_runs SET ended_at = ? WHERE id = ?;", (ended_at, crawl_run_id))
            conn.commit()

            robots_decisions = {}
            for host, (_fn, decision) in robots_cache.items():
                robots_decisions[host] = asdict(decision)

            return {
                "cmd": "crawl",
                "schema_version": schema_version,
                "docs_dir": str(root),
                "crawl_run_id": crawl_run_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "config": asdict(cfg),
                "robots": robots_decisions,
                "counts": {"fetched": fetched, "stored": stored, "skipped": skipped, "errors": len(errors)},
                "errors": errors[:50],
            }
        finally:
            conn.close()
            if pw is not None:
                pw.close()
