from __future__ import annotations

import socket
from typing import Any
from urllib.parse import urlsplit

import requests

from .errors import CexApiDocsError
from .registry import load_registry
from .timeutil import now_iso_utc


def _default_port(scheme: str) -> int:
    scheme = (scheme or "").lower()
    if scheme in ("http", "ws"):
        return 80
    return 443


def _resolve_host(host: str, port: int) -> tuple[bool, str | None]:
    try:
        socket.getaddrinfo(host, port)
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def validate_base_urls(
    *,
    registry_path,
    exchange: str | None = None,
    section: str | None = None,
    timeout_s: float = 10.0,
    retries: int = 1,
) -> dict[str, Any]:
    """
    Validate that registry `base_urls` are at least reachable.

    This is intentionally conservative:
    - For http/https, we only check that an HTTP response can be obtained (any status code).
    - For ws/wss, we only check that the host resolves (no websocket handshake).
    - We do NOT call authenticated/private endpoints.
    """
    reg = load_registry(registry_path)
    session = requests.Session()
    checked_at = now_iso_utc()

    results: list[dict[str, Any]] = []

    for ex in reg.exchanges:
        if exchange and ex.exchange_id != exchange:
            continue
        for sec in ex.sections:
            if section and sec.section_id != section:
                continue
            for base_url in sec.base_urls:
                base_url = str(base_url or "")
                parsed = urlsplit(base_url)
                scheme = (parsed.scheme or "").lower()
                host = (parsed.hostname or "").lower()
                port = int(parsed.port or _default_port(scheme))

                rec: dict[str, Any] = {
                    "exchange_id": ex.exchange_id,
                    "section_id": sec.section_id,
                    "base_url": base_url,
                    "scheme": scheme,
                    "host": host,
                    "port": port,
                    "checked_at": checked_at,
                    "ok": False,
                    "skipped": False,
                }

                if not scheme or not host:
                    rec["error"] = {"code": "EBADURL", "message": "Invalid base_url (missing scheme/host)."}
                    results.append(rec)
                    continue

                if scheme in ("ws", "wss"):
                    ok, err = _resolve_host(host, port)
                    rec["ok"] = bool(ok)
                    rec["skipped"] = True
                    if err:
                        rec["error"] = {"code": "ENET", "message": "DNS resolution failed.", "details": {"error": err}}
                    results.append(rec)
                    continue

                if scheme not in ("http", "https"):
                    rec["error"] = {"code": "EBADURL", "message": "Unsupported base_url scheme.", "details": {"scheme": scheme}}
                    results.append(rec)
                    continue

                attempt = 0
                while True:
                    try:
                        resp = session.get(
                            base_url,
                            timeout=float(timeout_s),
                            allow_redirects=False,
                            stream=True,
                        )
                        status = int(resp.status_code)
                        rec["http_status"] = status
                        rec["content_type"] = resp.headers.get("content-type", "") or ""
                        rec["ok"] = True
                        break
                    except Exception as e:
                        if attempt < int(retries):
                            attempt += 1
                            continue
                        rec["error"] = {"code": "ENET", "message": "Network error validating base_url.", "details": {"error": f"{type(e).__name__}: {e}"}}
                        break
                    finally:
                        try:
                            resp.close()  # type: ignore[name-defined]
                        except Exception:
                            pass

                results.append(rec)

    results.sort(key=lambda r: (r["exchange_id"], r["section_id"], r["base_url"]))

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "cmd": "validate-base-urls",
        "registry_path": str(registry_path),
        "filters": {"exchange": exchange, "section": section},
        "checked_at": checked_at,
        "counts": {"total": len(results), "ok": ok_count, "errors": len(results) - ok_count},
        "results": results,
    }

