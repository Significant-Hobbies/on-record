# on-record — PROJECT STATUS

Last updated: 2026-08-24

## Why / What

A source-backed knowledge graph of public statements by notable people. The
unit is the claim: Person → Claim → Topic → Stance → Date → Evidence.

**Users:** founders, investors, journalists, operators researching people or
markets.

**IN scope (V1):** ~10 people, 4 podcasts, captions/publisher transcripts,
claim extraction with verbatim-quote gate, D1 FTS5 search, public API.

**OUT of scope (V1):** Whisper, position clustering, agreement graphs,
semantic search, user accounts, public write API, editor UI beyond
review-report.

## Dependencies

### External

- Podcast Index (discovery)
- YouTube captions via `youtube-transcript-api`
- Publisher RSS transcript tags
- free-ai gateway (`AI_PROJECT_ID=on-record`)
- Cloudflare D1 + R2 + Workers (production resources not created yet)

### Internal

- Pattern reuse from high-signal adapters and claim ledger
- free-ai gateway for extraction

## Timeline

- 2026-08-24 — Session 1 scaffold: schema, API worker, ingest pipeline, CI

## Products

- `on-record-api` Worker (local)
- Python ingest CLI (local)
- Public site (Session 2, not started)

## Features (shipped)

- (none in production)

## Todo / Planned / Deferred / Blocked

Tracked in GitHub Issues once the repository is published. Session 1 still
needs a real-episode extract milestone and production resource creation
(blocked on operator approval).
