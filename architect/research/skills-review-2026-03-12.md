# Skills Review — 2026-03-12

## Skill Topology

Canonical repo skills live under [`skills/`](../../skills) and are symlinked into:

- [`.claude/skills`](../../.claude/skills)
- [`.agents/skills`](../../.agents/skills)

Current canonical skills:

- [`skills/cex-api-docs/SKILL.md`](../../skills/cex-api-docs/SKILL.md)
- [`skills/cex-api-query/SKILL.md`](../../skills/cex-api-query/SKILL.md)
- [`skills/cex-discovery/SKILL.md`](../../skills/cex-discovery/SKILL.md)
- [`skills/cex-qa-gapfinder/SKILL.md`](../../skills/cex-qa-gapfinder/SKILL.md)
- [`skills/agent-browser/SKILL.md`](../../skills/agent-browser/SKILL.md)

## Shared Conventions

Across the canonical skills, the common contract is:

- YAML frontmatter with `name` and `description`
- deterministic, operational workflows rather than vague advice
- strong emphasis on local store usage and cite-only behavior
- explicit shell commands rather than abstract prose

The repo’s skill system is not decorative. The skills encode real operating procedures.

## Skill-by-Skill Review

### 1. `cex-api-docs`

File: [`skills/cex-api-docs/SKILL.md`](../../skills/cex-api-docs/SKILL.md)

Purpose:

- Maintainer/operator workflow for crawling, syncing, importing, validating, and updating docs

Shape:

- onboarding sequence for new maintainers
- full sync workflow with readiness checks
- post-sync validation and maintenance workflow
- new exchange onboarding checklist
- doc/skill update checklist

Boundary:

- maintainer-side only
- assumes access to full source tree, local store, and optional heavy dependencies

Assessment:

- This is the strongest operational skill in the repo and effectively serves as the maintainer runbook.

### 2. `cex-api-query`

File: [`skills/cex-api-query/SKILL.md`](../../skills/cex-api-query/SKILL.md)

Purpose:

- End-user question answering over the local docs store

Shape:

- classify-first routing
- semantic-first path for natural-language questions
- targeted lookup for errors/endpoints/payloads/code snippets
- strict source-link and citation-ledger requirements
- fail-closed output guidance

Boundary:

- query-only behavior
- should not expand into general web research unless explicitly needed

Assessment:

- This is the main user-facing skill and mirrors the actual code path in `classify.py`, `lookup.py`, `semantic.py`, and `answer.py`.

Maintenance drift found:

1. Metadata version is `2.11.0`, but the retrieval-audit template still says `skill_used: cex-api-query@2.10.0`.
2. The "What's In The Store" counts are stale versus the current store report. The skill says `10,724 pages` and `4,872 structured endpoints`; the current store report is `10,727 pages` and `4,963 endpoints`.
3. The endpoint/page coverage examples are stale. For example, Kraken is described as pages-only/no endpoints in the skill section, but the current store report shows `kraken/spot` with `90` endpoints.

Related evaluation drift:

- [`skills/cex-api-query/EVALUATIONS.md`](../../skills/cex-api-query/EVALUATIONS.md) still has a scenario whose expected behavior says "Kraken is not in the store", which is no longer true.

### 3. `cex-discovery`

File: [`skills/cex-discovery/SKILL.md`](../../skills/cex-discovery/SKILL.md)

Purpose:

- exhaustive source discovery before registry onboarding or audit refresh

Shape:

- web/domain discovery
- robots/sitemap/llms/spec probing
- GitHub/org/spec discovery
- crawl-method testing
- CCXT cross-reference
- output into bible entry + registry block

Boundary:

- discovery and source research only
- does not perform the actual repo registration or sync itself

Assessment:

- This is effectively the research protocol behind the registry and bible. It is broad, checklist-driven, and intentionally exhaustive.

### 4. `cex-qa-gapfinder`

File: [`skills/cex-qa-gapfinder/SKILL.md`](../../skills/cex-qa-gapfinder/SKILL.md)

Purpose:

- test the live runtime/store and produce structured QA findings without fixing anything

Shape:

- smoke test prerequisite
- blind vs normal mode rotation
- multi-category QA plan: data integrity, coverage, query paths, correctness, fuzzing, golden QA, regressions
- required output artifacts: `qa-findings.jsonl` and `QA-REPORT.md`

Boundary:

- QA only, no remediation
- operationally targets the runtime environment more than the maintainer repo

Assessment:

- Strong test-plan skill with explicit report schema and useful adversarial coverage.

Maintenance nuance:

- The prerequisite path `scripts/runtime_query_smoke.py` is correct for the runtime repo after sync/export, but that file does not exist as a top-level script in this maintainer repo. The skill is canonical here but operationally runtime-targeted. That is acceptable, but it should be stated more explicitly up front to reduce confusion in maintainer-repo sessions.

### 5. `agent-browser`

File: [`skills/agent-browser/SKILL.md`](../../skills/agent-browser/SKILL.md)

Purpose:

- generic browser automation skill used by agents

Shape:

- command cookbook for `agent-browser`
- ref lifecycle guidance
- local file, auth, session, and capture patterns
- CEX-specific note on nav extraction and full-page/accordion expansion

Boundary:

- generic browser interaction, not CEX-specific logic

Assessment:

- This skill is infrastructural. In this repo it mainly supports nav extraction and crawl validation workflows for JS-heavy documentation sites.

## Cross-Skill Relationships

The skills form a coherent lifecycle:

1. `cex-discovery` finds sources
2. `cex-api-docs` ingests, validates, and packages them
3. `cex-api-query` answers questions from the resulting store
4. `cex-qa-gapfinder` stress-tests the result
5. `agent-browser` supports JS-rendered site interaction where static crawling is insufficient

That composition is clear and well-scoped.

## Main Maintenance Risks

1. Query-skill content drift: store counts and example expectations age quickly as the store changes.
2. Evaluation drift: scenario files can become actively wrong when exchange coverage changes.
3. Canonical-vs-symlink wording drift: some instructions still refer people to `.claude/skills/...` even though the repo rule says edit canonical files under `skills/`.
4. Runtime-targeted skills maintained in the maintainer repo need stronger labeling so operators know which repo context they are meant to run in.

## Net Assessment

The skill layer is high value and mostly aligned with the repo’s actual workflows. The largest issue is not conceptual overlap, but maintenance drift in query-facing examples and counts.
