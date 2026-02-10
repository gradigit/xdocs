from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
import yaml

from .endpoints import compute_endpoint_id, save_endpoints_bulk
from .errors import CexApiDocsError
from .httpfetch import fetch
from .ingest_page import ingest_page
from .markdown import normalize_markdown


HTTP_METHOD_KEYS: tuple[str, ...] = ("get", "post", "put", "delete", "patch", "head", "options", "trace")


@dataclass(frozen=True, slots=True)
class OpenApiImportConfig:
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
    # OpenAPI specs are typically UTF-8; fall back to replacement to avoid hard failures.
    return body.decode("utf-8", errors="replace")


def _is_http_url(url: str) -> bool:
    return urlsplit(url).scheme in ("http", "https")


def _parse_openapi(text: str) -> dict[str, Any]:
    t = text.lstrip()
    if t.startswith("{"):
        obj = json.loads(text)
    else:
        obj = yaml.safe_load(text)
    if not isinstance(obj, dict):
        raise CexApiDocsError(code="EBADOPENAPI", message="OpenAPI spec must parse to an object.")
    return obj


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


def _find_operation_excerpt(md: str, *, path: str, method_lower: str) -> tuple[int, int, str] | None:
    # Try to anchor on a reasonably unique string in the YAML/JSON spec text.
    candidates = [
        f"\n  {path}:",
        f"\n{path}:",
        f'"{path}"',
        path,
    ]
    for c in candidates:
        hit = _find_excerpt(md, c)
        if hit is None:
            continue
        start, end, excerpt = hit
        # Ensure the excerpt likely includes the method key (best-effort).
        if method_lower and method_lower not in excerpt.lower():
            # Try to shift anchor to the method key inside the path block.
            sub = md[start : min(len(md), start + 4000)]
            for mpat in (f"\n    {method_lower}:", f"\n  {method_lower}:", f'"{method_lower}"'):
                j = sub.find(mpat)
                if j >= 0:
                    start2 = start + j + 1  # skip leading newline for readability
                    end2 = min(len(md), start2 + 550)
                    if end2 > start2:
                        return start2, end2, md[start2:end2]
        return start, end, excerpt
    return None


def _extract_request_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    params = operation.get("parameters")
    req_body = operation.get("requestBody")
    if params is None and req_body is None:
        return None
    out: dict[str, Any] = {}
    if params is not None:
        out["parameters"] = params
    if req_body is not None:
        out["requestBody"] = req_body
    return out


def _extract_response_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    resp = operation.get("responses")
    if resp is None:
        return None
    return {"responses": resp}


def import_openapi(
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
        raise CexApiDocsError(code="EBADARG", message="import-openapi requires an http(s) URL.", details={"url": url})
    if not exchange or not section:
        raise CexApiDocsError(code="EBADARG", message="Missing exchange/section.", details={"exchange": exchange, "section": section})

    cfg = OpenApiImportConfig(
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
        raise CexApiDocsError(code="EOPENAPIHTTP", message="Failed to fetch OpenAPI spec.", details={"url": url, "http_status": fr.http_status})

    text_raw = _decode_body(fr.body)
    md_norm = normalize_markdown(text_raw)
    spec = _parse_openapi(text_raw)

    # Ingest the spec into the canonical store so citations are mechanically verifiable.
    tmp = Path(docs_dir) / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    md_path = tmp / "openapi-spec.md"
    md_path.write_text(md_norm + "\n", encoding="utf-8")
    ing = ingest_page(
        docs_dir=docs_dir,
        lock_timeout_s=float(lock_timeout_s),
        url=url,
        markdown_path=md_path,
        tool="import-openapi",
        notes=f"exchange={exchange} section={section}",
    )
    stored = ing["stored"]

    server_url: str | None = None
    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            server_url = str(first["url"]).strip() or None

    effective_base_url = cfg.base_url or server_url

    if not effective_base_url:
        raise CexApiDocsError(
            code="EBADOPENAPI",
            message="OpenAPI spec has no servers[].url and no --base-url was provided.",
            details={"url": url},
        )

    base_url_excerpt = None
    if effective_base_url and server_url and effective_base_url == server_url:
        base_url_excerpt = _find_excerpt(md_norm, server_url)

    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise CexApiDocsError(code="EBADOPENAPI", message="OpenAPI spec missing paths{}.", details={"url": url})

    records: list[dict[str, Any]] = []
    for p, path_item in paths.items():
        if not isinstance(p, str):
            continue
        if not isinstance(path_item, dict):
            continue
        for mk in HTTP_METHOD_KEYS:
            op = path_item.get(mk)
            if not isinstance(op, dict):
                continue

            method = mk.upper()
            path = p
            desc = op.get("summary") or op.get("description")
            description = None if desc is None else str(desc)

            req_schema = _extract_request_schema(op)
            resp_schema = _extract_response_schema(op)

            op_excerpt = _find_operation_excerpt(md_norm, path=path, method_lower=mk)

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

            # Method/path citations (and optionally request/response schema) from the operation block.
            if op_excerpt is not None:
                start, end, excerpt = op_excerpt
                for field_name in ("http.method", "http.path"):
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

                # Request/response schemas are deterministic in OpenAPI. Only mark documented if present.
                if req_schema is not None:
                    sources.append(
                        {
                            "url": url,
                            "crawled_at": stored["crawled_at"],
                            "content_hash": stored["content_hash"],
                            "path_hash": stored["path_hash"],
                            "excerpt": excerpt,
                            "excerpt_start": start,
                            "excerpt_end": end,
                            "field_name": "request_schema",
                        }
                    )
                    field_status["request_schema"] = "documented"
                else:
                    req_schema = None

                if resp_schema is not None:
                    sources.append(
                        {
                            "url": url,
                            "crawled_at": stored["crawled_at"],
                            "content_hash": stored["content_hash"],
                            "path_hash": stored["path_hash"],
                            "excerpt": excerpt,
                            "excerpt_start": start,
                            "excerpt_end": end,
                            "field_name": "response_schema",
                        }
                    )
                    field_status["response_schema"] = "documented"
                else:
                    resp_schema = None

            # Base URL citation from servers[] (best-effort).
            if base_url_excerpt is not None and effective_base_url:
                start, end, excerpt = base_url_excerpt
                sources.append(
                    {
                        "url": url,
                        "crawled_at": stored["crawled_at"],
                        "content_hash": stored["content_hash"],
                        "path_hash": stored["path_hash"],
                        "excerpt": excerpt,
                        "excerpt_start": start,
                        "excerpt_end": end,
                        "field_name": "http.base_url",
                    }
                )
                field_status["http.base_url"] = "documented"

            http_obj = {
                "method": method,
                "path": path,
                "base_url": effective_base_url or "",
                "api_version": cfg.api_version,
            }

            record: dict[str, Any] = {
                "exchange": cfg.exchange,
                "section": cfg.section,
                "protocol": "http",
                "http": http_obj,
                "description": description,
                "request_schema": req_schema,
                "response_schema": resp_schema,
                "required_permissions": None,
                "rate_limit": None,
                "error_codes": None,
                "sources": sources,
                "field_status": field_status,
                "extraction": {
                    "model": "import-openapi",
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
        "cmd": "import-openapi",
        "schema_version": "v1",
        "config": {
            "exchange": cfg.exchange,
            "section": cfg.section,
            "url": cfg.url,
            "base_url": cfg.base_url,
            "api_version": cfg.api_version,
        },
        "spec_ingest": ing,
        "counts": bulk["counts"],
        "errors": bulk["errors"],
    }
