from __future__ import annotations

import pytest

from cex_api_docs.url_sanitize import SanitizeResult, sanitize_url, sanitize_urls


class TestSanitizeUrlAccepted:
    def test_normal_https_url(self) -> None:
        r = sanitize_url("https://docs.binance.com/api/v1/overview")
        assert r.accepted is True
        assert r.reason is None

    def test_http_url(self) -> None:
        r = sanitize_url("http://example.com/docs/intro")
        assert r.accepted is True

    def test_url_with_query(self) -> None:
        r = sanitize_url("https://docs.example.com/api?lang=en")
        assert r.accepted is True

    def test_url_with_fragment(self) -> None:
        r = sanitize_url("https://docs.example.com/api#section")
        assert r.accepted is True

    def test_js_extension_not_asset_path(self) -> None:
        # A .js URL that is NOT in an asset path should be accepted.
        r = sanitize_url("https://docs.example.com/docs/websocket.js")
        assert r.accepted is True

    def test_html_extension(self) -> None:
        r = sanitize_url("https://docs.example.com/api/v1/overview.html")
        assert r.accepted is True


class TestSanitizeUrlRejected:
    # -- Template artifacts --
    def test_jinja_double_brace(self) -> None:
        r = sanitize_url("https://example.com/{{path}}/page")
        assert r.accepted is False
        assert r.reason == "template_artifact"

    def test_jinja_block(self) -> None:
        r = sanitize_url("https://example.com/{% if x %}/page")
        assert r.accepted is False
        assert r.reason == "template_artifact"

    def test_dollar_brace(self) -> None:
        r = sanitize_url("https://example.com/${var}/page")
        assert r.accepted is False
        assert r.reason == "template_artifact"

    # -- CDN / admin paths --
    def test_cdn_cgi(self) -> None:
        r = sanitize_url("https://example.com/cdn-cgi/l/email-protection")
        assert r.accepted is False
        assert "cdn_admin_path" in (r.reason or "")

    def test_wp_admin(self) -> None:
        r = sanitize_url("https://example.com/wp-admin/settings")
        assert r.accepted is False
        assert "cdn_admin_path" in (r.reason or "")

    # -- Non-doc resources --
    @pytest.mark.parametrize("ext", [".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"])
    def test_image_extensions(self, ext: str) -> None:
        r = sanitize_url(f"https://example.com/images/logo{ext}")
        assert r.accepted is False
        assert r.reason == f"resource_ext:{ext}"

    @pytest.mark.parametrize("ext", [".pdf", ".zip", ".tar", ".gz", ".exe", ".dmg", ".deb", ".rpm"])
    def test_binary_extensions(self, ext: str) -> None:
        r = sanitize_url(f"https://example.com/downloads/file{ext}")
        assert r.accepted is False
        assert r.reason == f"resource_ext:{ext}"

    @pytest.mark.parametrize("ext", [".css", ".woff", ".woff2", ".ttf", ".eot"])
    def test_static_asset_extensions(self, ext: str) -> None:
        r = sanitize_url(f"https://example.com/static/style{ext}")
        assert r.accepted is False
        assert r.reason == f"resource_ext:{ext}"

    # -- JS asset bundles --
    def test_js_in_assets_dir(self) -> None:
        r = sanitize_url("https://example.com/assets/main.abc123.js")
        assert r.accepted is False
        assert r.reason == "js_asset:.js"

    def test_mjs_in_static_dir(self) -> None:
        r = sanitize_url("https://example.com/static/chunk.mjs")
        assert r.accepted is False
        assert r.reason == "js_asset:.mjs"

    def test_cjs_in_next_dir(self) -> None:
        r = sanitize_url("https://example.com/_next/static/chunks/bundle.cjs")
        assert r.accepted is False
        assert r.reason == "js_asset:.cjs"

    def test_js_in_dist(self) -> None:
        r = sanitize_url("https://example.com/dist/app.js")
        assert r.accepted is False
        assert r.reason == "js_asset:.js"

    # -- Non-HTTP schemes --
    def test_javascript_scheme(self) -> None:
        r = sanitize_url("javascript:void(0)")
        assert r.accepted is False
        assert r.reason == "bad_scheme:javascript"

    def test_mailto_scheme(self) -> None:
        r = sanitize_url("mailto:user@example.com")
        assert r.accepted is False
        assert r.reason == "bad_scheme:mailto"

    def test_tel_scheme(self) -> None:
        r = sanitize_url("tel:+1234567890")
        assert r.accepted is False
        assert r.reason == "bad_scheme:tel"

    def test_data_scheme(self) -> None:
        r = sanitize_url("data:text/html,<h1>hello</h1>")
        assert r.accepted is False
        assert r.reason == "bad_scheme:data"

    def test_ftp_scheme(self) -> None:
        r = sanitize_url("ftp://files.example.com/doc.txt")
        assert r.accepted is False
        assert r.reason == "bad_scheme:ftp"

    # -- Empty / broken --
    def test_empty_string(self) -> None:
        r = sanitize_url("")
        assert r.accepted is False
        assert r.reason == "empty"

    def test_whitespace_only(self) -> None:
        r = sanitize_url("   ")
        assert r.accepted is False
        assert r.reason == "empty"

    def test_too_long(self) -> None:
        r = sanitize_url("https://example.com/" + "a" * 4100)
        assert r.accepted is False
        assert r.reason == "too_long"

    def test_no_hostname(self) -> None:
        r = sanitize_url("https://")
        assert r.accepted is False
        assert r.reason == "no_hostname"

    def test_control_chars(self) -> None:
        r = sanitize_url("https://example.com/page\x00bad")
        assert r.accepted is False
        assert r.reason == "control_chars"

    def test_fragment_only(self) -> None:
        r = sanitize_url("#section")
        assert r.accepted is False
        assert r.reason == "fragment_only"


class TestSanitizeUrls:
    def test_filters_and_returns_all_results(self) -> None:
        urls = [
            "https://docs.example.com/api/v1",
            "javascript:void(0)",
            "https://docs.example.com/api/v2",
            "",
            "https://example.com/logo.png",
        ]
        accepted, results = sanitize_urls(urls)
        assert len(accepted) == 2
        assert accepted[0] == "https://docs.example.com/api/v1"
        assert accepted[1] == "https://docs.example.com/api/v2"
        assert len(results) == 5
        assert results[0].accepted is True
        assert results[1].accepted is False
        assert results[2].accepted is True
        assert results[3].accepted is False
        assert results[4].accepted is False

    def test_empty_list(self) -> None:
        accepted, results = sanitize_urls([])
        assert accepted == []
        assert results == []
