from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from .db import open_db
from .errors import CexApiDocsError
from .httpfetch import FetchResult, fetch
from .lock import acquire_write_lock
from .markdown import extractor_info_v1
from .page_store import extract_page_markdown, store_page
from .playwrightfetch import PlaywrightFetcher
from .robots import fetch_robots_policy
from .store import require_store_db
from .timeutil import now_iso_utc


DEFAULT_TIMEOUT_S = 20.0
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_DELAY_S = 0.25
DEFAULT_RETRIES = 2


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


class _DomainRateLimiter:
    """Thread-safe per-domain rate limiter."""

    def __init__(self, delay_s: float) -> None:
        self._delay_s = delay_s
        self._locks: dict[str, threading.Lock] = {}
        self._last_fetch: dict[str, float] = {}
        self._global_lock = threading.Lock()

    def wait(self, domain: str) -> None:
        with self._global_lock:
            if domain not in self._locks:
                self._locks[domain] = threading.Lock()
            lock = self._locks[domain]
        with lock:
            now = time.monotonic()
            last = self._last_fetch.get(domain, 0.0)
            elapsed = now - last
            if elapsed < self._delay_s:
                time.sleep(self._delay_s - elapsed)
            self._last_fetch[domain] = time.monotonic()


@dataclass(frozen=True, slots=True)
class FetchInventoryConfig:
    exchange_id: str
    section_id: str
    inventory_id: int
    allowed_domains: list[str]
    delay_s: float
    timeout_s: float
    max_bytes: int
    max_redirects: int
    retries: int
    ignore_robots: bool
    render_mode: str  # http|playwright|auto
    resume: bool
    limit: int | None
    concurrency: int


def fetch_inventory(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    exchange_id: str,
    section_id: str,
    inventory_id: int,
    allowed_domains: list[str],
    delay_s: float = DEFAULT_DELAY_S,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    retries: int = DEFAULT_RETRIES,
    ignore_robots: bool = False,
    render_mode: str = "http",
    resume: bool = False,
    limit: int | None = None,
    concurrency: int = 1,
) -> dict[str, Any]:
    if render_mode not in ("http", "playwright", "auto"):
        raise CexApiDocsError(code="EBADARG", message="Invalid render_mode.", details={"render_mode": render_mode})

    db_path = require_store_db(docs_dir)
    docs_root = Path(docs_dir)
    lock_path = docs_root / "db" / ".write.lock"

    allow_hosts = {d.lower() for d in (allowed_domains or []) if d}

    cfg = FetchInventoryConfig(
        exchange_id=exchange_id,
        section_id=section_id,
        inventory_id=int(inventory_id),
        allowed_domains=sorted(allow_hosts),
        delay_s=float(delay_s),
        timeout_s=float(timeout_s),
        max_bytes=int(max_bytes),
        max_redirects=int(max_redirects),
        retries=int(retries),
        ignore_robots=bool(ignore_robots),
        render_mode=str(render_mode),
        resume=bool(resume),
        limit=None if limit is None else int(limit),
        concurrency=max(1, int(concurrency)),
    )

    started_at = now_iso_utc()
    extractor = extractor_info_v1()

    conn = open_db(db_path)
    pw: PlaywrightFetcher | None = None
    try:
        # Phase A: brief lock — create crawl_run + read entries.
        with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
            cur = conn.execute(
                "INSERT INTO crawl_runs (started_at, ended_at, config_json) VALUES (?, ?, ?);",
                (started_at, None, json.dumps(asdict(cfg), sort_keys=True)),
            )
            crawl_run_id = int(cur.lastrowid)
            conn.commit()

        # Read entries (WAL mode allows reads without flock).
        where = "WHERE inventory_id = ?"
        params: list[Any] = [int(inventory_id)]
        if cfg.resume:
            statuses = ["pending", "error"]
            if cfg.ignore_robots:
                statuses.append("skipped")
            placeholders = ", ".join("?" for _ in statuses)
            where += f" AND status IN ({placeholders})"
            params.extend(statuses)

        rows = conn.execute(
            f"""
SELECT id, canonical_url, status
FROM inventory_entries
{where}
ORDER BY canonical_url ASC;
""",
            tuple(params),
        ).fetchall()
        entries = [{"id": int(r["id"]), "canonical_url": str(r["canonical_url"]), "status": str(r["status"])} for r in rows]
        if cfg.limit is not None:
            entries = entries[: int(cfg.limit)]

        session = requests.Session()
        robots_cache: dict[str, Any] = {}

        def robots_can_fetch(u: str) -> bool:
            if cfg.ignore_robots:
                return True
            h = _host(u)
            if h not in robots_cache:
                robots_cache[h] = fetch_robots_policy(session, url=u, timeout_s=cfg.timeout_s)
            can_fetch_fn, _decision = robots_cache[h]
            return bool(can_fetch_fn(u))

        fetched = 0
        stored = 0
        skipped = 0
        new_pages = 0
        updated_pages = 0
        unchanged_pages = 0
        errors: list[dict[str, Any]] = []

        def _needs_playwright(fr0: FetchResult, wc0: int) -> bool:
            if int(fr0.http_status) >= 400:
                return True
            if wc0 <= 0:
                return True
            return False

        def _store_result(
            ent_id: int, url: str, fr: FetchResult, used_render: str,
            title: str | None, md_norm: str, wc: int,
        ) -> None:
            nonlocal fetched, stored, new_pages, updated_pages, unchanged_pages
            fetched += 1
            with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
                rec = store_page(
                    conn=conn,
                    docs_root=docs_root,
                    crawl_run_id=crawl_run_id,
                    url=url,
                    fr=fr,
                    render_mode=used_render,
                    extractor=extractor,
                    extracted_title=title,
                    extracted_markdown_norm=md_norm,
                    extracted_word_count=wc,
                )
                stored += 1
                if rec.get("prev_content_hash") is None:
                    new_pages += 1
                elif rec.get("prev_content_hash") != rec.get("content_hash"):
                    updated_pages += 1
                else:
                    unchanged_pages += 1
                with conn:
                    conn.execute(
                        """
UPDATE inventory_entries
SET status = 'fetched',
    last_fetched_at = ?,
    last_http_status = ?,
    last_content_hash = ?,
    last_final_url = ?,
    last_page_canonical_url = ?,
    error_json = NULL
WHERE id = ?;
""",
                        (
                            rec["crawled_at"],
                            int(fr.http_status),
                            rec["content_hash"],
                            fr.final_url,
                            rec["canonical_url"],
                            ent_id,
                        ),
                    )

        def _record_error_cex(ent_id: int, url: str, e: CexApiDocsError) -> None:
            errors.append({"url": url, "error": e.to_json()})
            with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
                with conn:
                    conn.execute(
                        """
UPDATE inventory_entries
SET status = 'error', last_fetched_at = ?, last_http_status = ?, last_final_url = ?, error_json = ?
WHERE id = ?;
""",
                        (
                            now_iso_utc(),
                            None,
                            None,
                            json.dumps(e.to_json(), sort_keys=True),
                            ent_id,
                        ),
                    )

        def _record_error_generic(ent_id: int, url: str, e: Exception) -> None:
            err = {"code": "ENET", "message": "Unexpected error fetching inventory URL.", "details": {"error": f"{type(e).__name__}: {e}"}}
            errors.append({"url": url, "error": err})
            with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
                with conn:
                    conn.execute(
                        """
UPDATE inventory_entries
SET status = 'error', last_fetched_at = ?, error_json = ?
WHERE id = ?;
""",
                        (now_iso_utc(), json.dumps(err, sort_keys=True), ent_id),
                    )

        def _record_skip(ent_id: int) -> None:
            nonlocal skipped
            skipped += 1
            with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
                with conn:
                    conn.execute(
                        """
UPDATE inventory_entries
SET status = 'skipped', last_fetched_at = ?, error_json = ?
WHERE id = ?;
""",
                        (now_iso_utc(), json.dumps({"code": "EROBOTS", "message": "Disallowed by robots.txt"}, sort_keys=True), ent_id),
                    )

        # Phase B: per-entry — lock only around DB writes.
        if cfg.concurrency <= 1:
            # Sequential path (original behavior).
            for ent in entries:
                url = ent["canonical_url"]
                ent_id = int(ent["id"])

                if not robots_can_fetch(url):
                    _record_skip(ent_id)
                    continue

                try:
                    fr: FetchResult | None = None
                    used_render = "http"
                    title = None
                    md_norm = ""
                    wc = 0

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
                        used_render = "http"
                        _html, title, md_norm, wc = extract_page_markdown(fr=fr)

                    if cfg.render_mode in ("playwright", "auto"):
                        do_pw = cfg.render_mode == "playwright"
                        if fr is not None and cfg.render_mode == "auto":
                            do_pw = _needs_playwright(fr, wc)
                        if do_pw:
                            if pw is None:
                                pw = PlaywrightFetcher(allowed_domains=allow_hosts).open()
                            fr_pw = pw.fetch(url=url, timeout_s=cfg.timeout_s, max_bytes=cfg.max_bytes, retries=cfg.retries)
                            _html_pw, title_pw, md_pw, wc_pw = extract_page_markdown(fr=fr_pw)
                            if fr is None or _needs_playwright(fr, wc) or wc_pw > wc:
                                fr = fr_pw
                                used_render = "playwright"
                                title, md_norm, wc = title_pw, md_pw, wc_pw

                    if fr is None:  # pragma: no cover
                        raise CexApiDocsError(code="ENET", message="No fetch result produced.", details={"url": url})

                    _store_result(ent_id, url, fr, used_render, title, md_norm, wc)

                except CexApiDocsError as e:
                    _record_error_cex(ent_id, url, e)
                except Exception as e:  # pragma: no cover
                    _record_error_generic(ent_id, url, e)
                finally:
                    time.sleep(cfg.delay_s)
        else:
            # Concurrent path: thread pool for HTTP fetches, serial DB writes.
            rate_limiter = _DomainRateLimiter(cfg.delay_s)
            pw_queue: list[dict[str, Any]] = []  # entries needing Playwright fallback

            # Pre-filter robots (sequential — uses cached HTTP, fast).
            fetchable: list[dict[str, Any]] = []
            for ent in entries:
                if not robots_can_fetch(ent["canonical_url"]):
                    _record_skip(int(ent["id"]))
                else:
                    fetchable.append(ent)

            def _http_fetch_worker(url: str) -> tuple[FetchResult, str | None, str, int]:
                """Worker: rate-limited HTTP fetch + markdown extraction."""
                rate_limiter.wait(_host(url))
                # Each thread gets its own session for thread safety.
                thread_session = requests.Session()
                try:
                    fr = fetch(
                        thread_session,
                        url=url,
                        timeout_s=cfg.timeout_s,
                        max_bytes=cfg.max_bytes,
                        max_redirects=cfg.max_redirects,
                        retries=cfg.retries,
                        allowed_domains=allow_hosts,
                    )
                    _html, title, md_norm, wc = extract_page_markdown(fr=fr)
                    return (fr, title, md_norm, wc)
                finally:
                    thread_session.close()

            if cfg.render_mode in ("http", "auto"):
                with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
                    future_to_ent = {
                        pool.submit(_http_fetch_worker, ent["canonical_url"]): ent
                        for ent in fetchable
                    }
                    for future in as_completed(future_to_ent):
                        ent = future_to_ent[future]
                        url = ent["canonical_url"]
                        ent_id = int(ent["id"])
                        try:
                            fr, title, md_norm, wc = future.result()
                            # Check if Playwright fallback needed (auto mode).
                            if cfg.render_mode == "auto" and _needs_playwright(fr, wc):
                                pw_queue.append({"ent": ent, "http_fr": fr, "http_title": title, "http_md": md_norm, "http_wc": wc})
                                continue
                            _store_result(ent_id, url, fr, "http", title, md_norm, wc)
                        except CexApiDocsError as e:
                            _record_error_cex(ent_id, url, e)
                        except Exception as e:  # pragma: no cover
                            _record_error_generic(ent_id, url, e)

            elif cfg.render_mode == "playwright":
                # All entries go to Playwright queue.
                pw_queue = [{"ent": ent, "http_fr": None, "http_title": None, "http_md": "", "http_wc": 0} for ent in fetchable]

            # Playwright fallback: serial (not thread-safe).
            if pw_queue:
                if pw is None:
                    pw = PlaywrightFetcher(allowed_domains=allow_hosts).open()
                for item in pw_queue:
                    ent = item["ent"]
                    url = ent["canonical_url"]
                    ent_id = int(ent["id"])
                    try:
                        fr_pw = pw.fetch(url=url, timeout_s=cfg.timeout_s, max_bytes=cfg.max_bytes, retries=cfg.retries)
                        _html_pw, title_pw, md_pw, wc_pw = extract_page_markdown(fr=fr_pw)

                        http_fr = item.get("http_fr")
                        http_wc = item.get("http_wc", 0)
                        if http_fr is None or _needs_playwright(http_fr, http_wc) or wc_pw > http_wc:
                            _store_result(ent_id, url, fr_pw, "playwright", title_pw, md_pw, wc_pw)
                        else:
                            _store_result(ent_id, url, http_fr, "http", item.get("http_title"), item.get("http_md", ""), http_wc)
                    except CexApiDocsError as e:
                        _record_error_cex(ent_id, url, e)
                    except Exception as e:  # pragma: no cover
                        _record_error_generic(ent_id, url, e)
                    finally:
                        time.sleep(cfg.delay_s)

        # Phase C: brief lock — finalize crawl run.
        ended_at = now_iso_utc()
        with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
            conn.execute("UPDATE crawl_runs SET ended_at = ? WHERE id = ?;", (ended_at, crawl_run_id))
            conn.commit()

        # Export a small robots summary.
        robots_decisions = {}
        for host, (_fn, decision) in robots_cache.items():
            robots_decisions[host] = asdict(decision)

        return {
            "cmd": "fetch-inventory",
            "schema_version": "v1",
            "docs_dir": str(docs_root),
            "exchange_id": exchange_id,
            "section_id": section_id,
            "inventory_id": int(inventory_id),
            "crawl_run_id": crawl_run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "config": asdict(cfg),
            "robots": robots_decisions,
            "counts": {
                "entries": len(entries),
                "fetched": fetched,
                "stored": stored,
                "skipped": skipped,
                "errors": len(errors),
                "new_pages": new_pages,
                "updated_pages": updated_pages,
                "unchanged_pages": unchanged_pages,
            },
            "errors": errors[:50],
        }
    finally:
        conn.close()
        if pw is not None:
            pw.close()
