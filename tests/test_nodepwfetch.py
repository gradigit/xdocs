from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from xdocs.errors import CexApiDocsError
from xdocs.nodepwfetch import (
    NodePlaywrightFetcher,
    _find_node_pw_module,
    _NODE_PW_MODULE,
)


class TestFindNodePwModule(unittest.TestCase):
    """Test _find_node_pw_module discovery logic."""

    @patch.dict("os.environ", {"CEX_NODE_PW_MODULE": "/tmp/fake-pw"})
    @patch("pathlib.Path.exists", return_value=True)
    def test_env_override(self, mock_exists) -> None:
        result = _find_node_pw_module()
        self.assertEqual(result, Path("/tmp/fake-pw"))

    @patch.dict("os.environ", {}, clear=True)
    @patch("xdocs.nodepwfetch._NODE_PW_MODULE", Path("/nonexistent/path"))
    def test_raises_if_not_found(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            with self.assertRaises(CexApiDocsError) as ctx:
                _find_node_pw_module()
            self.assertEqual(ctx.exception.code, "ENOPLAYWRIGHT")


class TestNodePlaywrightFetcherInit(unittest.TestCase):
    """Test NodePlaywrightFetcher open/close lifecycle."""

    @patch("xdocs.nodepwfetch._check_chromium_binary")
    @patch("xdocs.nodepwfetch._find_node_pw_module")
    @patch("subprocess.Popen")
    def test_open_success(self, mock_popen, mock_find, mock_check) -> None:
        mock_find.return_value = Path("/opt/homebrew/lib/node_modules/playwright")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        fetcher = NodePlaywrightFetcher(allowed_domains={"example.com"})
        result = fetcher.open()
        self.assertIs(result, fetcher)
        self.assertIsNotNone(fetcher._proc)

    @patch("xdocs.nodepwfetch._check_chromium_binary")
    @patch("xdocs.nodepwfetch._find_node_pw_module")
    @patch("subprocess.Popen")
    def test_close(self, mock_popen, mock_find, mock_check) -> None:
        mock_find.return_value = Path("/opt/homebrew/lib/node_modules/playwright")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        fetcher = NodePlaywrightFetcher(allowed_domains={"example.com"})
        fetcher.open()
        fetcher.close()
        self.assertIsNone(fetcher._proc)
        mock_proc.stdin.write.assert_called()


class TestNodePlaywrightFetcherFetch(unittest.TestCase):
    """Test fetch() with mocked subprocess I/O."""

    def _make_fetcher(self, response_json: dict) -> NodePlaywrightFetcher:
        fetcher = NodePlaywrightFetcher(allowed_domains={"example.com"})
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps(response_json) + "\n"
        fetcher._proc = mock_proc
        fetcher._pw_module = Path("/opt/pw")
        return fetcher

    def test_fetch_rejects_non_http_url(self) -> None:
        fetcher = self._make_fetcher({})
        with self.assertRaises(CexApiDocsError) as ctx:
            fetcher.fetch(url="ftp://example.com", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "EBADURL")

    def test_fetch_raises_if_not_open(self) -> None:
        fetcher = NodePlaywrightFetcher(allowed_domains={"example.com"})
        with self.assertRaises(CexApiDocsError) as ctx:
            fetcher.fetch(url="https://example.com", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "ENOPLAYWRIGHT")

    def test_fetch_success(self) -> None:
        resp = {
            "url": "https://example.com/page",
            "final_url": "https://example.com/page",
            "status": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {"etag": '"abc"'},
            "html": "<html><body>Hello</body></html>",
        }
        fetcher = self._make_fetcher(resp)
        result = fetcher.fetch(url="https://example.com/page", timeout_s=10, max_bytes=1000000, retries=0)

        self.assertEqual(result.url, "https://example.com/page")
        self.assertEqual(result.final_url, "https://example.com/page")
        self.assertEqual(result.http_status, 200)
        self.assertIn(b"Hello", result.body)
        self.assertEqual(result.headers.get("etag"), '"abc"')

    def test_fetch_domain_violation(self) -> None:
        resp = {
            "url": "https://example.com/page",
            "final_url": "https://evil.com/phish",
            "status": 200,
            "content_type": "text/html",
            "headers": {},
            "html": "<html></html>",
        }
        fetcher = self._make_fetcher(resp)
        with self.assertRaises(CexApiDocsError) as ctx:
            fetcher.fetch(url="https://example.com/page", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "EDOMAIN")

    def test_fetch_max_bytes(self) -> None:
        resp = {
            "url": "https://example.com/big",
            "final_url": "https://example.com/big",
            "status": 200,
            "content_type": "text/html",
            "headers": {},
            "html": "x" * 2000,
        }
        fetcher = self._make_fetcher(resp)
        with self.assertRaises(CexApiDocsError) as ctx:
            fetcher.fetch(url="https://example.com/big", timeout_s=10, max_bytes=100, retries=0)
        self.assertEqual(ctx.exception.code, "ETOOBIG")

    def test_fetch_node_error(self) -> None:
        resp = {"url": "https://example.com/fail", "error": "Navigation timeout"}
        fetcher = self._make_fetcher(resp)
        with self.assertRaises(CexApiDocsError) as ctx:
            fetcher.fetch(url="https://example.com/fail", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "ENET")

    def test_fetch_subprocess_closed(self) -> None:
        fetcher = NodePlaywrightFetcher(allowed_domains={"example.com"})
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Process exited
        fetcher._proc = mock_proc
        with self.assertRaises(CexApiDocsError) as ctx:
            fetcher.fetch(url="https://example.com", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "ENOPLAYWRIGHT")

    def test_fetch_redirect_detected(self) -> None:
        resp = {
            "url": "https://example.com/old",
            "final_url": "https://example.com/new",
            "status": 200,
            "content_type": "text/html",
            "headers": {},
            "html": "<html><body>redirected</body></html>",
        }
        fetcher = self._make_fetcher(resp)
        result = fetcher.fetch(url="https://example.com/old", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(result.redirect_chain, ["https://example.com/old"])
        self.assertEqual(result.final_url, "https://example.com/new")

    def test_fetch_empty_readline_raises(self) -> None:
        fetcher = NodePlaywrightFetcher(allowed_domains={"example.com"})
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = ""  # EOF
        fetcher._proc = mock_proc
        fetcher._pw_module = Path("/opt/pw")
        with self.assertRaises(CexApiDocsError) as ctx:
            fetcher.fetch(url="https://example.com", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "ENET")


if __name__ == "__main__":
    unittest.main()
