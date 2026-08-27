# People: High Signal Podcasts

The people index lists active speakers who have at least one published claim in
the current corpus. It is not a complete guest roster.

For current structured data, call
`GET https://api.podcasts.highsignal.app/api/people`. Then retrieve one person's
published claims and recommendations with `GET /api/people/{slug}`.

Preserve the claim's quote, date, and evidence when using the result. An absent
person means the current corpus has no published evidence for them; it does not
support a broader conclusion.
