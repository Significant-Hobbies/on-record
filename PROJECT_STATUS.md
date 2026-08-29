# on-record — PROJECT STATUS

Last updated: 2026-08-29

## Why / What

A source-backed knowledge graph of public statements by notable people. It
helps readers choose what is worth listening to, recover relevant content
without playing every episode, and track repeated books, apps, tools, and
technology signals across top guests. The unit is the claim: Person → Claim →
Topic → Stance → Date → Evidence.

**Users:** founders, investors, journalists, operators researching people or
markets.

**IN scope (public beta):** 25-show raw catalog, 23-show trusted public index,
publisher/RSS transcripts,
claim extraction with verbatim-quote and explicit-attribution gates, manually reviewed
recommendations, D1 FTS5 search, and public API.

**OUT of scope (V1):** Whisper, position clustering, agreement graphs,
semantic search, user accounts, public write API, editor UI beyond
review-report.

## Dependencies

### External

- Podcast Index (discovery)
- YouTube captions via `youtube-transcript-api`
- Publisher RSS transcript tags
- free-ai gateway (`AI_PROJECT_ID=on-record`)
- Cloudflare D1 `on-record-db` + R2 `on-record-raw` + Workers `on-record-api`,
  `high-signal-podcasts`

### Internal

- Pattern reuse from high-signal adapters and claim ledger
- free-ai gateway for extraction

## Timeline

- 2026-08-24 — Session 1 scaffold: schema, API worker, ingest pipeline, CI
- 2026-08-24 — GitHub repo Significant-Hobbies/on-record; local D1 migrate; Karpathy episode captions segmented
- 2026-08-24 — First published claims from Karpathy/Dwarkesh via Infisical Free_ai → free-ai gateway
- 2026-08-24 — extract-v2 stores evidenced book/app/tool references (`/api/recommendations`)
- 2026-08-25 — High Signal Podcasts SSR site + daily cron `--focus recs`
- 2026-08-25 — Production: `podcasts.highsignal.app` + `api.podcasts.highsignal.app`,
  GitHub Actions secrets, first published Karpathy/Dwarkesh claims
- 2026-08-27 — Public-beta corpus qualified locally: 25 shows, 10,305 episodes,
  3,106 transcript episodes, and 166 manually accepted recommendation claims
  with 189 named-reference rows
- 2026-08-28 — Local broad-claim expansion: grouped named recommendations with
  distinct-person counts; `extract-v5` exact-excerpt batching; per-episode
  published target; and deterministic recovery of 18,932 formerly unknown
  speaker segments. At the post-repair checkpoint, 1,534 claims were published
  locally and 100 transcript episodes had reached 10. Production remains
  unchanged.
- 2026-08-28 — Released the finished research product: TBPN and Odd Lots remain
  retained but publicly withheld; evidence-ledger home, search, people, grouped
  stack, episode, and claim-receipt surfaces are live. Production serves 11,624
  trusted claims from 935 people across 1,190 source episodes. D1 retains 300
  named-reference rows; the public quote-safety pass exposes 294 evidences in
  281 canonical groups. The live trusted catalog contains 23 shows, 8,414
  episodes, and 1,209 transcript episodes. Of those, 1,092 (90.3%) contain at
  least 10 claims and 19 contain none. API and web run commit `10a863b6` at
  100% Cloudflare traffic.
- 2026-08-29 — Qualified an uncapped production release candidate: 30,561
  public claims across 1,208 transcript episodes, 956
  verified people, and 1,144 named-reference evidences in 963 grouped items.
  The book slice now contains 539 evidences across 416 canonical titles, 63 of
  them supported by more than one verified person. Both focused book queues
  rerun at zero remaining candidates; corpus integrity and public grouped-
  reference duplicate checks are clean.
- 2026-08-29 — Released the v10 corpus after a D1 Time Travel backup and
  migration 0007. Production now serves 30,562 published claims, 30,562 primary
  evidence rows, 30,562 FTS rows, and 1,316 stored named-reference rows; public
  stats expose 956 verified people, 1,208 represented episodes, 1,209 trusted
  transcript episodes, and 1,141 sanitized named-item evidences. Remote checks
  found zero missing primary evidence, duplicate quote groups, foreign-key
  violations, or pending migrations. The incremental builder now emits
  provider-safe table layers and 1,000-claim FTS batches.

## Products

- `on-record-api` Worker — `https://api.podcasts.highsignal.app`
- Public Astro SSR site — `https://podcasts.highsignal.app`
- Python ingest CLI + GitHub Actions daily cron (`--focus recs`)

## Features

- Research-grade evidence index across home, search, people, grouped named
  items, source episodes, and exact claim receipts
- Central trusted-corpus policy excludes unresolved-show data from public
  claims, people, sources, recommendations, search, and statistics without
  deleting the retained raw records
- SSR site reads live D1 via the API; ingest does not rebuild the web Worker
- Exact transcript excerpts, explicit speaker-attribution status, source
  episodes, and timestamps when the publisher provides usable timing

## Todo / Planned / Deferred / Blocked

Tracked in GitHub Issues. Continue transcript and speaker coverage beyond the
verified beta slice; cataloged shows with no supported evidence remain pending
rather than being presented as fully analyzed.

The trusted-product goal is at least 10 defensible recommendations, ideas, or
opinions per transcribed episode without a per-episode ceiling. The released
v10 source has 30,561 public claims: 1,177 of 1,208 transcript episodes
(97.4%) have at least 10, 753 have at least 20, and 309 have at least 30. The
remaining 31 episodes stay below 10 because the evidence gate found no further
defensible claims; they must not be filled with weaker or invented material.
The trusted catalog has 8,395 episode records, so extending coverage beyond the
1,208 episodes with transcript segments is a separate source-acquisition
project, not unfinished extraction from data already held.
