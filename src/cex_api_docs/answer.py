from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .db import open_db
from .registry import load_registry


def _normalize_question(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip()).lower()


def _sections_present(conn, *, exchange_id: str, seed_prefixes: dict[str, str]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for section_id, prefix in seed_prefixes.items():
        row = conn.execute(
            "SELECT 1 FROM pages WHERE canonical_url LIKE ? LIMIT 1;",
            (prefix + "%",),
        ).fetchone()
        if row is not None:
            options.append({"exchange": exchange_id, "section": section_id})
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
    # Conservative: require an obvious "weight is 10" / "weight: 10" pattern.
    m = re.search(r"\bweight\b\s*(?:is|=|:)?\s*(\d{1,9})\b", excerpt, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _wants_rate_limit(norm: str) -> bool:
    return bool(re.search(r"\brate\s+limit\b|\bweight\b", norm, flags=re.IGNORECASE))


def _wants_permissions(norm: str) -> bool:
    return bool(re.search(r"\bpermissions?\b|\bapi\s+key\b|\bscopes?\b", norm, flags=re.IGNORECASE))


def _looks_like_permissions_requirement(text: str) -> bool:
    # Stay conservative: do not label something "required_permissions" unless the excerpt
    # is clearly about permissions as a requirement (not merely mentioning API keys).
    return bool(
        re.search(
            r"(?im)^\s*#+\s*permissions?\b|"
            r"\brequired\s+permissions?\b|"
            r"\bpermissions?\s*[:\-]\s*\w|"
            r"\bapi\s+key\s+permissions?\b|"
            r"\bpermission\s+required\b|"
            r"\benable\s+reading\b|"
            r"\benable\s+withdrawals?\b",
            text,
        )
    )


def _search_pages(conn, *, query: str, url_prefix: str, limit: int = 5) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
SELECT
  p.canonical_url, p.crawled_at, p.content_hash, p.path_hash, p.markdown_path
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ? AND p.canonical_url LIKE ?
ORDER BY bm25(pages_fts)
LIMIT ?;
""",
        (query, url_prefix + "%", int(limit)),
    )
    return [dict(r) for r in cur.fetchall()]


def _detect_exchange(norm: str, reg) -> list:
    """Match exchange names/IDs in the normalized question text."""
    matches = []
    for ex in reg.exchanges:
        ex_id = ex.exchange_id.lower()
        display = ex.display_name.lower()
        if ex_id in norm or display in norm:
            matches.append(ex)
    return matches


def _generic_search_answer(
    conn, *, exchange, question: str, norm: str,
) -> dict[str, Any]:
    """Generic cite-only answer for any exchange: FTS search across all sections."""
    seed_prefixes = {sec.section_id: sec.seed_urls[0] for sec in exchange.sections if sec.seed_urls}
    # Also search by allowed_domains as a fallback prefix.
    domain_prefixes = [f"https://{d}" for d in (exchange.allowed_domains or [])]

    claims: list[dict[str, Any]] = []
    notes: list[str] = []
    c = 1

    # Build FTS query from question terms (strip common words).
    terms = [w for w in re.sub(r"[^\w\s]", " ", norm).split() if len(w) > 2 and w not in {
        "the", "and", "for", "what", "how", "does", "this", "that", "with", "from",
        "are", "can", "api", exchange.exchange_id.lower(),
    }]
    fts_query = " OR ".join(terms[:8]) if terms else norm

    # Search each section, collect top results.
    for section_id, prefix in seed_prefixes.items():
        candidates = _search_pages(conn, query=fts_query, url_prefix=prefix, limit=3)
        for cand in candidates:
            md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
            if not md_path or not md_path.exists():
                continue
            md = md_path.read_text(encoding="utf-8")
            needle_re = re.compile("|".join(re.escape(t) for t in terms[:4]) if terms else re.escape(norm[:30]), re.IGNORECASE)
            excerpt, start, end = _make_excerpt(md, needle_re=needle_re)
            citation = {
                "url": cand["canonical_url"],
                "crawled_at": cand["crawled_at"],
                "content_hash": cand["content_hash"],
                "path_hash": cand["path_hash"],
                "excerpt": excerpt,
                "excerpt_start": start,
                "excerpt_end": end,
            }
            claims.append(_claim(f"c{c}", text=f"[{exchange.exchange_id}:{section_id}] {excerpt}", citation=citation))
            c += 1
            if c > 10:
                break
        if c > 10:
            break

    # Fallback: search by domain prefix if no section-based results.
    if not claims:
        for dp in domain_prefixes:
            candidates = _search_pages(conn, query=fts_query, url_prefix=dp, limit=5)
            for cand in candidates:
                md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
                if not md_path or not md_path.exists():
                    continue
                md = md_path.read_text(encoding="utf-8")
                needle_re = re.compile("|".join(re.escape(t) for t in terms[:4]) if terms else re.escape(norm[:30]), re.IGNORECASE)
                excerpt, start, end = _make_excerpt(md, needle_re=needle_re)
                citation = {
                    "url": cand["canonical_url"],
                    "crawled_at": cand["crawled_at"],
                    "content_hash": cand["content_hash"],
                    "path_hash": cand["path_hash"],
                    "excerpt": excerpt,
                    "excerpt_start": start,
                    "excerpt_end": end,
                }
                claims.append(_claim(f"c{c}", text=f"[{exchange.exchange_id}] {excerpt}", citation=citation))
                c += 1
                if c > 10:
                    break
            if claims:
                break

    if not claims:
        notes.append(f"No crawled pages found for {exchange.exchange_id} matching the question. Run `cex-api-docs sync --exchange {exchange.exchange_id}` first.")

    return {
        "ok": True,
        "schema_version": "v1",
        "status": "ok" if claims else "unknown",
        "question": question,
        "normalized_question": norm,
        "clarification": None,
        "claims": claims,
        "notes": notes,
    }


def _binance_answer(
    conn, *, reg, question: str, norm: str, clarification: str | None,
) -> dict[str, Any]:
    """Binance-specific answer logic with rate-limit comparison and permissions heuristics."""
    binance = reg.get_exchange("binance")
    seed_prefixes = {sec.section_id: sec.seed_urls[0] for sec in binance.sections if sec.seed_urls}

    # Clarification: "unified trading" is ambiguous.
    if "unified trading" in norm and not clarification:
        present = _sections_present(conn, exchange_id="binance", seed_prefixes=seed_prefixes)
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
        # Expect "<exchange_id>:<section_id>".
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
    missing: list[str] = []
    c = 1

    wants_rate = _wants_rate_limit(norm)
    wants_perm = _wants_permissions(norm)

    # Part 1: rate-limit comparison between unified section and spot.
    rate_limit_claims: list[tuple[str, str]] = []  # (claim_id, excerpt_text)
    if wants_rate and unified_section:
        for section_id, query in ((unified_section, "rate limit OR weight"), ("spot", "rate limit OR weight")):
            prefix = seed_prefixes.get(section_id)
            if not prefix:
                notes.append(f"No registry seed URL for binance section '{section_id}'.")
                continue
            candidates = _search_pages(conn, query=query, url_prefix=prefix, limit=5)
            if not candidates:
                notes.append(f"No crawled pages found for query '{query}' under {prefix}.")
                continue
            picked: dict[str, Any] | None = None
            picked_excerpt: tuple[str, int, int] | None = None
            for cand in candidates:
                md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
                if not md_path or not md_path.exists():
                    continue
                md = md_path.read_text(encoding="utf-8")
                if not re.search(r"rate\s+limit|\bweight\b", md, flags=re.IGNORECASE):
                    continue
                picked = cand
                picked_excerpt = _make_excerpt(md, needle_re=re.compile(r"rate\s+limit|\bweight\b", re.IGNORECASE))
                break
            if not picked or not picked_excerpt:
                notes.append(f"No stored markdown under {prefix} contained obvious rate-limit text.")
                continue

            excerpt, start, end = picked_excerpt
            citation = {
                "url": picked["canonical_url"],
                "crawled_at": picked["crawled_at"],
                "content_hash": picked["content_hash"],
                "path_hash": picked["path_hash"],
                "excerpt": excerpt,
                "excerpt_start": start,
                "excerpt_end": end,
                "field_name": "rate_limit",
            }
            claims.append(_claim(f"c{c}", text=f"[{section_id}] {excerpt}", citation=citation))
            rate_limit_claims.append((f"c{c}", excerpt))
            c += 1

        if len(rate_limit_claims) != 2:
            missing.append("rate_limit_comparison")
        else:
            # Derived diff when both excerpts contain an explicit numeric weight.
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

    # Part 2: API key permissions (only if the question asks).
    if wants_perm:
        pm_prefix = seed_prefixes.get("portfolio_margin")
        prefixes: list[str] = []
        if pm_prefix:
            prefixes.append(pm_prefix)
        # Portfolio margin key permissions are often described in general derivatives onboarding docs.
        prefixes.append("https://developers.binance.com/docs/derivatives/")
        spot_prefix = seed_prefixes.get("spot")
        if spot_prefix:
            prefixes.append(spot_prefix)

        # De-dupe while preserving order.
        seen_p: set[str] = set()
        prefixes = [p for p in prefixes if p and not (p in seen_p or seen_p.add(p))]

        picked: dict[str, Any] | None = None
        picked_excerpt: tuple[str, int, int] | None = None
        picked_prefix: str | None = None

        for prefix in prefixes:
            candidates = _search_pages(
                conn,
                query="permissions OR permission OR \"api key permissions\" OR \"required permissions\" OR \"enable reading\" OR \"enable withdrawals\"",
                url_prefix=prefix,
                limit=10,
            )
            for cand in candidates:
                md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
                if not md_path or not md_path.exists():
                    continue
                md = md_path.read_text(encoding="utf-8")
                if not _looks_like_permissions_requirement(md):
                    continue
                excerpt, start, end = _make_excerpt(
                    md,
                    needle_re=re.compile(r"permissions?|api\s+key\s+permissions?|required\s+permissions?|enable\s+reading|enable\s+withdrawals?", re.IGNORECASE),
                )
                if not _looks_like_permissions_requirement(excerpt):
                    continue
                picked = cand
                picked_excerpt = (excerpt, start, end)
                picked_prefix = prefix
                break
            if picked and picked_excerpt:
                break

        if not picked or not picked_excerpt:
            notes.append("No crawled Binance docs page contained an explicit API key permissions requirement in local store.")
            missing.append("required_permissions")
        else:
            excerpt, start, end = picked_excerpt
            citation = {
                "url": picked["canonical_url"],
                "crawled_at": picked["crawled_at"],
                "content_hash": picked["content_hash"],
                "path_hash": picked["path_hash"],
                "excerpt": excerpt,
                "excerpt_start": start,
                "excerpt_end": end,
                "field_name": "required_permissions",
            }
            label = "portfolio_margin" if (picked_prefix == pm_prefix) else "binance_docs"
            claims.append(_claim(f"c{c}", text=f"[{label}] {excerpt}", citation=citation))
            c += 1

    # If no specialized logic triggered, fall through to generic search.
    if not claims and not unified_section:
        return _generic_search_answer(conn, exchange=binance, question=question, norm=norm)

    # Status policy: only "ok" when every requested part is cite-backed.
    if wants_rate and unified_section and "rate_limit_comparison" in missing:
        status = "unknown"
    elif wants_perm and "required_permissions" in missing:
        status = "unknown"
    else:
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
        "missing": missing,
    }


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
            "notes": ["Store not initialized. Run `cex-api-docs init` and `cex-api-docs sync` first."],
        }

    norm = _normalize_question(question)
    repo_root = Path(__file__).resolve().parents[2]
    reg = load_registry(repo_root / "data" / "exchanges.yaml")

    # Detect which exchange(s) the question is about.
    matched = _detect_exchange(norm, reg)

    if not matched:
        available = sorted(ex.exchange_id for ex in reg.exchanges)
        return {
            "ok": True,
            "schema_version": "v1",
            "status": "unknown",
            "question": question,
            "normalized_question": norm,
            "clarification": None,
            "claims": [],
            "notes": [
                "Could not determine exchange from question. "
                f"Available exchanges: {', '.join(available)}. "
                "Include the exchange name in your question."
            ],
        }

    if len(matched) > 1:
        # Multiple exchanges mentioned — use clarification if provided, otherwise ask.
        if clarification:
            parts = clarification.split(":", 1)
            target_ex_id = parts[0]
            matched = [ex for ex in matched if ex.exchange_id == target_ex_id]
            if not matched:
                return {
                    "ok": True,
                    "schema_version": "v1",
                    "status": "unknown",
                    "question": question,
                    "normalized_question": norm,
                    "clarification": None,
                    "claims": [],
                    "notes": [f"Clarification exchange '{target_ex_id}' not found among matched exchanges."],
                }
        else:
            options = [
                {
                    "id": ex.exchange_id,
                    "label": ex.display_name,
                    "exchange": ex.exchange_id,
                }
                for ex in matched
            ]
            return {
                "ok": True,
                "schema_version": "v1",
                "status": "needs_clarification",
                "question": question,
                "normalized_question": norm,
                "clarification": {
                    "prompt": "Multiple exchanges detected. Which exchange is this question about?",
                    "options": options,
                },
                "claims": [],
                "notes": ["Re-run with `--clarification <exchange_id>` or `--clarification <exchange_id>:<section_id>`."],
            }

    exchange = matched[0]

    conn = open_db(db_path)
    try:
        # Binance: use richer Binance-specific logic.
        if exchange.exchange_id == "binance":
            return _binance_answer(conn, reg=reg, question=question, norm=norm, clarification=clarification)

        # All other exchanges: generic cite-only search.
        return _generic_search_answer(conn, exchange=exchange, question=question, norm=norm)
    finally:
        conn.close()
