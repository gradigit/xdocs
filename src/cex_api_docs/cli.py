from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .errors import CexApiDocsError
from .answer import answer_question
from .crawler import crawl_store
from .endpoints import review_list, review_resolve, review_show, save_endpoint, search_endpoints
from .pages import diff_pages, fts_optimize, fts_rebuild, get_page, search_pages
from .registry import load_registry
from .store import init_store


def _print_json(obj: object) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


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

    sub.add_parser("fts-optimize", help="Optimize SQLite FTS indexes", parents=[common])
    sub.add_parser("fts-rebuild", help="Rebuild SQLite FTS indexes from stored markdown", parents=[common])

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
                allowed_domains = list(set(allowed_domains + ex.allowed_domains))
                if args.section:
                    sec = reg.get_section(args.exchange, args.section)
                    seeds.extend(sec.seed_urls)
                else:
                    for sec in ex.sections:
                        seeds.extend(sec.seed_urls)

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

        if args.cmd == "fts-optimize":
            r = fts_optimize(docs_dir=args.docs_dir, lock_timeout_s=float(args.lock_timeout_s))
            _print_json({"ok": True, "schema_version": "v1", "result": r})
            raise SystemExit(0)

        if args.cmd == "fts-rebuild":
            r = fts_rebuild(docs_dir=args.docs_dir, lock_timeout_s=float(args.lock_timeout_s))
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
