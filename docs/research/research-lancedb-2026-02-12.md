# Research: LanceDB for API Documentation Semantic Search

Date: 2026-02-12
Depth: Full
Researcher: Claude Opus 4.6 (subagent)

## Executive Summary

LanceDB is a strong candidate for adding semantic search to the existing CEX API documentation knowledge base. It is an embedded, serverless vector database built on the Lance columnar format (written in Rust, Apache 2.0 licensed). Like SQLite, it runs in-process with no server to manage, stores data on local disk, and has low memory requirements. The Python SDK is mature (v0.26.2 as of Feb 2026, 8.9K GitHub stars).

**Key findings for our use case (3,800 pages, 4.5M words, 3,125 endpoints):**

1. **Coexistence with SQLite is straightforward.** LanceDB and SQLite serve complementary roles: SQLite for structured data, FTS5 for keyword search, LanceDB for semantic vector search. No architectural conflict -- they are both embedded, file-based databases.

2. **Setup cost is moderate.** The primary cost is selecting and running an embedding model. For ~4K documents, a local sentence-transformers model (e.g., `all-MiniLM-L6-v2` at 384 dims or `nomic-embed-text-v1.5` at 768 dims) can embed the entire corpus in minutes on a modern laptop. Storage overhead is small: ~6 MB for 4K documents at 384 dims (float32), or ~12 MB at 768 dims.

3. **Hybrid search is well-supported.** LanceDB has built-in FTS (BM25-based, via Tantivy) plus vector search, with Reciprocal Rank Fusion (RRF) reranking. This means LanceDB alone could theoretically replace SQLite FTS5 for search, but the better architecture for this project is to keep SQLite as the source of truth and use LanceDB as a supplementary semantic search index.

4. **Metadata filtering during vector search is a first-class feature.** Pre-filtering (default) and post-filtering are both supported with SQL-like syntax. Filtering by `exchange_id` during vector search is trivially supported.

5. **For ~4K documents, no vector index is needed.** LanceDB FAQ states brute-force kNN is sufficient for datasets under ~100K records, with latency under 100ms. At 4K docs, expect sub-10ms query latency for vector search.

6. **Incremental updates are well-supported.** `table.add()` appends new data, `table.delete()` removes rows by condition, `table.update()` modifies rows, and `merge_insert()` supports upsert patterns. Each mutation creates a new version (Lance has built-in versioning).

**Recommendation:** Add LanceDB as an optional semantic search layer. Keep SQLite as the primary store. Use LanceDB for natural language queries that benefit from semantic similarity (e.g., "How do I get my account balance?" matching docs about `/api/v3/account` even when the word "balance" does not appear). Use a local embedding model to avoid API dependencies.

## Sub-Questions Investigated

1. What is LanceDB and how does it differ from other vector databases?
2. How does LanceDB store embeddings (Lance columnar format)?
3. How do you create tables, insert vectors, and query in Python?
4. What embedding models work best for technical API documentation search?
5. Can LanceDB run fully local (no server) as an embedded database?
6. How does LanceDB handle hybrid search (vector + full-text)?
7. What are practical patterns for building a local knowledge base over structured API documentation?
8. What are LanceDB's limitations and gotchas?

## Detailed Findings

### Architecture and Storage

**Lance Format.** LanceDB is built on top of the Lance data format, a modern columnar file format written in Rust. Lance is both a file format and a table format. Key properties:

- **Columnar storage** based on Apache Arrow type system
- **Zero-copy** data access via Arrow
- **Built-in versioning**: every mutation (add, delete, update) creates a new version. Old versions are retained for concurrent reads. Metadata overhead is per-version.
- **Disk-based indexing**: Unlike Pinecone/Milvus/Qdrant which keep indexes in memory, LanceDB's IVF-PQ and HNSW indexes live on disk, meaning very low memory requirements.
- **Random access**: Lance is up to 1000x faster than Parquet for random access (official benchmark, cross-verified by the arxiv paper "Lance: Efficient Random Access in Columnar Storage", Apr 2025).
- **Compaction**: As data accumulates, fragments should be compacted to maintain query throughput (merge small fragments, remove deleted rows).

**Storage overhead calculation for our use case:**

- 4,000 documents at 384 dimensions (float32): `4,000 x 384 x 4 bytes = 6.14 MB` for vectors alone
- 4,000 documents at 768 dimensions (float32): `4,000 x 768 x 4 bytes = 12.3 MB` for vectors
- 4,000 documents at 1536 dimensions (float32): `4,000 x 1536 x 4 bytes = 24.6 MB` for vectors
- Plus metadata columns, Lance overhead, and FTS index if used. Total likely under 50 MB for all configurations.

This is negligible compared to the existing cex-docs store.

**How LanceDB differs from alternatives:**

| Feature | LanceDB | ChromaDB | Pinecone | Milvus |
|---------|---------|----------|----------|--------|
| Deployment | Embedded (in-process) | Embedded or client-server | Cloud-only SaaS | Self-hosted server |
| Index type | Disk-based (IVF-PQ, HNSW) | In-memory (HNSW) | Proprietary | In-memory (HNSW, IVF) |
| Storage format | Lance (columnar) | DuckDB+Parquet | Proprietary | Custom |
| FTS built-in | Yes (BM25 via Tantivy) | No | No | Yes (sparse vectors) |
| Hybrid search | Native (RRF reranker) | No | No | Yes |
| Versioning | Built-in | No | No | No |
| License | Apache 2.0 | Apache 2.0 | Proprietary | Apache 2.0 |
| Memory usage | Low (disk-based) | High (in-memory) | N/A (cloud) | High (in-memory) |

Sources: LanceDB docs (docs.lancedb.com), LanceDB GitHub (github.com/lancedb/lancedb), "Embedded databases (3): LanceDB" (thedataquarry.com, Nov 2023, updated 2025).

### Python Integration

LanceDB provides a clean, Pythonic API. Installation is a single `pip install lancedb`. No external server, no Docker, no configuration files.

**Basic usage pattern:**

```python
import lancedb
from lancedb.embeddings import get_registry
from lancedb.pydantic import LanceModel, Vector

# 1. Connect (creates local directory)
db = lancedb.connect("./lancedb-store")

# 2. Define schema with auto-embedding
embedder = get_registry().get("sentence-transformers").create()

class DocPage(LanceModel):
    text: str = embedder.SourceField()
    vector: Vector(embedder.ndims()) = embedder.VectorField()
    exchange: str
    section: str
    url: str
    page_id: int

# 3. Create table
table = db.create_table("pages", schema=DocPage)

# 4. Add data (embeddings generated automatically)
table.add([
    {"text": "The GET /api/v3/account endpoint...", "exchange": "binance",
     "section": "spot", "url": "https://...", "page_id": 42},
    # ...
])

# 5. Search with automatic query embedding
results = table.search("account balance API endpoint") \
    .where("exchange = 'binance'") \
    .limit(10) \
    .to_pandas()

# 6. Hybrid search (vector + FTS)
table.create_fts_index("text")
results = table.search("account balance", query_type="hybrid") \
    .where("exchange = 'binance'") \
    .limit(10) \
    .to_pandas()
```

**Key API operations:**

| Operation | Method | Notes |
|-----------|--------|-------|
| Create table | `db.create_table(name, data=..., schema=...)` | Schema inferred or explicit |
| Add rows | `table.add(data)` | Bulk insert recommended |
| Delete rows | `table.delete("condition")` | SQL-like WHERE clause |
| Update rows | `table.update(where="condition", values={...})` | |
| Upsert | `table.merge_insert("key").when_matched_update_all().when_not_matched_insert_all().execute(data)` | |
| Vector search | `table.search(query_vector_or_text).limit(k)` | Auto-embeds if string |
| FTS search | `table.search("keywords", query_type="fts")` | Requires FTS index |
| Hybrid search | `table.search("query", query_type="hybrid")` | Combines vector + FTS with RRF |
| Filtered search | `.where("column = 'value'")` | Pre-filter (default) or post-filter |
| Create vector index | `table.create_index(metric="cosine")` | HNSW or IVF-PQ |
| Create FTS index | `table.create_fts_index("column")` | BM25-based |
| Create scalar index | `table.create_scalar_index("column")` | BTree or Bitmap |
| Count rows | `table.count_rows()` | |
| List tables | `db.table_names()` | |
| Drop table | `db.drop_table(name)` | |

Sources: LanceDB Quickstart (docs.lancedb.com/quickstart), Embedding Quickstart (docs.lancedb.com/embedding/quickstart), Table Management (docs.lancedb.com/tables), Context7 documentation (/websites/lancedb).

### Embedding Models for Technical Docs

For API documentation search, the embedding model needs to handle:
- Technical vocabulary (HTTP methods, status codes, parameter names)
- Mixed natural language and code snippets
- Short queries matched against long documents
- Domain-specific terms (rate limits, API keys, HMAC signatures)

**Recommended models (local, no API dependency):**

| Model | Dims | Size | Context | MTEB Retrieval | Notes |
|-------|------|------|---------|---------------|-------|
| `all-MiniLM-L6-v2` | 384 | 80MB | 512 tokens | Moderate | LanceDB default. Fast, lightweight. Good baseline. |
| `nomic-embed-text-v1.5` | 768 | 274MB | 8192 tokens | Good | Long context. Good for full page embedding. Available via Ollama. |
| `BAAI/bge-base-en-v1.5` | 768 | 438MB | 512 tokens | Good | Strong retrieval performance. Easy to fine-tune. |
| `snowflake-arctic-embed-m-v1.5` | 768 | ~250MB | 512 tokens | Good | Used in alex garcia's hybrid search demo. |
| `MongoDB/mdbr-leaf-ir` | 384 | ~90MB | 512 tokens | BEIR 53.55 | Only 23M params. 5x smaller than bge-base. CPU-friendly. |
| `nomic-ai/modernbert-embed-base` | 256 | ~180MB | 8192 tokens | Good | Used in the LanceDB benchmark study. |
| `Jina Code V2` | 768 | 137M params | 8192 tokens | Good for code | Optimized for code search. Apache 2.0. |

**Recommendation for this project:**

1. **Start with `all-MiniLM-L6-v2`** (LanceDB default). It is small, fast, and works out of the box with LanceDB's embedding registry. No configuration needed.
2. **If retrieval quality is insufficient, upgrade to `nomic-embed-text-v1.5`** which handles longer contexts (8192 tokens) and has better MTEB scores.
3. **Consider `BAAI/bge-base-en-v1.5`** if fine-tuning is desired (the BGE family has excellent fine-tuning tooling).

**API-based alternatives (higher quality, but introduces dependency):**
- OpenAI `text-embedding-3-small` (1536 dims, $0.02/1M tokens)
- Cohere `embed-english-v3.0` (1024 dims)

For a local-only, cite-only project, local models are preferred. The quality difference for retrieval on technical documentation is modest, especially combined with FTS hybrid search.

**Important consideration:** For API documentation, document-level embeddings may not be sufficient. Consider also embedding at the endpoint/section level for finer-grained retrieval. A single page with 10 endpoints should ideally be split into 10 chunks.

Sources: MTEB Leaderboard (huggingface.co/spaces/mteb/leaderboard), Modal blog "6 Best Code Embedding Models" (Mar 2025), HN "Ask HN: How are you doing RAG locally?" (Jan 2026), BentoML "Guide to Open-Source Embedding Models" (Oct 2025).

### Hybrid Search (Vector + FTS)

LanceDB supports three search modes:

1. **Vector search** (`query_type="vector"`): Semantic similarity using embeddings.
2. **Full-text search** (`query_type="fts"`): BM25-based keyword search via Tantivy.
3. **Hybrid search** (`query_type="hybrid"`): Combines both with reranking.

**FTS implementation details:**
- Built on Tantivy (Rust-based Lucene equivalent)
- BM25 scoring algorithm
- Configurable tokenization: simple (default), ngram (for substring search)
- Supports: stemming, stop word removal, lowercase normalization, ASCII folding
- Phrase queries (with `with_position=True`)
- Fuzzy search (Levenshtein distance)
- Boolean queries (`&` for AND, `|` for OR)
- Boosting (promote/demote specific terms)
- Pre-filtering and post-filtering during FTS

**Hybrid search reranking options:**
- **RRF (Reciprocal Rank Fusion)**: Default. Combines vector and FTS ranks. Same algorithm used in the sqlite-vec hybrid search approach described by Alex Garcia.
- **Cross-encoder rerankers**: Cohere, sentence-transformers CrossEncoder
- **Custom rerankers**: Implement your own

**Comparison with SQLite FTS5:**

| Feature | SQLite FTS5 | LanceDB FTS |
|---------|-------------|-------------|
| Algorithm | BM25 (Okapi) | BM25 (Tantivy) |
| Tokenizer | Unicode61, porter, trigram | Simple, ngram, language-specific |
| Phrase search | Yes | Yes (with_position=True) |
| Boolean operators | Yes (AND, OR, NOT, NEAR) | Yes (Must, Should, MustNot) |
| Fuzzy search | No | Yes (Levenshtein) |
| Prefix search | Yes | Yes |
| Highlighting | Yes (highlight(), snippet()) | Not documented |
| External content tables | Yes | N/A (data stored in Lance) |
| Incremental index updates | Automatic | Requires explicit rebuild or background |
| Column filters during FTS | No (must JOIN) | Yes (pre-filter/post-filter) |
| Maturity | Battle-tested (15+ years) | Newer (Tantivy-based) |

**Key insight from the research:** Multiple HN commenters and practitioners (Jan 2026 thread) report that BM25/FTS5 alone is "surprisingly sufficient" for many use cases, especially code and technical documentation. The main gap is **synonym/concept matching** -- FTS cannot find "account balance" when the doc says "wallet funds." This is exactly where vector search adds value.

**Recommended hybrid strategy for this project:**

1. Use SQLite FTS5 as the primary keyword search (already working).
2. Add LanceDB vector search for semantic fallback.
3. Combine results using RRF, weighted toward FTS (e.g., weight_fts=1.5, weight_vec=1.0) since exact keyword matches are more reliable for API docs.
4. Alternatively, use the "keyword-first" approach: return FTS results first, then augment with vector search results.

Sources: LanceDB Hybrid Search docs (docs.lancedb.com/search/hybrid-search), LanceDB Full-Text Search docs (docs.lancedb.com/search/full-text-search), Alex Garcia "Hybrid full-text search and vector search with SQLite" (Oct 2024), HN thread (Jan 2026).

### Incremental Updates

LanceDB handles incremental updates natively through the Lance format's versioning system.

**Adding new pages:**
```python
# When a new page is synced, just add it
table.add([{"text": new_page_markdown, "exchange": "binance",
            "section": "spot", "url": url, "page_id": page_id}])
```

**Updating changed pages:**
```python
# Delete old version, add new
table.delete(f"page_id = {page_id}")
table.add([updated_record])

# Or use merge_insert for upsert
table.merge_insert("page_id") \
    .when_matched_update_all() \
    .when_not_matched_insert_all() \
    .execute([updated_record])
```

**Deleting pages:**
```python
table.delete(f"page_id = {page_id}")
```

**Important considerations:**

1. **Re-embedding on update**: When page content changes, the embedding must be regenerated. If using LanceDB's embedding API with a `SourceField`, this happens automatically on `add()`.

2. **Version accumulation**: Each mutation creates a new version. Over many updates, metadata overhead grows. Periodic compaction is recommended:
   ```python
   table.compact_files()
   table.cleanup_old_versions()
   ```

3. **FTS index rebuild**: After significant data changes, the FTS index should be rebuilt:
   ```python
   table.create_fts_index("text", replace=True)
   ```

4. **Vector index rebuild**: For small datasets (<100K), no vector index is needed. For larger datasets, the index may need occasional rebuilding after significant insertions (LanceDB does not automatically update ANN indexes for new data -- new data is searched via brute force until the index is rebuilt).

5. **Batch inserts**: Strongly recommended for performance. Each single-row insert creates a new data fragment. Batching reduces fragment count and improves read performance.

Sources: LanceDB FAQ (docs.lancedb.com/faq/faq-oss), LanceDB Table Versioning (docs.lancedb.com/tables/versioning), LanceDB Update docs (docs.lancedb.com/tables/update), Context7 docs (/websites/lancedb).

### Performance Characteristics

**Benchmarks relevant to our scale (~4K documents):**

For datasets under 100K records, LanceDB does not need a vector index. Brute-force kNN is used, and latency is excellent:

| Dataset Size | Dimensions | Index | Query Latency | Source |
|-------------|-----------|-------|---------------|--------|
| 100K | 1000 | None (brute force) | <20ms | LanceDB FAQ |
| 1M (GIST) | 960 | IVF-PQ | 3-5ms (>0.9 recall) | LanceDB benchmark blog (Dec 2023) |
| 1M (GIST) | 960 | IVF-PQ | 7-20ms on older Linux | LanceDB benchmark blog |
| 1B | 128 | IVF-PQ | <100ms | LanceDB benchmark blog |
| 130K (wine reviews) | 256 | HNSW | p50: 10ms (FTS), 134ms (vector) | thedataquarry.com benchmark (updated 2025) |

**For our use case (4K docs, 384-768 dims):**
- Expected vector search latency: **<5ms** (brute force, no index needed)
- Expected FTS latency: **<5ms**
- Expected hybrid search latency: **<10ms** (both searches + RRF merge)
- Indexing time: seconds (embedding 4K docs with all-MiniLM-L6-v2 takes ~30-60 seconds on a modern laptop)

**Comparison with SQLite FTS5 for our use case:**

| Metric | SQLite FTS5 | LanceDB Vector | LanceDB Hybrid |
|--------|-------------|----------------|----------------|
| Query latency | <1ms | <5ms | <10ms |
| Index build time | <1s | 30-60s (embedding) | 30-60s + FTS index |
| Storage overhead | ~20MB (FTS index) | ~6-12MB (vectors) | ~25-35MB |
| Query type | Keyword only | Semantic only | Both |
| "Adventure Time" problem | Exact match wins | May return irrelevant | Best of both |
| "account balance" -> "wallet funds" | Fails | Succeeds | Succeeds |

**Memory usage:**
LanceDB's disk-based architecture means very low memory usage. The entire 4K-document dataset with vectors would fit in a few tens of MB of RAM during queries. No need for dedicated RAM allocation.

Sources: LanceDB FAQ (docs.lancedb.com/faq/faq-oss), LanceDB Benchmark blog (medium.com/etoai, Dec 2023), thedataquarry.com benchmark (Nov 2023/2025), LanceDB Enterprise benchmarks page (docs.lancedb.com/enterprise/benchmarks).

### Comparison with SQLite FTS5

**What SQLite FTS5 does well (and LanceDB cannot replace):**

1. **Exact keyword matching**: When a user searches for `GET /api/v3/account`, FTS5 will find it. Vector search may return semantically similar but wrong endpoints.
2. **Boolean queries**: `"rate limit" AND "binance" AND "spot"` -- precise boolean logic.
3. **Integration with structured data**: FTS5 is just another SQLite virtual table. JOINs with endpoints, pages, inventories are trivial.
4. **Battle-tested maturity**: FTS5 has been in production for 15+ years on billions of devices.
5. **Zero additional dependencies**: Already part of the project's SQLite database.

**What LanceDB adds that FTS5 cannot do:**

1. **Semantic matching**: "How do I check my balance?" matches docs about `GET /api/v3/account` even without the word "balance."
2. **Concept bridging**: "authentication" matches docs about "API key," "HMAC signature," "secret key."
3. **Typo tolerance**: Vector search naturally handles minor spelling variations.
4. **Query reformulation robustness**: Users can phrase questions many ways; vectors capture intent.
5. **Cross-exchange similarity**: Find equivalent endpoints across different exchanges (e.g., Binance's `GET /api/v3/ticker/price` and Bybit's `GET /v5/market/tickers`).

**Architecture recommendation:**

```
User Query
    |
    v
+-------------------+     +-------------------+
| SQLite FTS5       |     | LanceDB Vector    |
| (keyword search)  |     | (semantic search) |
+-------------------+     +-------------------+
    |                         |
    v                         v
+---------------------------------------+
| Result Fusion (RRF or weighted merge) |
+---------------------------------------+
    |
    v
+-------------------+
| SQLite Structured |
| (endpoint details,|
|  citations, etc.) |
+-------------------+
    |
    v
  Answer
```

SQLite remains the source of truth. LanceDB is a supplementary index that can be rebuilt from SQLite data at any time.

### Integration Pattern for This Project

**Proposed architecture:**

1. **Keep SQLite as the primary store.** All page content, endpoint records, inventories, and citations stay in SQLite.

2. **Add a LanceDB sidecar index.** A new `lancedb-index/` directory alongside `cex-docs/db/`. Contains embeddings of page markdown and/or endpoint descriptions.

3. **Embed at two granularities:**
   - **Page-level**: Embed the full markdown of each page (or a truncated summary). Good for broad topic matching.
   - **Endpoint-level**: Embed each endpoint's description + path + parameters. Good for specific API question matching.

4. **Sync on demand.** After `cex-api-docs sync`, run an `embed` command that:
   - Reads all pages from SQLite
   - Chunks/embeds them
   - Upserts into LanceDB
   - Rebuilds FTS index in LanceDB

5. **Query integration.** The `answer` command would:
   - Run SQLite FTS5 search (existing)
   - Run LanceDB vector search (new)
   - Merge results with RRF
   - Assemble cited answer from merged results

**Minimal implementation:**

```python
# New module: src/cex_api_docs/semantic.py

import lancedb
from lancedb.embeddings import get_registry
from lancedb.pydantic import LanceModel, Vector

embedder = get_registry().get("sentence-transformers").create()

class PageEmbedding(LanceModel):
    text: str = embedder.SourceField()
    vector: Vector(embedder.ndims()) = embedder.VectorField()
    page_id: int
    exchange: str
    section: str
    url: str
    title: str

def build_index(docs_dir: str, db_path: str):
    """Build LanceDB index from SQLite page store."""
    lance_db = lancedb.connect(db_path)
    # Read pages from SQLite, create LanceDB table
    # ...

def semantic_search(db_path: str, query: str, exchange: str = None, limit: int = 10):
    """Run semantic search, optionally filtered by exchange."""
    lance_db = lancedb.connect(db_path)
    table = lance_db.open_table("pages")
    search = table.search(query).limit(limit)
    if exchange:
        search = search.where(f"exchange = '{exchange}'")
    return search.to_pandas()
```

## Hypothesis Assessment

**Hypothesis: Adding LanceDB semantic search will improve query quality over pure FTS5.**

Assessment: **Likely true, with caveats.**

- For natural language questions ("How do I get my account balance on Binance?"), semantic search will significantly improve recall by matching conceptually related documentation.
- For exact API queries ("GET /api/v3/account rate limit"), FTS5 will remain superior. Adding vector search should not degrade these queries if results are fused properly with FTS-weighted RRF.
- The improvement will be most visible for:
  - Cross-exchange queries ("Which exchanges support websocket order updates?")
  - Conceptual queries ("How do I authenticate with Bybit?")
  - Synonym-rich queries ("withdrawal" vs "transfer" vs "payout")
- The improvement will be minimal for:
  - Exact endpoint path lookups
  - Error code lookups
  - Parameter name searches

**Risk: Over-engineering.** Many practitioners in the Jan 2026 HN thread report that FTS5/BM25 alone is "surprisingly sufficient" for code and technical docs. The semantic search gap may be smaller than expected. A lightweight proof-of-concept (embed 100 pages, test 20 queries, compare results) should precede full implementation.

## Verification Status

| Claim | Sources | Verified |
|-------|---------|----------|
| LanceDB is embedded, serverless, Apache 2.0 | Official docs, GitHub, YC page | Yes (3 sources) |
| Built on Lance columnar format (Rust) | Official docs, GitHub, arxiv paper | Yes (3 sources) |
| Disk-based indexes, low memory | Official docs, FAQ, benchmark blog | Yes (3 sources) |
| <20ms brute-force for 100K vectors | FAQ, benchmark blog | Yes (2 sources) |
| Hybrid search with RRF reranking | Official docs, code examples | Yes (2 sources) |
| Pre-filter/post-filter during vector search | Official docs, FAQ, GitHub issues | Yes (3 sources) |
| merge_insert supports upsert | Official docs, Context7 docs | Yes (2 sources) |
| FTS uses Tantivy (BM25) | Official docs, thedataquarry.com | Yes (2 sources) |
| 8.9K GitHub stars, v0.26.2 | GitHub page (Feb 2026) | Yes (1 source, directly observed) |
| No vector index needed for <100K docs | FAQ | Yes (1 authoritative source) |
| Lance up to 1000x faster than Parquet for random access | FAQ, arxiv paper (Apr 2025) | Yes (2 sources) |
| all-MiniLM-L6-v2 is LanceDB default | Official embedding docs | Yes (1 authoritative source) |

## Limitations and Gaps

1. **No direct head-to-head benchmark for our exact use case.** The benchmarks found are for general datasets (GIST-1M, wine reviews), not API documentation. A local POC is needed.

2. **Embedding model quality for technical API docs is under-studied.** Most MTEB benchmarks test on general text. Performance on API documentation with HTTP methods, JSON schemas, and code snippets may differ. Fine-tuning may be needed.

3. **LanceDB FTS vs SQLite FTS5 quality comparison is absent.** No benchmark directly compares BM25 quality between Tantivy (LanceDB) and SQLite FTS5. They should be broadly equivalent since both implement BM25, but tokenization and stemming differences may matter.

4. **Concurrent write behavior.** LanceDB supports concurrent reads well but has limited concurrent write support (retries on conflict). Our project already uses a write lock for SQLite; the same pattern would work for LanceDB.

5. **Version/fragment accumulation.** For a project that updates pages frequently, Lance version accumulation could be an issue without periodic compaction. This is a maintenance task to add.

6. **Python >=3.9 required** for LanceDB (our project requires >=3.11, so no conflict).

7. **Embedding model dependency.** Adding a sentence-transformers model adds ~100-500MB of model weights to download. First-time setup will be slower. This can be mitigated by making the semantic search feature optional (`pip install cex-api-docs[semantic]`).

8. **No evaluation of sqlite-vec as an alternative.** The `sqlite-vec` extension could provide vector search directly within SQLite, avoiding a second database. However, it is less mature than LanceDB and lacks built-in embedding management, hybrid search, and reranking. Worth investigating as a lighter-weight alternative in a follow-up.

## Sources

| Source | URL | Quality | Notes |
|--------|-----|---------|-------|
| LanceDB Official Docs - Quickstart | https://docs.lancedb.com/quickstart | High (official) | Core setup and API |
| LanceDB Official Docs - Lance Format | https://docs.lancedb.com/lance | High (official) | Storage architecture |
| LanceDB Official Docs - Embeddings | https://docs.lancedb.com/embedding | High (official) | Embedding registry, models |
| LanceDB Official Docs - Hybrid Search | https://docs.lancedb.com/search/hybrid-search | High (official) | RRF, reranking |
| LanceDB Official Docs - Full-Text Search | https://docs.lancedb.com/search/full-text-search | High (official) | BM25, tokenization, fuzzy |
| LanceDB Official Docs - Filtering | https://docs.lancedb.com/search/filtering | High (official) | Pre/post filter, SQL syntax |
| LanceDB Official Docs - Indexing | https://docs.lancedb.com/indexing | High (official) | IVF-PQ, HNSW, scalar, FTS indexes |
| LanceDB Official Docs - FAQ (OSS) | https://docs.lancedb.com/faq/faq-oss | High (official) | Scaling, concurrency, performance guidance |
| LanceDB GitHub Repository | https://github.com/lancedb/lancedb | High (primary source) | v0.26.2, 8.9K stars, active development |
| "Benchmarking LanceDB" (EtoAI/LanceDB blog) | https://medium.com/etoai/benchmarking-lancedb-92b01032874a | High (first-party) | GIST-1M benchmark, Dec 2023 |
| "Embedded databases (3): LanceDB" (thedataquarry.com) | https://thedataquarry.com/blog/embedded-db-3 | High (independent, updated 2025) | Architecture deep-dive, LanceDB vs Elasticsearch benchmark |
| "Hybrid full-text search and vector search with SQLite" (Alex Garcia) | https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html | High (independent, author of sqlite-vec) | RRF, keyword-first, re-rank approaches in SQLite |
| "Ask HN: How are you doing RAG locally?" | https://news.ycombinator.com/item?id=46616529 | Medium (practitioner reports) | Jan 2026, 413 points, 157 comments. Real-world RAG stack choices. |
| "6 Best Code Embedding Models Compared" (Modal) | https://modal.com/blog/6-best-code-embedding-models-compared | Medium (vendor blog, well-researched) | Mar 2025. VoyageCode3, Jina Code V2, Nomic Embed Code |
| Lance arxiv paper | https://arxiv.org/html/2504.15247v1 | High (peer-reviewed) | "Lance: Efficient Random Access in Columnar Storage", Apr 2025 |
| LanceDB Context7 Documentation | /websites/lancedb (Context7 ID) | High (structured docs) | 1,959 code snippets, comprehensive |
| LanceDB Enterprise Benchmarks | https://docs.lancedb.com/enterprise/benchmarks | High (official) | 25ms vector search, 50ms with filtering |
| prrao87/lancedb-study (benchmark repo) | https://github.com/prrao87/lancedb-study | Medium (independent reproducible) | FTS + vector benchmark vs Elasticsearch |
