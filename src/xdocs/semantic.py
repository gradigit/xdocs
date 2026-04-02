"""Semantic search via LanceDB (optional, requires ``xdocs[semantic]``)."""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from .db import open_db
from .embeddings import get_embedder
from .store import require_store_db

logger = logging.getLogger(__name__)

# Lazy import to avoid hard dependency on lancedb.
_lancedb = None

TABLE_NAME = "pages"

_RERANK_POLICY_AUTO = "auto"
_RERANK_POLICY_ALWAYS = "always"
_RERANK_POLICY_NEVER = "never"

_AUTO_RERANK_MIN_CANDIDATES = int(os.getenv("CEX_RERANK_AUTO_MIN_CANDIDATES", "6"))
_AUTO_RERANK_TOP_DELTA = float(os.getenv("CEX_RERANK_AUTO_TOP_DELTA", "0.006"))
_AUTO_RERANK_TOPK_SPREAD = float(os.getenv("CEX_RERANK_AUTO_TOPK_SPREAD", "0.02"))

_EXCHANGE_NAME_RE = re.compile(r"^[a-z0-9_]+$")

# User-facing names → internal exchange IDs.
_EXCHANGE_ALIASES: dict[str, str] = {
    "crypto.com": "cryptocom",
    "crypto_com": "cryptocom",
    "gate.io": "gateio",
    "huobi": "htx",
    "mercado bitcoin": "mercadobitcoin",
    "perpetual protocol": "perp",
    "gains network": "gains",
    "woo x": "woo",
}


def _sanitize_exchange_filter(exchange: str) -> str:
    """Validate and normalize exchange name for LanceDB WHERE clauses."""
    normed = _EXCHANGE_ALIASES.get(exchange.lower(), exchange.lower())
    if not _EXCHANGE_NAME_RE.match(normed):
        raise ValueError(f"Invalid exchange name: {exchange!r}")
    return normed


def _require_lancedb():
    global _lancedb
    if _lancedb is None:
        try:
            import lancedb
        except ImportError:
            raise ImportError(
                "lancedb is not installed. Run: pip install xdocs[semantic]"
            )
        _lancedb = lancedb
    return _lancedb


def _lance_dir(docs_dir: str) -> str:
    return str(Path(docs_dir) / "lancedb-index")


def compact_index(
    *, docs_dir: str, max_bytes_per_file: int | None = None
) -> dict[str, Any]:
    """Compact LanceDB index: merge fragments + cleanup old versions.

    Args:
        docs_dir: Path to the docs directory containing lancedb-index/.
        max_bytes_per_file: Optional cap on .lance data file size in bytes.
            Use to keep fragments under hosting limits (e.g. 1_900_000_000
            for GitHub LFS 2 GB limit).  When set, the compacted index is
            rewritten with ``lance.write_dataset(max_rows_per_file=...)``
            so that no single data file exceeds the cap.  Note:
            ``table.optimize()`` always re-merges into one fragment, so the
            split must happen *after* the optimise call.
    """
    from datetime import timedelta

    import lance as _lance

    lancedb = _require_lancedb()
    lance_db = lancedb.connect(_lance_dir(docs_dir))
    table = lance_db.open_table(TABLE_NAME)
    pre = table.count_rows()

    # Standard compaction: merge fragments + prune old versions
    table.optimize(cleanup_older_than=timedelta(days=0))

    lance_path = str(Path(docs_dir) / "lancedb-index" / f"{TABLE_NAME}.lance")

    # If a size cap was requested, rewrite the (now single-fragment) dataset
    # into multiple fragments that each stay under the limit.
    if max_bytes_per_file:
        ds = _lance.dataset(lance_path)
        total_bytes = sum(
            (Path(lance_path) / "data" / df.path()).stat().st_size
            for frag in ds.get_fragments()
            for df in frag.metadata.data_files()
            if (Path(lance_path) / "data" / df.path()).exists()
        )
        if total_bytes > max_bytes_per_file:
            rows = ds.count_rows()
            bytes_per_row = total_bytes / rows if rows else 1
            target_rows = int(max_bytes_per_file / bytes_per_row)
            all_data = ds.to_table()
            import shutil
            tmp = lance_path + ".split_tmp"
            if Path(tmp).exists():
                shutil.rmtree(tmp)
            _lance.write_dataset(all_data, tmp, max_rows_per_file=target_rows)
            bak = lance_path + ".bak"
            import os
            os.rename(lance_path, bak)
            os.rename(tmp, lance_path)
            shutil.rmtree(bak)

    post = table.count_rows() if not max_bytes_per_file else _lance.dataset(lance_path).count_rows()

    # Report resulting fragment sizes
    ds = _lance.dataset(lance_path)
    fragments = []
    data_dir = Path(lance_path) / "data"
    for frag in ds.get_fragments():
        for df in frag.metadata.data_files():
            fp = data_dir / df.path()
            if fp.exists():
                fragments.append({"file": df.path(), "bytes": int(fp.stat().st_size)})
    return {
        "rows": post if not max_bytes_per_file else ds.count_rows(),
        "pre_compact_rows": pre,
        "lance_dir": _lance_dir(docs_dir),
        "fragments": fragments,
    }


def _normalize_rerank_policy(rerank: bool | str) -> str:
    if isinstance(rerank, bool):
        return _RERANK_POLICY_ALWAYS if rerank else _RERANK_POLICY_NEVER
    policy = str(rerank).strip().lower()
    if policy not in {_RERANK_POLICY_AUTO, _RERANK_POLICY_ALWAYS, _RERANK_POLICY_NEVER}:
        raise ValueError(
            f"Unsupported rerank policy {rerank!r}; use one of: "
            f"{_RERANK_POLICY_AUTO}|{_RERANK_POLICY_ALWAYS}|{_RERANK_POLICY_NEVER}"
        )
    return policy


def _should_auto_rerank(raw_results: list[dict[str, Any]], *, limit: int) -> tuple[bool, str]:
    """Decide whether reranking should be applied in auto mode.

    Heuristic intent:
    - Avoid default reranking cost for obviously strong rankings.
    - Trigger rerank when many near-tied candidates make ordering uncertain.
    """
    if not raw_results:
        return False, "no_candidates"

    if len(raw_results) < max(2, min(_AUTO_RERANK_MIN_CANDIDATES, limit * 2)):
        return False, "too_few_candidates"

    top = raw_results[: min(5, len(raw_results))]
    scores = [float(r.get("score", 0.0)) for r in top]
    if len(scores) < 2:
        return False, "single_candidate"

    top_delta = abs(scores[0] - scores[1])
    spread = max(scores) - min(scores)

    if top_delta <= _AUTO_RERANK_TOP_DELTA or spread <= _AUTO_RERANK_TOPK_SPREAD:
        return True, "ambiguous_top_scores"

    return False, "confident_ranking"


def _get_indexed_pages(table: Any) -> dict[int, str]:
    """Return {page_id: content_hash} for all pages currently in the index."""
    try:
        df = table.search().select(["page_id", "content_hash"]).limit(10_000_000).to_pandas()
        # De-duplicate: one row per page_id.
        deduped = df.drop_duplicates(subset=["page_id"])
        return dict(zip(deduped["page_id"].tolist(), deduped["content_hash"].tolist()))
    except Exception:
        return {}


def build_index(
    *,
    docs_dir: str,
    limit: int = 0,
    exchange: str | None = None,
    batch_size: int = 128,
    incremental: bool = False,
) -> dict[str, Any]:
    """Build or rebuild the LanceDB semantic index from SQLite pages.

    Uses jina-embeddings-v5-text-small (Jina MLX on macOS, SentenceTransformers on Linux) with markdown
    chunking for fine-grained retrieval.

    Args:
        docs_dir: Path to the cex-docs store directory.
        limit: Max pages to embed (0 = all).
        exchange: Optional filter by exchange domain pattern.
        batch_size: Rows per embedding batch.
        incremental: If True, only process new/changed pages instead of
            dropping and rebuilding the entire index.

    Returns:
        Summary dict with counts.
    """
    lancedb = _require_lancedb()
    embedder = get_embedder()

    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)

    try:
        # Build query — include content_hash for change detection.
        sql = """
SELECT
  p.id AS page_id,
  p.canonical_url,
  p.title,
  p.domain,
  p.word_count,
  p.markdown_path,
  p.content_hash
FROM pages p
WHERE p.word_count > 0 AND p.markdown_path IS NOT NULL
"""
        params: list[Any] = []
        if exchange:
            sql += " AND p.domain LIKE ?"
            params.append(f"%{exchange}%")
        sql += " ORDER BY p.id"
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"cmd": "build-index", "pages_processed": 0, "chunks_embedded": 0, "status": "no_pages"}

    # Import chunker (requires mistune from [semantic] extras).
    from .chunker import chunk_markdown

    # Connect to LanceDB.
    lance_db = lancedb.connect(_lance_dir(docs_dir))

    from lancedb.pydantic import LanceModel, Vector

    ndims = embedder.ndims()

    class ChunkEmbedding(LanceModel):
        text: str
        vector: Vector(ndims)  # type: ignore[valid-type]
        page_id: int
        chunk_index: int
        heading: str
        exchange: str
        domain: str
        url: str
        title: str
        word_count: int
        content_hash: str

    # Incremental mode: diff against existing index.
    pages_deleted = 0
    chunks_deleted = 0
    table = None

    if incremental:
        try:
            table = lance_db.open_table(TABLE_NAME)
            # Check schema compatibility — content_hash must exist.
            schema_cols = {f.name for f in table.schema}
            if "content_hash" not in schema_cols:
                logger.warning(
                    "Existing index lacks 'content_hash' column; falling back to full rebuild."
                )
                table = None
                indexed = {}
            else:
                # Check vector dimensions match current embedder via schema
                # inspection (not search — search fails on partially-written tables).
                vec_field = table.schema.field("vector")
                existing_dims = vec_field.type.list_size if vec_field else None
                if existing_dims is not None and existing_dims != ndims:
                    logger.warning(
                        "Model dimension mismatch: index has %d dims, embedder produces %d. "
                        "Falling back to full rebuild.",
                        existing_dims, ndims,
                    )
                    table = None
                    indexed = {}
                elif existing_dims is None:
                    logger.warning(
                        "Cannot determine vector dimensions from schema; falling back to full rebuild."
                    )
                    table = None
                    indexed = {}
                else:
                    indexed = _get_indexed_pages(table)
        except Exception:
            # No existing table — fall back to full build.
            indexed = {}
            table = None

        if indexed:
            # Build source-of-truth map from SQLite.
            source_pages: dict[int, str] = {
                row["page_id"]: (row["content_hash"] or "") for row in rows
            }

            # When exchange filter is active, only consider pages in the
            # filtered set for stale detection.  Without this guard,
            # ALL other exchanges' chunks would be deleted as "stale".
            scope = indexed if not exchange else {
                pid: h for pid, h in indexed.items() if pid in source_pages
            }

            # Pages to delete: removed from SQLite or content changed.
            stale_ids: list[int] = []
            for pid, old_hash in scope.items():
                if pid not in source_pages or source_pages[pid] != old_hash:
                    stale_ids.append(pid)

            # Pages to add: new or changed.
            new_page_ids: set[int] = set()
            for pid, cur_hash in source_pages.items():
                if pid not in indexed or indexed[pid] != cur_hash:
                    new_page_ids.add(pid)

            # Delete stale chunks.
            if stale_ids:
                # LanceDB delete predicate with IN clause (batch in groups of 500).
                for i in range(0, len(stale_ids), 500):
                    batch = stale_ids[i : i + 500]
                    id_list = ", ".join(str(x) for x in batch)
                    pre_count = table.count_rows()
                    table.delete(f"page_id IN ({id_list})")
                    post_count = table.count_rows()
                    chunks_deleted += pre_count - post_count
                pages_deleted = len(stale_ids)

            # Filter rows to only new/changed pages.
            rows = [r for r in rows if r["page_id"] in new_page_ids]

            if not rows:
                # Nothing new — just rebuild FTS index in case it's stale.
                if chunks_deleted > 0:
                    table.create_fts_index("text", replace=True)
                return {
                    "cmd": "build-index",
                    "mode": "incremental",
                    "pages_processed": 0,
                    "chunks_embedded": 0,
                    "pages_deleted": pages_deleted,
                    "chunks_deleted": chunks_deleted,
                    "total_rows": table.count_rows(),
                    "status": "up_to_date",
                }

    logger.info("Processing %d pages for chunking + embedding...", len(rows))

    # Create table if needed (full rebuild or no existing table).
    if table is None:
        try:
            lance_db.drop_table(TABLE_NAME)
        except Exception:
            pass
        table = lance_db.create_table(TABLE_NAME, schema=ChunkEmbedding)

    # Phase 1: Collect all chunks (fast, no embedding).
    skipped = 0
    pages_processed = 0
    all_chunks: list[dict[str, Any]] = []

    docs_path = Path(docs_dir)
    repo_root = docs_path.parent

    for row in rows:
        md_rel = row["markdown_path"]
        md_path = repo_root / md_rel if md_rel.startswith(docs_path.name) else docs_path / md_rel
        if not md_path.exists():
            skipped += 1
            continue
        md_text = md_path.read_text(encoding="utf-8", errors="replace")
        if not md_text.strip():
            skipped += 1
            continue

        domain = row["domain"]
        exchange_id = _domain_to_exchange(domain)
        content_hash = row["content_hash"] or ""

        chunks = chunk_markdown(md_text)
        if not chunks:
            skipped += 1
            continue

        pages_processed += 1
        page_title = row["title"] or ""
        for chunk in chunks:
            # Prepend page title + heading to chunk text for embedding context.
            # This disambiguates chunks from similarly named pages across
            # different exchange products/sections (e.g. "Binance Spot API >
            # Account Endpoints" vs "Binance Pay > Balance Query").
            context_parts: list[str] = []
            if page_title:
                context_parts.append(page_title)
            if chunk.heading and chunk.heading != page_title:
                context_parts.append(chunk.heading)
            context_prefix = " > ".join(context_parts)
            embed_text = f"[{context_prefix}]\n{chunk.text}" if context_prefix else chunk.text

            all_chunks.append(
                {
                    "text": embed_text,
                    "page_id": row["page_id"],
                    "chunk_index": chunk.chunk_index,
                    "heading": chunk.heading,
                    "exchange": exchange_id,
                    "domain": domain,
                    "url": row["canonical_url"],
                    "title": row["title"] or "",
                    "word_count": row["word_count"],
                    "content_hash": content_hash,
                }
            )

    logger.info("Chunked %d pages into %d chunks. Sorting by length for optimal batching...",
                pages_processed, len(all_chunks))

    # Phase 2: Sort by text length to minimize padding waste within batches.
    # With decoder models, padding all items to the longest in a batch is expensive.
    # Grouping similar-length chunks together avoids 10-40x slowdowns from mixed batches.
    all_chunks.sort(key=lambda c: len(c["text"]))

    # Phase 3: Embed in batches and stream to LanceDB.
    chunks_embedded = 0
    t_embed_start = time.monotonic()

    # Detect CUDA for periodic cache clearing (prevents OOM on long builds).
    _has_cuda = False
    try:
        import torch
        _has_cuda = torch.cuda.is_available()
    except ImportError:
        pass

    def _embed_batch(batch: list[dict]) -> None:
        """Embed a batch and add to table. On OOM, retry one-by-one."""
        try:
            vectors = embedder.embed_texts([r["text"] for r in batch])
            for row, vec in zip(batch, vectors):
                row["vector"] = vec
            table.add(batch)
        except (RuntimeError, Exception) as e:
            if "out of memory" not in str(e).lower() and "CUDA" not in str(e):
                raise
            # OOM — clear cache and retry each item individually.
            logger.warning("OOM on batch of %d — retrying one-by-one", len(batch))
            if _has_cuda:
                torch.cuda.empty_cache()
            for row in batch:
                row.pop("vector", None)
            for row in batch:
                try:
                    vecs = embedder.embed_texts([row["text"]])
                    row["vector"] = vecs[0]
                    table.add([row])
                except (RuntimeError, Exception) as e2:
                    if "out of memory" in str(e2).lower() or "CUDA" in str(e2):
                        logger.warning("OOM on single chunk (page_id=%s, %d chars) — skipping",
                                       row.get("page_id"), len(row.get("text", "")))
                        if _has_cuda:
                            torch.cuda.empty_cache()
                    else:
                        raise
        finally:
            for row in batch:
                row.pop("vector", None)

    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        _embed_batch(batch)
        chunks_embedded += len(batch)

        # Log progress with throughput every ~500 chunks.
        if chunks_embedded % 500 < batch_size:
            elapsed = time.monotonic() - t_embed_start
            rate = chunks_embedded / elapsed * 60 if elapsed > 0 else 0
            logger.info("  Embedded %d / %d chunks (%.0f/min)...",
                        chunks_embedded, len(all_chunks), rate)

        # Clear CUDA cache periodically to prevent OOM from memory fragmentation.
        # v5-small (1024d) uses ~15.8GB on a 16GB GPU — fragmentation kills it.
        if _has_cuda and chunks_embedded % (batch_size * 50) < batch_size:
            torch.cuda.empty_cache()

    if chunks_embedded == 0 and not incremental:
        return {
            "cmd": "build-index",
            "pages_processed": 0,
            "chunks_embedded": 0,
            "skipped": skipped,
            "status": "no_content",
        }

    # Create FTS index for hybrid search.
    table.create_fts_index("text", replace=True)

    result: dict[str, Any] = {
        "cmd": "build-index",
        "pages_processed": pages_processed,
        "chunks_embedded": chunks_embedded,
        "skipped": skipped,
        "total_rows": table.count_rows(),
        "lance_dir": _lance_dir(docs_dir),
        "model": embedder.model_name,
        "embedding_backend": embedder.backend_name,
        "ndims": ndims,
        "status": "ok",
    }
    if incremental:
        result["mode"] = "incremental"
        result["pages_deleted"] = pages_deleted
        result["chunks_deleted"] = chunks_deleted
    return result


def semantic_search(
    *,
    docs_dir: str,
    query: str,
    exchange: str | None = None,
    limit: int = 10,
    query_type: str = "hybrid",
    rerank: bool | str = True,
    include_meta: bool = False,
    keep_text: bool = False,
    query_type_hint: str | None = None,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run semantic (vector), FTS, or hybrid search against the LanceDB index.

    Args:
        docs_dir: Path to the cex-docs store directory.
        query: Natural language query string.
        exchange: Optional exchange filter.
        limit: Max results.
        query_type: "vector", "fts", or "hybrid".
        rerank:
            - bool: True=always rerank, False=never rerank
            - "auto": rerank only when top results are ambiguous
            - "always" / "never": explicit policy strings
        include_meta: Return `(results, meta)` when True.
        keep_text: Preserve the ``text`` field in results (for external reranking).

    Returns:
        List of result dicts with url, title, score, etc.
        Results are de-duplicated by page_id (best chunk per page).
    """
    rerank_policy = _normalize_rerank_policy(rerank)

    lancedb = _require_lancedb()
    lance_db = lancedb.connect(_lance_dir(docs_dir))
    table = lance_db.open_table(TABLE_NAME)

    # Fetch more candidates when reranking is possible.
    fetch_limit = limit * 3 if rerank_policy in {_RERANK_POLICY_ALWAYS, _RERANK_POLICY_AUTO} else limit * 2

    _cached_query_vector = None

    def _get_query_vector():
        nonlocal _cached_query_vector
        if _cached_query_vector is None:
            embedder = get_embedder()
            _cached_query_vector = embedder.embed_texts([query], is_query=True)[0]
        return _cached_query_vector

    def _build_search(kind: str):
        if kind == "vector":
            return table.search(_get_query_vector()).limit(fetch_limit)
        if kind == "fts":
            return table.search(query, query_type="fts").limit(fetch_limit)
        if kind == "hybrid":
            query_vector = _get_query_vector()
            return (
                table.search(query_type="hybrid")
                .vector(query_vector)
                .text(query)
                .limit(fetch_limit)
            )
        raise ValueError(f"Unsupported query_type={kind!r}; use vector|fts|hybrid")

    # LanceDB hybrid search silently returns 0 rows when combined with .where(),
    # so for hybrid mode we fetch extra unfiltered results and post-filter in Python.
    _hybrid_post_filter = query_type == "hybrid" and exchange is not None

    def _with_exchange_filter(search_obj):
        if exchange and not _hybrid_post_filter:
            safe = _sanitize_exchange_filter(exchange)
            return search_obj.where(f"exchange = '{safe}'")
        return search_obj

    if _hybrid_post_filter:
        # Over-fetch to ensure enough exchange-matching results after post-filter.
        # Small exchanges (<1% of chunks) need a high multiplier. 500 is enough
        # for exchanges with >=0.2% of the index (~700 chunks out of 357K).
        fetch_limit = max(fetch_limit * 20, 500)

    search = _with_exchange_filter(_build_search(query_type))
    try:
        arrow_table = search.to_arrow()
    except RuntimeError as exc:
        msg = str(exc)
        missing_fts = "Cannot perform full text search unless an INVERTED index has been created" in msg
        if query_type not in {"fts", "hybrid"} or not missing_fts:
            raise

        logger.warning(
            "FTS index missing for semantic table; attempting to create index and retry.",
        )
        try:
            table.create_fts_index("text", replace=False)
            retry = _with_exchange_filter(_build_search(query_type))
            arrow_table = retry.to_arrow()
        except Exception:
            if query_type == "fts":
                raise  # Don't fall back to vector for explicit FTS queries.
            logger.warning(
                "FTS index create/retry failed; falling back to vector-only search.",
                exc_info=True,
            )
            fallback = _with_exchange_filter(_build_search("vector"))
            arrow_table = fallback.to_arrow()
    raw_results: list[dict[str, Any]] = []
    cols = arrow_table.column_names
    has_text = "text" in cols
    for i in range(arrow_table.num_rows):
        score = 0.0
        score_kind = "none"
        if "_relevance_score" in cols:
            score = float(arrow_table.column("_relevance_score")[i].as_py())
            score_kind = "relevance"
        elif "_distance" in cols:
            score = float(arrow_table.column("_distance")[i].as_py())
            score_kind = "distance"

        result: dict[str, Any] = {
            "page_id": int(arrow_table.column("page_id")[i].as_py()),
            "url": str(arrow_table.column("url")[i].as_py()),
            "title": str(arrow_table.column("title")[i].as_py()),
            "exchange": str(arrow_table.column("exchange")[i].as_py()),
            "word_count": int(arrow_table.column("word_count")[i].as_py()),
            "score": score,
            "score_kind": score_kind,
        }

        # Include chunk fields if present.
        if "chunk_index" in cols:
            result["chunk_index"] = int(arrow_table.column("chunk_index")[i].as_py())
        if "heading" in cols:
            result["heading"] = str(arrow_table.column("heading")[i].as_py())
        if has_text:
            result["text"] = str(arrow_table.column("text")[i].as_py())

        raw_results.append(result)

    # Post-filter for hybrid mode (LanceDB WHERE bug workaround).
    if _hybrid_post_filter:
        raw_results = [r for r in raw_results if r["exchange"] == exchange]
        # Fallback: if post-filter eliminated everything, retry with FTS-only
        # which supports proper WHERE clause.
        if not raw_results:
            try:
                fts_search = _build_search("fts")
                safe = _sanitize_exchange_filter(exchange)
                fts_search = fts_search.where(f"exchange = '{safe}'")
                fts_arrow = fts_search.to_arrow()
                for i in range(fts_arrow.num_rows):
                    result = {
                        "page_id": int(fts_arrow.column("page_id")[i].as_py()),
                        "url": str(fts_arrow.column("url")[i].as_py()),
                        "title": str(fts_arrow.column("title")[i].as_py()),
                        "exchange": str(fts_arrow.column("exchange")[i].as_py()),
                        "word_count": int(fts_arrow.column("word_count")[i].as_py()),
                        "score": float(fts_arrow.column("_relevance_score")[i].as_py()) if "_relevance_score" in fts_arrow.column_names else 0.0,
                        "score_kind": "relevance",
                    }
                    if "chunk_index" in fts_arrow.column_names:
                        result["chunk_index"] = int(fts_arrow.column("chunk_index")[i].as_py())
                    if "heading" in fts_arrow.column_names:
                        result["heading"] = str(fts_arrow.column("heading")[i].as_py())
                    if "text" in fts_arrow.column_names:
                        result["text"] = str(fts_arrow.column("text")[i].as_py())
                    raw_results.append(result)
            except Exception:
                pass  # FTS fallback failed, return empty

    rerank_applied = False
    rerank_reason = "policy_never"
    should_rerank = False
    if rerank_policy == _RERANK_POLICY_ALWAYS:
        should_rerank = True
        rerank_reason = "policy_always"
    elif rerank_policy == _RERANK_POLICY_AUTO:
        should_rerank, rerank_reason = _should_auto_rerank(raw_results, limit=limit)

    # Rerank if requested/policy-triggered.
    if should_rerank and raw_results and has_text:
        try:
            from .reranker import rerank as do_rerank
            # Slice input to reduce cross-encoder compute (top_n only truncates output).
            rerank_input = raw_results[:min(limit * 3, len(raw_results))]
            raw_results = do_rerank(query, rerank_input, top_n=limit * 2, text_key="text")
            rerank_applied = True
        except ImportError:
            logger.warning("Reranker not available (pip install xdocs[reranker]). Skipping rerank.")
            rerank_reason = "reranker_unavailable"
    elif should_rerank and raw_results and not has_text:
        rerank_reason = "text_not_available"

    # Position-aware blending: when reranker was applied and results have both
    # RRF and reranker scores, blend them with position-aware weights so that
    # top retrieval positions retain more of the original ranking signal.
    if rerank_applied and raw_results:
        try:
            from .fts_util import position_aware_blend
            raw_results = position_aware_blend(raw_results, retrieval_score_key="score", query_type_hint=query_type_hint)
        except Exception:
            pass  # non-critical; fall through to default ordering

    # De-duplicate by page_id: keep the highest-scoring chunk per page.
    seen_pages: dict[int, dict[str, Any]] = {}
    for r in raw_results:
        pid = r["page_id"]
        if pid not in seen_pages:
            seen_pages[pid] = r

    results = list(seen_pages.values())[:limit]

    # Strip internal fields from output unless caller needs text for external reranking.
    for r in results:
        if not keep_text:
            r.pop("text", None)
        r.pop("score_kind", None)

    if include_meta:
        meta = {
            "rerank_policy": rerank_policy,
            "rerank_applied": rerank_applied,
            "rerank_reason": rerank_reason,
            "candidate_count": len(raw_results),
            "fetch_limit": fetch_limit,
            "query_type": query_type,
        }
        return results, meta
    return results


def fts5_search(
    *,
    docs_dir: str,
    query: str,
    exchange: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Run SQLite FTS5 BM25 search (baseline for comparison)."""
    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)
    try:
        sql = """
SELECT
  p.id AS page_id,
  p.canonical_url AS url,
  p.title,
  p.domain,
  p.word_count,
  rank
FROM pages_fts
JOIN pages p ON pages_fts.rowid = p.id
WHERE pages_fts MATCH ?
"""
        from .fts_util import sanitize_fts_query
        fts_query = sanitize_fts_query(query)
        params: list[Any] = [fts_query]
        if exchange:
            sql += " AND p.domain LIKE ?"
            params.append(f"%{exchange}%")
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        results: list[dict[str, Any]] = []
        for row in conn.execute(sql, params).fetchall():
            results.append(
                {
                    "page_id": row["page_id"],
                    "url": row["url"],
                    "title": row["title"],
                    "exchange": _domain_to_exchange(row["domain"]),
                    "word_count": row["word_count"],
                    "score": row["rank"],
                }
            )
        return results
    finally:
        conn.close()


_DOMAIN_MAP = {
    "developers.binance.com": "binance",
    "binance-docs.github.io": "binance",
    "bybit-exchange.github.io": "bybit",
    "www.kucoin.com": "kucoin",
    "www.okx.com": "okx",
    "www.bitget.com": "bitget",
    "www.gate.com": "gateio",
    "huobiapi.github.io": "htx",
    "exchange-docs.crypto.com": "cryptocom",
    "docs.bitfinex.com": "bitfinex",
    "www.bitstamp.net": "bitstamp",
    "docs.dydx.xyz": "dydx",
    "docs.dydx.exchange": "dydx",
    "hyperliquid.gitbook.io": "hyperliquid",
    "docs.upbit.com": "upbit",
    "global-docs.upbit.com": "upbit",
    "apidocs.bithumb.com": "bithumb",
    "docs.coinone.co.kr": "coinone",
    "docs.korbit.co.kr": "korbit",
    "raw.githubusercontent.com": "aggregator",
    # Pages-only exchanges (DEXs / docs-only)
    "docs.drift.trade": "drift",
    "docs.gmx.io": "gmx",
    "gmx-docs.io": "gmx",
    "api-docs.aevo.xyz": "aevo",
    "docs.aevo.xyz": "aevo",
    "docs.gains.trade": "gains",
    "docs.kwenta.io": "kwenta",
    "docs.lighter.xyz": "lighter",
    "lighter.gitbook.io": "lighter",
    "docs.perp.com": "perp",
    # New CEXes
    "docs.kraken.com": "kraken",
    "docs.cdp.coinbase.com": "coinbase",
    "docs.bitmex.com": "bitmex",
    "www.bitmex.com": "bitmex",
    "developer-pro.bitmart.com": "bitmart",
    "docs.whitebit.com": "whitebit",
    "api.mercadobitcoin.net": "mercadobitcoin",
    "ws.mercadobitcoin.net": "mercadobitcoin",
    # New DEXes
    "docs.asterdex.com": "aster",
    "api-docs.pro.apex.exchange": "apex",
    "docs.paradex.trade": "paradex",
    "api.prod.paradex.trade": "paradex",
    # New exchanges (M10+)
    "www.mexc.com": "mexc",
    "docs.deribit.com": "deribit",
    "orderly.network": "orderly",
    "docs.coinex.com": "coinex",
    "docs.nado.xyz": "nado",
    "docs.gemini.com": "gemini",
    "bluefin-exchange.readme.io": "bluefin",
    "bingx-api.github.io": "bingx",
    "docs.backpack.exchange": "backpack",
    "docs.woox.io": "woo",
    "phemex-docs.github.io": "phemex",
    # Aggregator
    "docs.ccxt.com": "ccxt",
    # GRVT uses github.com too, but majority of github.com pages are CCXT.
    # TODO: use per-URL prefix matching instead of domain-level mapping.
    "github.com": "ccxt",
}


def _domain_to_exchange(domain: str) -> str:
    return _DOMAIN_MAP.get(domain, domain)
