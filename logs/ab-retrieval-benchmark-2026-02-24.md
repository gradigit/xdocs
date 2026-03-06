# A/B Retrieval Benchmark

Compared two stress-test sessions for retrieval behavior and efficiency.

| Metric | A (pre update) | B (post update) | Delta (B-A) |
|---|---:|---:|---:|
| Commands | 122 | 177 | +55 |
| Semantic calls | 0 | 0 | +0 |
| Semantic+rERANK calls | 0 | 0 | +0 |
| search-pages calls | 5 | 32 | +27 |
| search-endpoints calls | 2 | 13 | +11 |
| get-endpoint calls | 3 | 8 | +5 |
| Raw scan-ish calls | 93 | 109 | +16 |
| Peak input tokens | 230497 | 205198 | -25299 |
| Peak total tokens | 244238 | 206586 | -37652 |
| Final answer chars | 13150 | 978 | -12172 |

- A context usage: input 89.2% / total 94.5% (window=258400)
- B context usage: input 79.4% / total 79.9% (window=258400)

## Compliance checks

- A_pre_update: skill_read=True, retrieval_audit=False, citation_ledger=True, conflict_audit=False, rollout_plan=False
- B_post_update: skill_read=True, retrieval_audit=False, citation_ledger=False, conflict_audit=False, rollout_plan=False

## Key finding

- B reduced token pressure vs A, but still did not use semantic-search or reranker; it remained FTS/raw-scan heavy.
