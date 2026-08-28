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
4. **extract** — cheap triage first (recommendations, positions, predictions,
   evaluations, explanations, commitments, and uncertainty; skip questions,
   filler, ads, and context-dependent fragments). Broad extraction uses
   deterministic rules for complete, high-signal non-reference claims and
   `extract-v5` to classify ambiguous candidates in batches of up to 20.
   Named-item extraction uses a separate batched `extract-recs-v5` contract
   that requires a direct speech act and a stable exact-named object. Neither
   path regenerates the assertion or quote: the stored assertion and evidence
   are the same source excerpt. Per-segment attempts make runs resumable. There is no
   default per-episode claim ceiling; `--target-claims` is an optional operator
   limit. The Worker revalidates every quote.
5. **publish** — worker re-validates the quote against stored segment text and
   applies deterministic banding. Identified speakers use their attribution
   confidence. A high-confidence exact excerpt may publish as
   `speaker_unverified`, but it is labeled in the UI and excluded from person
   and distinct-recommender counts. Manual review status changes also add or
   remove the claim from FTS so killed claims cannot continue surfacing.

Unknown diarized voices can be repaired separately with `--stage
recover-speakers`. The stage first admits only explicit publisher phrases such
as “our guest is” or “we speak with” into the episode roster. It can then use a
first-person introduction, a known host welcome followed by the guest accepting
it, or a single strongly dominant unknown label for one explicitly named guest.
Publisher pre-roll before a known program bumper is excluded. Multi-party RSS
transcripts above 300 segments, ambiguous labels, and multiple remaining people
or voices fail closed. The Worker also refuses label drift, non-roster people,
already identified segments, and segments with claims.
