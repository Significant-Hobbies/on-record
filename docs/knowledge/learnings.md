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

