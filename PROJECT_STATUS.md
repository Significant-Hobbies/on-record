# on-record — PROJECT STATUS

Last updated: 2026-08-25

## Why / What

A source-backed knowledge graph of public statements by notable people. It
helps readers choose what is worth listening to, recover relevant content
without playing every episode, and track repeated books, apps, tools, and
technology signals across top guests. The unit is the claim: Person → Claim →
Topic → Stance → Date → Evidence.

**Users:** founders, investors, journalists, operators researching people or
markets.

**IN scope (V1):** ~10 people, 4 podcasts, captions/publisher transcripts,
claim extraction with verbatim-quote gate, D1 FTS5 search, public API.

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

## Products

- `on-record-api` Worker — `https://api.podcasts.highsignal.app`
- Public Astro SSR site — `https://podcasts.highsignal.app`
- Python ingest CLI + GitHub Actions daily cron (`--focus recs`)

## Features (shipped)

- Production claim index (thin V1): 10-person roster, 4 shows, published
  Karpathy/Dwarkesh claims with verbatim excerpts
- SSR site reads live D1 via the API; ingest does not rebuild the web Worker

## Todo / Planned / Deferred / Blocked

Tracked in GitHub Issues. Grow the published recs/stack corpus; keep listing
hidden until the index is worth sharing.
