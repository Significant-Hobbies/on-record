# Ingest runbook

```bash
pnpm ingest -- --stage all --days 14
pnpm ingest -- --stage discover --show dwarkesh --days 30
pnpm ingest -- --episode <id> --stage transcripts --force
pnpm ingest -- --stage extract --dry-run
pnpm review:report
```

Stages: `all`, `discover`, `transcripts`, `extract`, `publish`. `extract`
includes segmentation. `publish` is the worker gate; the CLI just posts
claims.

Cron: daily 06:00 UTC plus workflow_dispatch. Production secrets live in
GitHub Actions, not this repo.

GitHub Actions `cron-ingest.yml` runs daily 06:00 UTC with `--focus recs`
against production `API_BASE` once secrets exist. The Astro site is SSR, so
published claims show up without a web rebuild.

Do not create D1/R2 or run `db:migrate:remote` without operator approval.
