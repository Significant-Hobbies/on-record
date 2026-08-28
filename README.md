# High Signal Podcasts (on-record)

Source-backed index of public statements by notable people. High Signal
sub-product, own layout, live at
[`podcasts.highsignal.app`](https://podcasts.highsignal.app). The unit is the
**claim**, not the episode.

Every published claim has a verbatim transcript excerpt, explicit attribution
status, date, and source link. Identified speakers are linked to people;
unresolved speakers are labeled and excluded from people counts. Timed YouTube
links are limited to claims extracted from that video's captions. Missing
evidence is preferred over a confident guess.

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
pnpm ingest -- --stage extract # batches 20; no per-episode claim ceiling
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

## Qualified release candidate

The 2026-08-29 v10 snapshot is the qualified production release source. It
contains 30,561 public claims across 1,208 transcript episodes and 956 verified
people. Coverage averages 25.3 claims per episode; 1,177 episodes have at least
10 claims, 753 have at least 20, and 309 have at least 30.

The named-item index exposes 1,144 evidence rows in 963 groups, including 539
book evidences grouped into 416 titles, 199 app evidences in 149 groups, 51 tool
evidences in 50 groups, and 194 other evidences in 191 groups. Book counts are
distinct verified people, while 15 book evidences from unverified speakers are
labeled separately. Both focused book queues rerun with zero remaining
extraction candidates, and integrity checks are clean for primary evidence,
quote duplication, attribution, and public cross-kind item duplication.

Qualification does not imply deployment. Source, CI, migration, import,
deployment, and public-verification receipts are tracked separately in
`HANDOFF.md`.

The broader expansion uses the separate v10 working snapshot. Extraction has no
default per-episode ceiling: strong complete claims can use deterministic
exact-excerpt rules, while named recommendations and ambiguous candidates keep
the model gate. Claims whose transcript does not establish the speaker carry
`speaker_unverified`; they remain searchable but never count as a person. The
responsive research UI and API trust boundary are qualified and live. The
previous release used a time-travel backup, uploaded all 1,208 reviewed R2
objects, applied an incremental no-delete D1 bundle, and deployed API and web
through the dispatch-only workflow.
