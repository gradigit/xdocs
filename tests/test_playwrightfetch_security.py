from __future__ import annotations

import unittest

from cex_api_docs.playwrightfetch import _is_localhostish, _is_public_ip_literal, _resolves_to_non_public_ip


class TestPlaywrightFetchSecurity(unittest.TestCase):
    def test_localhostish_detection(self) -> None:
        self.assertTrue(_is_localhostish("localhost"))
        self.assertTrue(_is_localhostish("a.localhost"))
        self.assertFalse(_is_localhostish("example.com"))

    def test_public_ip_literal_detection(self) -> None:
        self.assertFalse(_is_public_ip_literal("127.0.0.1"))
        self.assertFalse(_is_public_ip_literal("10.0.0.1"))
        self.assertTrue(_is_public_ip_literal("8.8.8.8"))
        self.assertFalse(_is_public_ip_literal("::1"))

    def test_resolves_to_non_public_ip_localhost(self) -> None:
        # Deterministic: localhost should resolve to loopback (non-global).
        self.assertTrue(_resolves_to_non_public_ip("localhost"))


if __name__ == "__main__":
    unittest.main()

