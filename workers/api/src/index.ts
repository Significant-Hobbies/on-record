import { Hono } from 'hono';
import { cache } from 'hono/cache';
import { cors } from 'hono/cors';
import { publicCacheGeneration } from './db';
import type { Env } from './env';
import { adminRoute } from './routes/admin';
import { publicRoute } from './routes/public';
import { anchorFor, D1_BOOKMARK_HEADER, envWithSession, openSession } from './session';
import { endpointTelemetryMiddleware } from './telemetry';

const app = new Hono<{ Bindings: Env }>();
const publicCors = cors({ origin: '*', exposeHeaders: [D1_BOOKMARK_HEADER] });
type PublicCacheTrace = { generationMs?: number; handlerMs?: number };
const publicCacheTraces = new WeakMap<object, PublicCacheTrace>();
const DIAGNOSTIC_HEADER = 'x-onrecord-diagnostic';
const publicReferenceCache = cache({
  cacheControl: 'public, max-age=3600',
  cacheName: async (c) => {
    const trace = publicCacheTraces.get(c);
    const startedAt = trace ? performance.now() : 0;
    const generation = await publicCacheGeneration(c.env.DB);
    if (trace) {
      trace.generationMs = performance.now() - startedAt;
    }
    return `on-record-public-references-v2-${generation}`;
  },
  onCacheNotAvailable: false,
});

const isAdminPath = (path: string) => path === '/admin' || path.startsWith('/admin/');

// Collection is limited to matched public API routes. Root, health, admin,
// and unmatched requests stay out of endpoint telemetry.
app.use('/api/*', endpointTelemetryMiddleware);

// This has to be the first middleware registered: the response cache below
// reads the generation out of D1 while building its cache key, before it even
// looks for a hit, and that read should go through the session like every
// other one. See session.ts for why public reads are unconstrained and admin
// reads are anchored to the primary.
app.use('*', async (c, next) => {
  // `c.env` is absent on routes reached without bindings at all (the 404
  // fallback, and the tests that exercise it), so this must not assume one.
  const session = openSession(
    c.env?.DB,
    anchorFor(c.req.header(D1_BOOKMARK_HEADER), isAdminPath(c.req.path))
  );
  if (session) {
    c.env = envWithSession(c.env, session);
  }
  await next();
  // A request that answered entirely from cache runs no query and has no
  // bookmark to report. Header writes are guarded because a response handed
  // back by the Cache API is not guaranteed to be mutable, and a missing
  // bookmark header is never worth failing a served response over.
  const bookmark = session?.getBookmark();
  if (bookmark) {
    try {
      c.res.headers.set(D1_BOOKMARK_HEADER, bookmark);
    } catch {
      // immutable response headers - nothing to do
    }
  }
});

app.use('*', async (c, next) => {
  if (!isAdminPath(c.req.path)) {
    return publicCors(c, next);
  }
  if (c.req.method === 'OPTIONS') {
    return c.json({ error: 'cors_not_allowed' }, 403);
  }
  return next();
});

// A bounded, header-only measurement path for issue #51. The normal public
// request path has no extra work or headers. This reports durations, never
// URLs, claims, bookmarks, or response bodies.
app.use('/api/*', async (c, next) => {
  if (c.req.header(DIAGNOSTIC_HEADER) !== 'onrecord-51') {
    return next();
  }
  const trace: PublicCacheTrace = {};
  publicCacheTraces.set(c, trace);
  const startedAt = performance.now();
  await next();
  if (trace.generationMs === undefined) {
    return;
  }
  const totalMs = performance.now() - startedAt;
  const handlerMs = trace.handlerMs ?? 0;
  const middlewareMs = Math.max(0, totalMs - trace.generationMs - handlerMs);
  c.header(
    'Server-Timing',
    `cache;desc="${trace.handlerMs === undefined ? 'HIT' : 'MISS'}", generation;dur=${trace.generationMs.toFixed(1)}, handler;dur=${handlerMs.toFixed(1)}, middleware;dur=${middlewareMs.toFixed(1)}, total;dur=${totalMs.toFixed(1)}`
  );
});

// These public routes all fan into the bounded reference listing. The corpus
// changes in release batches (daily ingest cron, ad hoc review-queue publish),
// not every 5 minutes, while the same anonymous URLs are requested repeatedly
// by the SSR site and API clients. The TTL is long enough to skip the
// six-table join on almost every request; the publish/unpublish paths in
// admin.ts and admin-claims.ts call bumpPublicCacheGeneration() so a new
// claim going live still busts the cache immediately instead of waiting out
// the TTL.
app.use('/api/stats', publicReferenceCache);
app.use('/api/recommendations', publicReferenceCache);
app.use('/api/recommendation-groups', publicReferenceCache);
app.use('/api/people', publicReferenceCache);
app.use('/api/people/*', publicReferenceCache);
app.use('/api/sources', publicReferenceCache);
app.use('/api/search', publicReferenceCache);
app.use('/api/topics/*', publicReferenceCache);

app.use('/api/*', async (c, next) => {
  const trace = publicCacheTraces.get(c);
  if (!trace || trace.generationMs === undefined) {
    return next();
  }
  const startedAt = performance.now();
  await next();
  trace.handlerMs = performance.now() - startedAt;
  // Diagnostic URLs use a unique probe key, and must not populate a cache.
  c.header('Cache-Control', 'no-store');
});

app.get('/', (c) => c.json({ env: c.env.ENVIRONMENT ?? 'unknown', name: 'on-record-api' }));
app.get('/health', (c) => c.json({ ok: true, ts: Date.now() }));
app.route('/api', publicRoute);
app.route('/admin', adminRoute);

app.notFound((c) =>
  c.json(
    {
      error: 'not_found',
      message: 'No public API route matches this request.',
      resolution:
        'Use https://podcasts.highsignal.app/openapi.json for supported read-only routes.',
    },
    404
  )
);

app.onError((err, c) => {
  console.error(`[error] ${c.req.method} ${c.req.path}:`, err.message);
  return c.json({ error: 'Internal Server Error' }, 500);
});

export default app;
