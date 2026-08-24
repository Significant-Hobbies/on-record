# on-record

Source-backed index of public statements by notable people. The unit is the
**claim**, not the episode.

Every published claim has a verbatim quote, speaker, date, timestamp, and
source link. Missing evidence is preferred over a confident guess.

## Stack

- API: Hono on Cloudflare Workers (`workers/api`)
- DB: Cloudflare D1 + Drizzle (`packages/db`)
- Raw storage: R2 bucket `on-record-raw`
- Ingest: Python / uv (`python/ingest`), GitHub Actions cron
- Web: Astro SSR (Session 2)

## Quickstart

```bash
pnpm install
uv sync --project python/ingest --dev
pnpm db:migrate:local
pnpm --filter @on-record/api dev   # wrangler on :8787
pnpm ingest -- --stage discover --days 14 --dry-run
pnpm quality
```

Copy `.env.example` to `.dev.vars` (worker) and `.env` (ingest). Do not commit
secrets.

Production D1/R2, remote migrate, and deploy are dispatch-only and require
explicit operator approval.

## Seed corpus (V1)

Shows: Dwarkesh Podcast, Lex Fridman, No Priors, Latent Space.

People: Karpathy, Dario Amodei, Altman, Hassabis, LeCun, Nadella, Brockman,
Collison, Sutskever, Jensen Huang.
