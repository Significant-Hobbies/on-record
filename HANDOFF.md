# on-record — correctness handoff

Updated 2026-08-28. This document describes the final correctness snapshot and
its verified production release. The previous 2026-08-26 figures were
contaminated by bad RSS/YouTube associations, a wrong Peel feed, seven adjacent
Lex transcripts, and one synthetic canary. Do not reuse those figures.

## Executive truth

- Production now exposes the trusted 23-show boundary: 8,414 catalog episodes,
  1,209 transcript episodes, 11,624 published claims from 935 people across
  1,190 source episodes, and 300 stored named-reference rows. The public
  quote-safety pass exposes 294 reference evidences across 281 groups. Of the
  live transcript episodes, 1,092 (90.3%) have at least 10 published claims;
  19 have no published claim. The one-episode difference from the qualified
  1,208-episode release bundle is newer production data preserved by the
  no-delete import.
- TBPN and Odd Lots are retained intact in the raw corpus but withheld from
  public claims, people, sources, recommendations, search, and statistics. Their
  diarized labels are not mapped to named people confidently enough for public
  attribution.
- The evidence-ledger research flow is live across home, search, people,
  grouped books/apps/tools, episodes, and exact claim receipts. Both Workers
  run source commit `10a863b6` at 100% traffic.
- The public grouped named-item slice contains 294 evidence rows across 281
  canonical item groups: 57 apps, 63 tools, 53 books, 51 other items, 21
  services, 14 hardware items, 16 people, 3 courses, and 3 papers. Counts use
  distinct attributable people, not raw mentions. Grouping depth is still modest:
  ChatGPT has four distinct people, Claude-as-app has three, and no book yet has
  more than one under the current evidence gate.

- The clean local catalog contains 25 configured shows and 10,305 unique
  episode rows covering 2015–2026.
- It has 10,138 audio URLs, 555 verified episode video IDs, 1,921 people, and
  27,722 person-to-episode links.
- Duplicate checks are clean: zero duplicate show/GUID pairs, zero duplicate
  video IDs, and zero literal `None` video IDs.
- Supported publisher/RSS transcript sources yield 3,106 transcript episodes
  and 745,737 evidence segments.
- 245,431 segments carry an exact publisher-provided person identity. The other
  500,306 stay `unknown`; the local identification models did not establish
  reliable identities and no speaker was guessed.
- Recommendation extraction is evidence gated: a public row needs an exact
  quote, an identified speaker, a direct speech act, a stable named object, and
  publisher timing when available. The local D1 contains 194 published claims /
  213 reference rows. Manual decisions reject 28 false or unsafe claims, so the
  canonical export contains 166 claims / 189 reference rows.
- The derived local analysis now contains 44 manually approved bold
  statements and 16 manually approved cross-year position refinements. All
  underlying quotes were reverified against their exact D1 segment/speaker
  anchor and R2 transcript body.
- Acquired's 65,023 and Lenny's 48,409 exact-speaker segments have completed
  recommendation and strict bold-statement review. Lenny's dedicated
  longitudinal pass also completed all 1,376 eligible candidates. The result
  still does not cover the 500,306 unknown-speaker segments, 7,199 episodes with
  no transcript segments, or the pre-existing unscreened broad longitudinal
  candidate tail, so it is verified local evidence rather than a complete
  corpus answer.

## 2026-08-28 broad-claim working expansion

The product target is now explicit: every trusted transcribed episode should
yield at least 10 defensible recommendations, ideas, predictions, opinions,
explanations, decisions, or commitments. Every item still needs an identified
speaker and an exact transcript excerpt. This is broader than the named-object
recommendation catalog; books/apps/tools remain a separately grouped slice.

- The current trusted transcript target is **12,080 published items** across
  1,208 episodes. The trusted all-catalog target is **83,950**, but 7,187
  episode rows first need transcripts. The raw 25-show figures remain preserved
  below for provenance and are not the public product boundary.
- The working store is
  `workers/api/.wrangler/audits/2026-08-27-recommendations-v10/`. The immutable
  correctness-v9 snapshot and reviewed release bundle remain unchanged.
- The production-ready overlay is
  `workers/api/.wrangler/releases/2026-08-28-trusted-v10/`. It preserves all
  28 manual v9 rejections, replaces the 166 accepted v3 claims' raw reference
  forms with their 189 reviewed rows, and adds 111 evidence-gated v4/v5
  reference rows. This is why the release has 300 named-reference rows while
  the underlying working D1 has 295; never import the working database directly.
- Deterministic speaker recovery assigned 18,932 formerly unknown segments
  without model guessing. This includes 460 explicit publisher-metadata guest
  links plus one verified spelling correction, direct self-introductions,
  host welcomes followed by guest acceptance, and a narrow single-guest
  dominance rule. Exact-speaker coverage is now 264,363 segments; 481,374
  remain unknown.
- The final repair pass deliberately rejects publisher pre-roll, multi-party
  RSS transcripts above 300 segments, ambiguous labels, and any segment that
  already anchors a claim. The unsafe broad dry run proposed 4,319 changes;
  after sampling and tightening, the applied pass contained 1,489 changes
  across 50 episodes, with zero Worker rejections.
- The post-repair audit finds 78,890 high-recall candidate segments. Under the
  current exact-speaker boundary, 1,386 transcript episodes have at least 10
  high-recall candidates and the theoretical ten-per-episode capacity is
  14,618. The remaining gap is predominantly speaker/transcript evidence, not
  a lack of things being said.
- `extract-v5` batches eight prefiltered excerpts per local call. The model only
  classifies keep/type/stance/topics/references; it cannot regenerate the
  assertion or quote. The exact excerpt is stored as both, then revalidated by
  the Worker. Existing published claims count toward `--target-claims 10`, and
  per-segment attempt checkpoints make interruption safe.
- A 25-episode Lenny qualification plus calibration brought 32 Lenny episodes
  to at least 10 published claims before the resumable continuation started.
  The continuation is now corpus-wide: every episode already at the target is
  skipped, and every attempted segment remains checkpointed. At the switch to
  the corpus-wide run, 51 transcript episodes were at the target and the local
  API contained 734 published claims.
- The completed trusted saturation pass contains 11,624 published claims from
  1,190 source episodes. It reached 96.2% of the nominal 12,080-item target;
  1,092 of 1,208 episodes reached 10, while 116 remain below target with a total
  shortfall of 456 claims.
- The residual is evidence-bound and must not be padded. A high-recall audit
  found capacity for at most 11,868 claims under the current exact-speaker and
  evidence rules; 30 episodes have fewer than 10 eligible candidates. At least
  212 of the nominal shortfall is therefore structurally unavailable, while the
  rest consists of candidates the model or Worker correctly did not publish.
- The final review reconciliation rejected 37 rows without deleting their
  evidence: 28 previously documented manual v9 rejections, six repeated
  OneSchema sponsor-insert claims across Lenny episodes, and three duplicate
  Zuckerberg excerpts from the Chase Center compilation that already have a
  canonical dedicated-interview source. Trusted published claims now have zero
  exact-quote duplicate groups, zero missing people, and zero broken
  claim-evidence pairs or R2 transcript quote anchors. Two same-segment groups
  remain and are legitimate multi-item recommendations with distinct quotes
  and objects.
- The local model intermittently returned a temporary "model unloaded" 400.
  Local extraction now retries the same batch up to four times, so a reload no
  longer silently skips otherwise eligible evidence.
- Production release completed on 2026-08-28 after D1 time-travel backup
  bookmark
  `00000084-00000ad4-000050d5-00c38b737972c80d0e4c89bca0196f54`.
  Migration `0006_llm_segment_attempts.sql`, all 1,208 R2 transcript objects,
  and the no-delete SQL bundle were applied successfully. The post-import D1
  bookmark is
  `00000091-00001a7d-000050d5-ce610641603e727426c1c9e2fdbcb93f`;
  CI and dispatch deploy run `33183059368` passed for API and web.

Final trusted coverage by show:

| Show | Transcript episodes | Claims | Episodes at 10+ | Below 10 | Gap to 10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Conversations with Tyler | 295 | 2,932 | 287 | 8 | 18 |
| Lenny's Podcast | 328 | 3,258 | 316 | 12 | 22 |
| Acquired | 170 | 1,615 | 146 | 24 | 85 |
| Lex Fridman Podcast | 113 | 1,092 | 108 | 5 | 38 |
| Latent Space | 116 | 1,051 | 81 | 35 | 109 |
| Dwarkesh Podcast | 89 | 886 | 85 | 4 | 4 |
| Machine Learning Street Talk | 39 | 356 | 30 | 9 | 34 |
| The Cognitive Revolution | 35 | 318 | 30 | 5 | 32 |
| Cheeky Pint | 21 | 116 | 9 | 12 | 94 |
| The Logan Bartlett Show | 2 | 0 | 0 | 2 | 20 |
| **Total** | **1,208** | **11,624** | **1,092** | **116** | **456** |

Optional targeted rerun command (explicitly local; never point this at
production by accident):

```bash
API_BASE=http://127.0.0.1:8787 \
ADMIN_TOKEN=local-audit \
AI_BASE_URL=http://127.0.0.1:1234/v1 \
ON_RECORD_FORCE_MODEL=qwen/qwen3.5-4b \
AI_MODEL=qwen/qwen3.5-4b \
uv run --project python/ingest python -m on_record_ingest \
  --stage extract --batch-size 8 --target-claims 10
```

During the correctness pass itself, no commit, push, deploy, production ingest,
migration, or release was performed.
The final local `pnpm quality` run passed 57 API tests, 199 Python tests,
formatting, lint, all TypeScript checks, unused-code, complexity, zero-clone
duplication, cycle, suppression, and hygiene gates. The Astro server build and
the Fleet design-review check also pass; browser qualification covers the core
routes at 390, 768, and 1440 pixels with no console errors or horizontal page
overflow. The exact historical correctness receipt remains recorded below.

## Local snapshot

The ignored, local-only store is:

`workers/api/.wrangler/audits/2026-08-27-correctness-v9/`

It occupies approximately 971 MB of logical disk space.
The earlier audit directories are preserved as historical evidence but are not
current truth.

The derived insight workspace is a clone at:

`workers/api/.wrangler/audits/2026-08-27-insights-v5/`

It occupies approximately 109 MB. Use `correctness-v9` for catalog, transcript,
and raw extraction truth. Use `insights-v5/analysis/final-v9` for reviewed
recommendation, bold-statement, and position-history truth. The previous
`analysis/final` directory is preserved as the v8 result. The raw D1
`published` label is an automated gate, not the final human-review state: it
contains 194 claims / 213 references, including the 28 rejected rows and
pre-correction reference forms.

### Episodes by show

| Show | Episodes | Audio | Verified video |
|---|---:|---:|---:|
| 20VC | 1,500 | 1,500 | 0 |
| Odd Lots | 1,261 | 1,261 | 0 |
| a16z | 1,000 | 1,000 | 2 |
| My First Million | 896 | 896 | 1 |
| TBPN | 649 | 649 | 6 |
| Invest Like the Best | 594 | 594 | 0 |
| Lex Fridman | 501 | 501 | 113 |
| Founders | 455 | 455 | 0 |
| All-In | 411 | 411 | 3 |
| Cognitive Revolution | 368 | 368 | 7 |
| Lenny's Podcast | 358 | 358 | 0 |
| This Week in Startups | 300 | 300 | 8 |
| Conversations with Tyler | 298 | 298 | 7 |
| MLST | 260 | 260 | 39 |
| Latent Space | 221 | 221 | 4 |
| Acquired | 216 | 216 | 1 |
| No Priors | 175 | 175 | 2 |
| Logan Bartlett | 163 | 163 | 10 |
| The Peel | 155 | 155 | 155 |
| Hard Fork | 155 | 3 | 154 |
| Dwarkesh | 137 | 137 | 2 |
| Unsupervised Learning | 101 | 101 | 11 |
| Lightcone | 52 | 37 | 15 |
| BG2 | 44 | 44 | 15 |
| Cheeky Pint | 35 | 35 | 0 |
| **Total** | **10,305** | **10,138** | **555** |

The exact 1,500, 1,000, and 300 counts are source/API ceilings. They are not
proof that those historical archives end there.

### Episodes by year

| Year | Episodes |
|---|---:|
| 2015 | 155 |
| 2016 | 348 |
| 2017 | 402 |
| 2018 | 377 |
| 2019 | 471 |
| 2020 | 750 |
| 2021 | 766 |
| 2022 | 956 |
| 2023 | 1,204 |
| 2024 | 1,402 |
| 2025 | 2,022 |
| 2026 | 1,452 |

## Archive reconciliation

### Hard Fork

- The official YouTube playlist has 156 unique entries: 154 long-form episodes
  and two Shorts under three minutes.
- The 154 long-form videos were admitted. Two matched current RSS episodes; 152
  became additional local episode rows. The trailer remains audio-only.
- Local result: 155 rows, three audio URLs, and 154 official video IDs.
- Apple currently reports 211 items, so 56 earlier audio episodes are still
  missing from the locally accessible current RSS/official-video surfaces.
  They were not invented or matched speculatively.

Audit evidence:

- `workers/api/.wrangler/audits/2026-08-27-correctness-v3/hard-fork-official-playlist.tsv`
- `workers/api/.wrangler/audits/2026-08-27-correctness-v3/ingest_hard_fork_playlist.py`

### The Peel

- The correct Apple-resolved Spotify/Anchor RSS feed yields 155 audio episodes.
- The official playlist has 156 entries: 155 public long-form videos and one
  private/unavailable video.
- All 155 public videos are attached to the corresponding 155 RSS rows. The
  matching evidence is 152 unique dates, two exact titles within two days, and
  one exact-title publisher-date correction.

Audit evidence:

- `workers/api/.wrangler/audits/2026-08-27-correctness-v3/the-peel-official-playlist.tsv`
- `workers/api/.wrangler/audits/2026-08-27-correctness-v3/attach_the_peel_playlist.py`

## Transcript corpus

| Source | Episodes | Segments | Speaker treatment |
|---|---:|---:|---|
| Odd Lots / Omny timed text | 653 | included in `rss_text` | unknown |
| Odd Lots / oversized Omny text | 604 | 8,138 | coarse, null timestamp, unknown |
| TBPN / Transistor timed HTML | 641 | included in `rss_text` | unknown |
| Lex / publisher HTML | 113 | 47,950 | exact publisher labels except 3,426 unknown continuations |
| Dwarkesh / timed publisher HTML | 47 | 7,355 | 7,354 exact; 1 unknown publisher typo |
| Dwarkesh / section-timed publisher HTML | 42 | 7,565 | coarse, null claim timestamp; 7,562 exact; 3 unknown publisher typos |
| Latent Space / turn-timed publisher HTML | 93 | 14,573 | 13,087 exact; 1,486 unknown |
| Latent Space / coarse publisher HTML | 23 | 4,533 | coarse, null claim timestamp; 4,158 exact; 375 unknown |
| Cognitive Revolution / official publisher HTML | 35 | 3,737 | 3,357 exact; 380 unknown |
| MLST / official Rescript shares | 39 | 3,692 | 3,472 exact; 220 unknown |
| Cheeky Pint / named timed text | 21 | 3,378 | 2,330 exact; 1,048 unknown |
| Conversations with Tyler / official publisher HTML | 295 | 46,548 | coarse, null claim timestamp; 46,155 exact; 393 unknown |
| Acquired / official publisher HTML | 170 | 68,348 | coarse, null claim timestamp; 65,023 exact; 3,325 unknown |
| Lenny's Podcast / official publisher JSON | 328 | 48,682 | 48,409 exact; 273 unknown |
| Logan Bartlett / VTT | 2 | 25 | unknown |
| **Total** | **3,106** | **745,737** | **245,431 exact; 500,306 unknown** |

Segment totals by stored kind are 481,213 `rss_text`, 20,236
`rss_text_coarse` (8,138 legacy unknown-speaker segments plus 7,565 Dwarkesh
and 4,533 Latent Space coarse segments), 77,307 `publisher_html`, 114,896
`publisher_html_coarse`, 48,682 `publisher_json`, 3,378 `rss_named_text`, and
25 `rss_vtt`.

Lex has 113 correct publisher transcripts. Seven earlier rows that pointed to
an adjacent episode were removed; six were recovered against their own
publisher pages and Dave Plummer remained rejected because the page linked to
Dave Hone. Network and malformed-page failures now fail closed and remain
retryable rather than being converted into false transcript absence.

The Cognitive Revolution audit checked 87 unique official publisher pages.
Thirty-five passed the fail-closed parser, contributing 3,610 publisher cues;
52 were rejected (51 had fewer than ten usable turns and one regressed in
timestamp order). Of those cues, 3,097 carried an approved exact speaker and
513 remained unknown. The MLST RSS exposed 39 official public Rescript shares;
all 39 passed, contributing 11,608 cues, with 10,928 mapped and 680 unknown.
Together these two sources added 74 transcript episodes and 15,218 publisher
cues without guessing a speaker.

The Dwarkesh audit checked 137 unique official publisher pages. Eighty-nine
passed the fail-closed parser and 48 were rejected for having fewer than ten
usable turns. The accepted pages contributed 14,562 publisher cues: 14,558 map
to manually approved publisher identities and four typo labels remain unknown.
Forty-seven pages carry turn-level timestamps. Forty-two only carry section
timing, so they use ordered coarse segments and deliberately produce null claim
timestamps rather than invented seconds.

The Latent Space audit checked 221 unique official publisher pages. One hundred
sixteen passed the fail-closed parser and 105 were rejected (104 had fewer than
ten usable turns and one failed its title match). The accepted pages contributed
22,811 publisher cues: 20,138 map to exact publisher identities and 2,673 remain
unknown. Ninety-three pages carry turn-level timing. Twenty-three use ordered
coarse segments and deliberately produce null claim timestamps. A separate
source verifier confirmed that mapping changed neither cue text nor timing and
that every exact identity came from an approved publisher label.

The Conversations with Tyler audit checked 297 official episode URLs against
298 local rows. Two RSS links were unusable (one missing and one pointed to the
wrong episode), and one local row was a duplicate rerelease. The remaining 295
official pages passed the fail-closed parser and contributed 47,052 publisher
cues. Manual label review approved 46,641 cues; 411 audience, typo, or ambiguous
cues remain unknown. They are stored as 46,548 ordered coarse segments: 46,155
exact and 393 unknown, with null claim timestamps because the publisher pages do
not provide playback timing. A source verifier matched every stored raw cue,
segment body, and approved speaker mapping back to the reviewed source corpus.

The Acquired audit checked all 216 local episodes against the official episode
sitemap and publisher pages. It resolved 211 official URLs; 170 pages contained
substantial speaker-labelled transcripts, 39 had empty transcript containers,
and five legacy Transistor links had no safe cross-show route. Two malformed
Netflix pages were quarantined because publisher labels disappeared and tens of
thousands of characters collapsed under one speaker. The accepted pages
contributed 68,586 raw publisher cues, of which 64,972 map to exact roster or
publisher-host identities and 3,614 remain unknown. They are stored as 68,348
coarse segments: 65,023 exact and 3,325 unknown. The v8 verifier matched every
accepted source cue to R2 and every segment and identity to D1.

The Lenny's Podcast audit checked all 358 local episodes against official
Substack post metadata. Three hundred twenty-eight posts supplied an approved
transcript, valid speaker map, and exact post match; 30 failed closed (13
missing transcripts, 16 missing speaker maps, and one invalid map). The
accepted posts contributed 315,881 timed cues and 26,321,744 characters. They
are stored as 48,682 `publisher_json` segments: 48,409 exact and 273 unknown.
The remaining 2,660 unknown cues preserve unresolved publisher labels rather
than guessing a person. A dedicated verifier matched all 328 imports back to
their source cues and found zero failures or signed-URL leakage.

The apparent BG2 "transcript" surface was rejected: it was Spotify page state
containing show-wide descriptions and chapter markers, not a per-episode
transcript.

YouTube caption requests from this machine currently fail with `IpBlocked`.
Those 555 video-linked rows remain retryable. A caption outage is not stored as
`no_transcript`.

## Verified recommendation data

The local D1 contains 194 high-confidence published claims and 213 reference
rows. The recorded manual decision sets accept 166 claims / 189 reference rows
and reject 28 claims. Lenny's Podcast contributes 71 accepted claims / 76
reference rows after 92 provisional claims received an explicit decision: 71
accepted and 21 rejected. Its accepted slice includes 20 book rows, 27 app
rows, 11 tool rows, and 18 rows across course, hardware, and other categories.

| Kind / role | Reference rows |
|---|---:|
| App / uses | 49 |
| App / recommends | 2 |
| App / built | 2 |
| App / avoids | 1 |
| Book / recommends | 28 |
| Book / uses | 7 |
| Tool / uses | 34 |
| Tool / recommends | 1 |
| Tool / built | 1 |
| Tool / avoids | 2 |
| Service / recommends | 3 |
| Service / uses | 6 |
| Hardware / uses | 8 |
| Course / recommends | 1 |
| Paper / uses | 1 |
| Person / recommends | 2 |
| Other / recommends | 23 |
| Other / uses | 16 |
| Other / built | 2 |
| **Total** | **189** |

Rejected examples include paid host reads, generic or pronoun-only objects,
third-person statements, employment rather than product use, jokes, truncated
evidence, and likely title corrections that were not verbatim-supported. The
API evidence gate also rejected manual normalizations when the normalized name
did not occur in the exact quote; those decisions were narrowed or rejected
rather than weakening the gate.

Every row stores the speaker, episode, exact quote, role, category, confidence,
and manual-review basis. It stores the timestamp where the publisher provides
turn timing; coarse section-timed evidence deliberately remains null. This is a
high-precision slice of the source-attributed segments, not corpus-wide recall.
Acquired recommendation extraction and manual review are complete for its 170
accepted official transcripts. Lenny recommendation extraction and manual
review are complete for its 328 accepted official transcripts.

## Verified bold statements

The earlier expanded deterministic scan, including Acquired, produced 55,287
quote-anchored statements. Its strict gates left 683 model-review candidates;
every one was reviewed, 58 were model-admitted, and manual review approved 32.
The dedicated Lenny scan added 21,915 quote-anchored statements. Its stricter
score-seven gate left 575 candidates; every one was reviewed, 20 were
model-admitted, and manual review approved 12 and rejected eight. The combined
final export therefore contains 44 manually approved statements.

| Year | Speaker | Reviewed position |
|---:|---|---|
| 2026 | Nathan Labenz | The government will bail out OpenAI if it cannot meet its obligations by 2029. |
| 2025 | Demis Hassabis | AGI is probably the most important technology ever invented. |
| 2024 | Elon Musk | Winning in AI requires the most powerful training compute and a faster rate of compute improvement than competitors. |
| 2026 | Dario Amodei | Anthropic cannot buy $1 trillion per year of compute in 2027 even if revenue continues growing tenfold. |
| 2022 | Jeremy Grantham | No serious climate scientist would bet that global society remains stable at five degrees Celsius of warming. |
| 2023 | Jimmy Wales | Wikipedia will never bow to government pressure anywhere in the world. |
| 2026 | Laura Burkhauser | AI creator tools will end traditional recorded-media roles and displace their workers. |
| 2025 | Richard Sutton | Superintelligence is inevitable and will gain resources and power over time. |
| 2026 | Robert Lange | The conduct of research and science will fundamentally change across five-, ten-, and twenty-year horizons. |
| 2026 | Ben Gilbert | Investor-controlled boards will always vote to lower fees when they can because doing so serves investors' interests. |
| 2022 | Brad Gerstner | The system will have more capital, access, ideas, and vitality within ten years. |
| 2025 | Bret Taylor | Human specifications for AI agents will always be incomplete, requiring agents to fill gaps with reasoning. |
| 2023 | Carl Shulman | AI systems that cannot be copied and integrated will be less valuable than GPUs. |
| 2023 | Carl Shulman | Rapidly adding guardrails could make an AI aligned enough despite loopholes. |
| 2023 | Carl Shulman | Humans can retain final authority over complex decisions through understandable summaries of the options. |
| 2023 | Carl Shulman | Even an inefficient attack on a solar system could pay off when its stellar resources remain valuable for billions of years. |
| 2025 | Casey Handmer | He will never hire anyone who cannot do math. |
| 2025 | Casey Handmer | Gas turbines cannot remain price-competitive over 25 years against current solar prices and falling battery prices. |
| 2026 | Dan Balsam | No perfect training setup will always produce aligned models. |
| 2023 | David Rosenthal | A luxury brand will never brand only a product feature. |
| 2024 | David Rosenthal | GLP-1 drugs will follow insulin's pattern of repeated product improvements, innovation, and increased supply. |
| 2024 | David Rosenthal | Serious product problems create a frightening risk for Hermes' future. |
| 2024 | David Rosenthal | Mobile platforms will never allow an app to run inside another app. |
| 2025 | Dwarkesh Patel | Individuals cannot fundamentally transform technology's trajectory or influence decisions through labor or cognition alone. |
| 2026 | Dwarkesh Patel | Nobody now disagrees that AGI will be achieved this century. |
| 2026 | Dylan Patel | Value per GPU will skyrocket further out in the scaling cycle. |
| 2026 | Eric Jang | Scaling energy, compute, and parameters will almost inevitably produce intelligence. |
| 2026 | Joel Mokyr | An Industrial Revolution requires a concept of progress and research directed toward material improvement. |
| 2026 | Nathan Labenz | A transformative-AI step change would make the world a Wild West. |
| 2024 | Sara Walker | The frontier of modern physics lies in life and intelligence rather than traditional high-energy or quantum-gravity programs. |
| 2025 | Satya Nadella | CRUD SaaS applications will fundamentally change as business logic moves into an agentic tier. |
| 2022 | Jeremy Grantham | The upfront energy demand from rapidly building wind, solar, and storage will increase fossil-fuel demand. |
| 2025 | Ben Horowitz | Anti-investor and anti-entrepreneur framing is unusually effective at winning press approval. |
| 2024 | Amjad Masad | Replit accepts missing the enterprise's main development pipeline in order to empower non-engineers to build. |
| 2026 | Dan Shipper | Model companies will structurally trail users who create specialized expertise and workflows from their models. |
| 2026 | Dan Shipper | AI-driven mass unemployment predicted by some AI CEOs will not happen. |
| 2025 | Dhanji R. Prasanna | Forcing strong engineers into narrowly constrained areas does more harm than good. |
| 2025 | Dmitry Zlokazov | Functionality can be cut, but quality, UX, and aesthetics will never be compromised. |
| 2023 | Elena Verna | Value-first product-led growth will heavily disrupt top-down sales organizations over ten years. |
| 2025 | Julie Zhuo | Startups that retain old products and working methods will be left behind. |
| 2024 | Kayvon Beykpour | Putting seemingly unqualified people in the deep end is one of the best ways to drive change. |
| 2023 | Kevin Aluwi | Product teams without clear accountability and decision authority execute much more slowly. |
| 2023 | Kim Scott | Organizations that fail to richly reward the risk of feedback will receive no more feedback. |
| 2026 | Mark Pincus | Product makers' greatest opportunity is infrastructure the next generation cannot imagine living without. |

The CSV/JSONL exports retain the exact quote, speaker, episode, timestamp,
source URL, review reason, and stable candidate ID.

## Verified position histories

The previous pass produced 11 manually approved refinements whose source
anchors still verify. The dedicated Lenny pass screened all 1,376 eligible
same-speaker, multi-year statements; 256 survived the position screen across 16
speakers. Embedding similarity produced 42 candidate pairs, the relation judge
admitted 27, and manual review approved five genuine refinements while rejecting
22 false semantic matches. The combined final export contains 16 histories:

| Years | Speaker / topic | Reviewed refinement |
|---|---|---|
| 2024 -> 2026 | Dario Amodei / regulation | Shifted from warning that poorly targeted rules discredit safety concerns to supporting a process biased toward cases with clear safety and efficacy. |
| 2024 -> 2026 | Dario Amodei / regulation | Made support for targeted, workable regulation concrete as a uniform federal standard with preemption. |
| 2025 -> 2026 | Dwarkesh Patel / compute | Sharpened a qualitative claim about valuable job-performing agents into a $10 trillion compute implication and timeline. |
| 2025 -> 2026 | Dylan Patel / capital | Clarified that model competition visible in revenue is revenue concentrating on the best models. |
| 2023 -> 2026 | Dylan Patel / compute | Gave the earlier general compute-bottleneck position a concrete supply-chain capacity mechanism. |
| 2025 -> 2026 | Dylan Patel / foundation models | Qualified the expectation that capable Chinese models would persist with a widened Western lead while retaining the expectation of new Chinese releases. |
| 2023 -> 2025 | Ilya Sutskever / alignment | Clarified that convergence could occur on alignment strategies even without one mathematical definition. |
| 2025 -> 2026 | Nathan Lambert / open weights | Added a concrete limitation: open models can struggle when a workflow mixes public and private information. |
| 2025 -> 2026 | Lex Fridman / coding agents | Expanded from Cursor after leaving Emacs to a half Cursor, half Claude Code workflow. |
| 2025 -> 2026 | Lex Fridman / software development | Added natural-language communication with agents as the mechanism behind expected programmer productivity gains. |
| 2024 -> 2025 | Mark Zuckerberg / product | Specified the general Meta AI assistant as a personalized product used throughout the day. |
| 2022 -> 2024 | Marty Cagan / product | Broadened a skills criticism of product owners into a wider criticism of proliferating product and process roles. |
| 2022 -> 2023 | Casey Winters / product | Added founder ownership and post-product-market-fit scaling as mechanisms behind the need for continuous improvement. |
| 2022 -> 2023 | Elena Verna / product | Strengthened her rejection of a product-led versus sales-led binary with a warning against siloing the approach in marketing. |
| 2022 -> 2025 | Elena Verna / product | Broadened user decision power in product-led sales into a general consumer-power principle and historical explanation. |
| 2023 -> 2024 | Lenny Rachitsky / startups | Sharpened the status-quo switching problem with the condition that incumbent options are already good enough. |

All sixteen are conservatively classified as refinements. No contradiction
survived manual review. No Acquired pair expressed a defensible
same-proposition cross-year change, while the Lenny pass produced five.

## Correctness fixes in the worktree

- Arbitrary YouTube links in show notes no longer become episode videos.
- Unmatched channel uploads are ignored unless a show explicitly opts in.
- Lex resolution uses the canonical episode page first, rejects episode-number
  mismatches, applies bounded title/token thresholds, and treats transient
  publisher failures as retryable.
- YouTube caption operational failures are retryable; only genuine disabled or
  missing captions can be empty.
- The wrong Peel feed was replaced by the Apple-resolved feed.
- Recommendation rows require a direct `recommends`, `uses`, `built`, or
  `avoids` relationship. Mention-only, hearsay, generic, and mismatched objects
  do not publish.
- Non-recommendation claims no longer fail solely because they have no named
  reference object, and their supplied assertion is preserved. Recommendation
  claims still require an evidenced reference; regression tests cover both
  sides of that boundary.
- Guest confidence uses the same 0.5 floor in roster construction and speaker
  identification.
- Generic transcript speaker labels stay unknown when identity evidence is
  insufficient.
- Cognitive Revolution, MLST, Dwarkesh, Latent Space, and Conversations with
  Tyler now ingest only from official publisher transcript surfaces, through
  the local Worker API. Speaker mappings are manually allowlisted; sponsor,
  generic, numeric, typo, and ambiguous labels remain unknown. Section-only
  Dwarkesh and coarse Latent Space/CWT pages use ordered segments and null claim
  timestamps.
- Acquired now resolves legacy root links through the official sitemap, checks
  the fetched page title, rejects ambiguous matches, keeps missing transcripts
  distinct from transient source failures, and quarantines structurally
  malformed pages. Stable host labels and unique roster initials are exact;
  unresolved guest labels remain unknown.
- Lenny's Podcast now resolves exact official Substack post metadata, accepts
  only approved transcript and speaker-map records, never persists signed CDN
  URLs, and handles padded or unpadded publisher labels without guessing.
  Missing labels remain unknown and malformed timing cues fail closed.
- CWT parsing separates Unicode, mixed-case, partially bold, and plain-text
  publisher labels before identity mapping. A cross-corpus scan finds no
  residual speaker labels inside attributed turns; the sole label-shaped match
  is an inline quotation of E. O. Wilson, not a turn boundary.
- Segment writes are exact transcript replacements: stale trailing anchors are
  deleted, invalid or duplicate indexes are rejected, and any episode with an
  existing claim is protected from replacement.
- The recommendation export has an explicit manual-review layer. Raw model
  `published` rows are never reported as final without the recorded decisions.
- Final export verification checks every accepted quote against its R2 segment,
  every bold/history speaker against the D1 speaker anchor, every recommendation
  object against the exact quote, and all catalog/duplicate invariants.

## Final verification receipt

- `pnpm ready`: passed.
- Worker tests: 45 passed across nine files.
- Python tests: 167 passed.
- Formatting, Biome/Ruff lint, TypeScript/Astro typecheck, unused-code,
  complexity, duplication, cycle, suppression, and hygiene checks: passed.
- `verify_final_exports.py` against `correctness-v9` and `analysis/final-v9`:
  verified 25 shows, 10,305 episodes, 3,106 transcript episodes, 745,737
  segments, 166 recommendation claims / 189 reference rows, 44 bold
  statements, and 16 position histories.
- SQLite integrity and foreign-key checks: passed.
- Duplicate show/GUID pairs and duplicate video IDs: zero.

## What is still missing

1. Reconcile every suspicious source/API ceiling against another official
   archive. Hard Fork still has a known 56-item audio gap.
2. Obtain transcripts for the 7,199 currently unsupported episodes. YouTube
   captions are retryable but IP-blocked locally; Whisper remains opt-in.
3. Resolve generic speakers only where evidence supports identity. Odd Lots and
   TBPN are ingested but intentionally produce no attributed claims today.
4. Recommendation and strict bold-statement extraction are complete over the
   65,023 exact Acquired segments and 48,409 exact Lenny segments. Lenny's 1,376
   eligible longitudinal candidates are also fully screened. The earlier broad
   cross-show longitudinal screen still has 2,287 candidates pending; the
   conservative approved-statement pass found no Acquired history worth
   publishing. Add a per-segment attempt marker so zero-result extraction rows
   are not repeatedly spent on.
5. Expand person/topic history coverage beyond the current screened slice; the
   16 approved refinements are a precision baseline, not corpus completion.
6. Productize significance scoring, semantic deduplication, and manual-review
   state so trivial, repeated, or context-dependent claims do not dominate
   output.

## Pipeline

```text
discover      official RSS/archive metadata -> episodes and people
attributions  determine whether a person is actually on an episode
transcripts   publisher/RSS transcript -> captions -> opt-in Whisper
identify      resolve generic voices from evidence, otherwise unknown
extract       quote-checked claims and named references
reverify      retract claims whose underlying evidence moved
publish       expose only rows that pass evidence and speaker gates
```

Remote migration and deployment commands are intentionally omitted. They need
explicit operator authorization.
