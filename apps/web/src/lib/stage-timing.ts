import type { APIContext } from 'astro';
import type { EdgeCacheResult } from './edge-cache';
import { runtimeEnv } from './runtime';

export function observeStageTiming(
  context: APIContext,
  result: EdgeCacheResult,
  totalMs: number
): void {
  try {
    const ctx = context.locals.cfContext;
    const env = runtimeEnv() as {
      APP_HEALTH_INGEST_KEY?: string;
      APP_HEALTH_STAGE_SAMPLE_RATE?: string;
    };
    const key = env.APP_HEALTH_INGEST_KEY?.trim();
    const route = context.routePattern.replace(/\[[^\]]+\]/g, ':param');
    const configuredRate = Number(env.APP_HEALTH_STAGE_SAMPLE_RATE ?? 0.1);
    const rate = Number.isFinite(configuredRate) ? Math.max(0, Math.min(1, configuredRate)) : 0.1;
    if (!(key && ctx && route) || Math.random() >= rate) {
      return;
    }
    // Only Astro's template is allowed, never a fallback to the request path.
    const concreteId = /^(?:\d+|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|[0-9a-f]{16,})$/i;
    if (
      !route.startsWith('/') ||
      route.length > 120 ||
      /[?#\s]/.test(route) ||
      route.split('/').some((segment) => concreteId.test(segment))
    ) {
      return;
    }
    const cf = (context.request as Request & { cf?: { colo?: unknown } }).cf;
    const colo =
      typeof cf?.colo === 'string' && /^[A-Za-z0-9]{1,8}$/.test(cf.colo) ? cf.colo : 'unknown';
    const props = {
      route,
      status: result.response.status,
      total_ms: Math.min(600_000, Math.max(0, totalMs)),
      edge_cache: result.edgeCache,
      inner_cache: 'NONE',
      colo,
      ...(result.edgeCache === 'MISS' && result.renderMs !== undefined
        ? { render_ms: Math.min(600_000, Math.max(0, result.renderMs)) }
        : {}),
    };
    ctx.waitUntil(
      fetch('https://ingest.sassmaker.com/v1/logs', {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${key}` },
        body: JSON.stringify({
          schema_version: 'v1',
          batch_id: crypto.randomUUID(),
          logs: [
            {
              log_id: crypto.randomUUID(),
              timestamp: Date.now(),
              event: 'api.stage_timing',
              level: 'debug',
              props,
            },
          ],
        }),
      }).catch(() => undefined)
    );
  } catch {
    // Stage telemetry can never fail a request, including missing runtime env.
  }
}
