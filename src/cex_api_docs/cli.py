from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .errors import CexApiDocsError
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
