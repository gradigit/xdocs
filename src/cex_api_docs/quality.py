from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .db import open_db
from .store import require_store_db


def quality_check(*, docs_dir: str) -> dict[str, Any]:
    """Check stored pages for content quality issues.

    Flags:
    - empty: word_count == 0
    - thin: word_count < 50 (possible nav-only or stub page)
    - tiny_html: raw HTML file < 1 KB (possible JS rendering failure)
    """
    db_path = require_store_db(docs_dir)
    docs_root = Path(docs_dir)
    conn = open_db(db_path)
    try:
        rows = conn.execute(
            "SELECT canonical_url, word_count, raw_path FROM pages ORDER BY canonical_url;"
        ).fetchall()

        total = len(rows)
        empty = 0
        thin = 0
        tiny_html = 0
        ok = 0
        issues: list[dict[str, Any]] = []

        for row in rows:
            url = str(row["canonical_url"])
            wc = int(row["word_count"] or 0)
            raw_path = row["raw_path"]

            issue_type = None
            if wc == 0:
                issue_type = "empty"
                empty += 1
            elif wc < 50:
                issue_type = "thin"
                thin += 1

            if raw_path:
                full_raw = docs_root / raw_path
                try:
                    size = os.path.getsize(full_raw)
                except OSError:
                    size = -1
                if size >= 0 and size < 1024:
                    if issue_type is None:
                        issue_type = "tiny_html"
                        tiny_html += 1
                    else:
                        # Already flagged as empty/thin — also note tiny_html.
                        tiny_html += 1
                        issue_type = issue_type + "+tiny_html"

            if issue_type is None:
                ok += 1
            else:
                issues.append({"url": url, "type": issue_type, "word_count": wc})

        return {
            "cmd": "quality-check",
            "counts": {
                "total": total,
                "empty": empty,
                "thin": thin,
                "tiny_html": tiny_html,
                "ok": ok,
            },
            "issues": issues,
        }
    finally:
        conn.close()
