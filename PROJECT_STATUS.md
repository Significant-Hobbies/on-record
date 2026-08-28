# on-record — PROJECT STATUS

Last updated: 2026-08-28

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
claim extraction with verbatim-quote and exact-speaker gates, manually reviewed
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
- 2026-08-28 — Finished local research product: trusted-show boundary with TBPN
  and Odd Lots retained but publicly withheld; evidence-ledger home, search,
  people, grouped stack, episode, and claim-receipt surfaces; 11,624 trusted
  claims from 935 people across 1,190 source episodes, with 300 named-reference
  rows. The trusted catalog contains 23 shows, 8,395 episodes, and 1,208
  transcript episodes. Of those transcript episodes, 1,092 (90.4%) contain at
  least 10 claims and only 18 contain none. Production remains unchanged.

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
- Exact quotes, identified speakers, source episodes, and timestamps when the
  publisher provides usable timing

## Todo / Planned / Deferred / Blocked

Tracked in GitHub Issues. Continue transcript and speaker coverage beyond the
verified beta slice; cataloged shows with no supported evidence remain pending
rather than being presented as fully analyzed.

The trusted-product goal is 10 defensible recommendations, ideas, or opinions
per transcribed episode. The completed local pass has 11,624 of the nominal
12,080 items (96.2%), with 1,092 of 1,208 transcript episodes at 10 or more.
The remaining 116 episodes have a combined gap of 456. A high-recall candidate
audit caps current evidence-rule capacity at 11,868 and finds 30 episodes with
fewer than 10 eligible candidates, so the residual should not be filled with
weaker or invented claims. Reaching the all-catalog target of 83,950 first
requires transcripts for 7,187 trusted catalog episodes; that is a separate
source-coverage project, not unfinished extraction from the data already held.
