# Security best practices report

## Executive summary
1. Path traversal during endpoint ingestion can escape the docs store and write arbitrary JSON anywhere the process can reach.
2. The LanceDB semantic search filter interpolates the `--exchange` string verbatim, so crafted CLI inputs can inject expressions and defeat result filtering.
3. The SQLite migration table is empty, so bumping `SCHEMA_USER_VERSION_V1` in the future will break existing stores unless a migration is added, posing an operational upgrade risk.

## High severity
1. **SEC-01: Untrusted exchange/section values escape docs store when writing endpoint JSON**
Impact: An endpoint JSON record with `exchange`/`section` containing `..` or absolute components causes `Path(docs_dir) / "endpoints" / exchange / section / ...` to resolve outside the store, letting an attacker (or malformed automation) overwrite any file the process user can reach whenever `save-endpoint` or `save-endpoints-bulk` runs. This can be used to drop arbitrary payloads or corrupt data outside the intended store boundary.
Location: `src/cex_api_docs/endpoints.py:410-417`
Remediation: Normalize/validate `exchange` and `section` before building `endpoint_dir` (reject absolute paths, `..`, path separators, or only accept IDs listed in `data/exchanges.yaml`). Alternatively resolve `endpoint_dir` and verify it sits under `Path(docs_dir).resolve()` before touching disk.
Tests: Add a regression that feeds a JSON with `exchange` = `"../../tmp/attack"` and asserts `save_endpoint` fails rather than writing, plus an end-to-end `save-endpoint` CLI test that confirms the directory stays inside the store when using valid IDs.

## Medium severity
1. **SEC-02: Semantic search exchange filter is injectable**
Impact: `semantic_search` builds the filter string with `search.where(f"exchange = '{exchange}'")` so any `'`-containing `--exchange` value is treated as part of the query language and can let a caller match every row or cause syntax errors leading to crashes. If the CLI is exposed to untrusted inputs (e.g., via an automation API), an attacker can bypass the intended exchange filter.
Location: `src/cex_api_docs/semantic.py:209-214`
Remediation: Use LanceDB parameter binding (e.g., `search.where("exchange = ?", exchange=exchange)`) or validate `exchange` against the known registry IDs before passing it through. Escaping single quotes is insufficient unless combined with a whitelist.
Tests: Add a unit test that injects `exchange="foo' OR 1=1 --"` and asserts the call raises before hitting LanceDB, plus a golden test that legitimate `--exchange binance` still filters correctly.

2. **SEC-03: No migration map limits schema upgrades**
Impact: `MIGRATIONS` is an empty dict while `SCHEMA_USER_VERSION_V1` is 1. The next time the schema needs to change (version 2), opening an existing store will immediately raise `ESCHEMAVER` because there is no migration entry, so any upgrade requires manual rebuilds and threatens data loss for existing users.
Location: `src/cex_api_docs/db.py:11-110`
Remediation: Populate `MIGRATIONS` with at least an identity entry per schema bump or ship a migration generator that can replay required DDL. Document in release notes that every schema change requires a migration snippet and add a check ensuring `MIGRATIONS` contains `(SCHEMA_USER_VERSION_V1 - 1, SCHEMA_USER_VERSION_V1)` before releasing.
Tests: Add a regression that simulates upgrading from user_version 1 to 2 by setting `SCHEMA_USER_VERSION_V1 = 2` in a test fixture and verifying `apply_schema` either runs an inserted migration script or raises a descriptive error that points maintainers to add the missing entry.
