# Ingest runbook

```bash
pnpm ingest --stage all --days 14
pnpm ingest --stage discover --show dwarkesh --days 30
pnpm ingest --episode <id> --stage transcripts --force
pnpm ingest --stage extract --dry-run
pnpm review:report
```

Stages: `all`, `discover`, `transcripts`, `extract`, `publish`. `extract`
includes segmentation. `publish` is the worker gate; the CLI just posts
claims. `--show` scopes discovery, transcript, and extraction work to the named
show. Publisher HTML adapters fail closed on the exact page identity; coarse
publisher text never receives a fabricated playback timestamp. Segment writes
replace the complete transcript and are refused after claims exist; rerun
transcript ingestion before extraction when a publisher parser changes.

Cron: daily 06:00 UTC plus workflow_dispatch. Production secrets live in
GitHub Actions, not this repo.

GitHub Actions `cron-ingest.yml` runs daily 06:00 UTC with `--focus recs`
against `https://api.podcasts.highsignal.app`. The Astro site is SSR, so
published claims show up without a web rebuild.

Production D1/R2 already exist. New schema changes still need
`pnpm db:migrate:remote` with operator approval.
