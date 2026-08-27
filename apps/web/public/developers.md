# Public API — High Signal Podcasts

Base URL: `https://api.podcasts.highsignal.app`

The API is public, unauthenticated, and read-only. It exposes published claims,
people, source episodes, search, recommendations, and corpus statistics. It does
not expose public create, edit, review, or publish operations.

- OpenAPI: https://podcasts.highsignal.app/openapi.json
- API catalog: https://podcasts.highsignal.app/.well-known/api-catalog
- Authentication boundary: https://podcasts.highsignal.app/auth.md
- Evidence policy: https://podcasts.highsignal.app/methodology.md

Preserve quotes, attribution, dates, and source evidence. Treat explicit
insufficient-evidence responses as corpus boundaries rather than answers.
