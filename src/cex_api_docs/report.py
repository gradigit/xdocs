from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import open_db
from .store import require_store_db
from .timeutil import now_iso_utc


def render_sync_markdown(*, sync_result: dict[str, Any], max_errors: int = 50) -> str:
    started_at = str(sync_result.get("started_at") or "")
    ended_at = str(sync_result.get("ended_at") or "")
    totals = sync_result.get("totals") or {}
    sections = sync_result.get("sections") or []
    post = sync_result.get("post") or {}

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
        f"revalidated_unchanged={totals.get('revalidated_unchanged')}, "
        f"retry_after_applied={totals.get('retry_after_applied')}, "
        f"skipped={totals.get('skipped')}, "
        f"dedupe_skipped={totals.get('dedupe_skipped')}, "
        f"errors={totals.get('errors')}"
    )
    lines.append("")

    lines.append("## Per Exchange/Section")
    lines.append("")
    lines.append(
        "| Exchange | Section | Inventory URLs | +Added | -Removed | Fetched | Stored | New | Updated | Unchanged | Revalidated | Retry-After | Skipped | Dedupe-Skipped | Errors | Inventory ID | Crawl Run |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

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
                    str(counts.get("revalidated_unchanged") or 0),
                    str(counts.get("retry_after_applied") or 0),
                    str(counts.get("skipped") or 0),
                    str(counts.get("dedupe_skipped") or 0),
                    str(counts.get("errors") or 0),
                    str(inv.get("inventory_id") or ""),
                    str(fetch.get("crawl_run_id") or ""),
                ]
            )
            + " |"
        )

    # Adaptive delay / Retry-After diagnostics (bounded).
    delay_lines: list[str] = []
    for s in sections:
        ex = s.get("exchange_id")
        sec = s.get("section_id")
        fetch = s.get("fetch") or {}
        snap = fetch.get("domain_delay_snapshot") or {}
        if not isinstance(snap, dict):
            continue
        for domain, st in sorted(snap.items()):
            if not isinstance(st, dict):
                continue
            ra = int(st.get("retry_after_applied") or 0)
            th = int(st.get("throttle_events") or 0)
            if ra <= 0 and th <= 0:
                continue
            delay_lines.append(
                f"- `{ex}:{sec}` `{domain}` delay={st.get('current_delay_s')}s, "
                f"next_allowed_in={st.get('next_allowed_in_s')}s, "
                f"retry_after_applied={ra}, throttle_events={th}, last_status={st.get('last_status')}"
            )
            if len(delay_lines) >= 50:
                break
        if len(delay_lines) >= 50:
            break

    lines.append("")
    lines.append("## Domain Delay Snapshot (Adaptive Throttle)")
    lines.append("")
    if not delay_lines:
        lines.append("No Retry-After/throttle events recorded.")
    else:
        lines.extend(delay_lines)

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

    # Optional post-processing summaries.
    if isinstance(post, dict) and post:
        cov = post.get("coverage_gaps") or {}
        stale = post.get("stale_citations") or {}

        if isinstance(cov, dict) and cov.get("counts"):
            c = cov.get("counts") or {}
            lines.append("")
            lines.append("## Endpoint Coverage Gaps (Aggregated)")
            lines.append("")
            lines.append(
                "- **Coverage rows:** "
                f"endpoints={c.get('endpoints')}, rows={c.get('rows')}, rows_with_gaps={c.get('rows_with_gaps')}"
            )
            lines.append("- Use `cex-api-docs coverage-gaps-list` to drill into field-level samples.")

        if isinstance(stale, dict) and stale.get("counts"):
            c = stale.get("counts") or {}
            lines.append("")
            lines.append("## Stale Citations (Sweep)")
            lines.append("")
            lines.append(
                "- **Findings:** "
                f"total={c.get('total_findings')}, stale={c.get('stale_citation')}, missing_source={c.get('missing_source')}, review_items_created={c.get('review_items_created')}"
            )
            lines.append("- Use `cex-api-docs review-list --status open` to triage.")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This report is generated from the deterministic `sync` JSON output.")
    lines.append(
        "- Inventory enumeration uses sitemaps when available and can fall back to deterministic link-follow inventories when configured in the registry."
    )
    lines.append("- For JS-heavy docs or WAF edge cases, use `--render auto` (Playwright optional) or browser capture + `ingest-page`.")

    return "\n".join(lines) + "\n"


def store_report(
    *,
    docs_dir: str,
    exchange: str | None = None,
    section: str | None = None,
) -> dict[str, Any]:
    """Query the store DB and return a summary of what's currently stored."""
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        generated_at = now_iso_utc()

        # Inventories: count + latest per exchange/section.
        inv_rows = conn.execute(
            "SELECT exchange_id, section_id, COUNT(*) AS cnt, MAX(generated_at) AS latest "
            "FROM inventories GROUP BY exchange_id, section_id ORDER BY exchange_id, section_id;"
        ).fetchall()
        inventories = [
            {"exchange": str(r["exchange_id"]), "section": str(r["section_id"]),
             "count": int(r["cnt"]), "latest": str(r["latest"])}
            for r in inv_rows
            if (not exchange or str(r["exchange_id"]) == exchange)
            and (not section or str(r["section_id"]) == section)
        ]

        # Inventory entries: status breakdown for the latest inventory per section.
        inv_entry_rows = conn.execute(
            """
SELECT i.exchange_id, i.section_id, ie.status, COUNT(*) AS cnt
FROM inventory_entries ie
JOIN inventories i ON i.id = ie.inventory_id
WHERE i.id IN (
    SELECT MAX(id) FROM inventories GROUP BY exchange_id, section_id
)
GROUP BY i.exchange_id, i.section_id, ie.status
ORDER BY i.exchange_id, i.section_id, ie.status;
"""
        ).fetchall()
        entry_status: dict[str, dict[str, int]] = {}
        for r in inv_entry_rows:
            key = f"{r['exchange_id']}/{r['section_id']}"
            if exchange and str(r["exchange_id"]) != exchange:
                continue
            if section and str(r["section_id"]) != section:
                continue
            entry_status.setdefault(key, {})[str(r["status"])] = int(r["cnt"])

        # Pages: count, domain breakdown, total word count.
        where_parts: list[str] = []
        params: list[Any] = []
        if exchange:
            where_parts.append("p.canonical_url LIKE ?")
            params.append(f"%{exchange}%")

        page_sql = "SELECT COUNT(*) AS cnt, COALESCE(SUM(p.word_count), 0) AS total_wc FROM pages p"
        if where_parts:
            page_sql += " WHERE " + " AND ".join(where_parts)
        page_row = conn.execute(page_sql, tuple(params)).fetchone()
        page_count = int(page_row["cnt"] or 0)
        total_word_count = int(page_row["total_wc"] or 0)

        # Domain breakdown (top 20).
        domain_rows = conn.execute(
            "SELECT SUBSTR(canonical_url, 1, INSTR(SUBSTR(canonical_url, 9), '/') + 8) AS domain, "
            "COUNT(*) AS cnt FROM pages GROUP BY domain ORDER BY cnt DESC LIMIT 20;"
        ).fetchall()
        domains = [{"domain": str(r["domain"]), "count": int(r["cnt"])} for r in domain_rows]

        # Endpoints.
        ep_sql = "SELECT exchange, section, protocol, COUNT(*) AS cnt FROM endpoints"
        ep_where: list[str] = []
        ep_params: list[Any] = []
        if exchange:
            ep_where.append("exchange = ?")
            ep_params.append(exchange)
        if section:
            ep_where.append("section = ?")
            ep_params.append(section)
        if ep_where:
            ep_sql += " WHERE " + " AND ".join(ep_where)
        ep_sql += " GROUP BY exchange, section, protocol ORDER BY exchange, section, protocol;"
        ep_rows = conn.execute(ep_sql, tuple(ep_params)).fetchall()
        endpoints = [
            {"exchange": str(r["exchange"]), "section": str(r["section"]),
             "protocol": str(r["protocol"]), "count": int(r["cnt"])}
            for r in ep_rows
        ]
        total_endpoints = sum(e["count"] for e in endpoints)

        # Review queue.
        rq_rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM review_queue GROUP BY status;"
        ).fetchall()
        review_queue = {str(r["status"]): int(r["cnt"]) for r in rq_rows}

        return {
            "cmd": "store-report",
            "schema_version": "v1",
            "docs_dir": str(Path(docs_dir)),
            "generated_at": generated_at,
            "filters": {"exchange": exchange, "section": section},
            "inventories": inventories,
            "inventory_entries": entry_status,
            "pages": {
                "count": page_count,
                "total_word_count": total_word_count,
                "domains": domains,
            },
            "endpoints": {
                "total": total_endpoints,
                "by_section": endpoints,
            },
            "review_queue": review_queue,
        }
    finally:
        conn.close()


def render_store_report_markdown(data: dict[str, Any]) -> str:
    """Format store_report() output into readable markdown."""
    lines: list[str] = []
    lines.append("# CEX API Docs Store Report")
    lines.append("")
    lines.append(f"- **Generated:** `{data.get('generated_at', '')}`")
    lines.append(f"- **Store:** `{data.get('docs_dir', '')}`")
    filters = data.get("filters") or {}
    if filters.get("exchange") or filters.get("section"):
        lines.append(f"- **Filters:** exchange={filters.get('exchange')}, section={filters.get('section')}")
    lines.append("")

    # Inventories.
    inventories = data.get("inventories") or []
    lines.append("## Inventories")
    lines.append("")
    if inventories:
        lines.append("| Exchange | Section | Count | Latest |")
        lines.append("|---|---|---:|---|")
        for inv in inventories:
            lines.append(f"| {inv['exchange']} | {inv['section']} | {inv['count']} | {inv['latest']} |")
    else:
        lines.append("No inventories found.")
    lines.append("")

    # Inventory entry status.
    entry_status = data.get("inventory_entries") or {}
    if entry_status:
        lines.append("## Latest Inventory Entry Status")
        lines.append("")
        lines.append("| Exchange/Section | Fetched | Pending | Error | Skipped |")
        lines.append("|---|---:|---:|---:|---:|")
        for key, statuses in sorted(entry_status.items()):
            lines.append(
                f"| {key} | {statuses.get('fetched', 0)} | {statuses.get('pending', 0)} "
                f"| {statuses.get('error', 0)} | {statuses.get('skipped', 0)} |"
            )
        lines.append("")

    # Pages.
    pages = data.get("pages") or {}
    lines.append("## Pages")
    lines.append("")
    lines.append(f"- **Total pages:** {pages.get('count', 0)}")
    lines.append(f"- **Total word count:** {pages.get('total_word_count', 0):,}")
    domains = pages.get("domains") or []
    if domains:
        lines.append("")
        lines.append("### Top Domains")
        lines.append("")
        lines.append("| Domain | Pages |")
        lines.append("|---|---:|")
        for d in domains:
            lines.append(f"| {d['domain']} | {d['count']} |")
    lines.append("")

    # Endpoints.
    ep = data.get("endpoints") or {}
    lines.append("## Endpoints")
    lines.append("")
    lines.append(f"- **Total:** {ep.get('total', 0)}")
    by_section = ep.get("by_section") or []
    if by_section:
        lines.append("")
        lines.append("| Exchange | Section | Protocol | Count |")
        lines.append("|---|---|---|---:|")
        for e in by_section:
            lines.append(f"| {e['exchange']} | {e['section']} | {e['protocol']} | {e['count']} |")
    lines.append("")

    # Review queue.
    rq = data.get("review_queue") or {}
    lines.append("## Review Queue")
    lines.append("")
    if rq:
        for status, count in sorted(rq.items()):
            lines.append(f"- **{status}:** {count}")
    else:
        lines.append("Review queue is empty.")
    lines.append("")

    return "\n".join(lines) + "\n"


def render_coverage_report_markdown(audit_result: Any) -> str:
    """Render a CoverageAuditResult into readable markdown.

    Accepts either a CoverageAuditResult dataclass or a dict with the same shape.
    """
    lines: list[str] = []
    lines.append("# Crawl Coverage Report")
    lines.append("")
    lines.append(f"- **Generated:** `{now_iso_utc()}`")

    # Handle both dataclass and dict forms.
    if hasattr(audit_result, "overall_coverage_pct"):
        overall_pct = audit_result.overall_coverage_pct
        total_missing = audit_result.total_missing
        total_stale = audit_result.total_stale
        sections = audit_result.sections
    else:
        overall_pct = audit_result.get("overall_coverage_pct", 0)
        total_missing = audit_result.get("total_missing", 0)
        total_stale = audit_result.get("total_stale", 0)
        sections = audit_result.get("sections", [])

    lines.append(f"- **Overall Coverage:** {overall_pct:.1f}%")
    lines.append(f"- **Total Missing:** {total_missing}")
    lines.append(f"- **Total Stale:** {total_stale}")
    lines.append(f"- **Sections Checked:** {len(sections)}")
    lines.append("")

    # Per-section table.
    lines.append("## Per-Section Coverage")
    lines.append("")
    lines.append("| Exchange | Section | Discovered | Stored | Missing | Stale | Coverage % | Methods |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|")

    for sc in sections:
        if hasattr(sc, "exchange_id"):
            ex_id = sc.exchange_id
            sec_id = sc.section_id
            discovered = sc.discovered_urls
            stored = sc.stored_urls
            missing = len(sc.missing_urls)
            stale = len(sc.stale_urls)
            cov_pct = sc.coverage_pct
            methods = ", ".join(sc.discovery_methods_used)
        else:
            ex_id = sc.get("exchange_id", "")
            sec_id = sc.get("section_id", "")
            discovered = sc.get("discovered_urls", 0)
            stored = sc.get("stored_urls", 0)
            missing = sc.get("missing_count", 0)
            stale = sc.get("stale_count", 0)
            cov_pct = sc.get("coverage_pct", 0)
            methods = ", ".join(sc.get("discovery_methods_used", []))
        lines.append(
            f"| {ex_id} | {sec_id} | {discovered} | {stored} | {missing} | {stale} | {cov_pct:.1f} | {methods} |"
        )

    # Missing URLs (actionable).
    has_missing = False
    for sc in sections:
        missing_urls = getattr(sc, "missing_urls", None) or (sc.get("missing_urls") if isinstance(sc, dict) else None)
        if missing_urls:
            has_missing = True
            break

    if has_missing:
        lines.append("")
        lines.append("## Missing URLs (Not in Store)")
        lines.append("")
        count = 0
        for sc in sections:
            if hasattr(sc, "exchange_id"):
                ex_id = sc.exchange_id
                sec_id = sc.section_id
                missing_urls_list = sc.missing_urls
            else:
                ex_id = sc.get("exchange_id", "")
                sec_id = sc.get("section_id", "")
                missing_urls_list = sc.get("missing_urls", [])
            for url in missing_urls_list[:20]:  # Cap per section.
                lines.append(f"- `{ex_id}/{sec_id}`: {url}")
                count += 1
                if count >= 100:
                    break
            if count >= 100:
                lines.append("- ... (truncated at 100)")
                break

    # Warnings.
    has_warnings = False
    for sc in sections:
        warn_list = getattr(sc, "warnings", None) or (sc.get("warnings") if isinstance(sc, dict) else None)
        if warn_list:
            has_warnings = True
            break

    if has_warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for sc in sections:
            if hasattr(sc, "exchange_id"):
                ex_id = sc.exchange_id
                sec_id = sc.section_id
                warn_list = sc.warnings
            else:
                ex_id = sc.get("exchange_id", "")
                sec_id = sc.get("section_id", "")
                warn_list = sc.get("warnings", [])
            for w in warn_list:
                lines.append(f"- `{ex_id}/{sec_id}`: {w}")

    lines.append("")
    return "\n".join(lines) + "\n"
