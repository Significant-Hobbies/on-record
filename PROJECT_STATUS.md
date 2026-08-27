# on-record — PROJECT STATUS

Last updated: 2026-08-27

## Why / What

A source-backed knowledge graph of public statements by notable people. It
helps readers choose what is worth listening to, recover relevant content
without playing every episode, and track repeated books, apps, tools, and
technology signals across top guests. The unit is the claim: Person → Claim →
Topic → Stance → Date → Evidence.

**Users:** founders, investors, journalists, operators researching people or
markets.

**IN scope (public beta):** 25-show catalog, publisher/RSS transcripts,
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

## Products

- `on-record-api` Worker — `https://api.podcasts.highsignal.app`
- Public Astro SSR site — `https://podcasts.highsignal.app`
- Python ingest CLI + GitHub Actions daily cron (`--focus recs`)

## Features

- Public-beta claim index: 25-show catalog and a manually reviewed,
  source-backed recommendation slice across nine shows
- SSR site reads live D1 via the API; ingest does not rebuild the web Worker
- Exact quotes, identified speakers, source episodes, and timestamps when the
  publisher provides usable timing

## Todo / Planned / Deferred / Blocked

Tracked in GitHub Issues. Continue transcript and speaker coverage beyond the
verified beta slice; cataloged shows with no supported evidence remain pending
rather than being presented as fully analyzed.
