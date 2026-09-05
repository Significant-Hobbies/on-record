import { Hono } from 'hono';
import { cache } from 'hono/cache';
import { cors } from 'hono/cors';
import { publicCacheGeneration } from './db';
import type { Env } from './env';
import { adminRoute } from './routes/admin';
import { publicRoute } from './routes/public';

const app = new Hono<{ Bindings: Env }>();
const publicCors = cors({ origin: '*' });
const publicReferenceCache = cache({
  cacheControl: 'public, max-age=3600',
  cacheName: async (c) => `on-record-public-references-v2-${await publicCacheGeneration(c.env.DB)}`,
  onCacheNotAvailable: false,
});

app.use('*', async (c, next) => {
  const isAdminPath = c.req.path === '/admin' || c.req.path.startsWith('/admin/');
  if (!isAdminPath) {
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
