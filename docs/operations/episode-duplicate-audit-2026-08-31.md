# Episode duplicate audit — 2026-08-31

This records the production audit and recovery-first reconciliation completed
for GitHub issue #7.

## Result

Production contains 204 `yt:` episode rows. All 204 are still `discovered` and
none owns segments, claims, evidence, or LLM runs. They do own episode-person
links and one discovery object each in R2, so even these otherwise-empty rows
must not be deleted blindly.

Only one pair was proven to represent the same episode. The RSS row and YouTube
row shared the same show, title, and YouTube video ID. Their source timestamps
differed by about 2.5 hours, which is consistent with feed/video publication
lag but was not used as identity evidence.

| role | episode id | guid | status | segments | claims | evidence | people | LLM runs |
|---|---|---|---|---:|---:|---:|---:|---:|
| canonical RSS | `0b99e4f6-1acb-4e31-8a6e-8184350c96fb` | `a176bd92-a13f-11f1-875a-97865eec8c7b` | discovered | 0 | 0 | 0 | 3 | 0 |
| duplicate YouTube | `c91af6e0-2e50-402a-aed9-eef247c42022` | `yt:TVpLs0F1zpA` | discovered | 0 | 0 | 0 | 3 | 0 |

Both rows already carry video ID `TVpLs0F1zpA`. Their discovery objects are
separate:

- `episodes/0b99e4f6-1acb-4e31-8a6e-8184350c96fb/discover.json`
- `episodes/c91af6e0-2e50-402a-aed9-eef247c42022/discover.json`

The earlier 17-row Lex estimate is no longer current production truth. Lex has
no `yt:` rows now. A title/date scan found four additional fuzzy candidates,
but they were different episodes or short clips and are not safe merge targets.

## Reconciliation result

Before mutation, D1 Time Travel bookmark
`0000015c-00000000-000050d8-12caed157ce5ec54683f7d4e6e481369`
was recorded. The duplicate discovery object was copied to
`recovery/2026-08-31/issue-7/c91af6e0-2e50-402a-aed9-eef247c42022/discover.json`;
the 2,035-byte copy matched the source SHA-256
`31f3e1652a9e3dac2e3e4365f19957571fb6e595d91641c5f3cc4c7bc4ee1bb8`.
The original object was retained.

The dependency guard was re-run immediately before mutation: the duplicate
still had zero segments, claims, evidence rows, and LLM runs. Its three person
links exactly matched the canonical row, so the idempotent transfer inserted
no new links. The duplicate's three links and then its episode row were
deleted.

Post-mutation verification found only the canonical episode, with the expected
video ID and three person links. The episode total moved from 10,363 to 10,362,
the duplicate owns no remaining person links, and `PRAGMA foreign_key_check`
returns no violations. The D1 restore bookmark and R2 recovery copy remain the
rollback path.

The current discovery merge already suppresses a matched YouTube item from the
unmatched-video append path. Its fixture test uses one matching and one
unmatched upload, so new duplicates of this exact shape remain covered.
