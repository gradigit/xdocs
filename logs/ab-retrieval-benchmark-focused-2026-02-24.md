# A/B Retrieval Benchmark (Focused Stress Turn)

| Metric | A (pre-update turn) | B (post-update turn) |
|---|---:|---:|
| Commands | 122 | 128 |
| Semantic calls | 0 | 0 |
| Semantic+rERANK calls | 0 | 0 |
| search-pages calls | 5 | 26 |
| search-endpoints calls | 2 | 11 |
| get-endpoint calls | 3 | 7 |
| Raw scan-ish calls | 93 | 79 |
| Peak input tokens | 230497 | 168306 |
| Peak total tokens | 244238 | 183243 |
| Final answer chars | 13150 | 12513 |

- A context usage: input 89.2%, total 94.5%
- B context usage: input 65.1%, total 70.9%

- A: retrieval_audit=False, citation_ledger=True, conflict_audit=False, rollout_plan=False
- B: retrieval_audit=True, citation_ledger=True, conflict_audit=True, rollout_plan=True
