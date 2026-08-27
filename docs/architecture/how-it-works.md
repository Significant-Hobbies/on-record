# How the pipeline works

```text
discover → transcripts → segment → extract → publish-rules (worker)
```

1. **discover** — Podcast RSS is the catalog when it works; the YouTube channel
   feed enriches matching episodes by title and date proximity. Unmatched
   channel uploads are admitted only when RSS returned nothing or the show is
   explicitly configured to use YouTube as an episode source. Upsert episode;
   store raw discovery JSON in R2.
2. **transcripts** — A canonical speaker-labelled publisher page when one is
   supported (currently Lex and Conversations with Tyler), then RSS
   `<podcast:transcript>` (VTT/SRT/JSON/text), YouTube captions, and opt-in
   Whisper. Publisher pages are accepted only after domain, redirect, title,
   and minimum-structure checks. Operational failures remain retryable; only a
   checked, genuine absence becomes `no_transcript`. Publisher labels are
   split before attribution, including Unicode and mixed-case variants; only
   manually reviewed label mappings become people and all other turns remain
   `unknown`.
3. **segment** — cues into ~3000-character windows at cue and speaker
   boundaries, with overlap only across same-speaker length splits. Segment
   bodies and cue maps live in R2; D1 retains the timing and attribution anchor.
   A transcript write is an exact replacement: stale trailing segment anchors
   are removed, and replacement is rejected once claims reference the episode.
   Sources such as Conversations with Tyler that preserve turn order but have
   no playback timing use `publisher_html_coarse`; their claim timestamps and
   deep links remain null rather than using ordinal turn numbers as seconds.
4. **extract** — cheap triage first (recs / claim speech / skip filler).
   Only then the configured model (`extract-v3`; recommendation focus has a
   stricter named-speech-act prompt). Segments that already have claims are
   skipped unless `--force`. Quote must be a verbatim substring. Reject,
   never repair.
5. **publish** — worker re-validates the quote against stored segment text
   and applies deterministic banding.
