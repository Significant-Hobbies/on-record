// App-Health endpoint telemetry: per-route method/status/duration to the
// ingest collector. Dependency-free — the ingest wire format is a single
// POST. Silent no-op until APP_HEALTH_INGEST_KEY is set (secret, not vars:
// a same-name vars entry replaces the secret on deploy). Telemetry can never
// fail a request; Hono's routePath supplies the template so raw ids/slugs
// never leave the worker.
import type { Context } from 'hono';

const INGEST_ENDPOINT = 'https://ingest.sassmaker.com/v1/ingest';

export function observeRequest(c: Context, startedAt: number): void {
  const key =
    typeof c.env?.APP_HEALTH_INGEST_KEY === 'string' ? c.env.APP_HEALTH_INGEST_KEY.trim() : '';
  const route = c.req.routePath && c.req.routePath !== '*' ? c.req.routePath : null;
  if (!key || !route) return;
  const batch = {
    batch_id: crypto.randomUUID(),
    schema_version: 'v1',
    runtime: 'worker',
    environment: 'production',
    events: [
      {
        event_id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        method: c.req.method,
        route,
        status_code: c.res.status,
        duration_ms: Math.max(0, Math.round(Date.now() - startedAt)),
      },
    ],
  };
  try {
    c.executionCtx.waitUntil(
      fetch(INGEST_ENDPOINT, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          authorization: `Bearer ${key}`,
        },
        body: JSON.stringify(batch),
      }).catch(() => undefined)
    );
  } catch {
    // Telemetry must never take down the request path.
  }
}
