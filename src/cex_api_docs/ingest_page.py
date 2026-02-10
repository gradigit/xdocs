from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import open_db
from .errors import CexApiDocsError
from .httpfetch import FetchResult
from .lock import acquire_write_lock
from .markdown import extractor_info_v1, normalize_markdown
from .page_store import store_page
from .store import require_store_db
from .timeutil import now_iso_utc


@dataclass(frozen=True, slots=True)
class IngestConfig:
    url: str
    html_path: str | None
    markdown_path: str | None
    tool: str | None
    notes: str | None


def ingest_page(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    url: str,
    html_path: Path | None = None,
    markdown_path: Path | None = None,
    tool: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if not url:
        raise CexApiDocsError(code="EBADARG", message="Missing --url for ingest-page.")
    if (html_path is None and markdown_path is None) or (html_path is not None and markdown_path is not None):
        raise CexApiDocsError(
            code="EBADARG",
            message="Provide exactly one of --html-path or --markdown-path.",
            details={"html_path": str(html_path) if html_path else None, "markdown_path": str(markdown_path) if markdown_path else None},
        )

    db_path = require_store_db(docs_dir)
    docs_root = Path(docs_dir)
    lock_path = docs_root / "db" / ".write.lock"

    started_at = now_iso_utc()
    extractor = extractor_info_v1()

    cfg = IngestConfig(
        url=str(url),
        html_path=str(html_path) if html_path else None,
        markdown_path=str(markdown_path) if markdown_path else None,
        tool=str(tool) if tool else None,
        notes=str(notes) if notes else None,
    )

    if html_path is not None:
        body = html_path.read_bytes()
        content_type = "text/html; charset=utf-8"
        md_norm = None
        wc = None
        title = None
    else:
        assert markdown_path is not None
        md_raw = markdown_path.read_text(encoding="utf-8")
        md_norm0 = normalize_markdown(md_raw)
        body = md_norm0.encode("utf-8", errors="replace")
        content_type = "text/markdown; charset=utf-8"
        md_norm = md_norm0
        wc = len(md_norm0.split())
        title = None

    fr = FetchResult(
        url=url,
        final_url=url,
        redirect_chain=[],
        http_status=200,
        content_type=content_type,
        headers={},
        body=body,
    )

    with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
        conn = open_db(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO crawl_runs (started_at, ended_at, config_json) VALUES (?, ?, ?);",
                (started_at, None, json.dumps(asdict(cfg), sort_keys=True, ensure_ascii=False)),
            )
            crawl_run_id = int(cur.lastrowid)
            conn.commit()

            rec = store_page(
                conn=conn,
                docs_root=docs_root,
                crawl_run_id=crawl_run_id,
                url=url,
                fr=fr,
                render_mode="ingest",
                extractor=extractor,
                extracted_title=title,
                extracted_markdown_norm=md_norm,
                extracted_word_count=wc,
                meta_extra={
                    "ingest": {
                        "tool": tool,
                        "notes": notes,
                        "input_path": str(html_path) if html_path else str(markdown_path),
                        "input_kind": "html" if html_path else "markdown",
                    }
                },
            )

            ended_at = now_iso_utc()
            conn.execute("UPDATE crawl_runs SET ended_at = ? WHERE id = ?;", (ended_at, crawl_run_id))
            conn.commit()

            return {
                "cmd": "ingest-page",
                "schema_version": "v1",
                "docs_dir": str(docs_root),
                "crawl_run_id": crawl_run_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "config": asdict(cfg),
                "stored": rec,
            }
        finally:
            conn.close()

