from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import requests

from .errors import CexApiDocsError
from .httpfetch import FetchResult, fetch
from .markdown import html_to_markdown, normalize_markdown
from .registry import load_registry


def _parse_charset(content_type: str) -> str | None:
    m = re.search(r"charset=([\\w\\-]+)", content_type or "", flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def _decode_body(body: bytes, content_type: str) -> str:
    charset = _parse_charset(content_type) or "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _detect_meta_refresh(html: str) -> dict[str, Any] | None:
    # Example: <meta http-equiv="refresh" content="0; url=https://example.com">
    m = re.search(
        r"(?is)<meta\\s+[^>]*http-equiv\\s*=\\s*['\\\"]?refresh['\\\"]?[^>]*content\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]",
        html,
    )
    if not m:
        return None
    content = m.group(1)
    m2 = re.search(r"(?i)\\burl\\s*=\\s*([^;\\s]+)", content)
    target = m2.group(1).strip() if m2 else None
    return {"content": content, "target": target}


def validate_registry(
    *,
    registry_path,
    exchange: str | None = None,
    section: str | None = None,
    timeout_s: float = 20.0,
    max_bytes: int = 10_000_000,
    max_redirects: int = 5,
    retries: int = 1,
) -> dict[str, Any]:
    reg = load_registry(registry_path)
    session = requests.Session()

    results: list[dict[str, Any]] = []

    for ex in reg.exchanges:
        if exchange and ex.exchange_id != exchange:
            continue
        allow = {d.lower() for d in ex.allowed_domains}
        for sec in ex.sections:
            if section and sec.section_id != section:
                continue
            for seed in sec.seed_urls:
                seed_host = (urlsplit(seed).hostname or "").lower()
                rec: dict[str, Any] = {
                    "exchange_id": ex.exchange_id,
                    "section_id": sec.section_id,
                    "seed_url": seed,
                    "seed_host": seed_host,
                    "seed_host_allowed": seed_host in allow or any(seed_host.endswith("." + d) for d in allow),
                    "ok": False,
                }
                try:
                    fr: FetchResult = fetch(
                        session,
                        url=seed,
                        timeout_s=float(timeout_s),
                        max_bytes=int(max_bytes),
                        max_redirects=int(max_redirects),
                        retries=int(retries),
                        allowed_domains=allow,
                    )
                    html = _decode_body(fr.body, fr.content_type)
                    md_norm = ""
                    if "text/html" in (fr.content_type or "").lower() or (fr.content_type or "").lower().startswith("text/"):
                        md_raw = html_to_markdown(html, base_url=fr.final_url)
                        md_norm = normalize_markdown(md_raw)
                    meta_refresh = _detect_meta_refresh(html)
                    suspected_stub = bool(meta_refresh) and len(md_norm.strip()) < 200

                    rec.update(
                        {
                            "ok": True,
                            "http_status": fr.http_status,
                            "final_url": fr.final_url,
                            "final_host": (urlsplit(fr.final_url).hostname or "").lower(),
                            "redirect_chain": list(fr.redirect_chain),
                            "content_type": fr.content_type,
                            "bytes": len(fr.body),
                            "markdown_chars": len(md_norm),
                            "word_count": len(md_norm.split()),
                            "meta_refresh": meta_refresh,
                            "suspected_redirect_stub": suspected_stub,
                        }
                    )
                except CexApiDocsError as e:
                    rec["error"] = e.to_json()
                results.append(rec)

    results.sort(key=lambda r: (r["exchange_id"], r["section_id"], r["seed_url"]))

    ok_count = sum(1 for r in results if r.get("ok"))
    stub_count = sum(1 for r in results if r.get("suspected_redirect_stub"))
    return {
        "cmd": "validate-registry",
        "registry_path": str(registry_path),
        "filters": {"exchange": exchange, "section": section},
        "counts": {"total": len(results), "ok": ok_count, "errors": len(results) - ok_count, "suspected_redirect_stubs": stub_count},
        "results": results,
    }
