"""Comprehensive store audit runner.

Orchestrates all validation checks in sequence and produces a consolidated report.
All checks are read-only (detection, not repair).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import require_store_db
from .timeutil import now_iso_utc

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str  # pass | warn | fail | skip | error
    elapsed_s: float
    summary: dict[str, Any]
    issues_count: int = 0
    error_message: str | None = None


def _run_check(name: str, fn: Any) -> CheckResult:
    """Run a check function, catching exceptions."""
    t0 = time.monotonic()
    try:
        return fn()
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.exception("Check %s failed with error", name)
        return CheckResult(
            name=name,
            status="error",
            elapsed_s=elapsed,
            summary={},
            error_message=f"{type(e).__name__}: {e}",
        )


def _check_fsck(*, docs_dir: str, limit: int) -> CheckResult:
    from .fsck import fsck_store

    t0 = time.monotonic()
    r = fsck_store(
        docs_dir=docs_dir,
        limit=limit,
        scan_orphans=True,
        verify_hashes=True,
        verify_fts=True,
        verify_endpoint_json=True,
    )
    elapsed = time.monotonic() - t0
    issue_count = r["counts"]["issues"]
    status = "pass" if issue_count == 0 else "fail"
    return CheckResult(
        name="fsck",
        status=status,
        elapsed_s=elapsed,
        issues_count=issue_count,
        summary=r["counts"],
    )


def _check_quality(*, docs_dir: str) -> CheckResult:
    from .quality import quality_check

    t0 = time.monotonic()
    r = quality_check(docs_dir=docs_dir)
    elapsed = time.monotonic() - t0
    issue_count = len(r["issues"])
    status = "pass" if r["counts"]["empty"] == 0 else "warn"
    return CheckResult(
        name="quality-check",
        status=status,
        elapsed_s=elapsed,
        issues_count=issue_count,
        summary=r["counts"],
    )


def _check_stale_citations(*, docs_dir: str, lock_timeout_s: float) -> CheckResult:
    from .stale_citations import detect_stale_citations

    t0 = time.monotonic()
    r = detect_stale_citations(
        docs_dir=docs_dir,
        lock_timeout_s=lock_timeout_s,
        dry_run=True,
    )
    elapsed = time.monotonic() - t0
    total = r["counts"]["total_findings"]
    status = "pass" if total == 0 else "fail"
    return CheckResult(
        name="stale-citations",
        status=status,
        elapsed_s=elapsed,
        issues_count=total,
        summary=r["counts"],
    )


def _check_coverage(*, docs_dir: str) -> CheckResult:
    from .coverage import endpoint_coverage

    t0 = time.monotonic()
    r = endpoint_coverage(docs_dir=docs_dir)
    elapsed = time.monotonic() - t0
    by_field = r.get("by_field", {})
    fields_with_gaps = sum(
        1 for counts in by_field.values()
        if counts.get("unknown", 0) + counts.get("undocumented", 0) > 0
    )
    total_endpoints = r.get("totals", {}).get("endpoints", 0)
    status = "pass" if fields_with_gaps == 0 else "warn"
    return CheckResult(
        name="coverage",
        status=status,
        elapsed_s=elapsed,
        issues_count=fields_with_gaps,
        summary={"total_endpoints": total_endpoints, "fields_with_gaps": fields_with_gaps},
    )


def _check_registry() -> CheckResult:
    from .registry_validate import validate_registry

    t0 = time.monotonic()
    repo_root = Path(__file__).resolve().parents[2]
    r = validate_registry(
        registry_path=repo_root / "data" / "exchanges.yaml",
        timeout_s=10.0,
        max_bytes=100_000,
        max_redirects=5,
        retries=2,
        render_mode="http",
    )
    elapsed = time.monotonic() - t0
    results = r.get("results", [])
    failures = sum(1 for rec in results if not rec.get("ok", False))
    status = "pass" if failures == 0 else "warn"
    return CheckResult(
        name="validate-registry",
        status=status,
        elapsed_s=elapsed,
        issues_count=failures,
        summary={"total_seeds": len(results), "failures": failures},
    )


def _check_base_urls() -> CheckResult:
    from .base_urls_validate import validate_base_urls

    t0 = time.monotonic()
    repo_root = Path(__file__).resolve().parents[2]
    r = validate_base_urls(
        registry_path=repo_root / "data" / "exchanges.yaml",
        timeout_s=10.0,
        retries=2,
    )
    elapsed = time.monotonic() - t0
    results = r.get("results", [])
    failures = sum(1 for rec in results if not rec.get("ok", False))
    status = "pass" if failures == 0 else "warn"
    return CheckResult(
        name="validate-base-urls",
        status=status,
        elapsed_s=elapsed,
        issues_count=failures,
        summary={"total_urls": len(results), "failures": failures},
    )


def _check_ccxt_xref(*, docs_dir: str) -> CheckResult:
    from .ccxt_xref import ccxt_cross_reference

    t0 = time.monotonic()
    r = ccxt_cross_reference(docs_dir=docs_dir)
    elapsed = time.monotonic() - t0
    summary = r.get("summary", {})
    status = "pass"  # Cross-reference is informational; always pass
    return CheckResult(
        name="ccxt-xref",
        status=status,
        elapsed_s=elapsed,
        issues_count=0,
        summary=summary,
    )


def _check_retrieval(*, docs_dir: str, qa_file: str) -> CheckResult:
    from .validate import validate_retrieval

    t0 = time.monotonic()
    vr = validate_retrieval(docs_dir=docs_dir, qa_path=qa_file)
    elapsed = time.monotonic() - t0
    status = "pass" if vr.hit_rate >= 0.8 else ("warn" if vr.hit_rate >= 0.5 else "fail")
    return CheckResult(
        name="validate-retrieval",
        status=status,
        elapsed_s=elapsed,
        issues_count=sum(1 for q in vr.per_query if not q.hit),
        summary={
            "total_queries": vr.total_queries,
            "hit_rate": round(vr.hit_rate, 4),
            "mean_recall": round(vr.mean_recall, 4),
            "k": vr.k,
        },
    )


def _check_url_sanitize(*, docs_dir: str) -> CheckResult:
    """Scan inventory_entries for URLs that fail sanitization."""
    from .url_sanitize import sanitize_url
    from .db import open_db

    t0 = time.monotonic()
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        rows = conn.execute(
            "SELECT canonical_url FROM inventory_entries ORDER BY canonical_url;"
        ).fetchall()
        bad_urls: list[dict[str, str]] = []
        for row in rows:
            url = str(row["canonical_url"])
            result = sanitize_url(url)
            if not result.accepted:
                bad_urls.append({"url": url, "reason": result.reason or "rejected"})
        elapsed = time.monotonic() - t0
        status = "pass" if len(bad_urls) == 0 else "warn"
        return CheckResult(
            name="url-sanitize",
            status=status,
            elapsed_s=elapsed,
            issues_count=len(bad_urls),
            summary={"total_urls": len(rows), "bad_urls": len(bad_urls)},
        )
    finally:
        conn.close()


def _check_extraction_quality(*, docs_dir: str, limit: int) -> CheckResult:
    """Verify structural extraction quality across stored pages."""
    from .extraction_verify import verify_extraction
    from .db import open_db

    t0 = time.monotonic()
    db_path = require_store_db(docs_dir)
    docs_root = Path(docs_dir)
    conn = open_db(db_path)
    try:
        rows = conn.execute(
            "SELECT canonical_url, raw_path, markdown_path FROM pages "
            "ORDER BY canonical_url LIMIT ?;",
            (limit,),
        ).fetchall()
        warnings_count = 0
        incomplete_count = 0
        checked = 0
        for row in rows:
            raw_path = row["raw_path"]
            md_path = row["markdown_path"]
            if not raw_path or not md_path:
                continue
            raw_file = docs_root / raw_path
            md_file = docs_root / md_path
            if not raw_file.exists() or not md_file.exists():
                continue
            try:
                html = raw_file.read_text(encoding="utf-8", errors="replace")
                md = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            eq = verify_extraction(html, md)
            checked += 1
            if eq.quality_score < 0.40:
                incomplete_count += 1
            elif eq.quality_score < 0.70:
                warnings_count += 1
        elapsed = time.monotonic() - t0
        status = "pass" if incomplete_count == 0 else ("warn" if incomplete_count < 5 else "fail")
        return CheckResult(
            name="extraction-quality",
            status=status,
            elapsed_s=elapsed,
            issues_count=incomplete_count + warnings_count,
            summary={
                "checked": checked,
                "incomplete": incomplete_count,
                "warnings": warnings_count,
            },
        )
    finally:
        conn.close()


def _check_sitemap_health(*, exchange: str | None) -> CheckResult:
    """Validate all configured sitemaps alive, not stale, cross-ref vs store."""
    from .sitemap_validate import validate_sitemaps
    from .registry import load_registry

    t0 = time.monotonic()
    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "data" / "exchanges.yaml"
    registry = load_registry(registry_path)

    total_sitemaps = 0
    unreachable = 0
    stale = 0
    all_warnings: list[str] = []

    for ex in registry.exchanges:
        if exchange and ex.exchange_id != exchange:
            continue
        for sec in ex.sections:
            try:
                result = validate_sitemaps(
                    exchange_id=ex.exchange_id,
                    section_id=sec.section_id,
                    registry_path=registry_path,
                    timeout_s=15.0,
                )
            except Exception as e:
                all_warnings.append(f"{ex.exchange_id}/{sec.section_id}: {e}")
                continue
            for sm in result.sitemaps:
                total_sitemaps += 1
                if not sm.reachable:
                    unreachable += 1
                if sm.stale_entry_count > 0:
                    stale += 1
            all_warnings.extend(result.warnings)

    elapsed = time.monotonic() - t0
    issues = unreachable + stale
    status = "pass" if issues == 0 else "warn"
    return CheckResult(
        name="sitemap-health",
        status=status,
        elapsed_s=elapsed,
        issues_count=issues,
        summary={
            "total_sitemaps": total_sitemaps,
            "unreachable": unreachable,
            "stale": stale,
            "warnings": len(all_warnings),
        },
    )


def _check_link_reachability(*, docs_dir: str, exchange: str | None) -> CheckResult:
    """Spot-check stored page URLs for reachability."""
    from .link_check import check_stored_links

    t0 = time.monotonic()
    report = check_stored_links(
        docs_dir=docs_dir,
        exchange=exchange,
        sample=200,
        timeout_s=10.0,
        concurrency=4,
        delay_s=0.5,
    )
    elapsed = time.monotonic() - t0
    error_count = report.client_error + report.server_error + report.network_error
    if report.checked == 0:
        error_rate = 0.0
    else:
        error_rate = error_count / report.checked
    if error_rate == 0.0:
        status = "pass"
    elif error_rate < 0.05:
        status = "warn"
    else:
        status = "fail"
    return CheckResult(
        name="link-reachability",
        status=status,
        elapsed_s=elapsed,
        issues_count=error_count,
        summary={
            "checked": report.checked,
            "ok": report.ok,
            "redirect": report.redirect,
            "client_error": report.client_error,
            "server_error": report.server_error,
            "network_error": report.network_error,
            "error_rate_pct": round(error_rate * 100, 1),
        },
    )


def _check_crawl_coverage(
    *,
    docs_dir: str,
    exchange: str | None,
    enable_nav: bool = False,
    enable_wayback: bool = False,
) -> CheckResult:
    """Multi-method discovery vs store comparison."""
    from .crawl_coverage import audit_crawl_coverage

    t0 = time.monotonic()
    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "data" / "exchanges.yaml"
    r = audit_crawl_coverage(
        docs_dir=docs_dir,
        registry_path=registry_path,
        exchange_id=exchange,
        enable_nav=enable_nav,
        enable_wayback=enable_wayback,
    )
    elapsed = time.monotonic() - t0
    status = "pass" if r.total_missing == 0 else ("warn" if r.overall_coverage_pct >= 90.0 else "fail")
    return CheckResult(
        name="crawl-coverage",
        status=status,
        elapsed_s=elapsed,
        issues_count=r.total_missing,
        summary={
            "overall_coverage_pct": round(r.overall_coverage_pct, 1),
            "total_missing": r.total_missing,
            "total_stale": r.total_stale,
            "sections_checked": len(r.sections),
        },
    )


def _check_live_validation(*, docs_dir: str, exchange: str | None) -> CheckResult:
    """Full JS-rendered nav extraction + comparison."""
    from .live_validate import validate_live_site
    from .registry import load_registry

    t0 = time.monotonic()
    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "data" / "exchanges.yaml"
    registry = load_registry(registry_path)

    total_missing = 0
    total_stale = 0
    sections_checked = 0
    coverage_pcts: list[float] = []

    for ex in registry.exchanges:
        if exchange and ex.exchange_id != exchange:
            continue
        for sec in ex.sections:
            try:
                result = validate_live_site(
                    exchange_id=ex.exchange_id,
                    section_id=sec.section_id,
                    registry_path=registry_path,
                    docs_dir=docs_dir,
                )
            except Exception as e:
                logger.warning(
                    "Live validation failed for %s/%s: %s",
                    ex.exchange_id, sec.section_id, e,
                )
                continue
            sections_checked += 1
            total_missing += len(result.missing_from_store)
            total_stale += len(result.missing_from_live)
            coverage_pcts.append(result.coverage_pct)

    elapsed = time.monotonic() - t0
    avg_coverage = sum(coverage_pcts) / max(len(coverage_pcts), 1)
    status = "pass" if total_missing == 0 else ("warn" if avg_coverage >= 90.0 else "fail")
    return CheckResult(
        name="live-site-validation",
        status=status,
        elapsed_s=elapsed,
        issues_count=total_missing,
        summary={
            "sections_checked": sections_checked,
            "total_missing": total_missing,
            "total_stale": total_stale,
            "avg_coverage_pct": round(avg_coverage, 1),
        },
    )


def run_audit(
    *,
    docs_dir: str,
    lock_timeout_s: float = 10.0,
    include_network: bool = False,
    include_ccxt: bool = False,
    include_semantic: bool = False,
    include_crawl_coverage: bool = False,
    include_live_validation: bool = False,
    exchange: str | None = None,
    qa_file: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Run all validation checks and return a consolidated report."""

    # Verify store exists before running checks.
    require_store_db(docs_dir)

    started_at = now_iso_utc()
    checks: list[CheckResult] = []

    # Always-run checks (fast, no network).
    checks.append(_run_check("fsck", lambda: _check_fsck(docs_dir=docs_dir, limit=limit)))
    checks.append(_run_check("quality-check", lambda: _check_quality(docs_dir=docs_dir)))
    checks.append(_run_check("stale-citations", lambda: _check_stale_citations(
        docs_dir=docs_dir, lock_timeout_s=lock_timeout_s,
    )))
    checks.append(_run_check("coverage", lambda: _check_coverage(docs_dir=docs_dir)))
    checks.append(_run_check("url-sanitize", lambda: _check_url_sanitize(docs_dir=docs_dir)))
    checks.append(_run_check("extraction-quality", lambda: _check_extraction_quality(
        docs_dir=docs_dir, limit=limit,
    )))

    # Network checks (opt-in).
    if include_network:
        checks.append(_run_check("validate-registry", _check_registry))
        checks.append(_run_check("validate-base-urls", _check_base_urls))
        checks.append(_run_check("sitemap-health", lambda: _check_sitemap_health(
            exchange=exchange,
        )))
        checks.append(_run_check("link-reachability", lambda: _check_link_reachability(
            docs_dir=docs_dir, exchange=exchange,
        )))
    else:
        checks.append(CheckResult(
            name="validate-registry", status="skip", elapsed_s=0.0,
            summary={"reason": "Network checks disabled (use --include-network)"},
        ))
        checks.append(CheckResult(
            name="validate-base-urls", status="skip", elapsed_s=0.0,
            summary={"reason": "Network checks disabled (use --include-network)"},
        ))
        checks.append(CheckResult(
            name="sitemap-health", status="skip", elapsed_s=0.0,
            summary={"reason": "Network checks disabled (use --include-network)"},
        ))
        checks.append(CheckResult(
            name="link-reachability", status="skip", elapsed_s=0.0,
            summary={"reason": "Network checks disabled (use --include-network)"},
        ))

    if include_ccxt:
        checks.append(_run_check("ccxt-xref", lambda: _check_ccxt_xref(docs_dir=docs_dir)))
    else:
        checks.append(CheckResult(
            name="ccxt-xref", status="skip", elapsed_s=0.0,
            summary={"reason": "CCXT check disabled (use --include-ccxt)"},
        ))

    if include_semantic and qa_file:
        checks.append(_run_check("validate-retrieval", lambda: _check_retrieval(
            docs_dir=docs_dir, qa_file=qa_file,
        )))
    else:
        checks.append(CheckResult(
            name="validate-retrieval", status="skip", elapsed_s=0.0,
            summary={"reason": "Semantic check disabled or no --qa-file"},
        ))

    # Crawl coverage (opt-in, medium cost).
    if include_crawl_coverage:
        checks.append(_run_check("crawl-coverage", lambda: _check_crawl_coverage(
            docs_dir=docs_dir, exchange=exchange,
        )))
    else:
        checks.append(CheckResult(
            name="crawl-coverage", status="skip", elapsed_s=0.0,
            summary={"reason": "Crawl coverage disabled (use --include-crawl-coverage)"},
        ))

    # Live site validation (opt-in, expensive).
    if include_live_validation:
        checks.append(_run_check("live-site-validation", lambda: _check_live_validation(
            docs_dir=docs_dir, exchange=exchange,
        )))
    else:
        checks.append(CheckResult(
            name="live-site-validation", status="skip", elapsed_s=0.0,
            summary={"reason": "Live validation disabled (use --include-live-validation)"},
        ))

    ended_at = now_iso_utc()
    total_elapsed = sum(c.elapsed_s for c in checks)

    # Overall status: worst non-skip status wins.
    statuses = [c.status for c in checks if c.status != "skip"]
    if any(s == "error" for s in statuses):
        overall = "error"
    elif any(s == "fail" for s in statuses):
        overall = "fail"
    elif any(s == "warn" for s in statuses):
        overall = "warn"
    else:
        overall = "pass"

    return {
        "cmd": "audit",
        "started_at": started_at,
        "ended_at": ended_at,
        "total_elapsed_s": round(total_elapsed, 2),
        "overall_status": overall,
        "summary": {
            "total_checks": len(checks),
            "pass": sum(1 for c in checks if c.status == "pass"),
            "warn": sum(1 for c in checks if c.status == "warn"),
            "fail": sum(1 for c in checks if c.status == "fail"),
            "skip": sum(1 for c in checks if c.status == "skip"),
            "error": sum(1 for c in checks if c.status == "error"),
        },
        "checks": [
            {
                "name": c.name,
                "status": c.status,
                "elapsed_s": round(c.elapsed_s, 2),
                "issues_count": c.issues_count,
                **({"error": c.error_message} if c.error_message else {}),
                "summary": c.summary,
            }
            for c in checks
        ],
    }
