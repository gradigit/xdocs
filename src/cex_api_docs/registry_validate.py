from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import requests

from .errors import CexApiDocsError
from .httpfetch import FetchResult, fetch
from .markdown import html_to_markdown, normalize_markdown
from .playwrightfetch import PlaywrightFetcher
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
    render_mode: str = "http",
) -> dict[str, Any]:
    if render_mode not in ("http", "playwright", "auto"):
        raise CexApiDocsError(code="EBADARG", message="Invalid render_mode.", details={"render_mode": render_mode})

    reg = load_registry(registry_path)
    session = requests.Session()
    pw: PlaywrightFetcher | None = None

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
                    fr: FetchResult | None = None
                    used_render = "http"

                    def extract(fr0: FetchResult) -> tuple[str, str, int, dict[str, Any] | None, bool]:
                        html0 = _decode_body(fr0.body, fr0.content_type)
                        md_norm0 = ""
                        if "text/html" in (fr0.content_type or "").lower() or (fr0.content_type or "").lower().startswith("text/"):
                            md_raw0 = html_to_markdown(html0, base_url=fr0.final_url)
                            md_norm0 = normalize_markdown(md_raw0)
                        meta_refresh0 = _detect_meta_refresh(html0)
                        suspected_stub0 = bool(meta_refresh0) and len(md_norm0.strip()) < 200
                        wc0 = len(md_norm0.split())
                        return md_norm0, html0, wc0, meta_refresh0, suspected_stub0

                    def is_good(fr0: FetchResult, wc0: int) -> bool:
                        # For validation, require a 2xx fetch and at least some extracted content.
                        if int(fr0.http_status) < 200 or int(fr0.http_status) >= 300:
                            return False
                        if wc0 <= 0:
                            return False
                        return True

                    if render_mode in ("http", "auto"):
                        fr = fetch(
                            session,
                            url=seed,
                            timeout_s=float(timeout_s),
                            max_bytes=int(max_bytes),
                            max_redirects=int(max_redirects),
                            retries=int(retries),
                            allowed_domains=allow,
                        )
                        used_render = "http"
                        md_norm, html, wc, meta_refresh, suspected_stub = extract(fr)
                    else:
                        md_norm, html, wc, meta_refresh, suspected_stub = ("", "", 0, None, False)

                    if render_mode in ("playwright", "auto"):
                        needs_pw = render_mode == "playwright"
                        if fr is not None and render_mode == "auto":
                            needs_pw = not is_good(fr, wc)

                        if needs_pw:
                            if pw is None:
                                pw = PlaywrightFetcher(allowed_domains=allow).open()
                            fr_pw = pw.fetch(
                                url=seed,
                                timeout_s=float(timeout_s),
                                max_bytes=int(max_bytes),
                                retries=int(retries),
                            )
                            md_pw, _html_pw, wc_pw, meta_refresh_pw, suspected_stub_pw = extract(fr_pw)
                            if fr is None or not is_good(fr, wc) or wc_pw > wc:
                                fr = fr_pw
                                used_render = "playwright"
                                md_norm, wc, meta_refresh, suspected_stub = md_pw, wc_pw, meta_refresh_pw, suspected_stub_pw

                    if fr is None:  # pragma: no cover
                        raise CexApiDocsError(code="ENET", message="No fetch result produced.", details={"seed": seed})

                    rec.update(
                        {
                            "ok": is_good(fr, wc),
                            "render_mode": used_render,
                            "http_status": fr.http_status,
                            "final_url": fr.final_url,
                            "final_host": (urlsplit(fr.final_url).hostname or "").lower(),
                            "redirect_chain": list(fr.redirect_chain),
                            "content_type": fr.content_type,
                            "bytes": len(fr.body),
                            "markdown_chars": len(md_norm),
                            "word_count": wc,
                            "meta_refresh": meta_refresh,
                            "suspected_redirect_stub": suspected_stub,
                        }
                    )
                except CexApiDocsError as e:
                    rec["error"] = e.to_json()
                results.append(rec)

    if pw is not None:
        pw.close()

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
