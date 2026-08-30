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
  Ingest: `pnpm ingest --stage extract --focus recs`.
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
- Unknown or low-confidence speakers must never be guessed or mapped to a
  person. A high-confidence, quote-validated claim may appear as explicitly
  `speaker_unverified`; public person and distinct-recommender counts exclude
  it.
- Python never writes D1 or R2 directly. It posts through the API worker with
  `ADMIN_TOKEN`.
- Prefer missing data over confident misinformation.

## Public list endpoints must be bounded

Every public list endpoint backed by D1 carries a `LIMIT`. No listing may end
in an unbounded `ORDER BY` over a join: the sort has to materialise every
matching row before the first one can be returned, so the cost tracks the
corpus rather than the page. Pagination is part of the endpoint, not a later
refinement, and a limit is only meaningful over a total order — add a unique
tiebreaker when the sort keys can tie.

Check any new query shape with `EXPLAIN QUERY PLAN` against a local D1 before
shipping it (`wrangler d1 execute <db> --local`, never `--remote`). A `SCAN`
on the outer loop of a join usually means no index matched the filter and the
planner had no cheap entry point; the fix belongs in a new migration, and it
is worth confirming, because an index that helps one shape can push the
planner off a good plan for another.

`wrangler d1 insights <db> --sort-by reads` is what surfaces a regression, and
`queryEfficiency` is the number to read: below roughly 0.1 the query is
scanning far more than it returns.

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
