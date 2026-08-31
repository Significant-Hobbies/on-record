import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
});

describe('public reference response cache', () => {
  it('serves a cached stats response before querying D1', async () => {
    const cached = Response.json({ cached: true });
    const match = vi.fn(async () => cached);
    const open = vi.fn(async () => ({ match, put: vi.fn() }));
    vi.stubGlobal('caches', { open });

    const { default: app } = await import('./index');
    const response = await app.request('https://api.podcasts.highsignal.app/api/stats');

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ cached: true });
    expect(open).toHaveBeenCalledWith('on-record-public-references-v1');
    expect(match).toHaveBeenCalledWith('https://api.podcasts.highsignal.app/api/stats');
  });

  it('does not put admin routes behind the public cache', async () => {
    const open = vi.fn();
    vi.stubGlobal('caches', { open });

    const { default: app } = await import('./index');
    const response = await app.request('https://api.podcasts.highsignal.app/admin');

    expect(response.status).not.toBe(200);
    expect(open).not.toHaveBeenCalled();
  });
});
