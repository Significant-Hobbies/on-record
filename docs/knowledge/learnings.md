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
