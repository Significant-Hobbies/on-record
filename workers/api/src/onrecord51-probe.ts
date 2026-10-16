import type { Context } from 'hono';
import type { Env } from './env';

// Temporary, metadata-only production timing probe for issue #51.
export type Probe = {
  id: string;
  generationMs?: number;
  sharedGenerationMs?: number;
  r2Ms?: number;
  handlerMs?: number;
  sharedResult?: 'HIT' | 'STALE' | 'MISS';
};

const probes = new WeakMap<object, Probe>();
const fixedPaths = new Set([
  '/api/stats',
  '/api/people?limit=8',
  '/api/search',
  '/api/recommendation-groups?limit=8',
  '/api/sources?limit=5',
]);

export function probeFor(c: object): Probe | undefined {
  return probes.get(c);
}

export function startProbe(c: Context<{ Bindings: Env }>): Probe | undefined {
  const id = c.req.header('x-onrecord51-probe');
  const url = new URL(c.req.url);
  if (
    c.req.method !== 'GET' ||
    !id ||
    !/^[a-f0-9-]{36}$/.test(id) ||
    !fixedPaths.has(`${url.pathname}${url.search}`) ||
    c.req.header('authorization') ||
    c.req.header('cookie')
  ) {
    return;
  }
  const probe: Probe = { id };
  probes.set(c, probe);
  return probe;
}

export function recordProbeDuration(
  probe: Probe | undefined,
  field: 'sharedGenerationMs' | 'r2Ms',
  startedAt: number
): void {
  if (probe) {
    probe[field] = performance.now() - startedAt;
  }
}

export function logProbe(
  c: Context<{ Bindings: Env }>,
  probe: Probe,
  startedAt: number,
  status: number | null
): void {
  const colo = (c.req.raw as Request & { cf?: { colo?: string } }).cf?.colo ?? 'unknown';
  const totalMs = performance.now() - startedAt;
  const { generationMs = 0, sharedGenerationMs = 0, r2Ms = 0, handlerMs = 0 } = probe;
  console.log(
    JSON.stringify({
      event: 'onrecord51_api',
      id: probe.id,
      route: c.req.path,
      colo,
      status,
      totalMs: Math.round(totalMs),
      generationMs: Math.round(generationMs),
      sharedGenerationMs: Math.round(sharedGenerationMs),
      r2Ms: Math.round(r2Ms),
      handlerMs: Math.round(handlerMs),
      residualMs: Math.round(
        Math.max(0, totalMs - generationMs - sharedGenerationMs - r2Ms - handlerMs)
      ),
      sharedResult: probe.sharedResult ?? 'OUTER_CACHE_OR_NONE',
    })
  );
}
