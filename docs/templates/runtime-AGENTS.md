# Runtime AGENTS Guide

This runtime repo is for **querying only**.

## Rules

- Use `cex-api-query` skill for CEX API doc questions.
- Do not run crawling/sync maintenance commands in normal teammate workflows.
- If data looks stale, request a maintainer snapshot refresh.

## Typical teammate flow

1. `git pull`
2. start fresh agent session
3. `Use cex-api-query skill.`
4. ask query
