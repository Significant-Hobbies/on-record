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
pnpm ingest -- --stage recover-speakers --dry-run
pnpm ingest -- --stage extract --batch-size 8 --target-claims 10
pnpm quality
```

Copy `.env.example` to `.dev.vars` (worker) and `.env` (ingest). Do not commit
secrets.

Production D1 `on-record-db` and R2 `on-record-raw` already exist. Deploys
are dispatch-only (`.github/workflows/deploy.yml`). New remote migrations
still need operator approval.

## Trusted production corpus

Production contains 25 shows and 10,325 episode rows. The public trusted 23-show
subset exposes 8,414 catalog episodes, 1,209 transcript episodes, 11,624
published claims from 935 people across 1,190 source episodes, and 294
quote-safe named-reference evidences in 281 canonical groups. D1 retains 300
reference rows before the public quote-safety pass. Of the transcript episodes,
1,092 (90.3%) have at least 10 claims and 19 have none. TBPN and Odd Lots remain
stored but are withheld from all public routes because their diarized speaker
labels are not safe to map to people yet.

Build the narrow reviewed v9 bundle with `pnpm release:build-reviewed`, or the
full trusted corpus bundle with `pnpm release:build-trusted`. The trusted bundle
is an incremental upsert with no data-deletion statements and overlays the v9
manual review decisions before adding the broader exact-evidence corpus.
Production deployment remains dispatch-only.

The broader expansion uses the separate v10 working snapshot. It targets
10 exact-evidence recommendations, ideas, or opinions per trusted transcribed
episode; speaker repair is deliberately limited to explicit publisher metadata
and unambiguous transcript evidence. The completed pass reached 11,624 of the
nominal 12,080 items (96.2%); its evidence-qualified candidate ceiling is
11,868, so remaining gaps are preserved rather than padded. The responsive
research UI and API trust boundary are qualified and live. The release used a
time-travel backup, uploaded all 1,208 reviewed R2 objects, applied an
incremental no-delete D1 bundle, and deployed API and web through the
dispatch-only workflow.
