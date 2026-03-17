# M1 Review Findings

## Finding 1: Redundant embedding computation on retry paths (WARNING)
- `_get_query_vector()` called up to 3x for hybrid/vector with retries
- Fix: cache query vector with `nonlocal`

## Finding 2: FTS fallback to vector loads embedder (WARNING)
- When FTS fails + retry fails, falls back to vector search, loading 495MB model
- Fix: don't fall back to vector for explicit `query_type="fts"`

## Positive
- Core optimization sound: FTS happy path avoids model loading (14s → 1s)
- inventory_fetch.py cascade fix is safe
- Closure captures `query` correctly
