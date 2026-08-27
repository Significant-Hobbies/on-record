# High Signal Podcasts (on-record)

Source-backed index of public statements by notable people. High Signal
sub-product, own layout, live at
[`podcasts.highsignal.app`](https://podcasts.highsignal.app). The unit is the
**claim**, not the episode.

Every published claim has a verbatim quote, speaker, date, timestamp, and
source link. Missing evidence is preferred over a confident guess.

## Stack

- API: Hono on Cloudflare Workers (`workers/api`)
- DB: Cloudflare D1 + Drizzle (`packages/db`)
- Raw storage: R2 bucket `on-record-raw`
- Ingest: Python / uv (`python/ingest`), GitHub Actions cron
- Web: Astro SSR at `podcasts.highsignal.app`

## Quickstart

```bash
pnpm install
uv sync --project python/ingest --dev
pnpm db:migrate:local
pnpm --filter @on-record/api dev   # wrangler on :8787
pnpm dev:web                       # Astro SSR on :4321
pnpm ingest -- --stage extract --focus recs
pnpm quality
```

Copy `.env.example` to `.dev.vars` (worker) and `.env` (ingest). Do not commit
secrets.

Production D1 `on-record-db` and R2 `on-record-raw` already exist. Deploys
are dispatch-only (`.github/workflows/deploy.yml`). New remote migrations
still need operator approval.

## Public-beta corpus

The catalog currently covers 25 shows and 10,305 episodes. The verified public
recommendation slice contains 166 manually accepted claims and 189 named
reference rows across nine shows. Coverage is explicit: cataloged episodes
without supported transcripts or exact speaker evidence remain pending.

Build the reviewed production bundle from the locally verified v9 snapshot with
`pnpm release:build-reviewed`. Production deployment remains dispatch-only.
