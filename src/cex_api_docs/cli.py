from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

from .errors import CexApiDocsError
from .answer import answer_question
from .base_urls_validate import validate_base_urls
from .crawler import crawl_store
from .coverage import endpoint_coverage
from .discover_sources import discover_sources
from .endpoints import review_list, review_resolve, review_show, save_endpoint, search_endpoints
from .ingest_page import ingest_page
from .inventory import create_inventory, latest_inventory_id
from .inventory_fetch import fetch_inventory
from .openapi_import import import_openapi
from .postman_import import import_postman
from .fsck import fsck_store
from .pages import diff_pages, fts_optimize, fts_rebuild, get_page, search_pages
from .report import render_sync_markdown
from .registry import load_registry
from .registry_validate import validate_registry
from .sync import run_sync
from .store import init_store


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
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--docs-dir", default="./cex-docs", help="Store root (default: ./cex-docs)")
    common.add_argument(
        "--lock-timeout-s",
        default=10.0,
        type=float,
        help="Seconds to wait for exclusive write lock (default: 10)",
    )

    parser = argparse.ArgumentParser(prog="cex-api-docs", parents=[common])

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Initialize store dirs + SQLite schema (idempotent)", parents=[common])

    crawl_p = sub.add_parser("crawl", help="Crawl docs and store pages + metadata", parents=[common])
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
    fi_p.add_argument("--render", default="http", choices=["http", "playwright", "auto"])

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
    sync_p.add_argument("--delay-s", type=float, default=0.25)
    sync_p.add_argument("--timeout-s", type=float, default=20.0)
    sync_p.add_argument("--max-bytes", type=int, default=10_000_000)
    sync_p.add_argument("--max-redirects", type=int, default=5)
    sync_p.add_argument("--retries", type=int, default=2)
    sync_p.add_argument("--ignore-robots", action="store_true")
    sync_p.add_argument("--render", default="http", choices=["http", "playwright", "auto"])

    rep_p = sub.add_parser("report", help="Render a sync JSON artifact into Markdown", parents=[common])
    rep_p.add_argument("--input", default="-", help="Path to sync JSON file, or '-' for stdin (default: -)")
    rep_p.add_argument("--output", default="-", help="Path to write Markdown, or '-' for stdout (default: -)")
    rep_p.add_argument("--max-errors", type=int, default=50)

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

    fsck_p = sub.add_parser("fsck", help="Detect store DB/file inconsistencies (detection-only by default)", parents=[common])
    fsck_p.add_argument("--limit", type=int, default=200)
    fsck_p.add_argument("--scan-orphans", action="store_true", help="Scan raw/pages/meta directories for orphan files (can be slow)")

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

    cov = sub.add_parser("coverage", help="Aggregate endpoint field_status coverage", parents=[common])
    cov.add_argument("--exchange", default=None)
    cov.add_argument("--section", default=None)
    cov.add_argument("--limit-samples", type=int, default=5)

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

    rr = sub.add_parser("review-resolve", help="Resolve a review queue item", parents=[common])
    rr.add_argument("id", type=int)
    rr.add_argument("--resolution", default=None)

    ap = sub.add_parser("answer", help="Assemble cite-only answers from local store", parents=[common])
    ap.add_argument("question")
    ap.add_argument("--clarification", default=None, help="Clarification selection id (e.g. binance:portfolio_margin)")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "init":
            result = init_store(
                docs_dir=args.docs_dir,
                schema_sql_path=Path(__file__).resolve().parents[2] / "schema" / "schema.sql",
                lock_timeout_s=float(args.lock_timeout_s),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": result})
            raise SystemExit(0)

        if args.cmd == "crawl":
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
                raise CexApiDocsError(
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
            raise SystemExit(0)

        if args.cmd == "search-pages":
            matches = search_pages(docs_dir=args.docs_dir, query=args.query, limit=int(args.limit))
            _print_json({"ok": True, "schema_version": "v1", "result": {"matches": matches}})
            raise SystemExit(0)

        if args.cmd == "get-page":
            page = get_page(docs_dir=args.docs_dir, url=args.url)
            _print_json({"ok": True, "schema_version": "v1", "result": page})
            raise SystemExit(0)

        if args.cmd == "diff":
            d = diff_pages(docs_dir=args.docs_dir, crawl_run_id=args.crawl_run_id, limit=int(args.limit))
            _print_json({"ok": True, "schema_version": "v1", "result": d})
            raise SystemExit(0)

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
            raise SystemExit(0)

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
                timeout_s=float(args.timeout_s),
                max_bytes=int(args.max_bytes),
                max_redirects=int(args.max_redirects),
                retries=int(args.retries),
                ignore_robots=bool(args.ignore_robots),
                include_urls=bool(args.include_urls),
                sample_limit=int(args.sample_limit),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": asdict(inv)})
            raise SystemExit(0)

        if args.cmd == "fetch-inventory":
            repo_root = Path(__file__).resolve().parents[2]
            reg = load_registry(repo_root / "data" / "exchanges.yaml")
            ex = reg.get_exchange(str(args.exchange))
            sec = reg.get_section(str(args.exchange), str(args.section))
            inv_id = args.inventory_id
            if inv_id is None:
                inv_id = latest_inventory_id(docs_dir=args.docs_dir, exchange_id=ex.exchange_id, section_id=sec.section_id)
            if inv_id is None:
                raise CexApiDocsError(
                    code="ENOINV",
                    message="No inventory exists yet for exchange/section. Run `cex-api-docs inventory` first.",
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
                limit=args.limit,
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            raise SystemExit(0)

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
            raise SystemExit(0)

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
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            raise SystemExit(0)

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
                raise CexApiDocsError(code="EBADJSON", message="Report input must be a JSON object.")
            md = render_sync_markdown(sync_result=data, max_errors=int(args.max_errors))
            out_path = str(args.output)
            if out_path == "-" or out_path == "":
                sys.stdout.write(md)
            else:
                Path(out_path).write_text(md, encoding="utf-8")
            raise SystemExit(0)

        if args.cmd == "fts-optimize":
            r = fts_optimize(docs_dir=args.docs_dir, lock_timeout_s=float(args.lock_timeout_s))
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            raise SystemExit(0)

        if args.cmd == "fts-rebuild":
            r = fts_rebuild(docs_dir=args.docs_dir, lock_timeout_s=float(args.lock_timeout_s))
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            raise SystemExit(0)

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
            raise SystemExit(0)

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
            raise SystemExit(0)

        if args.cmd == "fsck":
            r = fsck_store(docs_dir=args.docs_dir, limit=int(args.limit), scan_orphans=bool(args.scan_orphans))
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            raise SystemExit(0)

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
            raise SystemExit(0)

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
            raise SystemExit(0)

        if args.cmd == "coverage":
            r = endpoint_coverage(
                docs_dir=args.docs_dir,
                exchange=args.exchange,
                section=args.section,
                limit_samples=int(args.limit_samples),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            raise SystemExit(0)

        if args.cmd == "save-endpoint":
            repo_root = Path(__file__).resolve().parents[2]
            r = save_endpoint(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                endpoint_json_path=Path(args.endpoint_json_path),
                schema_path=repo_root / "schemas" / "endpoint.schema.json",
            )
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            raise SystemExit(0)

        if args.cmd == "search-endpoints":
            matches = search_endpoints(
                docs_dir=args.docs_dir,
                query=args.query,
                exchange=args.exchange,
                section=args.section,
                limit=int(args.limit),
            )
            _print_json({"ok": True, "schema_version": "v1", "result": {"matches": matches}})
            raise SystemExit(0)

        if args.cmd == "review-list":
            items = review_list(docs_dir=args.docs_dir, status=args.status, limit=int(args.limit))
            _print_json({"ok": True, "schema_version": "v1", "result": {"items": items}})
            raise SystemExit(0)

        if args.cmd == "review-show":
            item = review_show(docs_dir=args.docs_dir, review_id=int(args.id))
            _print_json({"ok": True, "schema_version": "v1", "result": item})
            raise SystemExit(0)

        if args.cmd == "review-resolve":
            item = review_resolve(
                docs_dir=args.docs_dir,
                lock_timeout_s=float(args.lock_timeout_s),
                review_id=int(args.id),
                resolution=args.resolution,
            )
            _print_json({"ok": True, "schema_version": "v1", "result": item})
            raise SystemExit(0)

        if args.cmd == "answer":
            result = answer_question(docs_dir=args.docs_dir, question=args.question, clarification=args.clarification)
            _print_json(result)
            raise SystemExit(0)

        _print_json({"ok": False, "schema_version": "v1", "error": {"code": "EBADCLI", "message": "unknown command"}})
        raise SystemExit(2)
    except CexApiDocsError as e:
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
