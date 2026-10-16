import type { Context, MiddlewareHandler } from 'hono';
import { publicCacheGeneration } from './db';
import type { Env } from './env';
import { probeFor, recordProbeDuration } from './onrecord51-probe';
import { publicRoute } from './routes/public';

// These are the five fixed, anonymous reads used by the homepage. Other API
// variants keep their ordinary per-colo response cache and publication gates.
const homeRequests = new Map([
  ['/api/stats', 'stats'],
  ['/api/people?limit=8', 'people'],
  ['/api/search', 'evidence'],
  ['/api/recommendation-groups?limit=8', 'groups'],
  ['/api/sources?limit=5', 'sources'],
]);
const maximumBytes = 256 * 1024;
const refreshAfterMs = 5 * 60 * 1000;
const maximumAgeMs = 24 * 60 * 60 * 1000;
// The outer per-colo Cache API must recheck R2 when its copy is due for
// refresh. Other public API variants keep their one-hour cache policy.
const homepageCacheControl = 'public, max-age=300';

function requestName(url: string): string | undefined {
  const parsed = new URL(url);
  return homeRequests.get(`${parsed.pathname}${parsed.search}`);
}

function objectKey(generation: number, name: string): string {
  return `public/homepage/v1/${generation}/${name}.json`;
}

type Snapshot = { text: string; capturedAt: Date; refresh: boolean };

async function readSnapshot(bucket: R2Bucket, key: string): Promise<Snapshot | undefined> {
  try {
    const object = await bucket.get(key);
    if (!object || object.size > maximumBytes) {
      return;
    }
    const capturedAt = object.uploaded;
    const age = Date.now() - capturedAt.getTime();
    if (!Number.isFinite(age) || age < 0 || age > maximumAgeMs) {
      return;
    }
    const text = await object.text();
    if (new TextEncoder().encode(text).byteLength > maximumBytes) {
      return;
    }
    JSON.parse(text);
    return { text, capturedAt, refresh: age >= refreshAfterMs };
  } catch {
    // A missing or malformed copy leaves the public route as the source.
  }
}

async function writeSnapshot(bucket: R2Bucket, key: string, response: Response): Promise<void> {
  if (
    response.status !== 200 ||
    !response.headers.get('content-type')?.includes('application/json') ||
    response.headers.has('set-cookie')
  ) {
    return;
  }
  const text = await response.text();
  if (new TextEncoder().encode(text).byteLength > maximumBytes) {
    return;
  }
  JSON.parse(text);
  await bucket.put(key, text, { httpMetadata: { contentType: 'application/json' } });
}

export const sharedHomepageCache: MiddlewareHandler<{ Bindings: Env }> = async (c, next) => {
  if (c.req.method !== 'GET' || c.req.header('authorization') || c.req.header('cookie')) {
    return next();
  }
  const name = requestName(c.req.url);
  if (!name) {
    return next();
  }

  // The same generation is used by the existing per-colo cache. A publish or
  // withdrawal changes it, making all older R2 snapshots unreachable.
  const probe = probeFor(c);
  const generationStartedAt = probe ? performance.now() : 0;
  const generation = await publicCacheGeneration(c.env.DB);
  recordProbeDuration(probe, 'sharedGenerationMs', generationStartedAt);
  const key = objectKey(generation, name);
  const r2StartedAt = probe ? performance.now() : 0;
  const snapshot = await readSnapshot(c.env.RAW, key);
  recordProbeDuration(probe, 'r2Ms', r2StartedAt);
  if (snapshot) {
    if (probe) {
      probe.sharedResult = snapshot.refresh ? 'STALE' : 'HIT';
    }
    if (snapshot.refresh) {
      try {
        const executionCtx = c.executionCtx;
        executionCtx.waitUntil(refreshSnapshot(c.env, generation, name).catch(() => undefined));
      } catch {
        // The bounded copy remains valid; a later request can refresh it.
      }
    }
    return new Response(snapshot.text, {
      headers: {
        'content-type': 'application/json; charset=UTF-8',
        'cache-control': homepageCacheControl,
        'x-shared-homepage-cache': snapshot.refresh ? 'STALE' : 'HIT',
        'x-shared-homepage-as-of': snapshot.capturedAt.toISOString(),
      },
    });
  }

  const handlerStartedAt = probe ? performance.now() : 0;
  await next();
  if (probe) {
    probe.handlerMs = performance.now() - handlerStartedAt;
    probe.sharedResult = 'MISS';
  }
  if (c.res.ok) {
    c.res.headers.set('cache-control', homepageCacheControl);
    try {
      const executionCtx = c.executionCtx;
      executionCtx.waitUntil(writeSnapshot(c.env.RAW, key, c.res.clone()).catch(() => undefined));
    } catch {
      // Tests and non-Worker runtimes may not provide waitUntil. The response
      // remains correct; the next request can fill the shared copy.
    }
    c.res.headers.set('x-shared-homepage-cache', 'MISS');
  }
};

/** Refresh the new generation after an admin publication change. */
export async function warmSharedHomepage(env: Env): Promise<void> {
  const generation = await publicCacheGeneration(env.DB);
  await Promise.all(
    [...homeRequests.values()].map((name) =>
      refreshSnapshot(env, generation, name).catch(() => undefined)
    )
  );
}

async function refreshSnapshot(env: Env, generation: number, name: string): Promise<void> {
  const path = [...homeRequests].find(([, candidate]) => candidate === name)?.[0];
  if (!path) {
    return;
  }
  const url = new URL(path, 'https://api.podcasts.highsignal.app');
  // Calling the public route directly applies the same quote, speaker,
  // trusted-show and source gates without another external network hop.
  const response = await publicRoute.request(
    `https://api.podcasts.highsignal.app${url.pathname.replace(/^\/api/, '')}${url.search}`,
    undefined,
    env
  );
  await writeSnapshot(env.RAW, objectKey(generation, name), response);
}

export function scheduleSharedHomepageWarm(c: Context<{ Bindings: Env }>): void {
  try {
    const executionCtx = c.executionCtx;
    executionCtx.waitUntil(warmSharedHomepage(c.env));
  } catch {
    // A missing background context cannot block an admin mutation. The
    // generation bump has already invalidated every old public response.
  }
}
