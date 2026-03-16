from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from .db import open_db
from .extraction_verify import verify_extraction
from .store import require_store_db

log = logging.getLogger(__name__)

_AUTH_GATE_PATTERNS = re.compile(
    r"please\s+log\s+in|sign\s+in\s+to\s+continue|authentication\s+required|access\s+denied",
    re.IGNORECASE,
)


def quality_check(*, docs_dir: str) -> dict[str, Any]:
    """Check stored pages for content quality issues.

    Flags:
    - empty: word_count == 0
    - thin: word_count < 50 (possible nav-only or stub page)
    - tiny_html: raw HTML file < 1 KB (possible JS rendering failure)
    - content_regression: current word_count < 50% of previous version
    - extraction_incomplete: verify_extraction quality_score < 0.40
    - auth_gate: http_status 401/403 or auth-wall patterns in markdown
    """
    db_path = require_store_db(docs_dir)
    docs_root = Path(docs_dir)
    conn = open_db(db_path)
    try:
        rows = conn.execute(
            "SELECT canonical_url, word_count, raw_path, markdown_path, http_status, "
            "content_hash, prev_content_hash, id "
            "FROM pages ORDER BY canonical_url;"
        ).fetchall()

        total = len(rows)
        empty = 0
        thin = 0
        tiny_html = 0
        content_regression = 0
        extraction_incomplete = 0
        auth_gate = 0
        ok = 0
        issues: list[dict[str, Any]] = []

        for row in rows:
            url = str(row["canonical_url"])
            wc = int(row["word_count"] or 0)
            raw_path = row["raw_path"]
            http_status = int(row["http_status"] or 0)
            page_id = int(row["id"])

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

            # --- auth_gate ---
            is_auth_gate = False
            if http_status in (401, 403):
                is_auth_gate = True
            elif row["markdown_path"]:
                md_path = Path(str(row["markdown_path"]))
                if md_path.exists():
                    try:
                        md_text = md_path.read_text(encoding="utf-8", errors="replace")
                        if _AUTH_GATE_PATTERNS.search(md_text):
                            is_auth_gate = True
                    except OSError:
                        pass

            if is_auth_gate:
                auth_gate += 1
                if issue_type is None:
                    issue_type = "auth_gate"
                else:
                    issue_type = issue_type + "+auth_gate"
                issues.append({"url": url, "type": issue_type, "word_count": wc, "http_status": http_status})
                continue

            # --- content_regression ---
            prev_hash = row["prev_content_hash"]
            curr_hash = row["content_hash"]
            if prev_hash and curr_hash and prev_hash != curr_hash:
                # Find the previous version's markdown file to compare word counts.
                prev_version = conn.execute(
                    "SELECT markdown_path FROM page_versions "
                    "WHERE page_id = ? AND content_hash = ? "
                    "ORDER BY crawled_at DESC LIMIT 1;",
                    (page_id, prev_hash),
                ).fetchone()
                if prev_version and prev_version["markdown_path"]:
                    prev_md_path = Path(str(prev_version["markdown_path"]))
                    if prev_md_path.exists():
                        try:
                            prev_md = prev_md_path.read_text(encoding="utf-8", errors="replace")
                            prev_wc = len(prev_md.split())
                            if prev_wc > 0 and wc < prev_wc * 0.5:
                                content_regression += 1
                                if issue_type is None:
                                    issue_type = "content_regression"
                                else:
                                    issue_type = issue_type + "+content_regression"
                                issues.append({
                                    "url": url,
                                    "type": issue_type,
                                    "word_count": wc,
                                    "prev_word_count": prev_wc,
                                })
                                continue
                        except OSError:
                            pass

            # --- extraction_incomplete ---
            # Only run on pages already flagged as thin or recently updated.
            if (issue_type in ("thin", "empty") or (prev_hash and prev_hash != curr_hash)) and raw_path:
                full_raw = docs_root / raw_path
                md_path_val = row["markdown_path"]
                if full_raw.exists() and md_path_val:
                    md_path_obj = Path(str(md_path_val))
                    if md_path_obj.exists():
                        try:
                            html_text = full_raw.read_bytes().decode("utf-8", errors="replace")
                            md_text = md_path_obj.read_text(encoding="utf-8", errors="replace")
                            eq = verify_extraction(html_text, md_text)
                            if eq.quality_score < 0.40:
                                extraction_incomplete += 1
                                if issue_type is None:
                                    issue_type = "extraction_incomplete"
                                else:
                                    issue_type = issue_type + "+extraction_incomplete"
                                issues.append({
                                    "url": url,
                                    "type": issue_type,
                                    "word_count": wc,
                                    "quality_score": round(eq.quality_score, 3),
                                    "warnings": eq.warnings,
                                })
                                continue
                        except OSError:
                            pass

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
                "content_regression": content_regression,
                "extraction_incomplete": extraction_incomplete,
                "auth_gate": auth_gate,
                "ok": ok,
            },
            "issues": issues,
        }
    finally:
        conn.close()
