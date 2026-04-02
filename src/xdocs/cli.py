from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import signal
import sys
from typing import Any

from .errors import XDocsError
from .answer import answer_question
from .base_urls_validate import validate_base_urls
from .crawler import crawl_store
from .coverage import endpoint_coverage
from .coverage_gaps import compute_and_persist_coverage_gaps, list_coverage_gaps
from .discover_sources import discover_sources
from .ccxt_xref import ccxt_cross_reference
from .classify import classify_input
from .endpoints import get_endpoint, list_endpoints, review_list, review_resolve, review_show, save_endpoint, search_endpoints
from .lookup import lookup_endpoint_by_path, search_error_code
from .ingest_page import ingest_page
from .inventory import create_inventory, latest_inventory_id
from .inventory_fetch import fetch_inventory
from .stale_citations import detect_stale_citations
from .asyncapi_import import import_asyncapi
from .openapi_import import import_openapi
from .postman_import import import_postman
from .fsck import fsck_store
from .pages import diff_pages, fts_optimize, fts_rebuild, get_page, search_pages
from .changelog import extract_changelogs, list_changelogs
from .quality import quality_check
from .report import render_sync_markdown, store_report, render_store_report_markdown
from .registry import load_registry
from .registry_validate import validate_registry
from .sync import run_sync
from .store import init_store, migrate_store_schema


def _print_json(obj: object) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if not it:
            continue
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def main(argv: list[str] | None = None) -> None:
    # Exit quietly on broken pipe (e.g., output piped to head).
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    common = argparse.ArgumentParser(add_help=False)
    _default_docs = os.environ.get("CEX_DOCS_DIR") or str(Path(__file__).resolve().parents[2] / "cex-docs")
    common.add_argument("--docs-dir", default=_default_docs, help="Store root (env: CEX_DOCS_DIR, default: <repo>/cex-docs)")
    common.add_argument(
        "--lock-timeout-s",
        default=10.0,
        type=float,
        help="Seconds to wait for exclusive write lock (default: 10)",
    )

    _version = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    parser = argparse.ArgumentParser(prog="xdocs", parents=[common])
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version}")

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Initialize store dirs + SQLite schema (idempotent)", parents=[common])
    ms = sub.add_parser("migrate-schema", help="Check/apply store DB schema migrations", parents=[common])
    ms.add_argument(
        "--apply",
        action="store_true",
        help="Apply pending migrations (default: dry-run status only).",
    )

    crawl_p = sub.add_parser("crawl", help="(DEPRECATED) Crawl docs and store pages + metadata", parents=[common])
    crawl_p.add_argument("--exchange", help="Exchange id from data/exchanges.yaml (recommended)")
    crawl_p.add_argument("--section", help="Section id under the exchange (optional; default: all sections)")
    crawl_p.add_argument("--url", action="append", default=[], help="Seed URL (repeatable)")
    crawl_p.add_argument("--domain-scope", action="append", default=[], help="Allowed domain host (repeatable)")
    crawl_p.add_argument("--max-depth", type=int, default=2)
    crawl_p.add_argument("--max-pages", type=int, default=200)
    crawl_p.add_argument("--delay-s", type=float, default=1.0)
    crawl_p.add_argument("--timeout-s", type=float, default=20.0)
    crawl_p.add_argument("--max-bytes", type=int, default=10_000_000)
    crawl_p.add_argument("--max-redirects", type=int, default=5)
    crawl_p.add_argument("--retries", type=int, default=2)
    crawl_p.add_argument("--ignore-robots", action="store_true")
    crawl_p.add_argument("--render", default="http", choices=["http", "playwright", "auto"])

    sp = sub.add_parser("search-pages", help="Full-text search crawled pages", parents=[common])
    sp.add_argument("query")
    sp.add_argument("--exchange", default=None, help="Filter by exchange (uses domain from registry)")
    sp.add_argument("--limit", type=int, default=10)

    gp = sub.add_parser("get-page", help="Get stored page (meta + markdown)", parents=[common])
    gp.add_argument("url", help="Page URL (will be canonicalized)")

    dp = sub.add_parser("diff", help="Report new/updated/stale pages for a crawl run", parents=[common])
    dp.add_argument("--crawl-run-id", type=int, default=None)
    dp.add_argument("--limit", type=int, default=50)

    ds = sub.add_parser("discover-sources", help="Discover sitemap/spec URLs from registry seed pages (best-effort)", parents=[common])
    ds.add_argument("--exchange", required=True)
    ds.add_argument("--section", default=None, help="Section id under the exchange (default: all sections)")
    ds.add_argument("--timeout-s", type=float, default=20.0)
    ds.add_argument("--max-bytes", type=int, default=10_000_000)
    ds.add_argument("--max-redirects", type=int, default=5)
    ds.add_argument("--retries", type=int, default=1)

    inv_p = sub.add_parser("inventory", help="Deterministically enumerate doc URLs for an exchange section", parents=[common])
    inv_p.add_argument("--exchange", required=True, help="Exchange id from data/exchanges.yaml")
    inv_p.add_argument("--section", required=True, help="Section id under the exchange")
    inv_p.add_argument("--timeout-s", type=float, default=20.0)
    inv_p.add_argument("--max-bytes", type=int, default=50_000_000)
    inv_p.add_argument("--max-redirects", type=int, default=5)
    inv_p.add_argument("--retries", type=int, default=1)
    inv_p.add_argument("--ignore-robots", action="store_true")
    inv_p.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Clamp link-follow inventory generation to at most N pages (debugging)",
    )
    inv_p.add_argument("--include-urls", action="store_true", help="Include full URL list in output (can be large)")
    inv_p.add_argument("--sample-limit", type=int, default=20)

    fi_p = sub.add_parser("fetch-inventory", help="Fetch every URL from an inventory into the store", parents=[common])
    fi_p.add_argument("--exchange", required=True, help="Exchange id from data/exchanges.yaml")
    fi_p.add_argument("--section", required=True, help="Section id under the exchange")
    fi_p.add_argument("--inventory-id", type=int, default=None, help="Inventory id (default: latest for exchange/section)")
    fi_p.add_argument("--limit", type=int, default=None, help="Fetch only the first N entries (debugging)")
    fi_p.add_argument("--delay-s", type=float, default=0.25)
    fi_p.add_argument("--timeout-s", type=float, default=20.0)
    fi_p.add_argument("--max-bytes", type=int, default=10_000_000)
    fi_p.add_argument("--max-redirects", type=int, default=5)
    fi_p.add_argument("--retries", type=int, default=2)
    fi_p.add_argument("--ignore-robots", action="store_true")
    fi_p.add_argument("--render", default="auto", choices=["http", "playwright", "auto"])
    fi_p.add_argument(
        "--resume",
        action="store_true",
        help="Fetch only non-fetched entries (pending/error; includes skipped when --ignore-robots is set).",
    )
    fi_p.add_argument(
        "--force-refetch",
        action="store_true",
        help="Re-download all pages to detect content changes. Reports new/updated/unchanged counts.",
    )
    fi_p.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Number of concurrent HTTP fetch workers (default: 8; per-domain rate limiting is independent)",
    )
    fi_p.add_argument(
        "--conditional",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use conditional revalidation headers (If-None-Match / If-Modified-Since) when available (default: true).",
    )
    fi_p.add_argument(
        "--adaptive-delay",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Adapt per-domain delay using Retry-After/HTTP status feedback (default: true).",
    )
    fi_p.add_argument(
        "--max-domain-delay",
        type=float,
        default=30.0,
        help="Upper bound (seconds) for adaptive per-domain delay (default: 30).",
    )
    fi_p.add_argument(
        "--scope-dedupe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable cross-section scope ownership dedupe (default: true).",
    )

    ip = sub.add_parser("ingest-page", help="Ingest a browser-captured page into the store (HTML or markdown)", parents=[common])
    ip.add_argument("--url", required=True)
    group = ip.add_mutually_exclusive_group(required=True)
    group.add_argument("--html-path", default=None)
    group.add_argument("--markdown-path", default=None)
    ip.add_argument("--tool", default=None, help="Capture tool (agent-browser|playwright|manual|other)")
    ip.add_argument("--notes", default=None)

    sync_p = sub.add_parser("sync", help="Inventory + fetch orchestration (cron-friendly JSON output)", parents=[common])
    sync_p.add_argument("--exchange", default=None)
    sync_p.add_argument("--section", default=None)
    sync_p.add_argument("--limit", type=int, default=None, help="Limit fetched URLs per section (debugging)")
    sync_p.add_argument(
        "--inventory-max-pages",
        type=int,
        default=None,
        help="Clamp link-follow inventory generation to at most N pages per section (debugging)",
    )
    sync_p.add_argument("--delay-s", type=float, default=0.25)
    sync_p.add_argument("--timeout-s", type=float, default=20.0)
    sync_p.add_argument("--max-bytes", type=int, default=10_000_000)
    sync_p.add_argument("--max-redirects", type=int, default=5)
    sync_p.add_argument("--retries", type=int, default=2)
    sync_p.add_argument("--ignore-robots", action="store_true")
    sync_p.add_argument("--render", default="auto", choices=["http", "playwright", "auto"])
    sync_p.add_argument(
        "--resume",
        action="store_true",
        help="Reuse existing inventories and fetch only non-fetched entries (pending/error).",
    )
    sync_p.add_argument(
        "--force-refetch",
        action="store_true",
        help="Re-download all pages to detect content changes. Reuses existing inventories. Reports new/updated/unchanged counts.",
    )
    sync_p.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Number of concurrent HTTP fetch workers (default: 8; per-domain rate limiting is independent)",
    )
    sync_p.add_argument(
        "--conditional",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use conditional revalidation headers when available (default: true).",
    )
    sync_p.add_argument(
        "--adaptive-delay",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Adapt per-domain delay using Retry-After/HTTP status feedback (default: true).",
    )
    sync_p.add_argument(
        "--max-domain-delay",
        type=float,
        default=30.0,
        help="Upper bound (seconds) for adaptive per-domain delay (default: 30).",
    )
    sync_p.add_argument(
        "--scope-dedupe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable cross-section scope ownership dedupe (default: true).",
    )

    rep_p = sub.add_parser("report", help="Render a sync JSON artifact into Markdown", parents=[common])
    rep_p.add_argument("--input", default="-", help="Path to sync JSON file, or '-' for stdin (default: -)")
    rep_p.add_argument("--output", default="-", help="Path to write Markdown, or '-' for stdout (default: -)")
    rep_p.add_argument("--max-errors", type=int, default=50)

    sr_p = sub.add_parser("store-report", help="Report on current store contents", parents=[common])
    sr_p.add_argument("--exchange", default=None, help="Filter by exchange id")
    sr_p.add_argument("--section", default=None, help="Filter by section id")
    sr_p.add_argument("--output", default="-", help="Path to write Markdown, or '-' for stdout (default: -)")

    sub.add_parser("fts-optimize", help="Optimize SQLite FTS indexes", parents=[common])
    sub.add_parser("fts-rebuild", help="Rebuild SQLite FTS indexes from stored markdown", parents=[common])

    vr = sub.add_parser("validate-registry", help="Validate data/exchanges.yaml seeds and allowlists (networked)", parents=[common])
    vr.add_argument("--exchange", default=None, help="Exchange id to validate (default: all)")
    vr.add_argument("--section", default=None, help="Section id to validate (default: all)")
    vr.add_argument("--timeout-s", type=float, default=20.0)
    vr.add_argument("--max-bytes", type=int, default=10_000_000)
    vr.add_argument("--max-redirects", type=int, default=5)
    vr.add_argument("--retries", type=int, default=1)
    vr.add_argument("--render", default="http", choices=["http", "playwright", "auto"])

    vbu = sub.add_parser(
        "validate-base-urls",
        help="Validate registry base_urls are reachable (networked; unauthenticated only)",
        parents=[common],
    )
    vbu.add_argument("--exchange", default=None, help="Exchange id to validate (default: all)")
    vbu.add_argument("--section", default=None, help="Section id to validate (default: all)")
    vbu.add_argument("--timeout-s", type=float, default=10.0)
    vbu.add_argument("--retries", type=int, default=1)

    ks_p = sub.add_parser("known-sources", help="List known source URLs for an exchange from the registry (no network)", parents=[common])
    ks_p.add_argument("--exchange", required=True, help="Exchange id from data/exchanges.yaml")
    ks_p.add_argument("--source-type", default=None, help="Filter to a specific source type (e.g., llms_txt, github_org)")

    vks = sub.add_parser("validate-known-sources", help="Probe known_sources URLs with content-aware validation (networked)", parents=[common])
    vks.add_argument("--exchange", default=None, help="Exchange id to validate (default: all)")
    vks.add_argument("--timeout-s", type=float, default=15.0)

    sub.add_parser("quality-check", help="Check stored pages for empty/thin content or tiny HTML (JS rendering failures)", parents=[common])

    ec = sub.add_parser("extract-changelogs", help="Extract dated changelog entries from stored changelog pages into changelog_entries table", parents=[common])
    ec.add_argument("--exchange", default=None, help="Limit to pages matching this exchange")
    ec.add_argument("--limit-pages", type=int, default=0, help="Process at most N pages (0=all)")
    ec.add_argument("--dry-run", action="store_true", help="Parse but do not write to DB")

    lc = sub.add_parser("list-changelogs", help="List extracted changelog entries from changelog_entries table", parents=[common])
    lc.add_argument("--exchange", default=None, help="Filter by exchange_id")
    lc.add_argument("--section", default=None, help="Filter by section_id")
    lc.add_argument("--since", default=None, help="Only entries >= this ISO date (YYYY-MM-DD)")
    lc.add_argument("--limit", type=int, default=50, help="Max entries to return (default: 50)")

    ca = sub.add_parser("classify-changelogs", help="Classify changelog entries by impact type (breaking, deprecated, new, etc.)", parents=[common])
    ca.add_argument("--exchange", default=None, help="Filter by exchange_id")
    ca.add_argument("--since", default=None, help="Only entries >= this ISO date (YYYY-MM-DD)")
    ca.add_argument("--severity", default=None, help="Filter by severity: err, warn, info")
    ca.add_argument("--limit", type=int, default=100, help="Max entries to classify (default: 100)")

    bi = sub.add_parser("build-index", help="Build LanceDB semantic search index from stored pages (requires [semantic])", parents=[common])
    bi.add_argument("--limit", type=int, default=0, help="Max pages to embed (0=all)")
    bi.add_argument("--exchange", default=None, help="Filter by exchange domain pattern")
    bi.add_argument("--batch-size", type=int, default=64, help="Embedding batch size (default: 64)")
    bi.add_argument("--incremental", action="store_true", help="Only embed new/changed pages (skip unchanged)")

    ci = sub.add_parser("compact-index", help="Compact LanceDB index: merge fragments + cleanup old versions (requires [semantic])", parents=[common])
    ci.add_argument("--max-bytes-per-file", type=int, default=None, help="Max bytes per .lance data file (e.g. 1900000000 for GitHub LFS)")

    ss = sub.add_parser("semantic-search", help="Semantic search via LanceDB vector index (requires [semantic])", parents=[common])
    ss.add_argument("query", help="Natural language search query")
    ss.add_argument("--exchange", default=None, help="Filter by exchange")
    ss.add_argument("--limit", type=int, default=10)
    ss.add_argument("--mode", default="hybrid", choices=["vector", "fts", "hybrid"], help="Search mode (default: hybrid)")
    ss.add_argument(
        "--rerank-policy",
        default="auto",
        choices=["auto", "always", "never"],
        help="Rerank policy: auto (confidence-triggered), always, or never (default: auto)",
    )
    ss.add_argument(
        "--rerank",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Explicitly force rerank on/off (overrides --rerank-policy)",
    )

    vr_p = sub.add_parser("validate-retrieval", help="Run golden QA validation against semantic search index (requires [semantic])", parents=[common])
    vr_p.add_argument("--qa-file", required=True, help="Path to JSONL file with golden QA pairs")
    vr_p.add_argument("--limit", type=int, default=5, help="Top-K results to check (default: 5)")
    vr_p.add_argument(
        "--rerank",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable reranking during validation (default: enabled)",
    )

    fsck_p = sub.add_parser("fsck", help="Detect store DB/file inconsistencies (detection-only by default)", parents=[common])
    fsck_p.add_argument("--limit", type=int, default=200)
    fsck_p.add_argument("--scan-orphans", action="store_true", help="Scan raw/pages/meta directories for orphan files (can be slow)")
    fsck_p.add_argument("--verify-hashes", action="store_true", help="Re-compute SHA256 of markdown files and compare to DB content_hash")
    fsck_p.add_argument("--verify-fts", action="store_true", help="Check FTS5 row counts and orphan/missing entries")
    fsck_p.add_argument("--verify-endpoint-json", action="store_true", help="Compare on-disk endpoint JSON to DB json column")

    audit_p = sub.add_parser("audit", help="Run all validation checks and produce consolidated report", parents=[common])
    audit_p.add_argument("--include-network", action="store_true", help="Include network checks (validate-registry, validate-base-urls, sitemap-health)")
    audit_p.add_argument("--include-ccxt", action="store_true", help="Include CCXT cross-reference check")
    audit_p.add_argument("--include-semantic", action="store_true", help="Include semantic retrieval validation")
    audit_p.add_argument("--include-crawl-coverage", action="store_true", help="Include multi-method crawl coverage check")
    audit_p.add_argument("--include-live-validation", action="store_true", help="Include live site nav validation (expensive)")
    audit_p.add_argument("--exchange", default=None, help="Limit network/coverage checks to this exchange")
    audit_p.add_argument("--qa-file", default=None, help="Path to golden QA JSONL file (for --include-semantic)")
    audit_p.add_argument("--limit", type=int, default=200, help="Max issues per check (default: 200)")

    # --- Crawl target validation subcommands ---

    san_p = sub.add_parser("sanitize-check", help="Scan inventory URLs for sanitization issues", parents=[common])
    san_p.add_argument("--exchange", default=None, help="Filter to exchange")

    vs_p = sub.add_parser("validate-sitemaps", help="Sitemap health + cross-validation (network)", parents=[common])
    vs_p.add_argument("--exchange", default=None, help="Filter to exchange")
    vs_p.add_argument("--section", default=None, help="Filter to section")
    vs_p.add_argument("--timeout-s", type=float, default=15.0)

    vct_p = sub.add_parser("validate-crawl-targets", help="Multi-method URL discovery", parents=[common])
    vct_p.add_argument("--exchange", required=True, help="Exchange to validate")
    vct_p.add_argument("--section", default=None, help="Section to validate (default: all)")
    vct_p.add_argument("--enable-nav", action="store_true", help="Enable nav extraction via agent-browser")
    vct_p.add_argument("--enable-wayback", action="store_true", help="Enable Wayback Machine CDX discovery")
    vct_p.add_argument("--timeout-s", type=float, default=30.0)

    cl_p = sub.add_parser("check-links", help="Check stored page URL reachability (HEAD requests)", parents=[common])
    cl_p.add_argument("--exchange", default=None, help="Filter to exchange")
    cl_p.add_argument("--sample", type=int, default=0, help="Random sample N URLs (0 = all)")
    cl_p.add_argument("--timeout-s", type=float, default=10.0, help="HTTP timeout per request")
    cl_p.add_argument("--concurrency", type=int, default=4, help="Max concurrent workers")
    cl_p.add_argument("--delay-s", type=float, default=0.5, help="Per-domain rate limiting delay")

    cc_p = sub.add_parser("crawl-coverage", help="Full coverage audit (discovery + store comparison)", parents=[common])
    cc_p.add_argument("--exchange", default=None, help="Filter to exchange")
    cc_p.add_argument("--section", default=None, help="Filter to section")
    cc_p.add_argument("--enable-live", action="store_true", help="Enable live site validation")
    cc_p.add_argument("--enable-nav", action="store_true", help="Enable nav extraction")
    cc_p.add_argument("--enable-wayback", action="store_true", help="Enable Wayback CDX")
    cc_p.add_argument("--backfill", action="store_true", help="Insert missing URLs as pending inventory entries (dry-run)")
    cc_p.add_argument("--fetch", action="store_true", help="With --backfill, also fetch the new entries")
    cc_p.add_argument("--timeout-s", type=float, default=30.0)
    cc_p.add_argument("--output", default=None, help="Write markdown report to file")

    io = sub.add_parser("import-openapi", help="Import OpenAPI (Swagger) spec into endpoint DB", parents=[common])
    io.add_argument("--exchange", required=True)
    io.add_argument("--section", required=True)
    io.add_argument("--url", required=True, help="OpenAPI spec URL (json/yaml)")
    io.add_argument("--base-url", default=None, help="Override base_url used for endpoint identity (default: servers[0].url)")
    io.add_argument("--api-version", default=None)
    io.add_argument("--timeout-s", type=float, default=20.0)
    io.add_argument("--max-bytes", type=int, default=50_000_000)
    io.add_argument("--max-redirects", type=int, default=5)
    io.add_argument("--retries", type=int, default=1)
    io.add_argument("--continue-on-error", action="store_true", help="Continue importing other endpoints after an error")

    pm = sub.add_parser("import-postman", help="Import Postman collection JSON into endpoint DB", parents=[common])
    pm.add_argument("--exchange", required=True)
    pm.add_argument("--section", required=True)
    pm.add_argument("--url", required=True, help="Postman collection URL (json)")
    pm.add_argument("--base-url", default=None, help="Optional base_url prefix used to derive per-request path")
    pm.add_argument("--api-version", default=None)
    pm.add_argument("--timeout-s", type=float, default=20.0)
    pm.add_argument("--max-bytes", type=int, default=50_000_000)
    pm.add_argument("--max-redirects", type=int, default=5)
    pm.add_argument("--retries", type=int, default=1)
    pm.add_argument("--continue-on-error", action="store_true", help="Continue importing other endpoints after an error")

    ia = sub.add_parser("import-asyncapi", help="Import AsyncAPI spec (not yet implemented — no CEX AsyncAPI specs found)", parents=[common])
    ia.add_argument("--exchange", required=True)
    ia.add_argument("--section", required=True)
    ia.add_argument("--url", required=True, help="AsyncAPI spec URL (json/yaml)")
    ia.add_argument("--base-url", default=None)
    ia.add_argument("--api-version", default=None)

    cov = sub.add_parser("coverage", help="Aggregate endpoint field_status coverage", parents=[common])
    cov.add_argument("--exchange", default=None)
    cov.add_argument("--section", default=None)
    cov.add_argument("--limit-samples", type=int, default=5)

    cg = sub.add_parser("coverage-gaps", help="Compute + persist aggregated endpoint completeness gaps", parents=[common])
    cg.add_argument("--exchange", default=None)
    cg.add_argument("--section", default=None)
    cg.add_argument("--limit-samples", type=int, default=5)

    cgl = sub.add_parser("coverage-gaps-list", help="List persisted coverage gap rows", parents=[common])
    cgl.add_argument("--exchange", default=None)
    cgl.add_argument("--section", default=None)
    cgl.add_argument("--limit", type=int, default=200)

    dsc = sub.add_parser("detect-stale-citations", help="Detect endpoint citations that are stale vs current sources", parents=[common])
    dsc.add_argument("--exchange", default=None)
    dsc.add_argument("--section", default=None)
    dsc.add_argument("--dry-run", action="store_true")
    dsc.add_argument("--limit", type=int, default=None)

    se = sub.add_parser("save-endpoint", help="Validate + ingest endpoint JSON", parents=[common])
    se.add_argument("endpoint_json_path")

    sep = sub.add_parser("search-endpoints", help="Full-text search ingested endpoints", parents=[common])
    sep.add_argument("query")
    sep.add_argument("--exchange", default=None)
    sep.add_argument("--section", default=None)
    sep.add_argument("--limit", type=int, default=10)

    rl = sub.add_parser("review-list", help="List review queue items", parents=[common])
    rl.add_argument("--status", default="open", choices=["open", "resolved"])
    rl.add_argument("--limit", type=int, default=50)

    rs = sub.add_parser("review-show", help="Show a review queue item", parents=[common])
    rs.add_argument("id", type=int)

    rr = sub.add_parser("review-resolve", help="Resolve a review queue item (or --auto-stale for bulk)", parents=[common])
    rr.add_argument("id", type=int, nargs="?", default=None)
    rr.add_argument("--resolution", default=None)
    rr.add_argument("--auto-stale", action="store_true", help="Bulk-resolve stale review items")
    rr.add_argument("--dry-run", action="store_true", help="Show counts without resolving")

    ap = sub.add_parser("answer", help="Assemble cite-only answers from local store", parents=[common])
    ap.add_argument("question")
    ap.add_argument("--clarification", default=None, help="Clarification selection id (e.g. binance:portfolio_margin)")

    ge = sub.add_parser("get-endpoint", help="Get full endpoint record by ID", parents=[common])
    ge.add_argument("endpoint_id")

    le = sub.add_parser("list-endpoints", help="List endpoint summaries by exchange/section", parents=[common])
    le.add_argument("--exchange", default=None)
    le.add_argument("--section", default=None)
    le.add_argument("--limit", type=int, default=100)

    lup = sub.add_parser("lookup-endpoint", help="Lookup endpoint by HTTP path", parents=[common])
    lup.add_argument("path", help="HTTP path (e.g. /sapi/v1/convert/getQuote)")
    lup.add_argument("--method", default=None, help="HTTP method filter")
    lup.add_argument("--exchange", default=None)
    lup.add_argument("--section", default=None)

    ser = sub.add_parser("search-error", help="Search error code across endpoints + pages", parents=[common])
    ser.add_argument("error_code")
    ser.add_argument("--exchange", default=None)
    ser.add_argument("--limit", type=int, default=10)

    cls = sub.add_parser("classify", help="Classify input text (error, endpoint, payload, code, question)", parents=[common])
    cls.add_argument("text")

    cx = sub.add_parser("ccxt-xref", help="Cross-reference endpoint DB against CCXT describe() metadata (requires [ccxt])", parents=[common])
    cx.add_argument("--exchange", default=None, help="Limit to a single exchange")

    le = sub.add_parser("link-endpoints", help="Resolve docs_url for spec-imported endpoints", parents=[common])
    le.add_argument("--exchange", required=True, help="Exchange ID")
    le.add_argument("--section", default=None, help="Section ID (optional)")
    le.add_argument("--limit", type=int, default=0, help="Max endpoints to resolve (0 = all)")

    sc = sub.add_parser("scan-endpoints", help="Scan crawled docs for endpoint candidates (regex-based)", parents=[common])
    sc.add_argument("--exchange", required=True, help="Exchange ID")
    sc.add_argument("--section", required=True, help="Section ID")
    sc.add_argument("--dry-run", action="store_true", help="Show candidates without saving")
    sc.add_argument("--skip-existing", action="store_true", default=True, help="Skip endpoints already in DB (default)")
    sc.add_argument("--no-skip-existing", dest="skip_existing", action="store_false", help="Don't skip existing endpoints")
    sc.add_argument("--continue-on-error", action="store_true", default=True)

    args = parser.parse_args(argv)

    try:
        if args.cmd == "init":
            result = init_store(
                docs_dir=args.docs_dir,
                schema_sql_path=Path(__file__).resolve().parents[2] / "schema" / "schema.sql",
                lock_timeout_s=float(args.lock_timeout_s),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": result})
            return

        if args.cmd == "migrate-schema":
            result = migrate_store_schema(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                dry_run=not bool(args.apply),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": result})
            return

        if args.cmd == "crawl":
            print("WARNING: 'crawl' is deprecated. Use 'sync' or 'inventory'+'fetch-inventory'.", file=sys.stderr)
            repo_root = Path(__file__).resolve().parents[2]
            seeds: list[str] = list(args.url or [])
            allowed_domains: list[str] = [d for d in (args.domain_scope or []) if d]

            if args.exchange:
                reg = load_registry(repo_root / "data" / "exchanges.yaml")
                ex = reg.get_exchange(args.exchange)
                allowed_domains = _dedupe_preserve_order([d.lower() for d in (allowed_domains + ex.allowed_domains) if d])
                if args.section:
                    sec = reg.get_section(args.exchange, args.section)
                    seeds.extend(sec.seed_urls)
                else:
                    for sec in ex.sections:
                        seeds.extend(sec.seed_urls)

            seeds = _dedupe_preserve_order([s for s in seeds if s])

            if not seeds:
                raise XDocsError(
                    code="EBADARG",
                    message="No seed URLs provided. Use --exchange/--section or --url.",
                )

            # Infer allowed domains from seed hosts if still empty.
            if not allowed_domains:
                from urllib.parse import urlsplit

                allowed_domains = sorted({(urlsplit(u).hostname or "").lower() for u in seeds if u})

            result = crawl_store(
                docs_dir=args.docs_dir,
                schema_version="v1",
                lock_timeout_s=float(args.lock_timeout_s),
                seeds=seeds,
                allowed_domains=allowed_domains,
                max_depth=int(args.max_depth),
                max_pages=int(args.max_pages),
                delay_s=float(args.delay_s),
                timeout_s=float(args.timeout_s),
                max_bytes=int(args.max_bytes),
                max_redirects=int(args.max_redirects),
                retries=int(args.retries),
                ignore_robots=bool(args.ignore_robots),
                render_mode=str(args.render),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": result})
            return

        if args.cmd == "search-pages":
            fetch_limit = int(args.limit)
            if args.exchange:
                fetch_limit = max(fetch_limit * 20, 200)  # Over-fetch, then filter
            matches = search_pages(docs_dir=args.docs_dir, query=args.query, limit=fetch_limit)
            if args.exchange:
                from .registry import load_registry as _load_reg
                repo_root = Path(__file__).resolve().parents[2]
                reg = _load_reg(repo_root / "data" / "exchanges.yaml")
                ex = reg.get_exchange(args.exchange)
                domains = set(ex.allowed_domains)
                matches = [m for m in matches if any(d in m.get("canonical_url", "") for d in domains)]
                matches = matches[:int(args.limit)]
            _print_json({"ok": True, "schema_version": "v1", "result": {"matches": matches}})
            return

        if args.cmd == "get-page":
            page = get_page(docs_dir=args.docs_dir, url=args.url)
            _print_json({"ok": True, "schema_version": "v1", "result": page})
            return

        if args.cmd == "diff":
            d = diff_pages(docs_dir=args.docs_dir, crawl_run_id=args.crawl_run_id, limit=int(args.limit))
            _print_json({"ok": True, "schema_version": "v1", "result": d})
            return

        if args.cmd == "discover-sources":
            repo_root = Path(__file__).resolve().parents[2]
            reg = load_registry(repo_root / "data" / "exchanges.yaml")
            ex = reg.get_exchange(str(args.exchange))

            results: list[dict[str, Any]] = []
            for sec in ex.sections:
                if args.section and sec.section_id != str(args.section):
                    continue
                results.append(
                    discover_sources(
                        exchange=ex.exchange_id,
                        section=sec.section_id,
                        seed_urls=sec.seed_urls,
                        allowed_domains=ex.allowed_domains,
                        timeout_s=float(args.timeout_s),
                        max_bytes=int(args.max_bytes),
                        max_redirects=int(args.max_redirects),
                        retries=int(args.retries),
                    )
                )

            _print_json({"ok": True, "schema_version": "v1", "result": {"results": results}})
            return

        if args.cmd == "inventory":
            repo_root = Path(__file__).resolve().parents[2]
            reg = load_registry(repo_root / "data" / "exchanges.yaml")
            ex = reg.get_exchange(str(args.exchange))
            sec = reg.get_section(str(args.exchange), str(args.section))
            inv = create_inventory(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                exchange_id=ex.exchange_id,
                section_id=sec.section_id,
                allowed_domains=ex.allowed_domains,
                seed_urls=sec.seed_urls,
                doc_sources=getattr(sec, "doc_sources", None),
                inventory_policy=getattr(sec, "inventory_policy", None),
                link_follow_max_pages_override=args.max_pages,
                timeout_s=float(args.timeout_s),
                max_bytes=int(args.max_bytes),
                max_redirects=int(args.max_redirects),
                retries=int(args.retries),
                ignore_robots=bool(args.ignore_robots),
                include_urls=bool(args.include_urls),
                sample_limit=int(args.sample_limit),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": asdict(inv)})
            return

        if args.cmd == "fetch-inventory":
            repo_root = Path(__file__).resolve().parents[2]
            reg = load_registry(repo_root / "data" / "exchanges.yaml")
            ex = reg.get_exchange(str(args.exchange))
            sec = reg.get_section(str(args.exchange), str(args.section))
            inv_id = args.inventory_id
            if inv_id is None:
                inv_id = latest_inventory_id(docs_dir=args.docs_dir, exchange_id=ex.exchange_id, section_id=sec.section_id)
            if inv_id is None:
                raise XDocsError(
                    code="ENOINV",
                    message="No inventory exists yet for exchange/section. Run `xdocs inventory` first.",
                    details={"exchange_id": ex.exchange_id, "section_id": sec.section_id},
                )
            r = fetch_inventory(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                exchange_id=ex.exchange_id,
                section_id=sec.section_id,
                inventory_id=int(inv_id),
                allowed_domains=ex.allowed_domains,
                delay_s=float(args.delay_s),
                timeout_s=float(args.timeout_s),
                max_bytes=int(args.max_bytes),
                max_redirects=int(args.max_redirects),
                retries=int(args.retries),
                ignore_robots=bool(args.ignore_robots),
                render_mode=str(args.render),
                resume=bool(args.resume),
                limit=args.limit,
                concurrency=int(args.concurrency),
                force_refetch=bool(args.force_refetch),
                conditional=bool(args.conditional),
                adaptive_delay=bool(args.adaptive_delay),
                max_domain_delay_s=float(args.max_domain_delay),
                scope_dedupe=bool(args.scope_dedupe),
                scope_group=(sec.inventory_policy.scope_group or ex.exchange_id),
                scope_priority=int(sec.inventory_policy.scope_priority),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "ingest-page":
            html_path = Path(args.html_path) if args.html_path else None
            md_path = Path(args.markdown_path) if args.markdown_path else None
            r = ingest_page(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                url=str(args.url),
                html_path=html_path,
                markdown_path=md_path,
                tool=args.tool,
                notes=args.notes,
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "sync":
            repo_root = Path(__file__).resolve().parents[2]
            r = run_sync(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                registry_path=repo_root / "data" / "exchanges.yaml",
                exchange=args.exchange,
                section=args.section,
                render_mode=str(args.render),
                ignore_robots=bool(args.ignore_robots),
                timeout_s=float(args.timeout_s),
                max_bytes=int(args.max_bytes),
                max_redirects=int(args.max_redirects),
                retries=int(args.retries),
                delay_s=float(args.delay_s),
                limit=args.limit,
                inventory_max_pages=args.inventory_max_pages,
                resume=bool(args.resume),
                concurrency=int(args.concurrency),
                force_refetch=bool(args.force_refetch),
                conditional=bool(args.conditional),
                adaptive_delay=bool(args.adaptive_delay),
                max_domain_delay_s=float(args.max_domain_delay),
                scope_dedupe=bool(args.scope_dedupe),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "report":
            in_path = str(args.input)
            if in_path == "-" or in_path == "":
                raw = sys.stdin.read()
            else:
                raw = Path(in_path).read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
                # Accept a full CLI JSON envelope.
                data = data["result"]
            if not isinstance(data, dict):
                raise XDocsError(code="EBADJSON", message="Report input must be a JSON object.")
            md = render_sync_markdown(sync_result=data, max_errors=int(args.max_errors))
            out_path = str(args.output)
            if out_path == "-" or out_path == "":
                sys.stdout.write(md)
            else:
                Path(out_path).write_text(md, encoding="utf-8")
            return

        if args.cmd == "store-report":
            data = store_report(
                docs_dir=args.docs_dir,
                exchange=args.exchange,
                section=args.section,
            )
            out_path = str(args.output)
            if out_path == "-" or out_path == "":
                md = render_store_report_markdown(data)
                sys.stdout.write(md)
            else:
                md = render_store_report_markdown(data)
                Path(out_path).write_text(md, encoding="utf-8")
                _print_json({"ok": True, "schema_version": "v1", "result": data})
            return

        if args.cmd == "fts-optimize":
            r = fts_optimize(docs_dir=args.docs_dir, lock_timeout_s=float(args.lock_timeout_s))
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "fts-rebuild":
            r = fts_rebuild(docs_dir=args.docs_dir, lock_timeout_s=float(args.lock_timeout_s))
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "validate-registry":
            repo_root = Path(__file__).resolve().parents[2]
            r = validate_registry(
                registry_path=repo_root / "data" / "exchanges.yaml",
                exchange=args.exchange,
                section=args.section,
                timeout_s=float(args.timeout_s),
                max_bytes=int(args.max_bytes),
                max_redirects=int(args.max_redirects),
                retries=int(args.retries),
                render_mode=str(args.render),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "validate-base-urls":
            repo_root = Path(__file__).resolve().parents[2]
            r = validate_base_urls(
                registry_path=repo_root / "data" / "exchanges.yaml",
                exchange=args.exchange,
                section=args.section,
                timeout_s=float(args.timeout_s),
                retries=int(args.retries),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "known-sources":
            repo_root = Path(__file__).resolve().parents[2]
            from .registry import load_registry
            reg = load_registry(repo_root / "data" / "exchanges.yaml")
            ex = reg.get_exchange(args.exchange)
            ks = ex.known_sources
            all_urls = ks.all_urls()
            # Merge with section-level doc_sources and seed_urls for completeness.
            doc_source_urls: dict[str, list[str]] = {}
            seed_urls: list[str] = []
            for sec in ex.sections:
                for ds in sec.doc_sources:
                    doc_source_urls.setdefault(f"doc_source_{ds.kind}", []).append(ds.url)
                seed_urls.extend(sec.seed_urls)
            sources: dict[str, Any] = {}
            for k, v in all_urls.items():
                sources[k] = v
            sources["confirmed_absent"] = ks.confirmed_absent
            sources["last_verified"] = ks.last_verified
            sources["allowed_domains"] = ex.allowed_domains
            sources["seed_urls"] = list(dict.fromkeys(seed_urls))
            sources.update(doc_source_urls)
            if args.source_type:
                val = sources.get(args.source_type)
                _print_json({"ok": True, "schema_version": "v1", "exchange_id": args.exchange, "source_type": args.source_type, "value": val})
            else:
                _print_json({"ok": True, "schema_version": "v1", "exchange_id": args.exchange, "display_name": ex.display_name, "sources": sources})
            return

        if args.cmd == "validate-known-sources":
            repo_root = Path(__file__).resolve().parents[2]
            from .known_sources import validate_known_sources
            from .registry import load_registry
            reg = load_registry(repo_root / "data" / "exchanges.yaml")
            r = validate_known_sources(registry=reg, exchange_id=args.exchange, timeout_s=float(args.timeout_s))
            _print_json({"ok": r["ok"], "schema_version": "v1", "result": r})
            if not r["ok"]:
                raise SystemExit(1)
            return

        if args.cmd == "quality-check":
            r = quality_check(docs_dir=args.docs_dir)
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "extract-changelogs":
            r = extract_changelogs(
                docs_dir=args.docs_dir,
                exchange=args.exchange,
                limit_pages=int(args.limit_pages),
                dry_run=bool(args.dry_run),
            )
            _print_json(r)
            return

        if args.cmd == "list-changelogs":
            r = list_changelogs(
                docs_dir=args.docs_dir,
                exchange=args.exchange,
                section=getattr(args, "section", None),
                since=getattr(args, "since", None),
                limit=int(args.limit),
            )
            _print_json(r)
            return

        if args.cmd == "classify-changelogs":
            from .changelog_classify import classify_entry, extract_endpoint_paths, max_severity
            from .db import open_db
            from .store import require_store_db
            db_path = require_store_db(docs_dir=args.docs_dir)
            conn = open_db(db_path)
            where: list[str] = []
            params: list = []
            if args.exchange:
                where.append("exchange_id = ?")
                params.append(args.exchange)
            if args.since:
                where.append("entry_date >= ?")
                params.append(args.since)
            where_sql = ("WHERE " + " AND ".join(where)) if where else ""
            params.append(int(args.limit))
            rows = conn.execute(
                f"SELECT id, exchange_id, section_id, entry_date, entry_text, source_url FROM changelog_entries {where_sql} ORDER BY entry_date DESC NULLS LAST LIMIT ?",
                params,
            ).fetchall()
            results = []
            for row in rows:
                text = row["entry_text"][:3000]
                classes = classify_entry(text)
                paths = extract_endpoint_paths(text)
                sev = max_severity(classes)
                if args.severity and sev != args.severity:
                    continue
                results.append({
                    "entry_id": row["id"],
                    "exchange": row["exchange_id"],
                    "section": row["section_id"],
                    "date": row["entry_date"],
                    "severity": sev,
                    "classifications": [c["impact_type"] for c in classes],
                    "affected_paths": [f"{m or '?'} {p}" for m, p in paths],
                    "source_url": row["source_url"],
                    "preview": text[:200],
                })
            conn.close()
            _print_json({"ok": True, "total": len(results), "entries": results, "schema_version": "v1"})
            return

        if args.cmd == "build-index":
            from .semantic import build_index
            r = build_index(
                docs_dir=args.docs_dir,
                limit=int(args.limit),
                exchange=args.exchange,
                batch_size=int(args.batch_size),
                incremental=bool(args.incremental),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "compact-index":
            from .semantic import compact_index
            r = compact_index(docs_dir=args.docs_dir, max_bytes_per_file=getattr(args, "max_bytes_per_file", None))
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "semantic-search":
            from .semantic import semantic_search
            if args.rerank is None:
                rerank_policy: str | bool = str(args.rerank_policy)
            else:
                rerank_policy = bool(args.rerank)
            results, meta = semantic_search(
                docs_dir=args.docs_dir,
                query=args.query,
                exchange=args.exchange,
                limit=int(args.limit),
                query_type=args.mode,
                rerank=rerank_policy,
                include_meta=True,
            )
            _print_json(
                {
                    "ok": True,
                    "schema_version": "v1",
                    "result": {
                        "cmd": "semantic-search",
                        "query": args.query,
                        "mode": args.mode,
                        "rerank_policy": meta["rerank_policy"],
                        "rerank_applied": meta["rerank_applied"],
                        "rerank_reason": meta["rerank_reason"],
                        "results": results,
                    },
                },
            )
            return

        if args.cmd == "validate-retrieval":
            from .validate import validate_retrieval
            vresult = validate_retrieval(
                docs_dir=args.docs_dir,
                qa_path=args.qa_file,
                limit=int(args.limit),
                rerank=bool(args.rerank),
            )
            _print_json({
                "ok": True,
                "schema_version": "v2",
                "result": {
                    "cmd": "validate-retrieval",
                    "rerank": bool(args.rerank),
                    "total_queries": vresult.total_queries,
                    "hit_rate": vresult.hit_rate,
                    "mean_recall": vresult.mean_recall,
                    "prefix_hit_rate": vresult.prefix_hit_rate,
                    "prefix_mean_recall": vresult.prefix_mean_recall,
                    "domain_hit_rate": vresult.domain_hit_rate,
                    "domain_mean_recall": vresult.domain_mean_recall,
                    "k": vresult.k,
                    "per_query": [
                        {
                            "query": qr.query,
                            "expected_urls": qr.expected_urls,
                            "retrieved_urls": qr.retrieved_urls,
                            "hit": qr.hit,
                            "recall": qr.recall,
                            "prefix_hit": qr.prefix_hit,
                            "prefix_recall": qr.prefix_recall,
                            "domain_hit": qr.domain_hit,
                            "domain_recall": qr.domain_recall,
                        }
                        for qr in vresult.per_query
                    ],
                },
            })
            return

        if args.cmd == "fsck":
            r = fsck_store(
                docs_dir=args.docs_dir,
                limit=int(args.limit),
                scan_orphans=bool(args.scan_orphans),
                verify_hashes=bool(args.verify_hashes),
                verify_fts=bool(args.verify_fts),
                verify_endpoint_json=bool(args.verify_endpoint_json),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "audit":
            from .audit import run_audit
            r = run_audit(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                include_network=bool(args.include_network),
                include_ccxt=bool(args.include_ccxt),
                include_semantic=bool(args.include_semantic),
                include_crawl_coverage=bool(getattr(args, "include_crawl_coverage", False)),
                include_live_validation=bool(getattr(args, "include_live_validation", False)),
                exchange=getattr(args, "exchange", None),
                qa_file=args.qa_file,
                limit=int(args.limit),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "sanitize-check":
            from .url_sanitize import sanitize_url
            from .db import open_db
            from .store import require_store_db as _rsdb
            db_path = _rsdb(args.docs_dir)
            conn = open_db(db_path)
            try:
                where = ""
                params: tuple[str, ...] = ()
                if getattr(args, "exchange", None):
                    where = " WHERE ie.canonical_url LIKE ?"
                    params = (f"%{args.exchange}%",)
                rows = conn.execute(
                    f"SELECT ie.canonical_url FROM inventory_entries ie{where} ORDER BY ie.canonical_url;",
                    params,
                ).fetchall()
                bad: list[dict[str, str]] = []
                for row in rows:
                    url = str(row["canonical_url"])
                    sr = sanitize_url(url)
                    if not sr.accepted:
                        bad.append({"url": url, "reason": sr.reason or "rejected"})
                _print_json({
                    "ok": True, "schema_version": "v1",
                    "result": {"total_urls": len(rows), "bad_urls": len(bad), "issues": bad},
                })
            finally:
                conn.close()
            return

        if args.cmd == "validate-sitemaps":
            from .sitemap_validate import validate_sitemaps
            from .registry import load_registry as _lr
            repo_root = Path(__file__).resolve().parents[2]
            registry_path = repo_root / "data" / "exchanges.yaml"
            registry = _lr(registry_path)
            results = []
            for ex in registry.exchanges:
                if getattr(args, "exchange", None) and ex.exchange_id != args.exchange:
                    continue
                for sec in ex.sections:
                    if getattr(args, "section", None) and sec.section_id != args.section:
                        continue
                    try:
                        vr = validate_sitemaps(
                            exchange_id=ex.exchange_id,
                            section_id=sec.section_id,
                            registry_path=registry_path,
                            timeout_s=float(args.timeout_s),
                        )
                        from dataclasses import asdict as _ad
                        results.append(_ad(vr))
                    except Exception as e:
                        results.append({
                            "exchange_id": ex.exchange_id,
                            "section_id": sec.section_id,
                            "error": f"{type(e).__name__}: {e}",
                        })
            _print_json({"ok": True, "schema_version": "v1", "result": {"sections": results}})
            return

        if args.cmd == "validate-crawl-targets":
            from .crawl_targets import discover_crawl_targets
            repo_root = Path(__file__).resolve().parents[2]
            registry_path = repo_root / "data" / "exchanges.yaml"
            from .registry import load_registry as _lr2
            registry = _lr2(registry_path)
            ex = registry.get_exchange(args.exchange)
            results = []
            for sec in ex.sections:
                if getattr(args, "section", None) and sec.section_id != args.section:
                    continue
                try:
                    dr = discover_crawl_targets(
                        exchange_id=ex.exchange_id,
                        section_id=sec.section_id,
                        registry_path=registry_path,
                        docs_dir=args.docs_dir,
                        enable_nav=bool(args.enable_nav),
                        enable_wayback=bool(args.enable_wayback),
                        timeout_s=float(args.timeout_s),
                    )
                    results.append({
                        "exchange_id": dr.exchange_id,
                        "section_id": dr.section_id,
                        "total_urls": len(dr.urls),
                        "method_counts": dr.method_counts,
                        "intersection_count": dr.intersection_count,
                        "single_source_count": dr.single_source_count,
                        "rejected_urls": len(dr.rejected_urls),
                        "warnings": dr.warnings,
                    })
                except Exception as e:
                    results.append({
                        "exchange_id": ex.exchange_id,
                        "section_id": sec.section_id,
                        "error": f"{type(e).__name__}: {e}",
                    })
            _print_json({"ok": True, "schema_version": "v1", "result": {"sections": results}})
            return

        if args.cmd == "crawl-coverage":
            from .crawl_coverage import audit_crawl_coverage, backfill_gaps
            repo_root = Path(__file__).resolve().parents[2]
            registry_path = repo_root / "data" / "exchanges.yaml"
            r = audit_crawl_coverage(
                docs_dir=args.docs_dir,
                registry_path=registry_path,
                exchange_id=getattr(args, "exchange", None),
                section_id=getattr(args, "section", None),
                enable_live=bool(getattr(args, "enable_live", False)),
                enable_nav=bool(getattr(args, "enable_nav", False)),
                enable_wayback=bool(getattr(args, "enable_wayback", False)),
                timeout_s=float(args.timeout_s),
            )
            output: dict[str, Any] = {
                "overall_coverage_pct": round(r.overall_coverage_pct, 1),
                "total_missing": r.total_missing,
                "total_stale": r.total_stale,
                "sections": [
                    {
                        "exchange_id": sc.exchange_id,
                        "section_id": sc.section_id,
                        "discovered_urls": sc.discovered_urls,
                        "stored_urls": sc.stored_urls,
                        "missing_count": len(sc.missing_urls),
                        "stale_count": len(sc.stale_urls),
                        "coverage_pct": round(sc.coverage_pct, 1),
                        "discovery_methods_used": sc.discovery_methods_used,
                        "warnings": sc.warnings,
                    }
                    for sc in r.sections
                ],
            }
            # Backfill if requested.
            if getattr(args, "backfill", False):
                backfill_results = []
                for sc in r.sections:
                    if sc.missing_urls:
                        bf = backfill_gaps(
                            docs_dir=args.docs_dir,
                            exchange_id=sc.exchange_id,
                            section_id=sc.section_id,
                            missing_urls=sc.missing_urls,
                            dry_run=not bool(getattr(args, "fetch", False)),
                        )
                        backfill_results.append({
                            "exchange_id": sc.exchange_id,
                            "section_id": sc.section_id,
                            **bf,
                        })
                output["backfill"] = backfill_results
            # Markdown report output.
            if getattr(args, "output", None):
                from .report import render_coverage_report_markdown
                md = render_coverage_report_markdown(r)
                Path(args.output).write_text(md, encoding="utf-8")
                output["report_written_to"] = args.output
            _print_json({"ok": True, "schema_version": "v1", "result": output})
            return

        if args.cmd == "import-openapi":
            r = import_openapi(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                exchange=args.exchange,
                section=args.section,
                url=args.url,
                base_url=args.base_url,
                api_version=args.api_version,
                timeout_s=float(args.timeout_s),
                max_bytes=int(args.max_bytes),
                max_redirects=int(args.max_redirects),
                retries=int(args.retries),
                continue_on_error=bool(args.continue_on_error),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "import-postman":
            r = import_postman(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                exchange=args.exchange,
                section=args.section,
                url=args.url,
                base_url=args.base_url,
                api_version=args.api_version,
                timeout_s=float(args.timeout_s),
                max_bytes=int(args.max_bytes),
                max_redirects=int(args.max_redirects),
                retries=int(args.retries),
                continue_on_error=bool(args.continue_on_error),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "import-asyncapi":
            r = import_asyncapi(exchange=args.exchange, section=args.section, url=args.url, base_url=args.base_url, api_version=args.api_version)
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "coverage":
            r = endpoint_coverage(
                docs_dir=args.docs_dir,
                exchange=args.exchange,
                section=args.section,
                limit_samples=int(args.limit_samples),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "coverage-gaps":
            r = compute_and_persist_coverage_gaps(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                exchange=args.exchange,
                section=args.section,
                limit_samples=int(args.limit_samples),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "coverage-gaps-list":
            r = list_coverage_gaps(docs_dir=args.docs_dir, exchange=args.exchange, section=args.section, limit=int(args.limit))
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "detect-stale-citations":
            r = detect_stale_citations(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                exchange=args.exchange,
                section=args.section,
                dry_run=bool(args.dry_run),
                limit=args.limit,
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "save-endpoint":
            repo_root = Path(__file__).resolve().parents[2]
            r = save_endpoint(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                endpoint_json_path=Path(args.endpoint_json_path),
                schema_path=repo_root / "schemas" / "endpoint.schema.json",
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            return

        if args.cmd == "search-endpoints":
            matches = search_endpoints(
                docs_dir=args.docs_dir,
                query=args.query,
                exchange=args.exchange,
                section=args.section,
                limit=int(args.limit),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": {"matches": matches}})
            return

        if args.cmd == "review-list":
            items = review_list(docs_dir=args.docs_dir, status=args.status, limit=int(args.limit))
            _print_json({"ok": True, "schema_version": "v1", "result": {"items": items}})
            return

        if args.cmd == "review-show":
            item = review_show(docs_dir=args.docs_dir, review_id=int(args.id))
            _print_json({"ok": True, "schema_version": "v1", "result": item})
            return

        if args.cmd == "review-resolve":
            if getattr(args, "auto_stale", False):
                # Bulk-resolve stale review queue items.
                from .db import open_db
                from .store import require_store_db
                db_path = require_store_db(docs_dir=args.docs_dir)
                conn = open_db(db_path)
                dry = getattr(args, "dry_run", False)
                # Count by kind before
                before = dict(conn.execute(
                    "SELECT kind, COUNT(*) FROM review_queue WHERE status = 'open' GROUP BY kind"
                ).fetchall())
                # Auto-resolve: source_changed older than 7 days
                if dry:
                    sc = conn.execute(
                        "SELECT COUNT(*) FROM review_queue WHERE status = 'open' AND kind = 'source_changed' AND created_at < datetime('now', '-7 days')"
                    ).fetchone()[0]
                    st = conn.execute(
                        "SELECT COUNT(*) FROM review_queue WHERE status = 'open' AND kind = 'stale_citation' AND created_at < datetime('now', '-7 days')"
                    ).fetchone()[0]
                else:
                    sc = conn.execute(
                        "UPDATE review_queue SET status = 'resolved', resolved_at = datetime('now'), reason = 'auto-stale' WHERE status = 'open' AND kind = 'source_changed' AND created_at < datetime('now', '-7 days')"
                    ).rowcount
                    st = conn.execute(
                        "UPDATE review_queue SET status = 'resolved', resolved_at = datetime('now'), reason = 'auto-stale' WHERE status = 'open' AND kind = 'stale_citation' AND created_at < datetime('now', '-7 days')"
                    ).rowcount
                    conn.commit()
                conn.close()
                _print_json({"ok": True, "schema_version": "v1", "dry_run": dry, "resolved": {"source_changed": sc, "stale_citation": st}, "before": before})
                return
            if args.id is None:
                _print_json({"ok": False, "error": "Provide a review ID or --auto-stale"})
                return
            item = review_resolve(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                review_id=int(args.id),
                resolution=args.resolution,
            )
            _print_json({"ok": True, "schema_version": "v1", "result": item})
            return

        if args.cmd == "answer":
            result = answer_question(docs_dir=args.docs_dir, question=args.question, clarification=args.clarification)
            _print_json(result)
            return

        if args.cmd == "get-endpoint":
            result = get_endpoint(docs_dir=args.docs_dir, endpoint_id=args.endpoint_id)
            _print_json({"ok": True, "schema_version": "v1", "result": result})
            return

        if args.cmd == "list-endpoints":
            items = list_endpoints(docs_dir=args.docs_dir, exchange=args.exchange, section=args.section, limit=int(args.limit))
            _print_json({"ok": True, "schema_version": "v1", "result": {"endpoints": items, "count": len(items)}})
            return

        if args.cmd == "lookup-endpoint":
            matches = lookup_endpoint_by_path(
                docs_dir=args.docs_dir,
                path=args.path,
                method=args.method,
                exchange=args.exchange,
                section=args.section,
            )
            _print_json({"ok": True, "schema_version": "v1", "result": {"matches": matches, "count": len(matches)}})
            return

        if args.cmd == "search-error":
            matches = search_error_code(
                docs_dir=args.docs_dir,
                error_code=args.error_code,
                exchange=args.exchange,
                limit=int(args.limit),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": {"matches": matches, "count": len(matches)}})
            return

        if args.cmd == "classify":
            classification = classify_input(args.text)
            _print_json({
                "ok": True,
                "schema_version": "v1",
                "result": {
                    "input_type": classification.input_type,
                    "confidence": classification.confidence,
                    "signals": classification.signals,
                },
            })
            return

        if args.cmd == "check-links":
            from .link_check import check_stored_links
            report = check_stored_links(
                docs_dir=args.docs_dir,
                exchange=getattr(args, "exchange", None),
                sample=int(getattr(args, "sample", 0)),
                timeout_s=float(args.timeout_s),
                concurrency=int(args.concurrency),
                delay_s=float(getattr(args, "delay_s", 0.5)),
            )
            result_dict: dict[str, Any] = {
                "checked": report.checked,
                "ok": report.ok,
                "redirect": report.redirect,
                "client_error": report.client_error,
                "server_error": report.server_error,
                "network_error": report.network_error,
                "checked_at": report.checked_at,
                "issues": [
                    {
                        "url": r.url,
                        "http_status": r.http_status,
                        "error": r.error,
                        "redirect_url": r.redirect_url,
                        "response_time_ms": r.response_time_ms,
                    }
                    for r in report.results
                ],
            }
            _print_json({"ok": True, "schema_version": "v1", "result": result_dict})
            return

        if args.cmd == "ccxt-xref":
            result = ccxt_cross_reference(docs_dir=args.docs_dir, exchange=args.exchange)
            _print_json(result)
            return

        if args.cmd == "link-endpoints":
            from .resolve_docs_urls import link_endpoints_bulk
            from .db import open_db
            from .store import require_store_db
            repo_root = Path(__file__).resolve().parents[2]
            reg = load_registry(repo_root / "data" / "exchanges.yaml")
            ex = reg.get_exchange(args.exchange)
            db_path = require_store_db(args.docs_dir)
            conn = open_db(db_path)
            try:
                result = link_endpoints_bulk(
                    conn,
                    exchange=args.exchange,
                    section=args.section,
                    allowed_domains=ex.allowed_domains,
                    limit=args.limit,
                )
                _print_json({"ok": True, "schema_version": "v1", **result})
            finally:
                conn.close()
            return

        if args.cmd == "scan-endpoints":
            from .endpoint_extract import scan_endpoints
            result = scan_endpoints(
                docs_dir=args.docs_dir,
                lock_timeout_s=args.lock_timeout_s,
                exchange=args.exchange,
                section=args.section,
                dry_run=args.dry_run,
                skip_existing=args.skip_existing,
                continue_on_error=args.continue_on_error,
            )
            _print_json({"ok": True, "schema_version": "v1", **result})
            return

        _print_json({"ok": False, "schema_version": "v1", "error": {"code": "EBADCLI", "message": "unknown command"}})
        raise SystemExit(2)
    except XDocsError as e:
        _print_json({"ok": False, "schema_version": "v1", "error": e.to_json()})
        raise SystemExit(2)
    except Exception as e:  # pragma: no cover
        _print_json(
            {
                "ok": False,
                "schema_version": "v1",
                "error": {
                    "code": "EUNEXPECTED",
                    "message": "Unexpected error.",
                    "details": {"type": type(e).__name__, "error": str(e)},
                },
            }
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
