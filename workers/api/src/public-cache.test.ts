import { afterEach, describe, expect, it, vi } from 'vitest';

const { publicCacheGeneration } = vi.hoisted(() => ({
  publicCacheGeneration: vi.fn(async () => 1),
}));

// The cacheName function reads c.env.DB before the middleware even checks
// for a cache hit, so every request needs an env even though this stub of
// publicCacheGeneration never actually touches it.
const FAKE_ENV = { DB: {} } as unknown as import('./env').Env;

vi.mock('./db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./db')>();
  return { ...actual, publicCacheGeneration };
});

afterEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
  publicCacheGeneration.mockReset().mockResolvedValue(1);
});

describe('public reference response cache', () => {
  it('serves a cached stats response before querying D1', async () => {
    const cached = Response.json({ cached: true });
    const match = vi.fn(async () => cached);
    const open = vi.fn(async () => ({ match, put: vi.fn() }));
    vi.stubGlobal('caches', { open });

    const { default: app } = await import('./index');
    const response = await app.request(
      'https://api.podcasts.highsignal.app/api/stats',
      undefined,
      FAKE_ENV
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ cached: true });
    expect(open).toHaveBeenCalledWith('on-record-public-references-v2-1');
    expect(match).toHaveBeenCalledWith('https://api.podcasts.highsignal.app/api/stats');
  });

  it('does not put admin routes behind the public cache', async () => {
    const open = vi.fn();
    vi.stubGlobal('caches', { open });

    const { default: app } = await import('./index');
    const response = await app.request(
      'https://api.podcasts.highsignal.app/admin',
      undefined,
      FAKE_ENV
    );

    expect(response.status).not.toBe(200);
    expect(open).not.toHaveBeenCalled();
  });

  it.each([
    ['/api/people', 'https://api.podcasts.highsignal.app/api/people'],
    ['/api/people/:slug', 'https://api.podcasts.highsignal.app/api/people/jane-doe'],
    ['/api/sources', 'https://api.podcasts.highsignal.app/api/sources'],
    ['/api/search', 'https://api.podcasts.highsignal.app/api/search?q=test'],
    ['/api/topics/:slug', 'https://api.podcasts.highsignal.app/api/topics/politics'],
  ])('serves a cached response for %s before querying D1', async (_label, url) => {
    const cached = Response.json({ cached: true });
    const match = vi.fn(async () => cached);
    const open = vi.fn(async () => ({ match, put: vi.fn() }));
    vi.stubGlobal('caches', { open });

    const { default: app } = await import('./index');
    const response = await app.request(url, undefined, FAKE_ENV);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ cached: true });
    expect(open).toHaveBeenCalledWith('on-record-public-references-v2-1');
    expect(match).toHaveBeenCalledWith(url);
  });

  it('embeds the current generation in the cache name so a bump busts every cached URL at once', async () => {
    publicCacheGeneration.mockResolvedValue(42);
    const cached = Response.json({ cached: true });
    const match = vi.fn(async () => cached);
    const open = vi.fn(async () => ({ match, put: vi.fn() }));
    vi.stubGlobal('caches', { open });

    const { default: app } = await import('./index');
    await app.request('https://api.podcasts.highsignal.app/api/stats', undefined, FAKE_ENV);

    expect(open).toHaveBeenCalledWith('on-record-public-references-v2-42');
  });
});
