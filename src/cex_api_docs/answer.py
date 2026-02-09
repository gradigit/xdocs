from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .db import open_db
from .registry import load_registry


def _normalize_question(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip()).lower()


def _sections_present(conn, *, seed_prefixes: dict[str, str]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for section_id, prefix in seed_prefixes.items():
        row = conn.execute(
            "SELECT 1 FROM pages WHERE canonical_url LIKE ? LIMIT 1;",
            (prefix + "%",),
        ).fetchone()
        if row is not None:
            options.append({"exchange": "binance", "section": section_id})
    return options


def _search_top_page(conn, *, query: str, url_prefix: str) -> dict[str, Any] | None:
    # Prefer matches inside the section prefix.
    row = conn.execute(
        """
SELECT
  p.canonical_url, p.crawled_at, p.content_hash, p.path_hash, p.markdown_path
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ? AND p.canonical_url LIKE ?
ORDER BY bm25(pages_fts)
LIMIT 1;
""",
        (query, url_prefix + "%"),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _make_excerpt(md: str, *, needle_re: re.Pattern[str], target_len: int = 400, hard_max: int = 600) -> tuple[str, int, int]:
    m = needle_re.search(md)
    if not m:
        # Fallback: first N chars.
        end = min(len(md), target_len)
        excerpt = md[:end]
        return excerpt, 0, end

    idx = m.start()
    start = max(0, idx - target_len // 2)
    end = min(len(md), start + target_len)
    if end - start > hard_max:
        end = start + hard_max
    excerpt = md[start:end]
    return excerpt, start, end


def _claim(claim_id: str, *, text: str, citation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": claim_id,
        "kind": "SOURCE",
        "text": text,
        "citations": [citation],
    }


def _extract_weight_from_excerpt(excerpt: str) -> int | None:
    # Very conservative: look for "weight ... <int>" patterns.
    m = re.search(r"\bweight\b[^0-9]{0,20}(\d{1,9})\b", excerpt, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def answer_question(
    *,
    docs_dir: str,
    question: str,
    clarification: str | None = None,
) -> dict[str, Any]:
    db_path = Path(docs_dir) / "db" / "docs.db"
    if not db_path.exists():
        return {
            "ok": True,
            "schema_version": "v1",
            "status": "unknown",
            "question": question,
            "normalized_question": _normalize_question(question),
            "clarification": None,
            "claims": [],
            "notes": ["Store not initialized. Run `cex-api-docs init` and `cex-api-docs crawl` first."],
        }

    norm = _normalize_question(question)
    if "binance" not in norm:
        return {
            "ok": True,
            "schema_version": "v1",
            "status": "unknown",
            "question": question,
            "normalized_question": norm,
            "clarification": None,
            "claims": [],
            "notes": ["Only Binance is supported by `answer` in v1 MVP. Specify the exchange or extend the assembler."],
        }

    repo_root = Path(__file__).resolve().parents[2]
    reg = load_registry(repo_root / "data" / "exchanges.yaml")
    binance = reg.get_exchange("binance")
    seed_prefixes = {sec.section_id: sec.seed_urls[0] for sec in binance.sections if sec.seed_urls}

    conn = open_db(db_path)
    try:
        # Clarification: "unified trading" is ambiguous.
        if "unified trading" in norm and not clarification:
            present = _sections_present(conn, seed_prefixes=seed_prefixes)
            options = [
                {
                    "id": f"{o['exchange']}:{o['section']}",
                    "label": f"{o['exchange']}:{o['section']}",
                    "exchange": o["exchange"],
                    "section": o["section"],
                }
                for o in present
            ]
            return {
                "ok": True,
                "schema_version": "v1",
                "status": "needs_clarification",
                "question": question,
                "normalized_question": norm,
                "clarification": {
                    "prompt": "What does 'unified trading' refer to in Binance docs for this question?",
                    "options": options,
                },
                "claims": [],
                "notes": ["Re-run with `--clarification <id>` (example: binance:portfolio_margin)."],
            }

        unified_section = None
        if clarification:
            # Expect "binance:<section_id>".
            parts = clarification.split(":", 1)
            if len(parts) == 2 and parts[0] == "binance":
                unified_section = parts[1]
        if "unified trading" in norm and not unified_section:
            return {
                "ok": True,
                "schema_version": "v1",
                "status": "unknown",
                "question": question,
                "normalized_question": norm,
                "clarification": None,
                "claims": [],
                "notes": ["Missing/invalid clarification for 'unified trading'. Use `--clarification binance:<section_id>`."],
            }

        claims: list[dict[str, Any]] = []
        notes: list[str] = []
        c = 1

        # Part 1: rate limit difference between unified section and spot.
        if unified_section:
            rate_limit_claims: list[tuple[str, str]] = []  # (claim_id, excerpt_text)
            for section_id, query in ((unified_section, "rate limit"), ("spot", "rate limit")):
                prefix = seed_prefixes.get(section_id)
                if not prefix:
                    notes.append(f"No registry seed URL for binance section '{section_id}'.")
                    continue
                top = _search_top_page(conn, query=query, url_prefix=prefix)
                if not top:
                    notes.append(f"No crawled pages found for query '{query}' under {prefix}.")
                    continue
                md_path = Path(top["markdown_path"]) if top.get("markdown_path") else None
                if not md_path or not md_path.exists():
                    notes.append(f"Missing markdown for {top['canonical_url']}.")
                    continue
                md = md_path.read_text(encoding="utf-8")
                excerpt, start, end = _make_excerpt(md, needle_re=re.compile(r"rate\s+limit", re.IGNORECASE))
                citation = {
                    "url": top["canonical_url"],
                    "crawled_at": top["crawled_at"],
                    "content_hash": top["content_hash"],
                    "path_hash": top["path_hash"],
                    "excerpt": excerpt,
                    "excerpt_start": start,
                    "excerpt_end": end,
                    "field_name": "rate_limit",
                }
                claims.append(
                    _claim(
                        f"c{c}",
                        text=f"[{section_id}] {excerpt}",
                        citation=citation,
                    )
                )
                rate_limit_claims.append((f"c{c}", excerpt))
                c += 1

            # Derived diff when both excerpts contain an explicit numeric weight.
            if len(rate_limit_claims) == 2:
                w1 = _extract_weight_from_excerpt(rate_limit_claims[0][1])
                w2 = _extract_weight_from_excerpt(rate_limit_claims[1][1])
                if w1 is not None and w2 is not None:
                    claims.append(
                        {
                            "id": f"c{c}",
                            "kind": "DERIVED",
                            "text": f"[DERIVED] rate_limit.weight diff (first - second): {w1} - {w2} = {w1 - w2}",
                            "citations": [],
                            "derived": {"op": "diff", "inputs": [{"claim_id": rate_limit_claims[0][0]}, {"claim_id": rate_limit_claims[1][0]}]},
                        }
                    )
                    c += 1

        # Part 2: Portfolio Margin API key permissions for balance lookup (best-effort cite-only).
        pm_prefix = seed_prefixes.get("portfolio_margin")
        if pm_prefix:
            top = _search_top_page(conn, query="permission OR permissions OR api key", url_prefix=pm_prefix)
            if top:
                md_path = Path(top["markdown_path"]) if top.get("markdown_path") else None
                if md_path and md_path.exists():
                    md = md_path.read_text(encoding="utf-8")
                    excerpt, start, end = _make_excerpt(md, needle_re=re.compile(r"permission|api\s+key", re.IGNORECASE))
                    citation = {
                        "url": top["canonical_url"],
                        "crawled_at": top["crawled_at"],
                        "content_hash": top["content_hash"],
                        "path_hash": top["path_hash"],
                        "excerpt": excerpt,
                        "excerpt_start": start,
                        "excerpt_end": end,
                        "field_name": "required_permissions",
                    }
                    claims.append(_claim(f"c{c}", text=f"[portfolio_margin] {excerpt}", citation=citation))
                    c += 1
                else:
                    notes.append(f"Missing markdown for {top['canonical_url']}.")
            else:
                notes.append("No Portfolio Margin docs page matched permission query in local store.")
        else:
            notes.append("Binance portfolio_margin section seed not found in registry.")

        status = "ok" if claims else "unknown"
        return {
            "ok": True,
            "schema_version": "v1",
            "status": status,
            "question": question,
            "normalized_question": norm,
            "clarification": None,
            "claims": claims,
            "notes": notes,
        }
    finally:
        conn.close()
