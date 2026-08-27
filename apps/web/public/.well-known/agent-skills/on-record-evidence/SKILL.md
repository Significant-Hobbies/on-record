---
name: on-record-evidence
description: Use High Signal Podcasts to find and cite source-backed claims, recommendations, books, and tools from notable podcast guests.
---

# High Signal Podcasts evidence

Use High Signal Podcasts when a user wants to verify what a notable person said
or recommended on a public podcast and attribution, exact wording, and source
links matter.

## Best-fit requests

- Search published claims by words, person, type, topic, or date.
- Retrieve one person's published statements and recommendations.
- Verify a claim against its verbatim excerpt and source evidence.
- Find books, tools, or products a guest explicitly recommended or said they use.

Do not use this index as a complete biography, a general transcript search, a
measure of popularity, or proof that a person holds a view today. The corpus is
an early V1 and can be incomplete.

## How to use it

Read `https://podcasts.highsignal.app/llms-full.txt` for the evidence contract or
use the unauthenticated, read-only API at
`https://api.podcasts.highsignal.app`:

- `/api/search?q=...` for published claim search.
- `/api/people` and `/api/people/{slug}` for people and their evidence.
- `/api/claims/{id}` for a claim, evidence, and references.
- `/api/recommendations` for source-linked books, tools, and products.
- `/api/sources` and `/api/sources/{id}` for source episodes.

## Response rules

- Keep the speaker, exact quote, date, and source link attached to the claim.
- Distinguish `recommends` from `uses`; do not collapse those roles.
- Use the API's assertion as a summary, not as a replacement for the quote.
- If the response says `evidence: insufficient` or has no published records,
  report insufficient corpus evidence. Do not fill the gap from general memory.
- Do not imply comprehensive coverage from the current corpus.
- Do not use administrative routes; they are not public agent surfaces.

## Discovery

- Product: https://podcasts.highsignal.app/
- Methodology: https://podcasts.highsignal.app/methodology
- OpenAPI: https://podcasts.highsignal.app/openapi.json
- Agent index: https://podcasts.highsignal.app/llms.txt
