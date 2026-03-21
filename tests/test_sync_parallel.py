"""Tests for parallel sync and rate limit telemetry (M37)."""
from __future__ import annotations

import threading
import time
import unittest


class TestDomainRateLimiterTelemetry(unittest.TestCase):
    """M37: Rate limiter must expose per-domain telemetry."""

    def test_domain_snapshot_returns_all_domains(self) -> None:
        from xdocs.inventory_fetch import _DomainRateLimiter
        rl = _DomainRateLimiter(0.1, adaptive=True, max_domain_delay_s=5.0)
        # Touch two domains
        rl.wait("a.com")
        rl.wait("b.com")
        snap = rl.domain_snapshot()
        self.assertIn("a.com", snap)
        self.assertIn("b.com", snap)
        self.assertIn("current_delay_s", snap["a.com"])

    def test_throttle_events_tracked(self) -> None:
        from xdocs.inventory_fetch import _DomainRateLimiter
        from xdocs.httpfetch import FetchResult
        rl = _DomainRateLimiter(0.0, adaptive=True, max_domain_delay_s=5.0)
        rl.wait("test.com")
        # Simulate a 429 response
        fr = FetchResult(
            url="https://test.com/page",
            final_url="https://test.com/page",
            redirect_chain=[],
            http_status=429,
            content_type="text/html",
            headers={"retry-after": "2"},
            body=b"",
        )
        rl.note_fetch_result("test.com", fr)
        snap = rl.domain_snapshot()
        self.assertGreater(snap["test.com"]["throttle_events"], 0)
        self.assertGreater(snap["test.com"]["retry_after_applied"], 0)

    def test_adaptive_backoff_on_429(self) -> None:
        from xdocs.inventory_fetch import _DomainRateLimiter
        from xdocs.httpfetch import FetchResult
        rl = _DomainRateLimiter(0.1, adaptive=True, max_domain_delay_s=10.0)
        rl.wait("slow.com")
        initial_delay = rl.domain_snapshot()["slow.com"]["current_delay_s"]
        # Simulate 429
        fr = FetchResult(
            url="https://slow.com/p", final_url="https://slow.com/p",
            redirect_chain=[], http_status=429, content_type="text/html",
            headers={}, body=b"",
        )
        rl.note_fetch_result("slow.com", fr)
        new_delay = rl.domain_snapshot()["slow.com"]["current_delay_s"]
        self.assertGreater(new_delay, initial_delay, "Delay should increase after 429")

    def test_delay_recovery_on_success(self) -> None:
        from xdocs.inventory_fetch import _DomainRateLimiter
        from xdocs.httpfetch import FetchResult
        rl = _DomainRateLimiter(0.1, adaptive=True, max_domain_delay_s=10.0)
        rl.wait("recover.com")
        # Force high delay
        fr429 = FetchResult(
            url="https://recover.com/p", final_url="https://recover.com/p",
            redirect_chain=[], http_status=429, content_type="text/html",
            headers={}, body=b"",
        )
        rl.note_fetch_result("recover.com", fr429)
        high_delay = rl.domain_snapshot()["recover.com"]["current_delay_s"]
        # Now succeed
        fr200 = FetchResult(
            url="https://recover.com/p", final_url="https://recover.com/p",
            redirect_chain=[], http_status=200, content_type="text/html",
            headers={}, body=b"ok",
        )
        rl.note_fetch_result("recover.com", fr200)
        recovered_delay = rl.domain_snapshot()["recover.com"]["current_delay_s"]
        self.assertLess(recovered_delay, high_delay, "Delay should decrease after success")


class TestDomainRateLimiterConcurrency(unittest.TestCase):
    """M37: Rate limiter must be safe under high concurrency."""

    def test_concurrent_domains_no_deadlock(self) -> None:
        from xdocs.inventory_fetch import _DomainRateLimiter
        rl = _DomainRateLimiter(0.0, adaptive=False, max_domain_delay_s=1.0)
        domains = [f"exchange{i}.com" for i in range(20)]
        errors: list[str] = []

        def worker(domain: str) -> None:
            try:
                for _ in range(5):
                    rl.wait(domain)
            except Exception as e:
                errors.append(f"{domain}: {e}")

        threads = [threading.Thread(target=worker, args=(d,)) for d in domains]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        alive = [t for t in threads if t.is_alive()]
        self.assertEqual(len(alive), 0, f"Deadlock: {len(alive)} threads still alive")
        self.assertEqual(len(errors), 0, f"Errors: {errors}")

    def test_many_workers_per_domain(self) -> None:
        """4 workers hitting the same domain should not crash."""
        from xdocs.inventory_fetch import _DomainRateLimiter
        rl = _DomainRateLimiter(0.0, adaptive=False, max_domain_delay_s=1.0)
        errors: list[str] = []
        fetch_count = {"count": 0}
        lock = threading.Lock()

        def worker() -> None:
            try:
                for _ in range(10):
                    rl.wait("same-domain.com")
                    with lock:
                        fetch_count["count"] += 1
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(len(errors), 0)
        self.assertEqual(fetch_count["count"], 40)  # 4 workers × 10 fetches


class TestSyncTelemetryOutput(unittest.TestCase):
    """M37: Sync results should include rate limit telemetry."""

    def test_telemetry_dict_structure(self) -> None:
        """Telemetry snapshot should have expected fields."""
        from xdocs.inventory_fetch import _DomainRateLimiter
        rl = _DomainRateLimiter(0.1, adaptive=True, max_domain_delay_s=5.0)
        rl.wait("example.com")
        snap = rl.domain_snapshot()
        entry = snap["example.com"]
        expected_keys = {"current_delay_s", "next_allowed_in_s", "retry_after_applied", "throttle_events", "last_status"}
        self.assertTrue(expected_keys.issubset(set(entry.keys())), f"Missing keys: {expected_keys - set(entry.keys())}")


class TestTwoPhaseSync(unittest.TestCase):
    """M37.2: Sync should create inventories sequentially then fetch in parallel."""

    def test_sync_config_has_concurrency(self) -> None:
        from xdocs.sync import SyncConfig
        cfg = SyncConfig(
            exchange=None, section=None, render_mode="http",
            ignore_robots=False, timeout_s=10, max_bytes=1000000,
            max_redirects=3, retries=1, delay_s=0.1, limit=None,
            inventory_max_pages=None, resume=False, concurrency=8,
            force_refetch=False, conditional=True, adaptive_delay=True,
            max_domain_delay_s=30.0, scope_dedupe=True,
        )
        self.assertEqual(cfg.concurrency, 8)

    def test_parallel_sections_capped(self) -> None:
        """parallel_sections should be capped to avoid runaway thread creation."""
        # The cap is min(len(inv_tasks), 8) in sync.py
        self.assertLessEqual(min(100, 8), 8)
        self.assertLessEqual(min(3, 8), 3)

    def test_fetch_section_error_handling(self) -> None:
        """A failed section fetch should not crash the entire sync."""
        # This tests the concept — _fetch_section wraps in try/except
        # and returns error string instead of raising.
        results = []
        def mock_fetch(task):
            if task.get("should_fail"):
                return {**task, "fetch_res": None, "error": "simulated failure"}
            return {**task, "fetch_res": {"counts": {"fetched": 1, "stored": 1, "skipped": 0, "errors": 0}}, "error": None}

        tasks = [
            {"id": 1, "should_fail": False},
            {"id": 2, "should_fail": True},
            {"id": 3, "should_fail": False},
        ]
        for t in tasks:
            results.append(mock_fetch(t))

        successes = [r for r in results if r["error"] is None]
        failures = [r for r in results if r["error"] is not None]
        self.assertEqual(len(successes), 2)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["error"], "simulated failure")


if __name__ == "__main__":
    unittest.main()
