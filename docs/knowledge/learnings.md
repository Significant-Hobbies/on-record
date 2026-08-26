# Learnings

- high-signal's YouTube helper joins cue text and drops timestamps. on-record
  must keep cues because the evidence triple includes time.
- YouTube blocks datacenter IPs, and that is the binding constraint on
  unattended ingestion. Measured 2026-08-25 over the same 59 discovered
  episodes: a GitHub Actions runner resolved **1** transcript, this laptop on a
  residential connection resolved **17**. The channel feed
  (`/feeds/videos.xml?channel_id=`) is worse still — it answers 404 for every
  channel from a runner, and answers 404 from a residential IP too once that IP
  has made a handful of requests in quick succession. The 404 is throttling,
  not a missing channel: the same id answers normally when the IP is cold.
- Consequence: a weekly GitHub Actions cron discovers episodes fine (feeds are
  ordinary RSS) but cannot transcribe them, so it produces no claims. Options
  are a runner on a residential connection, Whisper over the `audioUrl` the RSS
  already gives us, or per-publisher transcript adapters. Discovery specifically
  could be fixed with a YouTube Data API key (`playlistItems.list` on the
  uploads playlist, 1 quota unit per show per day); captions cannot, because
  `captions.download` needs OAuth as the video owner.
- The free-ai gateway treats `model` in the request body as a hint. Asking for
  `gemini-2.5-flash` and asking for `stealth/ox-alpha` both returned
  `ministral-3b-latest`, with `degraded: false` — it is ordinary routing, not a
  failure, so nothing in our logs looked wrong. Every extraction before
  2026-08-25 was done by a 3B model, which is what produced the truncated JSON
  and the weak claims. Pin the model with the `X-Gateway-Force-Model` header,
  and record `x_gateway.model` from the response as the claim's provenance
  rather than what was asked for. With gemini pinned plus
  `response_format: {"type":"json_object"}`, a sample segment went from
  0-2 accepted against 3-6 rejected to 5 accepted and 0 rejected.
- `stealth/ox-alpha` is listed in the registry (1M context, JSON mode, 100
  requests/day) but forcing it returns `no_candidate`,
  "No healthy free-tier model available" — no OpenRouter capacity behind it as
  of 2026-08-25. Force by config id (`openrouter-stealth-ox-alpha`) when it
  comes back; `/v1/models` lists config ids, not model strings.
- The gateway caps `max_tokens` at 8192 regardless of what the model supports.
- Forcing one model fixes quality and breaks availability: pinned to
  gemini-2.5-flash the run exhausted its 500/day quota and then every call was
  503 or 429, five retries deep, for nothing. The right lever is
  `response_format: {"type":"json_object"}` plus
  `min_reasoning_level: "high"`. The first filters the pool to models that can
  emit JSON, the second drops the low-reasoning tier where ministral-3b lives.
  38 enabled candidates across nine providers survive both, so the gateway
  still fails over — observed falling back to codestral-latest and
  mistral-medium-latest once gemini was spent. Keep `X-Gateway-Force-Model`
  for deliberate pinning only (`ON_RECORD_FORCE_MODEL`).
- The shows publish their own transcripts; we were only ever checking the RSS
  tag. `<podcast:transcript>` appears twice in 4,197 feed items, so the
  conclusion was "nobody publishes transcripts" — but that tag is not how they
  publish them. Fetching one real episode page per show on 2026-08-26 found
  seven of ten carry a full transcript, three of those with speaker labels and
  timestamps. Recorded per show as `transcript` in `seed/shows.py`.
- Lex Fridman's are the best data in the project. `lexfridman.com/<slug>-transcript`
  serves `div.ts-segment` blocks holding `ts-name`, `ts-timestamp` (wrapping a
  YouTube deep link) and `ts-text` — 513 turns and 29,359 words on the episode
  measured, speakers named by the publisher. That skips diarization, the
  speaker-identification pass and the confidence gate, which are the three
  places attribution has gone wrong. The episode page itself is a stub; the
  transcript is at a separate URL.
- Ranking the transcript sources by what they cost and what they carry:
  publisher page (free, authoritative speakers, ~40% of the corpus) beats
  YouTube captions (free but IP rate-limited, no speakers) beats Whisper
  (unlimited, 4.5 min an episode, speakers only via diarization). The
  resolution order should follow that, and until now it started with the one
  source that never fires.
- YouTube caption availability cannot be measured from a warm IP. A sample of
  12 verified video ids returned captions 12/12; twenty minutes later the same
  ids returned 0/5. Nothing changed but the request count.

