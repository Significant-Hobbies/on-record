# Recommendations: High Signal Podcasts

This surface contains books, tools, products, and other actionable references
linked to published podcast claims and primary evidence.

For counts grouped by named item, call
`GET https://api.podcasts.highsignal.app/api/recommendation-groups`. Each group
reports the number of distinct attributable people, the number of evidence
rows, and distinct-person counts split by action. Optional filters are `q`,
`kind`, `role`, `limit`, and `offset`.

For the underlying source-linked evidence rows, call
`GET https://api.podcasts.highsignal.app/api/recommendations`. Optional filters
are `person`, `kind`, `role`, and exact canonicalized `name`.

Keep roles distinct: a person saying they use, like, own, built, or avoid
something is not necessarily recommending it. Repeated evidence from one person
does not inflate a group's distinct-person count. If the API returns
`evidence: insufficient`, report that result without filling the gap.

TBPN and Odd Lots are retained in the local raw corpus but withheld from these
public responses until their diarized speakers can be attributed safely.
