# Stats performance, 9 September 2026

The API-only deployment run 34347367284 shipped source 825dd42a0484e7e23bde360aebe86cc819e0a43f. Worker version 27ba96c8-9822-490d-a1d4-5ed33931dc3d was verified at 100% traffic. Rollback version: 2b864d49-439c-4bb3-92e3-85e74d9d2c9a.

The paired public response receipts are in evidence/stats-2026-09-09. Unique URL parameters were used to infer fresh cache keys, followed by identical-URL repeat requests; no explicit MISS header was available. Median fresh requests were 586 ms before and 654 ms after, but the observed colos changed from HKG to SIN, so this is not causal performance evidence. Published references stayed at 1,141. Transcript episodes changed from 1,226 to 1,227; that query was unchanged by this release and the dataset was not frozen.

One-day D1 insights subsequently identified the transcript COUNT(DISTINCT segments.episode_id) join as the largest observed query by reads: 786,202 average rows, 55,820,394 total rows, 71 executions and 245.802087 ms average duration. The 15-minute insights query returned no entries.

PR26 replaces that join with trusted episodes plus an indexed EXISTS segment probe. Inactive trusted shows continue to count; withheld shows and episodes without segments do not. A real SQLite handler fixture checks 10,000 segments count once. Full quality passed: 123 API and 228 Python tests. Local Wrangler D1 EXPLAIN shows SCAN episodes, a correlated subquery, SEARCH segments USING COVERING INDEX segments_episode_id_idx (episode_id=?), and indexed show lookup. No migration is required.

## Released transcript rewrite

PR26 merged as 46badc63151dd30a7bd95914763cf493a653023c. Exact-main CI34348449974 passed, all six deployment gates passed, and API-only deployment34348609233 succeeded. Worker version 6ac7d86c-e48f-4dad-986b-c3c5455afc27 carries that full source tag at 100% traffic (deployment eb87f76e-e2fc-4269-a644-2b3c2f204736, 12:01:34 UTC). Rollback is version 27ba96c8-9822-490d-a1d4-5ed33931dc3d. Web was skipped; no migration ran.

All twelve paired responses before/after the transcript rewrite were HTTP200 with identical complete bodies, including 1,227 transcript episodes and 1,141 published references. Both sets reached SIN. Three inferred-fresh requests had median 792 ms before and 635 ms after; repeats had median 103 ms before and 201 ms after. This small network-inclusive sample is encouraging for fresh requests, but not proof of sustained improvement. The retained transcript-before/after receipts include every sample.

A separate synthetic SQLite fixture of 8,500 episodes and 780,800 segments returned 1,220 transcript episodes with both queries. Approximate VM instructions fell from 16,399,200 to 138,400 (see transcript-benchmark.json). These are local VM instructions, not production D1 row-read measurements. The refreshed one-day baseline is retained separately as d1-before.json; its rolling window differs from the earlier observation above.

Issue24 remains open until post-release D1 insights establish reduced production reads and the broader performance acceptance is reviewed.
