from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from pathlib import Path

import yaml

from xdocs.base_urls_validate import validate_base_urls
from tests.http_server import serve_handler


def test_validate_base_urls_smoke(tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args) -> None:  # pragma: no cover
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
            self.send_response(204)
            self.end_headers()

    with serve_handler(Handler) as base:
        reg = {
            "exchanges": [
                {
                    "exchange_id": "testex",
                    "display_name": "TestEx",
                    "allowed_domains": [],
                    "sections": [
                        {"section_id": "rest", "base_urls": [f"{base}/api"], "seed_urls": []},
                        {"section_id": "ws", "base_urls": ["wss://127.0.0.1:12345/ws"], "seed_urls": []},
                    ],
                }
            ]
        }
        reg_path = tmp_path / "exchanges.yaml"
        reg_path.write_text(yaml.safe_dump(reg), encoding="utf-8")

        out = validate_base_urls(registry_path=reg_path, timeout_s=2.0, retries=0)

    assert out["counts"]["total"] == 2
    assert out["counts"]["errors"] == 0

    # Ensure we mark ws/wss entries as "skipped" (DNS-only), but still ok if resolvable.
    ws = [r for r in out["results"] if r["scheme"] == "wss"][0]
    assert ws["skipped"] is True
    assert ws["ok"] is True

