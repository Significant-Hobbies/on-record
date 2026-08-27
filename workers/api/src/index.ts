import { Hono } from 'hono';
import { cors } from 'hono/cors';
import type { Env } from './env';
import { adminRoute } from './routes/admin';
import { publicRoute } from './routes/public';

const app = new Hono<{ Bindings: Env }>();
const publicCors = cors({ origin: '*' });

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
