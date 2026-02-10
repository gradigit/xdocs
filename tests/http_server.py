from __future__ import annotations

import contextlib
import os
import threading
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator, Type


@contextlib.contextmanager
def serve_directory(path: Path, *, bind_host: str = "127.0.0.1") -> Iterator[str]:
    """
    Serve a directory over HTTP for tests.

    Notes:
    - Uses a ThreadingHTTPServer to avoid shared state across tests.
    - Overrides server_bind to avoid reverse-DNS lookup in socket.getfqdn(host) on macOS,
      which can block tests for ~30s on misconfigured networks.
    """

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args) -> None:
            return

    class FastThreadingHTTPServer(ThreadingHTTPServer):
        def server_bind(self) -> None:  # type: ignore[override]
            self.socket.bind(self.server_address)
            self.server_address = self.socket.getsockname()
            host, port = self.server_address[:2]
            self.server_name = host
            self.server_port = port

    cwd = os.getcwd()
    os.chdir(path)
    try:
        httpd = FastThreadingHTTPServer((bind_host, 0), QuietHandler)
        host, port = httpd.server_address[:2]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield f"http://{host}:{port}"
        finally:
            httpd.shutdown()
            httpd.server_close()
            t.join(timeout=2)
    finally:
        os.chdir(cwd)


@contextlib.contextmanager
def serve_handler(handler_cls: Type[BaseHTTPRequestHandler], *, bind_host: str = "127.0.0.1") -> Iterator[str]:
    class FastThreadingHTTPServer(ThreadingHTTPServer):
        def server_bind(self) -> None:  # type: ignore[override]
            self.socket.bind(self.server_address)
            self.server_address = self.socket.getsockname()
            host, port = self.server_address[:2]
            self.server_name = host
            self.server_port = port

    httpd = FastThreadingHTTPServer((bind_host, 0), handler_cls)
    host, port = httpd.server_address[:2]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        t.join(timeout=2)
