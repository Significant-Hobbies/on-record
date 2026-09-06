# on-record

Source-backed index of what notable people have publicly said.

The product answers: what does this person believe, recommend, predict, or
disagree with — and how has that changed? Every published result is a claim
with a verbatim transcript excerpt, speaker, date, and source link. A timed
YouTube link is included only when the excerpt came from that video's captions.

This is not a transcript search engine. The primary unit is the claim.

The trusted public product is a research desk rather than a podcast directory:
readers can search ideas, browse people, compare recurring books, apps, and
tools, inspect source episodes, and open an exact evidence receipt for every
result. D1 FTS5 powers public search; person, claim, source, and recommendation
pages preserve the speaker and source trail.

The live corpus exposes 30,562 published claims from 956 people across 1,208
source episodes, plus 8,509 catalog episodes and 1,226 episodes with
transcript evidence across 23 trusted shows (as of 2026-09-06; the homepage
reads these counts live from `/api/stats` so they track the corpus without a
doc edit). The public quote-safety pass exposes 1,141 named-reference
evidences in 958 canonical groups (live via `/api/stats` and
`/api/recommendation-groups`). D1 retains 300 named-reference rows before the
public pass (last verified 26 Aug 2026). Of the transcript episodes, 1,092
(90.3%) have at least 10 claims and 19 have none (last verified 26 Aug 2026).
TBPN and Odd Lots remain retained in the raw 25-show corpus but are withheld
from every public route until their diarized speakers can be attributed safely.
