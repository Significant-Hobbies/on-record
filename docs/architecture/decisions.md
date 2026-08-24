# Architecture decisions

## A1 — Python ingest on GitHub Actions, writes through the API worker

`youtube-transcript-api` works from GitHub runner IPs; Worker egress to
YouTube does not. Podcast Index SHA1 auth and feedparser already exist in
high-signal's Python adapters. Python never touches D1: it POSTs to
`workers/api` with `ADMIN_TOKEN`. Ported YouTube captions keep per-cue
`{start, duration, text}` because timestamps are part of the evidence triple.

## A2 — D1 + Drizzle + FTS5; R2 for raw bytes

Fleet default storage. Search is D1 FTS5 (`claims_fts`) plus structured
filters. Vectorize is deferred. Raw feeds and transcripts live in R2
`on-record-raw`. Normalized segments live in D1.

## A3 — Speaker attribution is gated

Show hosts come from seed config. Guests are matched from episode
title/description against people aliases, then the extractor may pick a
roster member or `unknown`. `speaker_confidence < 0.80` or unknown speaker
never publishes.

## A4 — Web reads the API worker only

Astro SSR on `on-record.significanthobbies.com` (Session 2) has no D1
binding. Draft and held claims must not leak from public routes.

## A5 — Append-only claim ledger

Episodes move through a linear status column. Episode `guid` and claim
`dedupeHash` are unique. Reprocessing inserts a new claim version
(`parentClaimId`) and flips the old row to `corrected`. No in-place claim
edits.

## A6 — Seed corpus

Shows: Dwarkesh Podcast, Lex Fridman, No Priors, Latent Space. People:
Karpathy, Dario Amodei, Altman, Hassabis, LeCun, Nadella, Brockman,
Collison, Sutskever, Jensen Huang.
