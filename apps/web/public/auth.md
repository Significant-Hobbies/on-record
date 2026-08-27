# Authentication — High Signal Podcasts

## Public website and API

No authentication is currently required for the public website or read-only API
at `https://api.podcasts.highsignal.app`. Public operations are GET requests and
cannot create, edit, review, or publish claims.

## Administrative boundary

Administrative ingestion and review routes require protected operator access.
They are not public integration surfaces and are intentionally absent from the
public OpenAPI document.

There is no public OAuth flow, user account system, API-key signup, or delegated
write scope. Agents should not attempt administrative routes.
