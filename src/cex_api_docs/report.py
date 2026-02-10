from __future__ import annotations

import json
from typing import Any


def render_sync_markdown(*, sync_result: dict[str, Any], max_errors: int = 50) -> str:
    started_at = str(sync_result.get("started_at") or "")
    ended_at = str(sync_result.get("ended_at") or "")
    totals = sync_result.get("totals") or {}
    sections = sync_result.get("sections") or []

    lines: list[str] = []
    lines.append(f"# CEX API Docs Sync Report")
    lines.append("")
    if started_at:
        lines.append(f"- **Started:** `{started_at}`")
    if ended_at:
        lines.append(f"- **Ended:** `{ended_at}`")
    lines.append(
        "- **Totals:** "
        f"inventories={totals.get('inventories')}, "
        f"inventory_urls={totals.get('inventory_urls')}, "
        f"fetched={totals.get('fetched')}, "
        f"stored={totals.get('stored')}, "
        f"new_pages={totals.get('new_pages')}, "
        f"updated_pages={totals.get('updated_pages')}, "
        f"unchanged_pages={totals.get('unchanged_pages')}, "
        f"skipped={totals.get('skipped')}, "
        f"errors={totals.get('errors')}"
    )
    lines.append("")

    lines.append("## Per Exchange/Section")
    lines.append("")
    lines.append(
        "| Exchange | Section | Inventory URLs | +Added | -Removed | Fetched | Stored | New | Updated | Unchanged | Skipped | Errors | Inventory ID | Crawl Run |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

    for s in sections:
        ex = s.get("exchange_id")
        sec = s.get("section_id")
        inv = s.get("inventory") or {}
        inv_diff = inv.get("diff") or {}
        fetch = s.get("fetch") or {}
        counts = fetch.get("counts") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(ex),
                    str(sec),
                    str(inv.get("url_count") or 0),
                    str(inv_diff.get("added") or 0),
                    str(inv_diff.get("removed") or 0),
                    str(counts.get("fetched") or 0),
                    str(counts.get("stored") or 0),
                    str(counts.get("new_pages") or 0),
                    str(counts.get("updated_pages") or 0),
                    str(counts.get("unchanged_pages") or 0),
                    str(counts.get("skipped") or 0),
                    str(counts.get("errors") or 0),
                    str(inv.get("inventory_id") or ""),
                    str(fetch.get("crawl_run_id") or ""),
                ]
            )
            + " |"
        )

    # Collect a bounded set of errors.
    err_lines: list[str] = []
    for s in sections:
        ex = s.get("exchange_id")
        sec = s.get("section_id")
        inv = s.get("inventory") or {}
        for e in (inv.get("errors") or [])[: max_errors]:
            err_lines.append(f"- `{ex}:{sec}` inventory error: `{json.dumps(e, sort_keys=True, ensure_ascii=False)}`")
        fetch = s.get("fetch") or {}
        for e in (fetch.get("errors") or [])[: max_errors]:
            err_lines.append(f"- `{ex}:{sec}` fetch error: `{json.dumps(e, sort_keys=True, ensure_ascii=False)}`")
        if len(err_lines) >= max_errors:
            break

    lines.append("")
    lines.append("## Errors (Sample)")
    lines.append("")
    if not err_lines:
        lines.append("No errors recorded.")
    else:
        lines.extend(err_lines[:max_errors])
        if len(err_lines) > max_errors:
            lines.append(f"- ... truncated (showing {max_errors})")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This report is generated from the deterministic `sync` JSON output.")
    lines.append("- Inventory enumeration uses sitemaps when available; sections with low inventory URL counts likely need explicit `doc_sources` additions or browser-assisted ingestion (`ingest-page`).")

    return "\n".join(lines) + "\n"
