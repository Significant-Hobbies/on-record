import { Hono, type Context } from 'hono';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Env } from './env';
import { publicRoute } from './routes/public';

const { generation } = vi.hoisted(() => ({ generation: vi.fn(async () => 1) }));
vi.mock('./db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./db')>();
  return { ...actual, publicCacheGeneration: generation };
});

const { sharedHomepageCache, warmSharedHomepage } = await import('./shared-homepage-cache');

function fixture(status: 200 | 503 = 200) {
  const objects = new Map<string, string>();
  const uploaded = new Map<string, Date>();
  const get = vi.fn(async (key: string) => {
    const value = objects.get(key);
    return value === undefined
      ? null
      : { size: value.length, uploaded: uploaded.get(key) ?? new Date(), text: async () => value };
  });
  const put = vi.fn(async (key: string, value: string) => {
    objects.set(key, value);
    uploaded.set(key, new Date());
  });
  const env = { DB: {}, RAW: { get, put } } as unknown as Env;
  const waits: Promise<unknown>[] = [];
  const executionCtx = {
    waitUntil: (promise: Promise<unknown>) => {
      waits.push(promise);
    },
  } as unknown as ExecutionContext;
  const app = new Hono<{ Bindings: Env }>();
  const handler = vi.fn((c: Context) => c.json({ count: 7 }, status));
  app.use('*', sharedHomepageCache);
  app.get('/api/stats', handler);
  app.get('/api/people', handler);
  const request = (path: string, init?: RequestInit) =>
    app.request(`https://api.podcasts.highsignal.app${path}`, init, env, executionCtx);
  return { objects, uploaded, get, put, env, waits, handler, request };
}

afterEach(() => {
  generation.mockReset().mockResolvedValue(1);
  vi.restoreAllMocks();
});

describe('shared homepage cache', () => {
  it('fills one fixed public response on a miss and serves it to a cold colo', async () => {
    const { objects, put, waits, handler, request } = fixture();
    const first = await request('/api/stats');
    expect(first.headers.get('x-shared-homepage-cache')).toBe('MISS');
    await Promise.all(waits);
    expect(objects.get('public/homepage/v1/1/stats.json')).toBe('{"count":7}');
    expect(put).toHaveBeenCalledTimes(1);

    const second = await request('/api/stats');
    expect(second.headers.get('x-shared-homepage-cache')).toBe('HIT');
    await expect(second.json()).resolves.toEqual({ count: 7 });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('never serves an old generation after publication or withdrawal', async () => {
    const { objects, handler, waits, request } = fixture();
    objects.set('public/homepage/v1/1/stats.json', '{"count":1}');
    generation.mockResolvedValue(2);

    const response = await request('/api/stats');
    expect(response.headers.get('x-shared-homepage-cache')).toBe('MISS');
    await expect(response.json()).resolves.toEqual({ count: 7 });
    await Promise.all(waits);
    expect(objects.get('public/homepage/v1/2/stats.json')).toBe('{"count":7}');
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('falls back from a malformed shared copy, and ignores unrelated URL variants', async () => {
    const { objects, get, waits, handler, request } = fixture();
    objects.set('public/homepage/v1/1/stats.json', 'not JSON');
    const repaired = await request('/api/stats');
    expect(repaired.headers.get('x-shared-homepage-cache')).toBe('MISS');
    await Promise.all(waits);
    expect(objects.get('public/homepage/v1/1/stats.json')).toBe('{"count":7}');

    await request('/api/people?limit=7');
    expect(handler).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('serves a dated copy while refreshing it, but refuses one older than 24 hours', async () => {
    const { objects, uploaded, put, waits, handler, request } = fixture();
    const key = 'public/homepage/v1/1/stats.json';
    objects.set(key, '{"count":6}');
    uploaded.set(key, new Date(Date.now() - 6 * 60 * 1000));
    vi.spyOn(publicRoute, 'request').mockImplementation(async () => Response.json({ count: 7 }));

    const stale = await request('/api/stats');
    expect(stale.headers.get('x-shared-homepage-cache')).toBe('STALE');
    expect(stale.headers.get('x-shared-homepage-as-of')).toBe(uploaded.get(key)?.toISOString());
    await expect(stale.json()).resolves.toEqual({ count: 6 });
    await Promise.all(waits);
    expect(objects.get(key)).toBe('{"count":7}');
    expect(put).toHaveBeenCalledTimes(1);
    expect(handler).not.toHaveBeenCalled();

    uploaded.set(key, new Date(Date.now() - 25 * 60 * 60 * 1000));
    const expired = await request('/api/stats');
    expect(expired.headers.get('x-shared-homepage-cache')).toBe('MISS');
    await expect(expired.json()).resolves.toEqual({ count: 7 });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('does not publish genuine errors as a shared success', async () => {
    const { objects, put, waits, request } = fixture(503);
    const response = await request('/api/stats');
    expect(response.status).toBe(503);
    expect(objects.size).toBe(0);
    expect(put).not.toHaveBeenCalled();
    expect(waits).toHaveLength(0);
  });

  it('does not share a request carrying authorization or cookies', async () => {
    const { objects, get, request } = fixture();
    await request('/api/stats', { headers: { authorization: 'synthetic' } });
    await request('/api/stats', { headers: { cookie: 'synthetic=1' } });
    expect(get).not.toHaveBeenCalled();
    expect(objects.size).toBe(0);
  });

  it('prewarms the exact five public routes in the current generation', async () => {
    const { env, objects } = fixture();
    vi.spyOn(publicRoute, 'request').mockImplementation(async () => Response.json({ count: 7 }));
    generation.mockResolvedValue(9);
    await warmSharedHomepage(env);
    expect(objects.size).toBe(5);
    expect(objects.get('public/homepage/v1/9/stats.json')).toBe('{"count":7}');
    expect(objects.get('public/homepage/v1/9/evidence.json')).toBe('{"count":7}');
  });
});
