# Architecture decisions

## A1 — Python ingest on GitHub Actions, writes through the API worker

`youtube-transcript-api` works from GitHub runner IPs; Worker egress to
YouTube does not. Podcast Index SHA1 auth and feedparser already exist in
high-signal's Python adapters. Python never touches D1: it POSTs to
`workers/api` with `ADMIN_TOKEN`. Ported YouTube captions keep per-cue
`{start, duration, text}` because timestamps are part of the evidence triple.

## A2 — D1 + Drizzle + FTS5; R2 for raw bytes

Fleet default storage. Search is D1 FTS5 (`claims_fts`) plus structured
filters. Vectorize is deferred. Raw feeds, transcript bodies, normalized
segment text, and cue maps live in R2 `on-record-raw`; D1 stores segment
anchors and metadata so it remains small and queryable.

## A3 — Speaker attribution is gated

Show hosts come from seed config. Guests are matched from episode
title/description against people aliases. Publisher-named transcript formats
may resolve exact names against the roster; generic caption, SRT, VTT, and
unlabelled transcript formats stay explicitly `unknown` until a separate
identification step supplies evidence. `speaker_confidence < 0.80` or an
unknown speaker never publishes. A publisher transcript can add a missing
episode participant with `publisher_transcript` provenance, but ambiguous
initials, audience labels, and transcription typos remain unknown.

Publisher-label parsing separates every label-shaped turn before identity
mapping, including accented and mixed-case labels. This may create extra
unknown turns, but it prevents an unrecognized guest label from attaching the
guest's answer to the preceding host.

## A4 — Web reads the API worker only

Astro SSR on `on-record.significanthobbies.com` (Session 2) has no D1
binding. Draft and held claims must not leak from public routes.

## A5 — Append-only claim ledger

Episodes move through a linear status column. Episode `guid` and claim
`dedupeHash` are unique. Reprocessing inserts a new claim version
(`parentClaimId`) and flips the old row to `corrected`. No in-place claim
edits.

## A6 — Configured corpus

The configured corpus contains 25 shows and a locally discovered roster of
1,270 people. RSS is the canonical episode source when it works; BG2 and
Lightcone explicitly permit YouTube-only episodes. A successful feed fetch is
not proof of a complete historical archive, so exact feed caps and unusually
short feeds require a separate official-playlist/archive reconciliation.

## A7 — Segment writes replace one complete transcript

The segment endpoint upserts the incoming anchors and removes any stale indexes
left by an older, longer segmentation. It rejects duplicate or invalid indexes
and refuses replacement when the episode already has claims, preserving every
claim-to-segment evidence anchor.
