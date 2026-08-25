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
  Production D1 `on-record-db`, R2 `on-record-raw`, and GitHub Actions secrets
  already exist; do not recreate them.

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

## Kept in sync with Mashup

`mashup/` transcribes podcast audio the same way this project does:
`whisperkit-cli` over a 16 kHz mono WAV produced by ffmpeg. The logic is
duplicated on purpose — the two products have different rights postures and
release cycles, and neither should be able to break the other — but duplicated
code drifts silently, so treat these as a pair.

| here | there |
|---|---|
| `python/ingest/src/on_record_ingest/transcripts/whisper_local.py` | `src/mashup/ingest/transcribe.py` |

Known differences, both deliberate:

- Mashup resolves two backends (`whisperkit`, `mlx-whisper`) lazily and takes
  its model directory from `MASHUP_WHISPERKIT_MODEL`. This project pins one
  backend and one model path. Theirs is the more careful version.
- Diarization exists only here. Mashup has none, so its transcripts carry no
  speaker turns.

When you change transcription in either repo — model, flags, audio conversion,
timeout, cleanup — read the other file and say in the commit message whether
the change applies there too. If it does and you are not making it, note it in
that repo's issues rather than leaving the two to drift.
