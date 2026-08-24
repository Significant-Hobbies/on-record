## Repository operating rules

This repository is independently operable. Its tracked instructions and
commands are authoritative; no sibling Fleet checkout is required. Protect
production stability, keep changes scoped, verify work with repo-local checks,
and record durable follow-up in this repository's GitHub Issues.

## Project

- **Product**: High Signal Podcasts (repo `on-record`) — a source-backed
  index of public statements. High Signal sub-product, own layout, intended
  domain `podcasts.highsignal.app`. The unit is the **claim**, not the episode.
- **Stack**: Hono on Cloudflare Workers, D1 + Drizzle, R2 for raw feeds and
  transcripts, Astro SSR (Session 2), Python ingest on GitHub Actions via uv.
- **Local dev**: `pnpm install` then `uv sync --project python/ingest --dev`.
  API: `pnpm --filter @on-record/api dev`. Web: `pnpm dev:web` (reads the API).
  Ingest: `pnpm ingest -- --stage extract --focus recs`.
- **Build/check**: `pnpm quality`
- **Deploy**: dispatch-only (`.github/workflows/deploy.yml`). Never auto-deploy.
  Create production D1/R2 and set secrets only with explicit operator approval.

## Work tracking

- Use GitHub Issues as the only operational work queue.
- Keep `PROJECT_STATUS.md` limited to current and shipped product truth.

## Hard rules

- Never publish a claim without a verbatim quote that exists in the stored
  segment text.
- Unknown or low-confidence speakers stay draft; they never appear on public
  routes.
- Python never writes D1 or R2 directly. It posts through the API worker with
  `ADMIN_TOKEN`.
- Prefer missing data over confident misinformation.
