# How the pipeline works

```text
discover → transcripts → segment → extract → publish-rules (worker)
```

1. **discover** — Podcast Index `byfeedid` plus YouTube channel RSS. Match
   episode to video by title and date proximity. Upsert episode; store raw
   feed JSON in R2.
2. **transcripts** — RSS `<podcast:transcript>` (VTT/SRT/JSON) first, then
   YouTube captions. No transcript → `no_transcript`, skipped forever.
3. **segment** — cues into ~3000-character windows at cue boundaries, 200
   character overlap, carrying `startS`/`endS`.
4. **extract** — per segment, roster + previous-segment tail + text →
   free-ai gateway (`extract-v1`, temperature 0). Quote must be a verbatim
   substring. Reject, never repair.
5. **publish** — worker re-validates the quote against stored segment text
   and applies deterministic banding.
