// App-Health endpoint telemetry: per-route method/status/duration to the
// ingest collector. Dependency-free — the ingest wire format is a single
// POST. Silent no-op until APP_HEALTH_INGEST_KEY is set on the worker
// (secret, not vars: a same-name vars entry replaces the secret on deploy).
// Route templates come from Astro's routePattern — `[id]`/`[slug]` params
// never leave the worker in raw form. Telemetry can never fail a request.
import type { APIContext } from 'astro';

const INGEST_ENDPOINT = 'https://ingest.sassmaker.com/v1/ingest';

type WorkerRuntime = {
  env?: Record<string, unknown>;
  ctx?: { waitUntil: (promise: Promise<unknown>) => void };
};

export function observeRequest(
  context: APIContext,
  response: Response,
  startedAt: number
): void {
  const runtime = (context.locals as { runtime?: WorkerRuntime }).runtime;
  const env = runtime?.env as Record<string, unknown> | undefined;
  const ctx = runtime?.ctx;
  const key =
    typeof env?.APP_HEALTH_INGEST_KEY === 'string' ? env.APP_HEALTH_INGEST_KEY.trim() : '';
  const pattern = context.routePattern;
  if (!key || !ctx || !pattern) return;
  // Astro templates use [param]; normalize to :param to match worker routes.
  const route = pattern.replace(/\[[^\]]+\]/g, ':param');
  const batch = {
    batch_id: crypto.randomUUID(),
    schema_version: 'v1',
    runtime: 'worker',
    environment: 'production',
    events: [
      {
        event_id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        method: context.request.method,
        route,
        status_code: response.status,
        duration_ms: Math.max(0, Math.round(Date.now() - startedAt)),
      },
    ],
  };
  try {
    ctx.waitUntil(
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
