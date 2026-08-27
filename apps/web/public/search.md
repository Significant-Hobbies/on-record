# Search — High Signal Podcasts

Search returns only published claims from the current evidence corpus.

Call `GET https://api.podcasts.highsignal.app/api/search` with optional query
parameters:

- `q` for full-text terms.
- `person` for a person slug.
- `type` for a supported claim type.
- `topic` for a topic slug.
- `from` and `to` for date bounds.

The result includes `evidence: insufficient` when no published evidence matches.
Do not interpret an empty result as proof that a person never made a statement.
