from __future__ import annotations

import shutil
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from xdocs.agentbrowserfetch import AgentBrowserFetcher, _run
from xdocs.errors import XDocsError


class TestAgentBrowserFetcherInit(unittest.TestCase):
    """Test AgentBrowserFetcher construction and open/close lifecycle."""

    def test_open_raises_if_not_on_path(self) -> None:
        with patch.object(shutil, "which", return_value=None):
            fetcher = AgentBrowserFetcher(allowed_domains={"example.com"})
            with self.assertRaises(XDocsError) as ctx:
                fetcher.open()
            self.assertEqual(ctx.exception.code, "ENOAGENTBROWSER")

    @patch("xdocs.agentbrowserfetch._run")
    @patch.object(shutil, "which", return_value="/usr/bin/agent-browser")
    def test_open_success(self, mock_which, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        fetcher = AgentBrowserFetcher(allowed_domains={"example.com"})
        result = fetcher.open()
        self.assertIs(result, fetcher)
        self.assertTrue(fetcher._open)
        mock_run.assert_called_once()

    @patch("xdocs.agentbrowserfetch._run")
    @patch.object(shutil, "which", return_value="/usr/bin/agent-browser")
    def test_context_manager(self, mock_which, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with AgentBrowserFetcher(allowed_domains={"example.com"}) as fetcher:
            self.assertTrue(fetcher._open)
        # close() was called
        self.assertFalse(fetcher._open)


def _mock_side_effect(*, final_url: str, html_body: str):
    """Create a mock side_effect for _run that dispatches eval correctly."""

    def side_effect(args, **kwargs):
        cmd = args[1] if len(args) > 1 else ""
        if cmd == "open":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        elif cmd == "wait":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        elif cmd == "eval":
            js_expr = args[2] if len(args) > 2 else ""
            if "outerHTML" in js_expr:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=html_body, stderr="")
            # innerText length check
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="500", stderr="")
        elif cmd == "get":
            if "url" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=final_url, stderr="")
            elif "html" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=html_body, stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return side_effect


class TestAgentBrowserFetcherFetch(unittest.TestCase):
    """Test fetch() method with mocked subprocess calls."""

    def _make_fetcher(self) -> AgentBrowserFetcher:
        fetcher = AgentBrowserFetcher(allowed_domains={"example.com"})
        fetcher._bin = "/usr/bin/agent-browser"
        fetcher._open = True
        return fetcher

    def test_fetch_rejects_non_http_url(self) -> None:
        fetcher = self._make_fetcher()
        with self.assertRaises(XDocsError) as ctx:
            fetcher.fetch(url="ftp://example.com", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "EBADURL")

    def test_fetch_raises_if_not_open(self) -> None:
        fetcher = AgentBrowserFetcher(allowed_domains={"example.com"})
        with self.assertRaises(XDocsError) as ctx:
            fetcher.fetch(url="https://example.com", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "ENOAGENTBROWSER")

    @patch("xdocs.agentbrowserfetch._run")
    def test_fetch_success(self, mock_run) -> None:
        html_body = "<html><body><p>Hello World</p></body></html>"
        mock_run.side_effect = _mock_side_effect(final_url="https://example.com/page", html_body=html_body)
        fetcher = self._make_fetcher()
        result = fetcher.fetch(url="https://example.com/page", timeout_s=10, max_bytes=1000000, retries=0)

        self.assertEqual(result.url, "https://example.com/page")
        self.assertEqual(result.final_url, "https://example.com/page")
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.body, html_body.encode("utf-8"))

    @patch("xdocs.agentbrowserfetch._run")
    def test_fetch_domain_violation(self, mock_run) -> None:
        """Final URL on a different domain should raise EDOMAIN."""
        mock_run.side_effect = _mock_side_effect(final_url="https://evil.com/phish", html_body="<html></html>")
        fetcher = self._make_fetcher()
        with self.assertRaises(XDocsError) as ctx:
            fetcher.fetch(url="https://example.com/page", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(ctx.exception.code, "EDOMAIN")

    @patch("xdocs.agentbrowserfetch._run")
    def test_fetch_max_bytes_enforced(self, mock_run) -> None:
        big_body = "x" * 2000
        mock_run.side_effect = _mock_side_effect(final_url="https://example.com/big", html_body=big_body)
        fetcher = self._make_fetcher()
        with self.assertRaises(XDocsError) as ctx:
            fetcher.fetch(url="https://example.com/big", timeout_s=10, max_bytes=100, retries=0)
        self.assertEqual(ctx.exception.code, "ETOOBIG")

    @patch("xdocs.agentbrowserfetch._run")
    def test_fetch_redirect_detected(self, mock_run) -> None:
        """When final_url differs from requested url, redirect_chain should be populated."""
        mock_run.side_effect = _mock_side_effect(
            final_url="https://example.com/new-page",
            html_body="<html><body>content</body></html>",
        )
        fetcher = self._make_fetcher()
        result = fetcher.fetch(url="https://example.com/old-page", timeout_s=10, max_bytes=1000000, retries=0)
        self.assertEqual(result.redirect_chain, ["https://example.com/old-page"])
        self.assertEqual(result.final_url, "https://example.com/new-page")


class TestRunHelper(unittest.TestCase):
    """Test the _run subprocess helper."""

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="test", timeout=10))
    def test_timeout_raises_etimeout(self, mock_subrun) -> None:
        with self.assertRaises(XDocsError) as ctx:
            _run(["agent-browser", "open", "https://example.com"], timeout=10)
        self.assertEqual(ctx.exception.code, "ETIMEOUT")

    @patch("subprocess.run", side_effect=FileNotFoundError("not found"))
    def test_missing_binary_raises_enoagentbrowser(self, mock_subrun) -> None:
        with self.assertRaises(XDocsError) as ctx:
            _run(["agent-browser", "open", "https://example.com"], timeout=10)
        self.assertEqual(ctx.exception.code, "ENOAGENTBROWSER")


if __name__ == "__main__":
    unittest.main()
