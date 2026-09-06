import { Hono } from 'hono';
import { cache } from 'hono/cache';
import { cors } from 'hono/cors';
import { publicCacheGeneration } from './db';
import type { Env } from './env';
import { adminRoute } from './routes/admin';
import { publicRoute } from './routes/public';
import { anchorFor, D1_BOOKMARK_HEADER, envWithSession, openSession } from './session';

const app = new Hono<{ Bindings: Env }>();
const publicCors = cors({ origin: '*', exposeHeaders: [D1_BOOKMARK_HEADER] });
const publicReferenceCache = cache({
  cacheControl: 'public, max-age=3600',
  cacheName: async (c) => `on-record-public-references-v2-${await publicCacheGeneration(c.env.DB)}`,
  onCacheNotAvailable: false,
});

const isAdminPath = (path: string) => path === '/admin' || path.startsWith('/admin/');

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
