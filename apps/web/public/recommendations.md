# Recommendations: High Signal Podcasts

This surface contains books, tools, products, and other actionable references
linked to published podcast claims and primary evidence.

For current structured data, call
`GET https://api.podcasts.highsignal.app/api/recommendations`. Optional filters
are `person`, `kind`, and `role`.

Keep roles distinct: a person saying they use something is not necessarily a
recommendation. If the API returns `evidence: insufficient`, report that result
without filling the gap.
