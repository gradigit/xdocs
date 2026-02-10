from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .errors import CexApiDocsError
from .fs import atomic_write_bytes, atomic_write_text
from .hashing import sha256_hex_bytes, sha256_hex_text
from .httpfetch import FetchResult
from .markdown import ExtractorInfo, html_to_markdown, normalize_markdown
from .timeutil import now_iso_utc
from .urlcanon import canonicalize_url
from .urlutil import url_host as _host


def _parse_charset(content_type: str) -> str | None:
    m = re.search(r"charset=([\w\-]+)", content_type or "", flags=re.IGNORECASE)
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


def extract_page_markdown(*, fr: FetchResult) -> tuple[str, str | None, str, int]:
    html = _decode_body(fr.body, fr.content_type)
    title = _extract_title(html)
    md_norm = ""
    if "text/html" in (fr.content_type or "").lower() or (fr.content_type or "").lower().startswith("text/"):
        md_raw = html_to_markdown(html, base_url=fr.final_url)
        md_norm = normalize_markdown(md_raw)
    wc = len(md_norm.split())
    return html, title, md_norm, wc


def _write_jsonl(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False))
        f.write("\\n")


def store_page(
    *,
    conn,
    docs_root: Path,
    crawl_run_id: int,
    url: str,
    fr: FetchResult,
    render_mode: str,
    extractor: ExtractorInfo,
    extracted_title: str | None = None,
    extracted_markdown_norm: str | None = None,
    extracted_word_count: int | None = None,
    meta_extra: dict[str, Any] | None = None,
    write_crawl_log: bool = True,
) -> dict[str, Any]:
    """
    Persist a fetched page into the store (files + pages/page_versions + FTS).

    Caller is responsible for holding the write lock and committing/ending crawl_runs.
    """
    if crawl_run_id <= 0:
        raise CexApiDocsError(code="EBADARG", message="crawl_run_id must be > 0")

    final_url = fr.final_url
    canonical_url = canonicalize_url(final_url)
    domain = _host(final_url)
    path_hash = sha256_hex_text(canonical_url)
    crawled_at = now_iso_utc()
    raw_hash = sha256_hex_bytes(fr.body)

    if extracted_markdown_norm is None or extracted_word_count is None:
        _html, title0, md_norm0, wc0 = extract_page_markdown(fr=fr)
        title = extracted_title if extracted_title is not None else title0
        md_norm = md_norm0
        wc = wc0
    else:
        title = extracted_title
        md_norm = extracted_markdown_norm
        wc = int(extracted_word_count)

    content_hash = sha256_hex_text(md_norm)

    raw_path = docs_root / "raw" / domain / f"{path_hash}.bin"
    md_path = docs_root / "pages" / domain / f"{path_hash}.md"
    meta_path = docs_root / "meta" / domain / f"{path_hash}.json"

    # Write files first (atomic).
    atomic_write_bytes(raw_path, fr.body)
    if md_norm:
        atomic_write_text(md_path, md_norm)

    meta: dict[str, Any] = {
        "url": url,
        "final_url": final_url,
        "canonical_url": canonical_url,
        "redirect_chain": list(fr.redirect_chain),
        "crawled_at": crawled_at,
        "http_status": int(fr.http_status),
        "content_type": fr.content_type,
        "raw_hash": raw_hash,
        "content_hash": content_hash,
        "prev_content_hash": None,
        "path_hash": path_hash,
        "render_mode": render_mode,
        "title": title,
        "word_count": wc,
        "headers": fr.headers,
        "extractor": {
            "name": extractor.name,
            "version": extractor.version,
            "config": extractor.config,
            "config_hash": extractor.config_hash,
        },
    }
    if meta_extra:
        # Keep store metadata stable; do not allow overriding core keys.
        extra = {k: v for k, v in meta_extra.items() if k not in meta}
        if extra:
            meta.update(extra)

    prev_content_hash: str | None = None
    page_id: int
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
                    int(fr.http_status),
                    fr.content_type,
                    render_mode,
                    raw_hash,
                    content_hash,
                    prev_content_hash,
                    crawled_at,
                    str(raw_path),
                    str(md_path) if md_norm else None,
                    str(meta_path),
                    wc,
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
            cur = conn.execute(
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
                    int(fr.http_status),
                    fr.content_type,
                    render_mode,
                    raw_hash,
                    content_hash,
                    None,
                    crawled_at,
                    str(raw_path),
                    str(md_path) if md_norm else None,
                    str(meta_path),
                    wc,
                    extractor.name,
                    extractor.version,
                    json.dumps(extractor.config, sort_keys=True),
                    extractor.config_hash,
                    crawl_run_id,
                ),
            )
            page_id = int(cur.lastrowid)

        meta["prev_content_hash"] = prev_content_hash
        atomic_write_text(meta_path, json.dumps(meta, sort_keys=True, ensure_ascii=False, indent=2) + "\\n")

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
                int(fr.http_status),
                fr.content_type,
                raw_hash,
                content_hash,
                str(raw_path),
                str(md_path) if md_norm else None,
                str(meta_path),
            ),
        )

        if md_norm:
            conn.execute("DELETE FROM pages_fts WHERE rowid = ?;", (page_id,))
            conn.execute(
                "INSERT INTO pages_fts (rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);",
                (page_id, canonical_url, title or "", md_norm),
            )

    if write_crawl_log:
        _write_jsonl(
            docs_root / "crawl-log.jsonl",
            {
                "ts": crawled_at,
                "crawl_run_id": crawl_run_id,
                "url": url,
                "final_url": final_url,
                "canonical_url": canonical_url,
                "path_hash": path_hash,
                "http_status": int(fr.http_status),
                "content_hash": content_hash,
            },
        )

    return {
        "page_id": page_id,
        "canonical_url": canonical_url,
        "domain": domain,
        "path_hash": path_hash,
        "content_hash": content_hash,
        "prev_content_hash": prev_content_hash,
        "crawled_at": crawled_at,
        "render_mode": render_mode,
        "paths": {"raw_path": str(raw_path), "markdown_path": str(md_path) if md_norm else None, "meta_path": str(meta_path)},
    }

