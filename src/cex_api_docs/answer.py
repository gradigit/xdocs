from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import logging

from .classify import classify_input
from .db import open_db
from .fts_util import sanitize_fts_query, build_fts_query, extract_search_terms
from .registry import load_registry

logger = logging.getLogger(__name__)


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
ORDER BY rank
LIMIT 1;
""",
        (sanitize_fts_query(query), url_prefix + "%"),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _make_excerpt(md: str, *, needle_re: re.Pattern[str], target_len: int = 400, hard_max: int = 600) -> tuple[str, int, int]:
    m = needle_re.search(md)
    if not m:
        # Fallback: first N chars, snapped to boundary.
        end = min(len(md), target_len)
        end = _snap_end_forward(md, end)
        excerpt = _clean_excerpt(md[:end])
        return excerpt, 0, end

    idx = m.start()
    start = max(0, idx - target_len // 2)
    end = min(len(md), start + target_len)
    if end - start > hard_max:
        end = start + hard_max

    # Snap start backward to nearest newline or whitespace boundary.
    start = _snap_start_backward(md, start)
    # Snap end forward to nearest sentence end or paragraph break.
    end = _snap_end_forward(md, end)
    # Enforce hard max after snapping.
    if end - start > hard_max:
        end = start + hard_max
        end = _snap_end_forward(md, end)

    excerpt = _clean_excerpt(md[start:end])
    return excerpt, start, end


def _snap_start_backward(md: str, pos: int) -> int:
    """Snap start position backward to nearest newline or word boundary."""
    if pos == 0:
        return 0
    # Look for newline within 50 chars backward.
    search_start = max(0, pos - 50)
    nl = md.rfind("\n", search_start, pos)
    if nl != -1:
        return nl + 1
    # Fall back to word boundary.
    sp = md.rfind(" ", search_start, pos)
    if sp != -1:
        return sp + 1
    return pos


def _snap_end_forward(md: str, pos: int) -> int:
    """Snap end position forward to nearest sentence end or paragraph break."""
    if pos >= len(md):
        return len(md)
    # Look for paragraph break (double newline) within 80 chars.
    para = md.find("\n\n", pos, min(len(md), pos + 80))
    if para != -1:
        return para
    # Look for sentence-ending punctuation followed by space or newline.
    for i in range(pos, min(len(md), pos + 80)):
        if md[i] in ".!?" and (i + 1 >= len(md) or md[i + 1] in " \n\t"):
            return i + 1
    # Fall back to newline.
    nl = md.find("\n", pos, min(len(md), pos + 80))
    if nl != -1:
        return nl
    # Fall back to word boundary.
    sp = md.find(" ", pos, min(len(md), pos + 50))
    if sp != -1:
        return sp
    return pos


def _clean_excerpt(text: str) -> str:
    """Strip zero-width characters and broken markdown fragments."""
    # Remove zero-width chars.
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)
    # Strip leading/trailing whitespace.
    return text.strip()


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
ORDER BY rank
LIMIT ?;
""",
        (sanitize_fts_query(query), url_prefix + "%", int(limit)),
    )
    return [dict(r) for r in cur.fetchall()]


def _search_pages_with_semantic(
    conn: sqlite3.Connection,
    *,
    query: str,
    url_prefix: str,
    limit: int = 5,
    docs_dir: str | None = None,
    exchange: str | None = None,
) -> list[dict[str, Any]]:
    """Search pages via FTS5 and semantic search (co-primary), interleaving results."""
    # FTS5 search.
    fts_results = _search_pages(conn, query=query, url_prefix=url_prefix, limit=limit)

    # Semantic search (if available).
    sem_results_raw: list[dict[str, Any]] = []
    if docs_dir is not None:
        try:
            from .semantic import semantic_search
            sem_hits = semantic_search(
                docs_dir=docs_dir,
                query=query,
                exchange=exchange,
                limit=limit,
                query_type="hybrid",
                rerank="auto",
            )
            for sr in sem_hits:
                url = sr.get("url", "")
                if url_prefix and not url.startswith(url_prefix):
                    continue
                # Convert semantic result to the format _search_pages returns.
                row = conn.execute(
                    "SELECT canonical_url, crawled_at, content_hash, path_hash, markdown_path FROM pages WHERE canonical_url = ?;",
                    (url,),
                ).fetchone()
                if row:
                    sem_results_raw.append(dict(row))
        except ImportError:
            # Semantic search extras not installed — expected in minimal installs.
            pass
        except Exception:
            logger.warning("Semantic search failed (non-fatal)", exc_info=True)

    if not sem_results_raw:
        return fts_results[:limit]
    if not fts_results:
        return sem_results_raw[:limit]

    # Interleaved merge: alternate FTS and semantic results, dedup by URL.
    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    fts_iter = iter(fts_results)
    sem_iter = iter(sem_results_raw)
    fts_done = False
    sem_done = False

    while len(merged) < limit:
        # Take from FTS.
        if not fts_done:
            try:
                item = next(fts_iter)
                url = item.get("canonical_url", "")
                if url not in seen_urls:
                    seen_urls.add(url)
                    merged.append(item)
                    if len(merged) >= limit:
                        break
            except StopIteration:
                fts_done = True

        # Take from semantic.
        if not sem_done:
            try:
                item = next(sem_iter)
                url = item.get("canonical_url", "")
                if url not in seen_urls:
                    seen_urls.add(url)
                    merged.append(item)
            except StopIteration:
                sem_done = True

        if fts_done and sem_done:
            break

    return merged[:limit]


def _search_endpoints_for_answer(
    conn: sqlite3.Connection,
    *,
    query: str,
    exchange: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search endpoint records and return relevant fields for answer composition."""
    terms = [t for t in re.findall(r"[A-Za-z0-9_]+", query) if len(t) > 1]
    fts_query = build_fts_query(terms) if terms else sanitize_fts_query(query)
    if not fts_query.strip():
        return []

    where = ["endpoints_fts MATCH ?", "endpoints_fts.exchange = ?"]
    params: list[Any] = [fts_query, exchange, int(limit)]

    sql = f"""
SELECT
  endpoints_fts.endpoint_id,
  endpoints_fts.exchange,
  endpoints_fts.section,
  endpoints_fts.method,
  endpoints_fts.path,
  snippet(endpoints_fts, 5, '[', ']', '...', 12) AS snippet,
  rank
FROM endpoints_fts
WHERE {' AND '.join(where)}
ORDER BY rank
LIMIT ?;
"""
    try:
        cur = conn.execute(sql, tuple(params))
    except sqlite3.OperationalError:
        return []

    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        # Get the full endpoint record.
        full = conn.execute("SELECT json FROM endpoints WHERE endpoint_id = ?;", (r["endpoint_id"],)).fetchone()
        record = json.loads(full["json"]) if full else {}
        out.append({
            "endpoint_id": r["endpoint_id"],
            "exchange": r["exchange"],
            "section": r["section"],
            "method": r["method"],
            "path": r["path"],
            "snippet": r["snippet"],
            "record": record,
        })
    return out


def _detect_exchange(norm: str, reg) -> list:
    """Match exchange names/IDs in the normalized question text using word boundaries."""
    matches = []
    for ex in reg.exchanges:
        ex_id = ex.exchange_id.lower()
        display = ex.display_name.lower()
        if re.search(rf"\b{re.escape(ex_id)}\b", norm) or re.search(rf"\b{re.escape(display)}\b", norm):
            matches.append(ex)
    return matches


def _resolve_endpoint_citation_url(
    conn: sqlite3.Connection, *, ep: dict[str, Any], exchange,
) -> str | None:
    """Resolve the best citation URL for an endpoint (docs page > spec URL).

    Priority: docs_url column → query-time FTS resolution → sources[0].url.
    """
    # Fast path: check pre-resolved docs_url column.
    try:
        row = conn.execute(
            "SELECT docs_url FROM endpoints WHERE endpoint_id = ?;",
            (ep["endpoint_id"],),
        ).fetchone()
        if row and row["docs_url"]:
            return row["docs_url"]
    except sqlite3.OperationalError:
        pass  # Column may not exist yet (pre-migration).

    # Query-time fallback: FTS resolution.
    path = ep.get("path", "")
    if path:
        try:
            from .resolve_docs_urls import resolve_docs_url

            docs_url = resolve_docs_url(
                conn,
                path=path,
                exchange=ep["exchange"],
                allowed_domains=exchange.allowed_domains or [],
            )
            if docs_url:
                return docs_url
        except Exception:
            pass

    # Last resort: spec URL from sources[].
    record = ep.get("record", {})
    sources = record.get("sources") or []
    if sources and isinstance(sources[0], dict):
        return sources[0].get("url")

    return None


def _directory_prefix(url: str) -> str:
    """Extract directory prefix from a URL (strip trailing path segment).

    e.g. 'https://example.com/docs/ws/connect' -> 'https://example.com/docs/ws/'
    This ensures searches match sibling pages, not just the exact seed URL.
    """
    # Strip query/fragment.
    clean = url.split("?")[0].split("#")[0]
    if clean.endswith("/"):
        return clean
    # Strip last path segment.
    last_slash = clean.rfind("/")
    if last_slash > 8:  # after https://
        return clean[:last_slash + 1]
    return clean


def _generic_search_answer(
    conn, *, exchange, question: str, norm: str, docs_dir: str | None = None,
) -> dict[str, Any]:
    """Generic cite-only answer for any exchange: FTS search across all sections."""
    # Use directory prefixes (not exact seed URLs) for broader matching.
    seed_prefixes = {}
    for sec in exchange.sections:
        if sec.seed_urls:
            seed_prefixes[sec.section_id] = _directory_prefix(sec.seed_urls[0])
    # Domain-level fallback — always searched regardless of section results.
    domain_prefixes = [f"https://{d}" for d in (exchange.allowed_domains or [])]

    claims: list[dict[str, Any]] = []
    notes: list[str] = []
    c = 1
    max_claims = 10  # Reduced from 20 for precision.

    # Build FTS query from question terms (strip common words).
    terms = extract_search_terms(norm, extra_stopwords={exchange.exchange_id.lower()})
    fts_query = build_fts_query(terms) if terms else sanitize_fts_query(norm)

    # Search endpoints for relevant results.
    endpoint_results = _search_endpoints_for_answer(conn, query=fts_query, exchange=exchange.exchange_id, limit=3)
    for ep in endpoint_results:
        record = ep.get("record", {})
        ep_desc = record.get("description", ep.get("snippet", ""))
        rate_limit = record.get("rate_limit")
        field_status = record.get("field_status", {})

        # If rate_limit is unknown, try to infer from page markdown.
        rate_limit_note = ""
        if field_status.get("rate_limit") in ("unknown", "undocumented") and rate_limit is None:
            inferred = _infer_rate_limit_from_pages(conn, exchange=exchange, path=ep.get("path", ""), terms=terms, docs_dir=docs_dir)
            if inferred:
                rate_limit_note = f" [inferred rate limit: {inferred['text']}]"

        text = f"[{ep['exchange']}:{ep['section']}] {ep.get('method', '')} {ep.get('path', '')} — {ep_desc}{rate_limit_note}"
        citation_url = _resolve_endpoint_citation_url(conn, ep=ep, exchange=exchange)
        citations = [{"url": citation_url}] if citation_url else []
        claims.append({
            "id": f"c{c}",
            "kind": "ENDPOINT",
            "text": text,
            "citations": citations,
            "endpoint_id": ep["endpoint_id"],
        })
        c += 1

    # Search each section using directory prefix, collect top results.
    for section_id, prefix in seed_prefixes.items():
        if c > max_claims:
            break
        candidates = _search_pages_with_semantic(conn, query=fts_query, url_prefix=prefix, limit=3, docs_dir=docs_dir, exchange=exchange.exchange_id)
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
            if c > max_claims:
                break

    # Always search domain-level too (not just as fallback).
    # This catches pages outside section prefixes.
    seen_urls = {cl["citations"][0]["url"] for cl in claims if cl.get("citations")}
    for dp in domain_prefixes:
        if c > max_claims:
            break
        candidates = _search_pages_with_semantic(conn, query=fts_query, url_prefix=dp, limit=5, docs_dir=docs_dir, exchange=exchange.exchange_id)
        for cand in candidates:
            if cand["canonical_url"] in seen_urls:
                continue
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
            seen_urls.add(cand["canonical_url"])
            c += 1
            if c > max_claims:
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


def _infer_rate_limit_from_pages(
    conn: sqlite3.Connection,
    *,
    exchange,
    path: str,
    terms: list[str],
    docs_dir: str | None = None,
) -> dict[str, str] | None:
    """Try to infer rate limit from page markdown near the endpoint path."""
    if not path:
        return None
    seed_prefixes = {sec.section_id: sec.seed_urls[0] for sec in exchange.sections if sec.seed_urls}
    path_tail = path.rstrip("/").rsplit("/", 1)[-1] if "/" in path else path

    for _section_id, prefix in seed_prefixes.items():
        candidates = _search_pages_with_semantic(conn, query=f"rate limit {path_tail}", url_prefix=prefix, limit=3, docs_dir=docs_dir, exchange=exchange.exchange_id if hasattr(exchange, 'exchange_id') else None)
        for cand in candidates:
            md_path = Path(cand["markdown_path"]) if cand.get("markdown_path") else None
            if not md_path or not md_path.exists():
                continue
            md = md_path.read_text(encoding="utf-8")
            # Find the endpoint path in the markdown, then look for weight/limit nearby.
            idx = md.lower().find(path_tail.lower())
            if idx == -1:
                continue
            window = md[max(0, idx - 200):min(len(md), idx + 500)]
            weight = _extract_weight_from_excerpt(window)
            if weight is not None:
                return {"text": f"weight {weight} (inferred)", "source_url": cand["canonical_url"]}
    return None


def _binance_answer(
    conn, *, reg, question: str, norm: str, clarification: str | None, docs_dir: str | None = None,
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
            candidates = _search_pages_with_semantic(conn, query=query, url_prefix=prefix, limit=5, docs_dir=docs_dir, exchange="binance")
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
            candidates = _search_pages_with_semantic(
                conn,
                query="permissions OR permission OR \"api key permissions\" OR \"required permissions\" OR \"enable reading\" OR \"enable withdrawals\"",
                url_prefix=prefix,
                limit=10,
                docs_dir=docs_dir,
                exchange="binance",
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
        return _generic_search_answer(conn, exchange=binance, question=question, norm=norm, docs_dir=docs_dir)

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


def _augment_with_classification(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    *,
    classification,
    exchange,
    docs_dir: str,
) -> dict[str, Any]:
    """Augment answer with classification-specific search results.

    Classification is used as AUGMENTATION: if error_message, prepend error
    search results; if endpoint_path, prepend path lookup. The generic search
    results are always preserved (F4: augment, not replace).
    """
    if classification.confidence < 0.5:
        return result

    existing_ids = {cl.get("endpoint_id") for cl in result.get("claims", []) if cl.get("endpoint_id")}
    existing_urls = set()
    for cl in result.get("claims", []):
        for cit in cl.get("citations", []):
            if cit.get("url"):
                existing_urls.add(cit["url"])

    augmented_claims: list[dict[str, Any]] = []
    c_start = len(result.get("claims", [])) + 1

    if classification.input_type == "error_message":
        # Prepend error code search results.
        error_codes = classification.signals.get("error_codes", [])
        for ec_info in error_codes[:2]:  # Max 2 error codes.
            code = ec_info.get("code", "")
            if not code:
                continue
            try:
                from .lookup import search_error_code
                error_results = search_error_code(
                    docs_dir=docs_dir,
                    error_code=code,
                    exchange=exchange.exchange_id,
                    limit=3,
                )
                for er in error_results:
                    if er.get("source_type") == "page":
                        url = er.get("canonical_url", "")
                        if url in existing_urls:
                            continue
                        existing_urls.add(url)
                        augmented_claims.append({
                            "id": f"c{c_start}",
                            "kind": "SOURCE",
                            "text": f"[{exchange.exchange_id}:error] {er.get('snippet', '')}",
                            "citations": [{"url": url}],
                        })
                        c_start += 1
                    elif er.get("source_type") == "endpoint":
                        ep_id = er.get("endpoint_id", "")
                        if ep_id in existing_ids:
                            continue
                        existing_ids.add(ep_id)
                        augmented_claims.append({
                            "id": f"c{c_start}",
                            "kind": "ENDPOINT",
                            "text": f"[{exchange.exchange_id}:{er.get('section', '')}] {er.get('method', '')} {er.get('path', '')} — {er.get('snippet', '')}",
                            "citations": [],
                            "endpoint_id": ep_id,
                        })
                        c_start += 1
            except Exception:
                logger.debug("Error code augmentation failed for %s", code, exc_info=True)

    elif classification.input_type == "endpoint_path":
        # Prepend endpoint path lookup results.
        path = classification.signals.get("path", "")
        method = classification.signals.get("method")
        if path:
            try:
                from .lookup import lookup_endpoint_by_path
                path_results = lookup_endpoint_by_path(
                    docs_dir=docs_dir,
                    path=path,
                    method=method,
                    exchange=exchange.exchange_id,
                )
                for record in path_results[:3]:
                    ep_id = record.get("endpoint_id", "")
                    if ep_id in existing_ids:
                        continue
                    existing_ids.add(ep_id)
                    http = record.get("http", {})
                    augmented_claims.append({
                        "id": f"c{c_start}",
                        "kind": "ENDPOINT",
                        "text": f"[{exchange.exchange_id}:{record.get('section', '')}] {http.get('method', '')} {http.get('path', '')} — {record.get('description', '')}",
                        "citations": [{"url": record.get("docs_url", "")}] if record.get("docs_url") else [],
                        "endpoint_id": ep_id,
                    })
                    c_start += 1
            except Exception:
                logger.debug("Endpoint path augmentation failed for %s", path, exc_info=True)

    if augmented_claims:
        # Prepend augmented claims (they're more specific) and re-number.
        all_claims = augmented_claims + result.get("claims", [])
        for i, cl in enumerate(all_claims, 1):
            cl["id"] = f"c{i}"
        result["claims"] = all_claims
        if result.get("status") == "unknown" and augmented_claims:
            result["status"] = "ok"

    return result


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
        # Classify input to augment search (F4: augment, don't replace).
        classification = classify_input(question)

        # Binance: use richer Binance-specific logic.
        if exchange.exchange_id == "binance":
            result = _binance_answer(conn, reg=reg, question=question, norm=norm, clarification=clarification, docs_dir=docs_dir)
        else:
            # All other exchanges: generic cite-only search.
            result = _generic_search_answer(conn, exchange=exchange, question=question, norm=norm, docs_dir=docs_dir)

        # Augment with classification-specific results.
        result = _augment_with_classification(
            conn, result,
            classification=classification,
            exchange=exchange,
            docs_dir=docs_dir,
        )
        return result
    finally:
        conn.close()
