# on-record — handoff

Written 2026-08-26. Numbers are live queries against production D1, not estimates.

## Where this actually is

A large, clean metadata corpus and almost no content.

| | count | trust |
|---|---|---|
| Shows | 25 | solid — feeds resolved via the Apple directory, each verified to return items |
| Episodes | **10,017** | solid — title and date on 100%, from RSS |
| Audio URLs | 9,628 (96%) | solid — Whisper can reach all of these |
| Roster | 1,270 people | good — mined from real episode titles, ranked by appearances |
| Verified YouTube ids | 2,013 (20%) | solid — every one channel-checked |
| Person↔episode links | 26,772 | **~50% precision, 19 checked** |
| **Transcribed episodes** | **8 (0.08%)** | **this is the blocker** |
| Published claims | 606, across 10 people | demo, not an index |

The claim layer rests on 8 of 10,017 episodes and 10 of 1,270 people. Everything
that makes this a product is downstream of transcription.

## The one thing to do next

**Build the Lex Fridman transcript adapter.** 518 episodes, and it needs no
Whisper, no diarization, and no speaker identification — the three places
attribution has gone wrong.

`lexfridman.com/<slug>-transcript` serves:

```html
<div class="ts-segment">
  <span class="ts-name">Lex Fridman</span>
  <span class="ts-timestamp"><a href="https://youtube.com/watch?v=…&t=0">(00:00:00)</a></span>
  <span class="ts-text">The following is a conversation with…</span>
</div>
```

Speaker, timestamp, text, and a YouTube deep link per turn. Measured on one
episode: 513 turns, 29,359 words, speakers named by the publisher. That maps
directly onto our `segments` shape with `speakerHint` already resolved.

Two known wrinkles: the episode page is a stub (the transcript is at a separate
URL), and the slug pattern is not uniform — `andrej-karpathy-transcript` 404s.
Derive URLs per episode rather than guessing them.

Then, in order:

1. **Attributions across the corpus.** 19 of 26,772 checked. The 4B answers in
   ~0.6s, so the full set is a few hours. Until then the roster feeding
   extraction is ~50% precise, which is how a quote lands on the wrong person.
2. **The other publisher transcripts.** `seed/shows.py` records what each show
   publishes, measured by fetching a real episode page. Machine Learning Street
   Talk is structured (187k chars, 1,045 timestamps, 132 turns). Six more carry
   full text.
3. **Whisper for the rest.** ~4.5 min an episode locally, unlimited, and the
   only path for a16z and 20VC, which publish nothing.

## How the pipeline works now

```
discover      RSS + YouTube channel feed -> episodes (+ hosts and matched guests)
attributions  4B judges whether each matched person is really on the episode
transcripts   publisher page -> YouTube captions -> Whisper (diarized)
identify      names each diarized voice once per episode, from how it talks
extract       claims per segment, quote checked verbatim against stored text
reverify      retracts claims whose source moved under them
```

Storage: D1 holds claims, anchors and metadata. **Segment text and cue maps live
in R2** — one object per episode, read once per claim batch. Nothing public reads
them; they exist so a quote can be checked and a timestamp resolved.

Models: extraction goes through the free-ai gateway asking for JSON mode and a
high reasoning floor, never a pinned model. Judgement over short passages (is
this a guest? which voice is this?) goes to local Qwen via LM Studio.

## Traps

Read these before debugging anything. Every one cost hours today, and they share
a shape: **plausible output that is silently wrong, with nothing crashing.**

- **The gateway treats `model` as a hint.** Asking for gemini returned
  `ministral-3b` with `degraded: false`. Every extraction before 2026-08-25 was
  done by a 3B model. Ask for capability (`response_format`,
  `min_reasoning_level`), and record `x_gateway.model` as provenance. Do not pin
  a single model — that trades quality for availability and every call 503s when
  its quota goes.
- **A stage reporting zero is often a crash.** The YouTube backfill logged
  "0 filled" while a traceback sat in the log. Check the log, not the summary.
- **Small models are strong at judgement, weak at reproduction.** The 4B is
  excellent at "is this person on this episode" and bad at verbatim quoting. One
  bad benchmark does not condemn a model for every job.
- **A benchmark can reward the wrong behaviour.** I passed Jensen Huang's roster
  to Sam Altman's episode; Qwen obediently filed Altman's words under Huang and
  scored "0 rejected, perfect", while a better model refused and scored 19
  failures. Verify against known-correct answers, not throughput.
- **Re-transcribing invalidates everything downstream.** Cue boundaries shift,
  quotes stop anchoring, `reverify` retracts the claims. Worth it only for a real
  quality gain — not for flag changes. Compare on a scratch copy.
- **YouTube rate-limits per IP, and it looks like absence.** 12 of 12 video ids
  returned captions; twenty minutes later the same ids returned 0 of 5. The
  channel feed 404s for every channel once the IP is warm. Never conclude "no
  captions" from a warm IP.
- **Show notes link other people's videos.** Mining ids from metadata attached
  Lex episodes to Tucker Carlson's channel, to TED, to FloGrappling — 122 of
  1,745 wrong. A video must be on the show's own channel; `youtube-verify`
  enforces it.
- **Title similarity alone will mis-link.** "Undruggable Drugs" scored a perfect
  match against a Georgia Cancer Center upload. Require the channel too.

## Known broken

- **References cite the wrong evidence.** Validation checks the name against the
  3,000-char segment, not the claim's quote, so 27% of published references name a
  thing their quote never mentions. One-line fix in two places:
  `workers/api/src/references.ts` and `extract/validate.py`.
- **92% of references are `mentions`.** The extractor is asked for the role while
  shown a whole segment. It should judge from the sentence, and the PRD's own
  rule is that a mention must not become a claim.
- **No significance gate.** Karpathy's page is 148 claims of which 1% name
  anything concrete, and one idea repeats four times. The agreed filter — a named
  public thing, or a strong opinion — is unbuilt, as is the `strength` field.
- **No semantic dedup** within an episode.
- **`/api/people/:slug` has no pagination.** Fine at 606 claims, not at scale.

## Commands

```bash
pnpm quality                     # the gate: 55 python tests, 16 ts, complexity, dupes
pnpm db:migrate:remote           # migrations (0005 is the latest)
cd workers/api && pnpm exec wrangler deploy

# ingest — env: ADMIN_TOKEN, API_BASE, AI_BASE_URL, AI_API_KEY, YOUTUBE_API_KEY
pnpm ingest -- --stage discover --days 3650
pnpm ingest -- --stage attributions --limit 500
pnpm ingest -- --stage transcripts --episode <id> --whisper
pnpm ingest -- --stage identify --episode <id>     # re-name voices, no re-transcribe
pnpm ingest -- --stage extract --episode <id> --focus all
pnpm ingest -- --stage youtube-api                 # fill video ids
pnpm ingest -- --stage youtube-verify              # drop wrong-channel links
```

Secrets are in Infisical (`ADMIN_TOKEN`, `Free_ai`, `YOUTUBE_API_KEY`). Local
models run through LM Studio (`lms load qwen/qwen3.5-4b`).

## Open decisions

- **Unattended running.** GitHub Actions can discover but cannot transcribe —
  YouTube blocks datacenter IPs, and Whisper needs this machine. A launchd agent
  locally is the obvious answer and is not built.
- **Whether captions can substitute for Whisper.** Fast and free, but no speaker
  labels, and it is unverified whether YouTube video and podcast RSS audio share
  a timeline — dynamic ad insertion would offset every label.
- **Corpus target.** 10,017 episodes at 4.5 min each is ~750 hours if everything
  needs Whisper. Publisher transcripts and captions cut that substantially; the
  attribution pass should decide which episodes are worth it at all.

## Also

`mashup/` duplicates the transcription logic deliberately. Both `AGENTS.md`
files carry a "Kept in sync" section naming the other's file. Diarization exists
only here.

Someone else has been committing in parallel — `e52d4d8` fixed a real bug in the
YouTube verification, where a show with no configured channel would have had its
video ids cleared. Check `git log` before assuming the tree is only yours.
