# Stats performance, 9 September 2026

The API-only deployment run 34347367284 shipped source 825dd42a0484e7e23bde360aebe86cc819e0a43f. Worker version 27ba96c8-9822-490d-a1d4-5ed33931dc3d was verified at 100% traffic. Rollback version: 2b864d49-439c-4bb3-92e3-85e74d9d2c9a.

The paired public response receipts are in evidence/stats-2026-09-09. Unique URL parameters were used to infer fresh cache keys, followed by identical-URL repeat requests; no explicit MISS header was available. Median fresh requests were 586 ms before and 654 ms after, but the observed colos changed from HKG to SIN, so this is not causal performance evidence. Published references stayed at 1,141. Transcript episodes changed from 1,226 to 1,227; that query was unchanged by this release and the dataset was not frozen.

One-day D1 insights subsequently identified the transcript COUNT(DISTINCT segments.episode_id) join as the largest observed query by reads: 786,202 average rows, 55,820,394 total rows, 71 executions and 245.802087 ms average duration. The 15-minute insights query returned no entries.

PR26 replaces that join with trusted episodes plus an indexed EXISTS segment probe. Inactive trusted shows continue to count; withheld shows and episodes without segments do not. A real SQLite handler fixture checks 10,000 segments count once. Full quality passed: 123 API and 228 Python tests. Local Wrangler D1 EXPLAIN shows SCAN episodes, a correlated subquery, SEARCH segments USING COVERING INDEX segments_episode_id_idx (episode_id=?), and indexed show lookup. No migration is required.

The rewrite is source-validated only until its release and production measurements are recorded. Issue24 remains open.
