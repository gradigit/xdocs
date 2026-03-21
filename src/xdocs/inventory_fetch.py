from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from .db import open_db
from .errors import XDocsError
from .extraction_verify import verify_extraction
from .httpfetch import FetchResult, fetch
from .lock import acquire_write_lock
from .markdown import extractor_info_v1
from .page_store import extract_page_markdown, store_page
from .playwrightfetch import PlaywrightFetcher
from .robots import fetch_robots_policy
from .store import ensure_store_schema, require_store_db
from .timeutil import now_iso_utc
from .urlutil import url_host as _host

log = logging.getLogger(__name__)


def _get_render_backend(allowed_domains: set[str]):
    """Fallback chain: agent-browser → Node.js playwright → Python playwright."""
    # 1. agent-browser CLI (primary — already installed, bundled browser).
    if shutil.which("agent-browser"):
        try:
            from .agentbrowserfetch import AgentBrowserFetcher
            log.info("render backend: agent-browser")
            return AgentBrowserFetcher(allowed_domains=allowed_domains)
        except Exception:
            pass

    # 2. Node.js playwright (secondary — lower per-page overhead, exposes HTTP status).
    try:
        from .nodepwfetch import NodePlaywrightFetcher, _find_node_pw_module
        _find_node_pw_module()  # Validate Node.js playwright is actually available.
        backend = NodePlaywrightFetcher(allowed_domains=allowed_domains)
        log.info("render backend: node-playwright")
        return backend
    except (ImportError, XDocsError):
        pass

    # 3. Python playwright (tertiary — raises ENOPLAYWRIGHT if unavailable).
    log.info("render backend: python-playwright")
    return PlaywrightFetcher(allowed_domains=allowed_domains)


DEFAULT_TIMEOUT_S = 20.0
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_DELAY_S = 0.25
DEFAULT_RETRIES = 2
DEFAULT_MAX_DOMAIN_DELAY_S = 30.0


def _parse_retry_after_seconds(value: str | None, *, now_epoch_s: float | None = None) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        return max(0.0, float(int(raw)))
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = float(now_epoch_s) if now_epoch_s is not None else datetime.now(timezone.utc).timestamp()
        delta = dt.timestamp() - now
        return max(0.0, float(delta))
    except Exception:
        return None


def _check_truncation(fr: FetchResult, *, max_bytes: int) -> dict[str, str] | None:
    """Detect possible response truncation."""
    body_len = len(fr.body)
    if body_len >= max_bytes * 0.95:
        return {"code": "WTRUNCATED", "message": f"Body size {body_len} near max_bytes {max_bytes}"}
    cl = fr.headers.get("content-length") if fr.headers else None
    if cl and cl.isdigit() and int(cl) > body_len:
        return {"code": "WTRUNCATED", "message": f"Content-Length {cl} > actual {body_len}"}
    return None


class _DomainRateLimiter:
    """Thread-safe per-domain rate limiter."""

    def __init__(self, delay_s: float, *, adaptive: bool, max_domain_delay_s: float) -> None:
        self._base_delay_s = max(0.0, float(delay_s))
        self._adaptive = bool(adaptive)
        self._max_domain_delay_s = max(self._base_delay_s, float(max_domain_delay_s))
        self._locks: dict[str, threading.RLock] = {}
        self._last_fetch: dict[str, float] = {}
        self._next_allowed_at: dict[str, float] = {}
        self._domain_delay_s: dict[str, float] = {}
        self._retry_after_applied: dict[str, int] = {}
        self._throttle_events: dict[str, int] = {}
        self._last_status: dict[str, int] = {}
        self._global_lock = threading.Lock()

    def _domain_lock(self, domain: str) -> threading.RLock:
        with self._global_lock:
            if domain not in self._locks:
                self._locks[domain] = threading.RLock()
            return self._locks[domain]

    def _wait_locked(self, domain: str) -> None:
        now = time.monotonic()
        last = self._last_fetch.get(domain, 0.0)
        spacing_delay = self._domain_delay_s.get(domain, self._base_delay_s)
        spacing_target = last + spacing_delay
        next_allowed = self._next_allowed_at.get(domain, 0.0)
        target = max(spacing_target, next_allowed)
        if now < target:
            time.sleep(target - now)
        self._last_fetch[domain] = time.monotonic()

    def wait(self, domain: str) -> None:
        lock = self._domain_lock(domain)
        with lock:
            self._wait_locked(domain)

    @contextmanager
    def fetch_turn(self, domain: str):
        lock = self._domain_lock(domain)
        with lock:
            self._wait_locked(domain)
            yield

    def note_fetch_result(self, domain: str, fr: FetchResult) -> None:
        with self._domain_lock(domain):
            self._note_fetch_result_inner(domain, fr)

    def note_fetch_result_locked(self, domain: str, fr: FetchResult) -> None:
        # For callers that already hold fetch_turn(domain).
        self._note_fetch_result_inner(domain, fr)

    def _note_fetch_result_inner(self, domain: str, fr: FetchResult) -> None:
        status = int(fr.http_status or 0)
        retry_after_raw = fr.headers.get("retry-after")
        retry_after_s = _parse_retry_after_seconds(retry_after_raw)
        self._last_status[domain] = status
        if retry_after_s is not None:
            now_mono = time.monotonic()
            current = self._next_allowed_at.get(domain, 0.0)
            self._next_allowed_at[domain] = max(current, now_mono + retry_after_s)
            self._retry_after_applied[domain] = int(self._retry_after_applied.get(domain, 0)) + 1

        if not self._adaptive:
            return

        current_delay = self._domain_delay_s.get(domain, self._base_delay_s)
        if status == 429:
            self._throttle_events[domain] = int(self._throttle_events.get(domain, 0)) + 1
            next_delay = max(self._base_delay_s, current_delay * 2.0)
            if retry_after_s is not None:
                next_delay = max(next_delay, retry_after_s)
            self._domain_delay_s[domain] = min(self._max_domain_delay_s, next_delay)
            log.warning(
                "rate-limited by %s (429) — backoff %.1fs→%.1fs (event #%d)",
                domain, current_delay, self._domain_delay_s[domain],
                self._throttle_events[domain],
            )
        elif status >= 500:
            self._throttle_events[domain] = int(self._throttle_events.get(domain, 0)) + 1
            next_delay = max(self._base_delay_s, current_delay * 1.5)
            self._domain_delay_s[domain] = min(self._max_domain_delay_s, next_delay)
            log.warning(
                "server error from %s (%d) — backoff %.1fs→%.1fs",
                domain, status, current_delay, self._domain_delay_s[domain],
            )
        else:
            if current_delay <= self._base_delay_s:
                self._domain_delay_s[domain] = self._base_delay_s
            else:
                self._domain_delay_s[domain] = max(self._base_delay_s, current_delay * 0.9)

    def retry_after_applied_total(self) -> int:
        with self._global_lock:
            return sum(int(v) for v in self._retry_after_applied.values())

    def domain_snapshot(self) -> dict[str, dict[str, Any]]:
        with self._global_lock:
            domains = sorted(
                set(self._locks.keys())
                | set(self._domain_delay_s.keys())
                | set(self._next_allowed_at.keys())
                | set(self._retry_after_applied.keys())
                | set(self._throttle_events.keys())
                | set(self._last_status.keys())
            )
        now = time.monotonic()
        out: dict[str, dict[str, Any]] = {}
        for domain in domains:
            lock = self._domain_lock(domain)
            with lock:
                out[domain] = {
                    "current_delay_s": round(float(self._domain_delay_s.get(domain, self._base_delay_s)), 6),
                    "next_allowed_in_s": round(max(0.0, float(self._next_allowed_at.get(domain, 0.0) - now)), 6),
                    "retry_after_applied": int(self._retry_after_applied.get(domain, 0)),
                    "throttle_events": int(self._throttle_events.get(domain, 0)),
                    "last_status": int(self._last_status.get(domain, 0)),
                }
        return out


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
    force_refetch: bool
    conditional: bool
    adaptive_delay: bool
    max_domain_delay_s: float
    scope_dedupe: bool
    scope_group: str | None
    scope_priority: int


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
    force_refetch: bool = False,
    conditional: bool = True,
    adaptive_delay: bool = True,
    max_domain_delay_s: float = DEFAULT_MAX_DOMAIN_DELAY_S,
    scope_dedupe: bool = True,
    scope_group: str | None = None,
    scope_priority: int = 100,
) -> dict[str, Any]:
    if render_mode not in ("http", "playwright", "auto"):
        raise XDocsError(code="EBADARG", message="Invalid render_mode.", details={"render_mode": render_mode})
    if resume and force_refetch:
        raise XDocsError(code="EBADARG", message="Cannot use both --resume and --force-refetch.", details={})

    ensure_store_schema(docs_dir=docs_dir, lock_timeout_s=lock_timeout_s)
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
        force_refetch=bool(force_refetch),
        conditional=bool(conditional),
        adaptive_delay=bool(adaptive_delay),
        max_domain_delay_s=max(float(max_domain_delay_s), 0.0),
        scope_dedupe=bool(scope_dedupe),
        scope_group=str(scope_group).strip() if scope_group else None,
        scope_priority=int(scope_priority),
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
        if cfg.force_refetch:
            pass  # No status filter — fetch all entries including already-fetched ones.
        elif cfg.resume:
            statuses = ["pending", "error"]
            if cfg.ignore_robots:
                statuses.append("skipped")
            elif cfg.scope_dedupe:
                # Re-evaluate scope-dedup skips on resume in case priorities/grouping changed.
                statuses.append("skipped")
            placeholders = ", ".join("?" for _ in statuses)
            where += f" AND status IN ({placeholders})"
            params.extend(statuses)

        rows_query = f"""
SELECT id, canonical_url, status
     , last_etag, last_last_modified
FROM inventory_entries
{where}
ORDER BY canonical_url ASC;
"""
        try:
            rows = conn.execute(rows_query, tuple(params)).fetchall()
        except sqlite3.OperationalError:
            # Backward compatibility for pre-conditional stores.
            rows = conn.execute(
                f"""
SELECT id, canonical_url, status
FROM inventory_entries
{where}
ORDER BY canonical_url ASC;
""",
                tuple(params),
            ).fetchall()
        entries = [
            {
                "id": int(r["id"]),
                "canonical_url": str(r["canonical_url"]),
                "status": str(r["status"]),
                "last_etag": str(r["last_etag"]) if "last_etag" in r.keys() and r["last_etag"] is not None else None,
                "last_last_modified": (
                    str(r["last_last_modified"])
                    if "last_last_modified" in r.keys() and r["last_last_modified"] is not None
                    else None
                ),
            }
            for r in rows
        ]
        if cfg.limit is not None:
            entries = entries[: int(cfg.limit)]

        session = requests.Session()
        robots_cache: dict[str, Any] = {}
        robots_lock = threading.Lock()

        def robots_can_fetch(u: str) -> bool:
            if cfg.ignore_robots:
                return True
            h = _host(u)
            with robots_lock:
                if h not in robots_cache:
                    robots_cache[h] = fetch_robots_policy(session, url=u, timeout_s=cfg.timeout_s)
                can_fetch_fn, _decision = robots_cache[h]
            return bool(can_fetch_fn(u))

        fetched = 0
        stored = 0
        skipped = 0
        dedupe_skipped = 0
        revalidated_unchanged = 0
        new_pages = 0
        updated_pages = 0
        unchanged_pages = 0
        errors: list[dict[str, Any]] = []
        rate_limiter = _DomainRateLimiter(
            cfg.delay_s,
            adaptive=cfg.adaptive_delay,
            max_domain_delay_s=cfg.max_domain_delay_s,
        )

        truncation_warnings = 0
        extraction_quality_warnings = 0

        owned_map: dict[str, dict[str, Any]] = {}
        scope_dedupe_active = bool(cfg.scope_dedupe and cfg.scope_group)
        if scope_dedupe_active:
            try:
                rows_owned = conn.execute(
                    """
SELECT canonical_url, owner_exchange_id, owner_section_id, owner_inventory_id, owner_priority
FROM inventory_scope_ownership
WHERE scope_group = ?;
""",
                    (cfg.scope_group,),
                ).fetchall()
                for r in rows_owned:
                    owned_map[str(r["canonical_url"])] = {
                        "owner_exchange_id": str(r["owner_exchange_id"]),
                        "owner_section_id": str(r["owner_section_id"]),
                        "owner_inventory_id": int(r["owner_inventory_id"]),
                        "owner_priority": int(r["owner_priority"]),
                    }
            except sqlite3.OperationalError:
                # Backward compatibility for pre-scope-dedupe stores until schema is migrated.
                scope_dedupe_active = False

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
                    try:
                        conn.execute(
                            """
UPDATE inventory_entries
SET status = 'fetched',
    last_fetched_at = ?,
    last_http_status = ?,
    last_content_hash = ?,
    last_final_url = ?,
    last_page_canonical_url = ?,
    last_etag = ?,
    last_last_modified = ?,
    last_cache_control = ?,
    error_json = NULL
WHERE id = ?;
""",
                            (
                                rec["crawled_at"],
                                int(fr.http_status),
                                rec["content_hash"],
                                fr.final_url,
                                rec["canonical_url"],
                                fr.headers.get("etag"),
                                fr.headers.get("last-modified"),
                                fr.headers.get("cache-control"),
                                ent_id,
                            ),
                        )
                    except sqlite3.OperationalError:
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
            _claim_scope_ownership(url)

        def _record_error_cex(ent_id: int, url: str, e: XDocsError) -> None:
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

        def _record_revalidated_unchanged(ent_id: int, fr: FetchResult, *, canonical_url: str) -> None:
            nonlocal fetched, revalidated_unchanged
            fetched += 1
            revalidated_unchanged += 1
            with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
                with conn:
                    try:
                        conn.execute(
                            """
UPDATE inventory_entries
SET status = 'fetched',
    last_fetched_at = ?,
    last_http_status = ?,
    last_final_url = ?,
    last_etag = ?,
    last_last_modified = ?,
    last_cache_control = ?,
    error_json = NULL
WHERE id = ?;
""",
                            (
                                now_iso_utc(),
                                int(fr.http_status),
                                fr.final_url,
                                fr.headers.get("etag"),
                                fr.headers.get("last-modified"),
                                fr.headers.get("cache-control"),
                                ent_id,
                            ),
                        )
                    except sqlite3.OperationalError:
                        conn.execute(
                            """
UPDATE inventory_entries
SET status = 'fetched',
    last_fetched_at = ?,
    last_http_status = ?,
    last_final_url = ?,
    error_json = NULL
WHERE id = ?;
""",
                            (
                                now_iso_utc(),
                                int(fr.http_status),
                                fr.final_url,
                                ent_id,
                            ),
                        )
            _claim_scope_ownership(canonical_url)

        def _claim_scope_ownership(url: str) -> None:
            if not scope_dedupe_active:
                return
            try:
                with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
                    with conn:
                        conn.execute(
                            """
INSERT INTO inventory_scope_ownership (
  scope_group, canonical_url, owner_exchange_id, owner_section_id,
  owner_inventory_id, owner_priority, owned_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(scope_group, canonical_url) DO UPDATE SET
  owner_exchange_id = excluded.owner_exchange_id,
  owner_section_id = excluded.owner_section_id,
  owner_inventory_id = excluded.owner_inventory_id,
  owner_priority = excluded.owner_priority,
  owned_at = excluded.owned_at
WHERE
  excluded.owner_priority < inventory_scope_ownership.owner_priority
  OR (
    excluded.owner_priority = inventory_scope_ownership.owner_priority
    AND inventory_scope_ownership.owner_exchange_id = excluded.owner_exchange_id
    AND inventory_scope_ownership.owner_section_id = excluded.owner_section_id
  );
""",
                            (
                                cfg.scope_group,
                                url,
                                cfg.exchange_id,
                                cfg.section_id,
                                int(inventory_id),
                                int(cfg.scope_priority),
                                now_iso_utc(),
                            ),
                        )
                        row = conn.execute(
                            """
SELECT owner_exchange_id, owner_section_id, owner_inventory_id, owner_priority
FROM inventory_scope_ownership
WHERE scope_group = ? AND canonical_url = ?
LIMIT 1;
""",
                            (cfg.scope_group, url),
                        ).fetchone()
                if row is not None:
                    owned_map[url] = {
                        "owner_exchange_id": str(row["owner_exchange_id"]),
                        "owner_section_id": str(row["owner_section_id"]),
                        "owner_inventory_id": int(row["owner_inventory_id"]),
                        "owner_priority": int(row["owner_priority"]),
                    }
            except sqlite3.OperationalError:
                pass

        def _conditional_headers_for_entry(ent: dict[str, Any]) -> dict[str, str] | None:
            if cfg.force_refetch or not cfg.conditional:
                return None
            out: dict[str, str] = {}
            etag = ent.get("last_etag")
            if etag:
                out["If-None-Match"] = str(etag)
            last_mod = ent.get("last_last_modified")
            if last_mod:
                out["If-Modified-Since"] = str(last_mod)
            return out or None

        def _scope_skip_owner(url: str) -> dict[str, Any] | None:
            if not scope_dedupe_active:
                return None
            owner = owned_map.get(url)
            if owner is None:
                return None
            same_owner = (
                str(owner.get("owner_exchange_id")) == cfg.exchange_id
                and str(owner.get("owner_section_id")) == cfg.section_id
            )
            if same_owner:
                return None
            owner_priority = int(owner.get("owner_priority") or 100)
            if owner_priority <= int(cfg.scope_priority):
                return owner
            return None

        def _record_scope_skip(ent_id: int, *, owner: dict[str, Any]) -> None:
            nonlocal skipped, dedupe_skipped
            skipped += 1
            dedupe_skipped += 1
            err = {
                "code": "ESCOPEDEDUP",
                "message": "Skipped due to scope ownership by higher-priority section.",
                "details": {
                    "scope_group": cfg.scope_group,
                    "owner_exchange_id": owner.get("owner_exchange_id"),
                    "owner_section_id": owner.get("owner_section_id"),
                    "owner_inventory_id": owner.get("owner_inventory_id"),
                    "owner_priority": owner.get("owner_priority"),
                    "current_exchange_id": cfg.exchange_id,
                    "current_section_id": cfg.section_id,
                    "current_priority": cfg.scope_priority,
                },
            }
            with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
                with conn:
                    conn.execute(
                        """
UPDATE inventory_entries
SET status = 'skipped', last_fetched_at = ?, error_json = ?
WHERE id = ?;
""",
                        (now_iso_utc(), json.dumps(err, sort_keys=True), ent_id),
                    )

        # Phase B: per-entry — lock only around DB writes.
        if cfg.concurrency <= 1:
            # Sequential path (original behavior).
            for ent in entries:
                url = ent["canonical_url"]
                ent_id = int(ent["id"])
                domain = _host(url)

                owner = _scope_skip_owner(url)
                if owner is not None:
                    _record_scope_skip(ent_id, owner=owner)
                    continue

                if not robots_can_fetch(url):
                    _record_skip(ent_id)
                    continue

                try:
                    fr: FetchResult | None = None
                    used_render = "http"
                    title = None
                    md_norm = ""
                    wc = 0
                    cond_headers = _conditional_headers_for_entry(ent)

                    if cfg.render_mode in ("http", "auto"):
                        with rate_limiter.fetch_turn(domain):
                            fr = fetch(
                                session,
                                url=url,
                                timeout_s=cfg.timeout_s,
                                max_bytes=cfg.max_bytes,
                                max_redirects=cfg.max_redirects,
                                retries=cfg.retries,
                                allowed_domains=allow_hosts,
                                conditional_headers=cond_headers,
                            )
                            rate_limiter.note_fetch_result_locked(domain, fr)
                        if int(fr.http_status) == 304:
                            _record_revalidated_unchanged(ent_id, fr, canonical_url=url)
                            continue
                        trunc = _check_truncation(fr, max_bytes=cfg.max_bytes)
                        if trunc:
                            truncation_warnings += 1
                            log.warning("Truncation detected for %s: %s", url, trunc["message"])
                        used_render = "http"
                        _html, title, md_norm, wc = extract_page_markdown(fr=fr)
                        eq = verify_extraction(_html, md_norm)
                        if eq.warnings:
                            extraction_quality_warnings += 1
                            log.warning("Extraction quality issues for %s: %s", url, "; ".join(eq.warnings))

                    if cfg.render_mode in ("playwright", "auto"):
                        do_pw = cfg.render_mode == "playwright"
                        if fr is not None and cfg.render_mode == "auto":
                            do_pw = _needs_playwright(fr, wc)
                        if do_pw:
                            if pw is None:
                                pw = _get_render_backend(allow_hosts).open()
                            with rate_limiter.fetch_turn(domain):
                                fr_pw = pw.fetch(
                                    url=url,
                                    timeout_s=cfg.timeout_s,
                                    max_bytes=cfg.max_bytes,
                                    retries=cfg.retries,
                                )
                                rate_limiter.note_fetch_result_locked(domain, fr_pw)
                            _html_pw, title_pw, md_pw, wc_pw = extract_page_markdown(fr=fr_pw)
                            # Compare structural quality alongside word count
                            prefer_pw = fr is None or _needs_playwright(fr, wc)
                            if not prefer_pw and wc_pw > wc:
                                prefer_pw = True
                            if not prefer_pw and fr is not None:
                                eq_http = verify_extraction(_html, md_norm)
                                eq_pw = verify_extraction(_html_pw, md_pw)
                                if eq_pw.quality_score > eq_http.quality_score:
                                    prefer_pw = True
                            if prefer_pw:
                                fr = fr_pw
                                used_render = "playwright"
                                title, md_norm, wc = title_pw, md_pw, wc_pw
                                _html = _html_pw

                    if fr is None:  # pragma: no cover
                        raise XDocsError(code="ENET", message="No fetch result produced.", details={"url": url})

                    _store_result(ent_id, url, fr, used_render, title, md_norm, wc)

                except XDocsError as e:
                    _record_error_cex(ent_id, url, e)
                except Exception as e:  # pragma: no cover
                    _record_error_generic(ent_id, url, e)
        else:
            # Concurrent path: thread pool for HTTP fetches, serial DB writes.
            pw_queue: list[dict[str, Any]] = []  # entries needing Playwright fallback

            # Pre-filter robots (sequential — uses cached HTTP, fast).
            fetchable: list[dict[str, Any]] = []
            for ent in entries:
                owner = _scope_skip_owner(ent["canonical_url"])
                if owner is not None:
                    _record_scope_skip(int(ent["id"]), owner=owner)
                elif not robots_can_fetch(ent["canonical_url"]):
                    _record_skip(int(ent["id"]))
                else:
                    fetchable.append(ent)

            def _http_fetch_worker(ent: dict[str, Any]) -> tuple[FetchResult, str | None, str, int]:
                """Worker: rate-limited HTTP fetch + markdown extraction."""
                nonlocal truncation_warnings, extraction_quality_warnings
                url = str(ent["canonical_url"])
                domain = _host(url)
                # Each thread gets its own session for thread safety.
                thread_session = requests.Session()
                try:
                    with rate_limiter.fetch_turn(domain):
                        fr = fetch(
                            thread_session,
                            url=url,
                            timeout_s=cfg.timeout_s,
                            max_bytes=cfg.max_bytes,
                            max_redirects=cfg.max_redirects,
                            retries=cfg.retries,
                            allowed_domains=allow_hosts,
                            conditional_headers=_conditional_headers_for_entry(ent),
                        )
                        rate_limiter.note_fetch_result_locked(domain, fr)
                    if int(fr.http_status) == 304:
                        return (fr, None, "", 0)
                    trunc = _check_truncation(fr, max_bytes=cfg.max_bytes)
                    if trunc:
                        truncation_warnings += 1
                        log.warning("Truncation detected for %s: %s", url, trunc["message"])
                    _html, title, md_norm, wc = extract_page_markdown(fr=fr)
                    eq = verify_extraction(_html, md_norm)
                    if eq.warnings:
                        extraction_quality_warnings += 1
                        log.warning("Extraction quality issues for %s: %s", url, "; ".join(eq.warnings))
                    return (fr, title, md_norm, wc)
                finally:
                    thread_session.close()

            if cfg.render_mode in ("http", "auto"):
                with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
                    future_to_ent = {
                        pool.submit(_http_fetch_worker, ent): ent
                        for ent in fetchable
                    }
                    for future in as_completed(future_to_ent):
                        ent = future_to_ent[future]
                        url = ent["canonical_url"]
                        ent_id = int(ent["id"])
                        try:
                            fr, title, md_norm, wc = future.result()
                            if int(fr.http_status) == 304:
                                _record_revalidated_unchanged(ent_id, fr, canonical_url=url)
                                continue
                            # Check if Playwright fallback needed (auto mode).
                            if cfg.render_mode == "auto" and _needs_playwright(fr, wc):
                                pw_queue.append({"ent": ent, "http_fr": fr, "http_title": title, "http_md": md_norm, "http_wc": wc})
                                continue
                            _store_result(ent_id, url, fr, "http", title, md_norm, wc)
                        except XDocsError as e:
                            _record_error_cex(ent_id, url, e)
                        except Exception as e:  # pragma: no cover
                            _record_error_generic(ent_id, url, e)

            elif cfg.render_mode == "playwright":
                # All entries go to Playwright queue.
                pw_queue = [{"ent": ent, "http_fr": None, "http_title": None, "http_md": "", "http_wc": 0} for ent in fetchable]

            # Playwright fallback: serial (not thread-safe).
            if pw_queue:
                if pw is None:
                    pw = _get_render_backend(allow_hosts).open()
                for item in pw_queue:
                    ent = item["ent"]
                    url = ent["canonical_url"]
                    ent_id = int(ent["id"])
                    domain = _host(url)
                    try:
                        with rate_limiter.fetch_turn(domain):
                            fr_pw = pw.fetch(url=url, timeout_s=cfg.timeout_s, max_bytes=cfg.max_bytes, retries=cfg.retries)
                            rate_limiter.note_fetch_result_locked(domain, fr_pw)
                        _html_pw, title_pw, md_pw, wc_pw = extract_page_markdown(fr=fr_pw)

                        http_fr = item.get("http_fr")
                        http_wc = item.get("http_wc", 0)
                        http_md = item.get("http_md", "")
                        prefer_pw = http_fr is None or _needs_playwright(http_fr, http_wc)
                        if not prefer_pw and wc_pw > http_wc:
                            prefer_pw = True
                        if not prefer_pw and http_fr is not None:
                            # Structural comparison: use Playwright-rendered HTML vs HTTP HTML
                            eq_pw = verify_extraction(_html_pw, md_pw)
                            http_html_decoded = http_fr.body.decode("utf-8", errors="replace")
                            eq_http = verify_extraction(http_html_decoded, http_md)
                            if eq_pw.quality_score > eq_http.quality_score:
                                prefer_pw = True
                        if prefer_pw:
                            _store_result(ent_id, url, fr_pw, "playwright", title_pw, md_pw, wc_pw)
                        else:
                            _store_result(ent_id, url, http_fr, "http", item.get("http_title"), http_md, http_wc)
                    except XDocsError as e:
                        _record_error_cex(ent_id, url, e)
                    except Exception as e:  # pragma: no cover
                        _record_error_generic(ent_id, url, e)

        # Phase C: brief lock — finalize crawl run.
        ended_at = now_iso_utc()
        with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
            conn.execute("UPDATE crawl_runs SET ended_at = ? WHERE id = ?;", (ended_at, crawl_run_id))
            conn.commit()

        # Export a small robots summary.
        robots_decisions = {}
        for host, (_fn, decision) in robots_cache.items():
            robots_decisions[host] = asdict(decision)

        # Completeness gate
        entries_total = len(entries)
        entries_fetched = fetched
        entries_error = len(errors)
        completion_pct = (entries_fetched / entries_total * 100) if entries_total > 0 else 100.0
        if completion_pct < 90.0:
            log.warning(
                "Low fetch completion for %s/%s: %.1f%% (%d/%d fetched, %d errors)",
                exchange_id, section_id, completion_pct, entries_fetched, entries_total, entries_error,
            )

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
            "domain_delay_snapshot": rate_limiter.domain_snapshot(),
            "counts": {
                "entries": len(entries),
                "fetched": fetched,
                "stored": stored,
                "skipped": skipped,
                "dedupe_skipped": dedupe_skipped,
                "revalidated_unchanged": revalidated_unchanged,
                "retry_after_applied": rate_limiter.retry_after_applied_total(),
                "errors": len(errors),
                "new_pages": new_pages,
                "updated_pages": updated_pages,
                "unchanged_pages": unchanged_pages,
            },
            "completeness": {
                "entries_total": entries_total,
                "entries_fetched": entries_fetched,
                "entries_error": entries_error,
                "completion_pct": round(completion_pct, 1),
                "truncation_warnings": truncation_warnings,
                "extraction_quality_warnings": extraction_quality_warnings,
            },
            "errors": errors[:50],
        }
    finally:
        conn.close()
        if pw is not None:
            pw.close()
