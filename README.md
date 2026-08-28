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

## Trusted local product corpus

The raw catalog covers 25 shows and 10,305 episodes. The finished local product
exposes the trusted 23-show subset: 8,395 catalog episodes, 1,208 transcript
episodes, 11,624 published claims from 935 people across 1,190 source episodes,
and 300 named-reference rows. Of the transcript episodes, 1,092 (90.4%) have at
least 10 claims and only 18 have none. TBPN and Odd Lots remain stored locally
but are withheld from all public routes because their diarized speaker labels
are not safe to map to people yet.

Build the narrow reviewed v9 bundle with `pnpm release:build-reviewed`, or the
full trusted corpus bundle with `pnpm release:build-trusted`. The trusted bundle
is an incremental upsert with no data-deletion statements and overlays the v9
manual review decisions before adding the broader exact-evidence corpus.
Production deployment remains dispatch-only.

The broader local expansion uses the separate v10 working snapshot. It targets
10 exact-evidence recommendations, ideas, or opinions per trusted transcribed
episode; speaker repair is deliberately limited to explicit publisher metadata
and unambiguous transcript evidence. The completed pass reached 11,624 of the
nominal 12,080 items (96.2%); its evidence-qualified candidate ceiling is
11,868, so remaining gaps are preserved rather than padded. The responsive
research UI and API trust boundary are locally qualified. Production remains
unchanged until a separately authorized release.
