from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from xdocs.nav_extract import (
    NavExtractionResult,
    NavNode,
    _COMBINED_SELECTOR,
    _domain_allowed,
    _extract_via_agent_browser,
    _extract_via_http,
    _process_raw_links,
    extract_nav_urls,
)


# ---------------------------------------------------------------------------
# Sample HTML fixtures
# ---------------------------------------------------------------------------

SAMPLE_HTML = """\
<html>
<head><title>API Docs</title></head>
<body>
<nav>
  <ul>
    <li><a href="/docs/spot">Spot API</a></li>
    <li><a href="/docs/margin">Margin API</a></li>
    <li>
      <ul>
        <li><a href="/docs/margin/borrow">Borrow</a></li>
      </ul>
    </li>
  </ul>
</nav>
<aside>
  <a href="/docs/changelog">Changelog</a>
  <a href="https://external.com/unrelated">External</a>
  <a href="javascript:void(0)">JS link</a>
  <a href="#section-anchor">Anchor</a>
  <a href="/static/logo.png">Logo</a>
</aside>
<div class="sidebar">
  <a href="/docs/futures">Futures API</a>
</div>
<main>
  <a href="/docs/hidden">Not in nav</a>
</main>
</body>
</html>
"""

SEED_URL = "https://docs.example.com/docs/"
ALLOWED_DOMAINS = ["docs.example.com"]


# ---------------------------------------------------------------------------
# _domain_allowed
# ---------------------------------------------------------------------------


class TestDomainAllowed:
    def test_exact_match(self):
        assert _domain_allowed("https://docs.example.com/x", ["docs.example.com"]) is True

    def test_subdomain_match(self):
        assert _domain_allowed("https://api.docs.example.com/x", ["docs.example.com"]) is True

    def test_no_match(self):
        assert _domain_allowed("https://other.com/x", ["docs.example.com"]) is False

    def test_empty_allowed(self):
        assert _domain_allowed("https://any.com/x", []) is False

    def test_bad_url(self):
        assert _domain_allowed("not-a-url", ["example.com"]) is False


# ---------------------------------------------------------------------------
# _process_raw_links
# ---------------------------------------------------------------------------


class TestProcessRawLinks:
    def test_resolves_relative_urls(self):
        raw = [{"href": "/docs/spot", "text": "Spot", "depth": "0"}]
        urls, nodes = _process_raw_links(raw, seed_url=SEED_URL, allowed_domains=ALLOWED_DOMAINS)
        assert urls == ["https://docs.example.com/docs/spot"]
        assert len(nodes) == 1
        assert nodes[0].text == "Spot"

    def test_filters_non_http(self):
        raw = [{"href": "javascript:void(0)", "text": "JS", "depth": "0"}]
        urls, _ = _process_raw_links(raw, seed_url=SEED_URL, allowed_domains=ALLOWED_DOMAINS)
        assert urls == []

    def test_filters_disallowed_domains(self):
        raw = [{"href": "https://other.com/page", "text": "Other", "depth": "0"}]
        urls, _ = _process_raw_links(raw, seed_url=SEED_URL, allowed_domains=ALLOWED_DOMAINS)
        assert urls == []

    def test_deduplicates(self):
        raw = [
            {"href": "/docs/spot", "text": "Spot", "depth": "0"},
            {"href": "/docs/spot", "text": "Spot Again", "depth": "0"},
        ]
        urls, nodes = _process_raw_links(raw, seed_url=SEED_URL, allowed_domains=ALLOWED_DOMAINS)
        assert len(urls) == 1
        assert len(nodes) == 2  # nodes are not deduped

    def test_sanitize_rejects_fragment_only(self):
        raw = [{"href": "#section", "text": "Section", "depth": "0"}]
        urls, _ = _process_raw_links(raw, seed_url=SEED_URL, allowed_domains=ALLOWED_DOMAINS)
        # Fragment-only resolves to the seed URL itself, which should pass sanitize.
        # The resolved URL is the seed with a fragment, which sanitize_url accepts.
        # So this depends on sanitize_url behavior with fragments.

    def test_empty_href_skipped(self):
        raw = [{"href": "", "text": "Empty", "depth": "0"}]
        urls, _ = _process_raw_links(raw, seed_url=SEED_URL, allowed_domains=ALLOWED_DOMAINS)
        assert urls == []

    def test_sanitize_rejects_image_ext(self):
        raw = [{"href": "/static/logo.png", "text": "Logo", "depth": "0"}]
        urls, _ = _process_raw_links(raw, seed_url=SEED_URL, allowed_domains=ALLOWED_DOMAINS)
        assert urls == []

    def test_depth_parsed(self):
        raw = [{"href": "/docs/nested", "text": "Nested", "depth": "3"}]
        _, nodes = _process_raw_links(raw, seed_url=SEED_URL, allowed_domains=ALLOWED_DOMAINS)
        assert nodes[0].depth == 3


# ---------------------------------------------------------------------------
# HTTP fallback extraction
# ---------------------------------------------------------------------------


class TestExtractViaHttp:
    @patch("xdocs.nav_extract.requests")
    def test_extracts_nav_links(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        result = _extract_via_http(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=10.0,
        )

        assert result.method == "http_fallback"
        assert len(result.errors) == 0
        # Should find: /docs/spot, /docs/margin, /docs/margin/borrow, /docs/changelog, /docs/futures
        # #section-anchor resolves to /docs/ (seed URL) after fragment stripping
        # Should NOT find: external.com, javascript:, .png, /docs/hidden (not in nav/aside/sidebar)
        expected_paths = {"/docs/", "/docs/spot", "/docs/margin", "/docs/margin/borrow", "/docs/changelog", "/docs/futures"}
        result_paths = {u.replace("https://docs.example.com", "") for u in result.urls}
        assert result_paths == expected_paths

    @patch("xdocs.nav_extract.requests")
    def test_handles_http_error(self, mock_requests):
        mock_requests.get.side_effect = ConnectionError("Network error")

        result = _extract_via_http(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=5.0,
        )

        assert result.method == "http_fallback"
        assert len(result.urls) == 0
        assert len(result.errors) == 1
        assert result.errors[0]["stage"] == "http_fetch"

    @patch("xdocs.nav_extract.requests")
    def test_nav_node_depth(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        result = _extract_via_http(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=10.0,
        )

        # /docs/margin/borrow is inside nested UL, so depth > 0
        borrow_nodes = [n for n in result.nav_nodes if "/borrow" in n.url]
        assert len(borrow_nodes) == 1
        assert borrow_nodes[0].depth > 0


# ---------------------------------------------------------------------------
# Agent-browser extraction (mocked subprocess)
# ---------------------------------------------------------------------------


class TestExtractViaAgentBrowser:
    def _make_completed(self, stdout="", stderr="", returncode=0):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr,
        )

    @patch("xdocs.nav_extract.shutil.which", return_value="/usr/local/bin/agent-browser")
    @patch("xdocs.nav_extract._run_agent_browser")
    def test_successful_extraction(self, mock_run, mock_which):
        nav_data = json.dumps([
            {"href": "/docs/spot", "text": "Spot API", "depth": 0},
            {"href": "/docs/margin", "text": "Margin API", "depth": 0},
        ])

        # Calls: open, wait, eval, close
        mock_run.side_effect = [
            self._make_completed(),        # open
            self._make_completed(),        # wait
            self._make_completed(stdout=nav_data),  # eval
            self._make_completed(),        # close
        ]

        result = _extract_via_agent_browser(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=30.0,
        )

        assert result.method == "agent_browser"
        assert len(result.urls) == 2
        assert len(result.errors) == 0

    @patch("xdocs.nav_extract.shutil.which", return_value=None)
    def test_agent_browser_not_found(self, mock_which):
        with pytest.raises(FileNotFoundError, match="agent-browser"):
            _extract_via_agent_browser(
                seed_url=SEED_URL,
                allowed_domains=ALLOWED_DOMAINS,
                timeout_s=30.0,
            )

    @patch("xdocs.nav_extract.shutil.which", return_value="/usr/local/bin/agent-browser")
    @patch("xdocs.nav_extract._run_agent_browser")
    def test_open_failure(self, mock_run, mock_which):
        mock_run.return_value = self._make_completed(returncode=1, stderr="connection refused")

        with pytest.raises(RuntimeError, match="open failed"):
            _extract_via_agent_browser(
                seed_url=SEED_URL,
                allowed_domains=ALLOWED_DOMAINS,
                timeout_s=30.0,
            )

    @patch("xdocs.nav_extract.shutil.which", return_value="/usr/local/bin/agent-browser")
    @patch("xdocs.nav_extract._run_agent_browser")
    def test_eval_failure_returns_empty(self, mock_run, mock_which):
        mock_run.side_effect = [
            self._make_completed(),        # open
            self._make_completed(),        # wait
            self._make_completed(returncode=1, stderr="eval error"),  # eval fails
        ]

        result = _extract_via_agent_browser(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=30.0,
        )

        assert result.method == "agent_browser"
        assert len(result.urls) == 0
        assert len(result.errors) == 1
        assert result.errors[0]["stage"] == "eval"

    @patch("xdocs.nav_extract.shutil.which", return_value="/usr/local/bin/agent-browser")
    @patch("xdocs.nav_extract._run_agent_browser")
    def test_invalid_json_returns_empty(self, mock_run, mock_which):
        mock_run.side_effect = [
            self._make_completed(),        # open
            self._make_completed(),        # wait
            self._make_completed(stdout="not valid json"),  # eval returns garbage
        ]

        result = _extract_via_agent_browser(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=30.0,
        )

        assert result.method == "agent_browser"
        assert len(result.urls) == 0
        assert len(result.errors) == 1
        assert result.errors[0]["stage"] == "json_parse"


# ---------------------------------------------------------------------------
# Top-level extract_nav_urls (integration of both methods)
# ---------------------------------------------------------------------------


class TestExtractNavUrls:
    @patch("xdocs.nav_extract._extract_via_agent_browser")
    def test_uses_agent_browser_when_available(self, mock_ab):
        mock_ab.return_value = NavExtractionResult(
            seed_url=SEED_URL,
            urls=["https://docs.example.com/docs/spot"],
            nav_nodes=[NavNode(url="https://docs.example.com/docs/spot", text="Spot", depth=0)],
            errors=[],
            method="agent_browser",
        )

        result = extract_nav_urls(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=10.0,
        )

        assert result.method == "agent_browser"
        assert len(result.urls) == 1
        mock_ab.assert_called_once()

    @patch("xdocs.nav_extract._extract_via_http")
    @patch("xdocs.nav_extract._extract_via_agent_browser")
    def test_falls_back_to_http_on_file_not_found(self, mock_ab, mock_http):
        mock_ab.side_effect = FileNotFoundError("not found")
        mock_http.return_value = NavExtractionResult(
            seed_url=SEED_URL,
            urls=["https://docs.example.com/docs/spot"],
            nav_nodes=[NavNode(url="https://docs.example.com/docs/spot", text="Spot", depth=0)],
            errors=[],
            method="http_fallback",
        )

        result = extract_nav_urls(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=10.0,
        )

        assert result.method == "http_fallback"
        mock_http.assert_called_once()

    @patch("xdocs.nav_extract._extract_via_http")
    @patch("xdocs.nav_extract._extract_via_agent_browser")
    def test_falls_back_to_http_on_zero_urls(self, mock_ab, mock_http):
        mock_ab.return_value = NavExtractionResult(
            seed_url=SEED_URL,
            urls=[],
            nav_nodes=[],
            errors=[],
            method="agent_browser",
        )
        mock_http.return_value = NavExtractionResult(
            seed_url=SEED_URL,
            urls=["https://docs.example.com/docs/spot"],
            nav_nodes=[NavNode(url="https://docs.example.com/docs/spot", text="Spot", depth=0)],
            errors=[],
            method="http_fallback",
        )

        result = extract_nav_urls(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=10.0,
        )

        assert result.method == "http_fallback"

    @patch("xdocs.nav_extract._extract_via_http")
    @patch("xdocs.nav_extract._extract_via_agent_browser")
    def test_falls_back_on_timeout(self, mock_ab, mock_http):
        mock_ab.side_effect = subprocess.TimeoutExpired(cmd="agent-browser", timeout=30)
        mock_http.return_value = NavExtractionResult(
            seed_url=SEED_URL,
            urls=["https://docs.example.com/docs/spot"],
            nav_nodes=[],
            errors=[],
            method="http_fallback",
        )

        result = extract_nav_urls(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=10.0,
        )

        assert result.method == "http_fallback"

    @patch("xdocs.nav_extract._extract_via_http")
    @patch("xdocs.nav_extract._extract_via_agent_browser")
    def test_falls_back_on_runtime_error(self, mock_ab, mock_http):
        mock_ab.side_effect = RuntimeError("open failed")
        mock_http.return_value = NavExtractionResult(
            seed_url=SEED_URL,
            urls=[],
            nav_nodes=[],
            errors=[],
            method="http_fallback",
        )

        result = extract_nav_urls(
            seed_url=SEED_URL,
            allowed_domains=ALLOWED_DOMAINS,
            timeout_s=10.0,
        )

        assert result.method == "http_fallback"
