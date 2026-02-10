from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from .endpoints import compute_endpoint_id, save_endpoints_bulk
from .errors import CexApiDocsError
from .httpfetch import fetch
from .ingest_page import ingest_page
from .markdown import normalize_markdown


@dataclass(frozen=True, slots=True)
class PostmanImportConfig:
    exchange: str
    section: str
    url: str
    base_url: str | None
    api_version: str | None
    timeout_s: float
    max_bytes: int
    max_redirects: int
    retries: int
    continue_on_error: bool


def _decode_body(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _is_http_url(url: str) -> bool:
    return urlsplit(url).scheme in ("http", "https")


def _find_excerpt(md: str, anchor: str, *, window: int = 550) -> tuple[int, int, str] | None:
    if not anchor:
        return None
    i = md.find(anchor)
    if i < 0:
        return None
    start = i
    end = min(len(md), start + int(window))
    if end <= start:
        return None
    excerpt = md[start:end]
    return start, end, excerpt


def _iter_postman_items(obj: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(items: Any) -> None:
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            if "request" in it and isinstance(it.get("request"), dict):
                out.append(it)
                continue
            # Folder-like: recurse into nested items.
            walk(it.get("item"))

    walk(obj.get("item"))
    return out


def _extract_request_raw_url(req: dict[str, Any]) -> str | None:
    u = req.get("url")
    if isinstance(u, str):
        return u.strip() or None
    if isinstance(u, dict):
        raw = u.get("raw")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def import_postman(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    exchange: str,
    section: str,
    url: str,
    base_url: str | None,
    api_version: str | None,
    timeout_s: float = 20.0,
    max_bytes: int = 50_000_000,
    max_redirects: int = 5,
    retries: int = 1,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    if not _is_http_url(url):
        raise CexApiDocsError(code="EBADARG", message="import-postman requires an http(s) URL.", details={"url": url})
    if not exchange or not section:
        raise CexApiDocsError(code="EBADARG", message="Missing exchange/section.", details={"exchange": exchange, "section": section})

    cfg = PostmanImportConfig(
        exchange=str(exchange),
        section=str(section),
        url=str(url),
        base_url=str(base_url) if base_url else None,
        api_version=str(api_version) if api_version else None,
        timeout_s=float(timeout_s),
        max_bytes=int(max_bytes),
        max_redirects=int(max_redirects),
        retries=int(retries),
        continue_on_error=bool(continue_on_error),
    )

    session = requests.Session()
    fr = fetch(
        session,
        url=url,
        timeout_s=cfg.timeout_s,
        max_bytes=cfg.max_bytes,
        max_redirects=cfg.max_redirects,
        retries=cfg.retries,
        allowed_domains=None,
    )
    if int(fr.http_status) >= 400:
        raise CexApiDocsError(code="EPOSTMANHTTP", message="Failed to fetch Postman collection.", details={"url": url, "http_status": fr.http_status})

    raw_text = _decode_body(fr.body)
    coll = json.loads(raw_text)
    if not isinstance(coll, dict):
        raise CexApiDocsError(code="EBADPOSTMAN", message="Postman collection must parse to an object.", details={"url": url})

    # Canonicalize to a stable JSON string for ingestion/citations.
    md_norm = normalize_markdown(json.dumps(coll, sort_keys=True, ensure_ascii=False, indent=2) + "\n")

    tmp = Path(docs_dir) / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    md_path = tmp / "postman-collection.md"
    md_path.write_text(md_norm + "\n", encoding="utf-8")
    ing = ingest_page(
        docs_dir=docs_dir,
        lock_timeout_s=float(lock_timeout_s),
        url=url,
        markdown_path=md_path,
        tool="import-postman",
        notes=f"exchange={exchange} section={section}",
    )
    stored = ing["stored"]

    items = _iter_postman_items(coll)
    records: list[dict[str, Any]] = []

    for it in items:
        req = it.get("request")
        if not isinstance(req, dict):
            continue
        method_raw = req.get("method")
        if not isinstance(method_raw, str) or not method_raw.strip():
            continue
        method = method_raw.strip().upper()

        raw_url = _extract_request_raw_url(req)
        if raw_url is None:
            continue

        # Determine base_url + path with an optional registry-provided base_url prefix.
        effective_base_url = cfg.base_url
        path = None
        if effective_base_url and raw_url.startswith(effective_base_url):
            path0 = raw_url[len(effective_base_url) :]
            path = path0 if path0.startswith("/") else "/" + path0
        else:
            u = urlsplit(raw_url)
            effective_base_url = f"{u.scheme}://{u.netloc}"
            path = u.path or "/"
            if u.query:
                path += "?" + u.query

        # Best-effort citation: anchor on raw_url in the ingested JSON text.
        ex = _find_excerpt(md_norm, raw_url)

        sources: list[dict[str, Any]] = []
        field_status: dict[str, str] = {
            "http.method": "unknown",
            "http.path": "unknown",
            "http.base_url": "unknown",
            "description": "unknown",
            "request_schema": "unknown",
            "response_schema": "unknown",
            "required_permissions": "unknown",
            "rate_limit": "unknown",
            "error_codes": "unknown",
        }

        if ex is not None:
            start, end, excerpt = ex
            for field_name in ("http.method", "http.path", "http.base_url"):
                sources.append(
                    {
                        "url": url,
                        "crawled_at": stored["crawled_at"],
                        "content_hash": stored["content_hash"],
                        "path_hash": stored["path_hash"],
                        "excerpt": excerpt,
                        "excerpt_start": start,
                        "excerpt_end": end,
                        "field_name": field_name,
                    }
                )
                field_status[field_name] = "documented"

        http_obj = {"method": method, "path": path, "base_url": effective_base_url, "api_version": cfg.api_version}

        record: dict[str, Any] = {
            "exchange": cfg.exchange,
            "section": cfg.section,
            "protocol": "http",
            "http": http_obj,
            "description": it.get("name") if isinstance(it.get("name"), str) else None,
            "request_schema": None,
            "response_schema": None,
            "required_permissions": None,
            "rate_limit": None,
            "error_codes": None,
            "sources": sources,
            "field_status": field_status,
            "extraction": {
                "model": "import-postman",
                "temperature": 0,
                "prompt_hash": "n/a",
                "input_content_hash": stored["content_hash"],
            },
        }
        record["endpoint_id"] = compute_endpoint_id(record)
        records.append(record)

    bulk = save_endpoints_bulk(
        docs_dir=docs_dir,
        lock_timeout_s=float(lock_timeout_s),
        schema_path=Path(__file__).resolve().parents[2] / "schemas" / "endpoint.schema.json",
        records=records,
        continue_on_error=cfg.continue_on_error,
    )

    return {
        "cmd": "import-postman",
        "schema_version": "v1",
        "config": {
            "exchange": cfg.exchange,
            "section": cfg.section,
            "url": cfg.url,
            "base_url": cfg.base_url,
            "api_version": cfg.api_version,
        },
        "collection_ingest": ing,
        "counts": bulk["counts"],
        "errors": bulk["errors"],
    }

