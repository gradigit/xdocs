# Full Review Synthesis — 2026-03-12

## What The Repo Does

This repo is a local documentation operating system for exchange APIs.

Its intended end state is:

1. official exchange docs are discovered and fetched exhaustively
2. page content and structured endpoints are stored locally with provenance
3. local search surfaces can answer exchange API questions without browsing live docs
4. all answers fail closed when evidence is missing
5. maintainers can validate coverage, drift, and retrieval quality continuously

## What It Is Supposed To Do

The repo is supposed to support three user classes:

1. **Maintainers** who crawl, import, validate, benchmark, and package the dataset
2. **Runtime users** who query the packaged snapshot with a smaller runtime repo
3. **Agents** who use the skill layer to operate both workflows consistently

The central product promise is not "search docs" in the generic sense. It is:

- cite-only answers
- deterministic ingestion/storage
- exhaustive coverage expectations
- explicit validation gates around completeness and retrieval quality

## Main Workflows Attached To The Repo

### Maintainer

- bootstrap environment
- init store
- sync/inventory/fetch docs
- import specs
- run validation/coverage/audit/retrieval checks
- update docs/skills
- export runtime repo and publish data snapshot

### Runtime

- install query-only package
- download data snapshot
- run runtime smoke test
- use query/answer commands or the query skill

### Expansion

- discover a new exchange
- add registry + bible entries
- crawl and validate it
- import specs
- rebuild index
- update documentation and skills

### QA

- run targeted or exploratory QA against the live store
- compare to golden QA and previous runs
- write structured findings without fixing anything

## Architecture Reality

The repo is centered on shared state, not on services:

- registry state in YAML
- persistent state in SQLite
- optional semantic state in LanceDB
- operational state in scripts, tests, docs, and skills

The code splits cleanly into:

- crawl/inventory/fetch
- store/schema/persistence
- endpoint/spec import
- query/classify/retrieve/answer
- validation/benchmark/audit
- runtime packaging

## Skill Layer Reality

The skill system is meaningful and aligned with the codebase:

- `cex-discovery` -> find sources
- `xdocs` -> ingest and maintain
- `cex-api-query` -> answer questions
- `cex-qa-gapfinder` -> test the result
- `agent-browser` -> support rendered-site inspection and automation

The main issue in the skill layer is maintenance drift in examples and counts, not poor structure.

## Highest-Value Risks Found During Review

1. The query skill has stale version text and stale store-count content.
2. The query skill evaluation scenarios are stale enough to be wrong for at least Kraken.
3. The repo relies heavily on documentation and skill updates as part of correctness, so stale docs are an operational risk, not just a polish issue.
4. The project has many moving parts, but the real source of truth is distributed across code, registry data, and operational docs rather than a single architecture document.

## Bottom Line

This codebase is mature, workflow-heavy, and intentionally operational. It is best understood as a documentation ingestion/query platform with strong maintainer procedures, not as a simple CLI package or a single-agent skill bundle.
