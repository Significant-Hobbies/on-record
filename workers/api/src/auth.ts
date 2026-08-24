import type { Context, Next } from 'hono';
import type { Env } from './env';

export async function requireAdmin(c: Context<{ Bindings: Env }>, next: Next) {
  const token = c.env.ADMIN_TOKEN;
  if (!token) {
    return c.json({ error: 'admin_disabled' }, 503);
  }
  const auth = c.req.header('Authorization') ?? '';
  if (auth !== `Bearer ${token}`) {
    return c.json({ error: 'unauthorized' }, 401);
  }
  await next();
}
