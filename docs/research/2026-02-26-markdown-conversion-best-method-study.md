# Research: Is Markdown Conversion the Best Method for API-Docs Ingestion?
Date: 2026-02-26
Depth: Full

## Short Answer
Markdown conversion is **a strong baseline**, but **not the single best method** across all API-doc pages.
For reliability and retrieval quality, the best approach is usually **hybrid**:
1) keep raw HTML as source of truth,
2) keep Markdown for LLM-friendly retrieval,
3) keep structure-aware element metadata (headings/tables/code blocks) for precision.

## Why this conclusion

### 1) A single extractor is often suboptimal
Recent research shows extractor choice materially changes what survives preprocessing:
- ArXiv 2602.19548 reports that taking a **union over extractors** can increase token yield by up to **71%** while maintaining benchmark performance.
- It also reports extractor-sensitive downstream differences on **tables/code** tasks.

Implication: “one converter for everything” is risky.

### 2) Markdown itself is useful, but conversion can be lossy
Pandoc docs explicitly warn that conversions from more expressive formats can be lossy and that complex tables may not map cleanly to Markdown representations.

Implication: Markdown is good for readability/token-efficiency, but can drop fidelity in complex structures.

### 3) Your current converter (html2text) has known tradeoffs
html2text supports options like:
- `MARK_CODE` -> wraps code with `[code]...[/code]`
- table behaviors (`BYPASS_TABLES`, `IGNORE_TABLES`)

Implication: defaults may be suboptimal for API docs where strict code/table preservation matters.

### 4) Structure-aware pipelines improve chunking/retrieval
Unstructured docs emphasize partitioning into semantic elements first, then chunking, with special treatment for tables (`Table`, `TableChunk`).
Azure AI Search docs similarly recommend structure-aware chunking based on headings/paragraph coherence.

Implication: element-aware ingestion generally outperforms flat text splitting for retrieval quality.

### 5) Alternative Markdown-focused tools are designed for LLM pipelines
Microsoft MarkItDown explicitly positions Markdown conversion for LLM/text-analysis pipelines with structure preservation (headings/lists/tables/links).
Trafilatura supports multiple output modes and extraction controls (tables/formatting/links), and publishes comparative evaluation.

Implication: if staying Markdown-first, use richer extractors and fallback strategies, not a single fixed converter.

## Recommendation for this repo

### Keep
- Raw HTML + metadata storage (already good)
- Markdown output for retrieval and human inspection

### Add (high ROI)
1. **Code-fence normalization layer**
   - Convert `[code]...[/code]` to fenced code blocks with optional inferred language.
2. **Table-preservation policy**
   - Prefer keeping complex tables as HTML blocks in markdown or as structured table objects.
3. **Dual-extractor path (A/B or fallback)**
   - Keep current extractor as baseline; add a second extractor path for pages where quality checks fail.
4. **Element sidecar JSON**
   - Persist heading hierarchy + block type + offsets + source URL/hash so retrieval can target code/table blocks directly.

## Confidence
High that Markdown-only is not universally best.
Medium-high on exact tool choice for your corpus (needs local A/B with your exchanges).

## Sources
- arXiv: Beyond a Single Extractor (2602.19548)
- Pandoc User’s Guide
- html2text usage docs
- Unstructured chunking docs
- Azure AI Search structure-aware chunking docs
- Microsoft MarkItDown README
- Trafilatura usage and evaluation docs
