# Agent Interface Design — CLI vs MCP Server

**Started:** 2026-02-11
**Status:** In discussion

## The Core Insight

The cex-api-docs tool was always meant to be an **agent tool** — like Context7 is for library docs, this is for CEX API documentation. A user prompts Claude in natural language, Claude uses a skill/tool to query the stored docs, retrieves raw data, and synthesizes a readable answer.

The architecture:

```
User prompt
  → Claude (agent)
    → Skill/MCP (teaches Claude how to use the tool)
      → cex-api-docs (retrieval layer)
        → SQLite store (3,813 pages, 3,125 endpoints, 16 exchanges)
      ← structured data back
    ← Claude synthesizes
  → readable answer to user
```

## What Exists Today

**Storage layer (solid):**
- 3,813 pages, 4.48M words across 16 exchanges, 37 sections
- 3,125 structured endpoint records with method, path, base_url, request/response schemas
- SQLite FTS5 indexes on both pages and endpoints
- Markdown files on disk with full doc content

**CLI commands available:**
- `search-pages <query>` — FTS5 search across stored pages, returns URLs + snippets
- `search-endpoints <query> [--exchange X]` — FTS5 search on endpoint records
- `get-page <url>` — retrieve a stored page by canonical URL
- `answer <question>` — prototype Q&A (FTS5 + 400-char excerpts, mostly nav chrome)
- `store-report` — stats on what's in the store

**What's missing:**
- A skill/tool definition that teaches an agent HOW to use these commands
- Nav-stripping / section-aware content extraction (excerpts hit sidebar chrome)
- A way to get clean endpoint details (the JSON is there but buried in a blob column)

## Demo That Proved the Concept

User asked: "What is the endpoint to transfer between my Binance master account and the Unified Sub Account?"

What Claude actually did (ad-hoc, not via any skill):
1. `search-endpoints --exchange binance "sub account transfer"` → found `POST /sapi/v1/sub-account/universalTransfer`
2. Queried SQLite directly to get the full endpoint JSON (method, path, params, description)
3. `search-pages "universalTransfer fromAccountType toAccountType"` → found the doc page URL
4. Read the stored markdown file, used regex to skip nav chrome, extracted the content section
5. Synthesized: endpoint, parameters table, transfer rules, rate limits, response example, source URL

Result: Complete, accurate, cited answer. But the workflow was improvised — no skill guided it.

## Decision: CLI Tool vs MCP Server

### Option A: CLI Tool + Skill

How it works:
- A SKILL.md file teaches Claude how to use `cex-api-docs` CLI commands via Bash
- Claude runs bash commands, parses JSON output, reads markdown files
- Works only inside Claude Code (needs bash access)

Pros:
- No new code to write (CLI already exists)
- Skill file is just documentation
- Fast to ship — hours not days
- Easy to iterate (edit SKILL.md, test immediately)

Cons:
- Only works in Claude Code (requires Bash tool)
- Agent must parse JSON output from CLI
- Multiple round-trips: search → get page → read file → synthesize
- Can't be used by other AI tools (Cursor, Windsurf, etc.) without modification
- Direct SQLite queries feel hacky vs proper tool interface

### Option B: MCP Server

How it works:
- Python MCP server exposes tools: `search_endpoints`, `search_pages`, `get_page_content`, `get_endpoint_detail`
- Tools return structured, clean data (nav-stripped, section-extracted)
- Any MCP-compatible client can use it (Claude Code, Claude Desktop, Cursor, etc.)

Pros:
- Works everywhere MCP is supported (Claude Code, Claude Desktop, Cursor, etc.)
- Tools return clean structured data (can strip nav chrome server-side)
- Can combine search + content retrieval in fewer calls
- Proper tool descriptions guide the agent automatically
- Reusable by any AI agent, not just Claude
- Like Context7 — proven pattern that works

Cons:
- Need to write new code (MCP server wrapper)
- Need to handle server lifecycle (start/stop, config)
- More moving parts to maintain
- Requires MCP SDK dependency

### Option C: Both (CLI stays as-is, MCP server wraps it)

The CLI remains the data management interface (crawl, sync, import).
The MCP server is the agent query interface (search, read, get endpoint).
A skill teaches Claude Code users about both.

### Key Questions to Decide

1. **Who are the users?** Just Claude Code, or also Claude Desktop / other AI tools?
2. **Is nav-stripping important enough to do server-side?** Or can the agent handle it?
3. **How important is the "works like Context7" pattern?** (MCP server with tool descriptions)
4. **Should `answer.py` be replaced or kept alongside?** It tries to synthesize answers but that's the agent's job.

## Transcript

### 2026-02-11 — Initial Discussion

**User's observation:** The wow query showcase showed 8/16 exchanges returned "Weak" results from the `answer` command. But when Claude manually searched the endpoint DB, read the stored markdown, and synthesized an answer, the result was excellent. The tool's value is in the data layer, not in `answer.py`.

**User's vision:** "A user would prompt the AI what they want to know about the exchange's API documentation and the AI using a skill that it invokes... the skill will basically line out exactly how to use the tool to get exactly the information... Just like Context7."

### 2026-02-11 — CLI vs MCP: Are They Actually Different?

**User's challenge:** "Aren't MCP servers just CLI tools that agents can use online? Any other agent can use CLI tools."

**Realization:** Yes. From the agent's perspective, calling an MCP tool vs running a bash command produces the same result — JSON in, JSON out. The CLI already outputs JSON.

The actual differences are thin:

| | CLI + Skill | MCP Server |
|---|---|---|
| Agent calls it via | Bash tool | MCP tool call |
| Tool descriptions | Skill file (markdown) | JSON Schema (built-in) |
| Works in Claude Code | Yes | Yes |
| Works in Cursor/Windsurf/etc | Yes (bash) | Yes (MCP) |
| Works in Claude Desktop | No (no bash) | Yes |
| Server lifecycle | None (one-shot) | Must run as process |
| New code needed | Just a skill file | MCP wrapper around existing CLI |
| Output format | Already JSON | Already JSON (same) |

**Conclusion:** An MCP server is the CLI with a JSON-RPC wrapper and self-describing tool schemas. The skill file serves the same purpose as tool descriptions — it tells the agent what commands exist and how to use them. Unless Claude Desktop support is needed, the MCP wrapper adds protocol overhead without functional benefit.

**Decision:** Start with CLI + Skill (zero new code, ship today). If Claude Desktop or remote hosting becomes a requirement, wrap the CLI in MCP later — it's mechanical, not architectural.

**Open question:** What should the skill contain? What's the right set of "tools" (CLI commands) the agent needs to answer any exchange API question?

### 2026-02-11 — Skill Designed and Written

**Decision:** CLI + Skill. MCP adds protocol overhead without functional benefit for local use.

**Skill created:** `skills/cex-api-query/SKILL.md`

The skill teaches the agent a 4-step workflow:
1. **Search endpoints** — `search-endpoints` for structured endpoint data (method, path, params, schemas)
2. **Search pages** — `search-pages` for full-text doc search (auth flows, conceptual docs, changelogs)
3. **Read full content** — Direct SQLite + file read for complete markdown when snippets aren't enough
4. **Synthesize** — Present the answer with endpoint, params, rules, response example, source URL

Key design choices:
- Includes direct SQLite queries (not just CLI) because the CLI `get-page` has a JSON parsing bug and the endpoint JSON blob needs to be parsed from the `json` column
- Documents the nav chrome problem and how to skip it (regex to first `#` heading)
- Covers all 6 common query patterns: endpoint lookup, auth/signing, rate limits, parameters, comparison, error codes
- Lists all 16 exchanges with endpoint counts so the agent knows what coverage exists

**Next:** Test the skill by using it to answer a real question.

### 2026-02-11 — Evaluation and Fixes

**Issues found (6):**
1. Missing `metadata.version` in frontmatter
2. `activation` isn't a standard field — triggers belong in `description`
3. Workflow used code block instead of `- [ ]` checklist
4. No concrete input→output example
5. No self-evolution section
6. No EVALUATIONS.md

**Also fixed:**
- Replaced hardcoded counts ("3,125 endpoints") with instruction to run `store-report`
- Replaced fragile `python3 -c` for reading files with Read tool + Grep guidance
- Added "when to stop" guidance (Step 5)
- Added "not found" handling (exchange not in store, topic not covered, partial info)

**Files updated:**
- `skills/cex-api-query/SKILL.md` — v1.0.0, 214 lines, all checklist items passing
- `skills/cex-api-query/EVALUATIONS.md` — 3 scenarios (happy path, edge case, not found)

**Evaluation re-check:**

| Check | Status |
|-------|--------|
| `name` lowercase hyphens | Pass |
| `description` third person, what+when | Pass |
| `metadata.version` semver | Pass |
| Body under 500 lines | Pass (214) |
| Workflow checklist `- [ ]` | Pass |
| Concrete example | Pass (Binance universal transfer) |
| Self-evolution section | Pass |
| 3 evaluation scenarios | Pass |

### 2026-02-11 — Evaluation Scenarios Run — All Pass

All 3 evaluation scenarios were run using parallel agents that followed the skill workflow.

**Scenario 1: Happy Path — Binance Spot Limit Order**
- Agent ran `search-endpoints "place order" --exchange binance` → found `POST /api/v3/order`
- Retrieved full endpoint JSON from SQLite → extracted 8 parameters with types and required flags
- Read stored markdown for additional rules (timeInForce required for LIMIT, STOP_LOSS needs stopPrice)
- Presented: method, path, parameters table, usage rules, source URL
- **Result: PASS** — all 5 success criteria met

**Scenario 2: Edge Case — OKX Single-Page Doc (224K words)**
- Agent ran `search-pages "OKX sign request header"` → found the single OKX page
- Used Grep to locate authentication section within the 224K-word file (did NOT read entire file)
- Read ~150 lines around the auth heading
- Extracted all 4 headers (OK-ACCESS-KEY, OK-ACCESS-SIGN, OK-ACCESS-TIMESTAMP, OK-ACCESS-PASSPHRASE) and HMAC-SHA256 signing procedure
- **Result: PASS** — all 4 success criteria met, large file handled correctly

**Scenario 3: Not Found — Kraken (not in store)**
- Agent ran `search-endpoints "rate limit" --exchange kraken` → no results
- Agent ran `search-pages "Kraken rate limit"` → no results
- Agent tried one more variation, then stopped
- Clearly stated Kraken is not in the store, listed all 16 available exchanges
- **Result: PASS** — no hallucination, clear communication, stopped after 3 searches

**Conclusion:** The skill successfully guides agents through all tested patterns. The 4-step workflow (search → get details → read markdown → synthesize) works for happy paths, edge cases, and not-found scenarios.

**Status: Skill v1.0.0 is ready for use.**
