import { createAppHealthClient } from '@saas-maker/app-health';
import { honoMiddleware } from '@saas-maker/app-health/hono';
import type { Env } from './env';

const INGEST_ENDPOINT = 'https://ingest.sassmaker.com/v1/ingest';

// The resolver keeps collection disabled when the existing secret is absent.
// App Health's Hono adapter records only the matched route template, method,
// final status, and duration, then flushes through Worker waitUntil.
export const endpointTelemetryMiddleware = honoMiddleware<{ Bindings: Env }>({
  client: (c) => {
    const key = c.env?.APP_HEALTH_INGEST_KEY?.trim();
    const route = c.req.routePath;
    if (!(key && route) || route.includes('*')) {
      return null;
    }

    return createAppHealthClient({
      key,
      environment: c.env.ENVIRONMENT ?? 'production',
      endpoint: INGEST_ENDPOINT,
      runtime: 'worker',
      disableTimer: true,
    });
  },
});
