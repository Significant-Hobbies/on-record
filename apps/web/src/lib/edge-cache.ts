import type { APIContext } from 'astro';
import { runWithDegradedTracking } from './degraded';

const FRESH_MS = 300_000;
const RETENTION_MS = FRESH_MS + 3_600_000;
const CACHED_AT = 'X-Edge-Cached-At';
const CACHE_CONTROL = 'public, max-age=0, s-maxage=300, stale-while-revalidate=3600';
const publicPages = new Set([
  '/',
  '/about',
  '/contact',
  '/developers',
  '/evidence',
  '/methodology',
  '/people',
  '/people/[slug]',
  '/pricing',
  '/privacy',
  '/recommendations',
  '/search',
  '/sources',
  '/sources/[id]',
  '/claims/[id]',
]);

type EdgeCache = 'HIT' | 'MISS' | 'STALE' | 'BYPASS';
export type EdgeCacheResult = { response: Response; edgeCache: EdgeCache; renderMs?: number };

function cacheable(response: Response): boolean {
  return (
    response.status === 200 &&
    /^text\/html(?:;|$)/i.test(response.headers.get('Content-Type') ?? '') &&
    !response.headers.has('Set-Cookie') &&
    (response.headers.get('Vary') ?? '')
      .split(',')
      .every((value) => !value.trim() || value.trim().toLowerCase() === 'accept-encoding')
  );
}

async function store(cache: Cache, key: string, response: Response): Promise<void> {
  try {
    if (!cacheable(response)) {
      return;
    }
    const stored = new Response(response.body, response);
    // Cache API does not implement SWR. Retain the body for the stale window;
    // CACHED_AT enforces five-minute freshness, and clients get CACHE_CONTROL.
    stored.headers.set('Cache-Control', 'public, max-age=0, s-maxage=3900');
    stored.headers.set(CACHED_AT, String(Date.now()));
    stored.headers.delete('Server-Timing');
    stored.headers.delete('X-Edge-Cache');
    await cache.put(key, stored);
  } catch {
    // Cache failures must never fail a render or a background refresh.
  }
}

export async function withEdgeCache(
  context: APIContext,
  render: () => Promise<Response>
): Promise<EdgeCacheResult> {
  const { request, url } = context;
  const ctx = context.locals.cfContext;
  const pattern = context.routePattern ? context.routePattern.replace(/\/+$/, '') || '/' : '';
  const eligible =
    request.method === 'GET' &&
    publicPages.has(pattern) &&
    // The query-parameter allowlist is empty, including the agent view.
    !request.url.includes('?') &&
    !request.headers.has('Authorization') &&
    !request.headers.has('Cookie') &&
    ctx;
  if (!eligible) {
    const { result: response } = await runWithDegradedTracking(render);
    return { response, edgeCache: 'BYPASS' };
  }

  const key = `${url.origin}${url.pathname.replace(/\/+$/, '') || '/'}`;
  let cache: Cache | undefined;
  try {
    const defaultCache = (caches as CacheStorage & { default: Cache }).default;
    cache = defaultCache;
    const cached = await defaultCache.match(key);
    const cachedAt = Number(cached?.headers.get(CACHED_AT) ?? Number.NaN);
    const age = Date.now() - cachedAt;
    if (cached && cacheable(cached) && age >= 0 && age < RETENTION_MS) {
      const edgeCache = age < FRESH_MS ? 'HIT' : 'STALE';
      if (edgeCache === 'STALE') {
        ctx.waitUntil(
          runWithDegradedTracking(render)
            .then(({ result, degraded }) => {
              if (!degraded) {
                return store(defaultCache, key, result);
              }
            })
            .catch(() => undefined)
        );
      }
      const response = new Response(cached.body, cached);
      response.headers.set('Cache-Control', CACHE_CONTROL);
      response.headers.set('X-Edge-Cache', edgeCache);
      response.headers.delete(CACHED_AT);
      return { response, edgeCache };
    }
  } catch {
    // Missing Cache API, failed reads, or waitUntil failures fall back to SSR.
  }

  const renderStartedAt = Date.now();
  const { result: response, degraded } = await runWithDegradedTracking(render);
  const renderMs = Math.max(0, Date.now() - renderStartedAt);
  if (degraded || !cacheable(response)) {
    return { response, edgeCache: 'BYPASS' };
  }
  const result = new Response(response.body, response);
  result.headers.set('Cache-Control', CACHE_CONTROL);
  result.headers.set('X-Edge-Cache', 'MISS');
  try {
    if (cache) {
      ctx.waitUntil(store(cache, key, result.clone()));
    }
  } catch {
    // Scheduling a cache write is optional, just like the write itself.
  }
  return { response: result, edgeCache: 'MISS', renderMs };
}
