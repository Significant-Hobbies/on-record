import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { type ApiFetcher, apiGet } from '../src/lib/api';
import { withEdgeCache } from '../src/lib/edge-cache';

const NOW = 1_800_000_000_000;
const POLICY = 'public, max-age=0, s-maxage=300, stale-while-revalidate=3600';
const html = (body = 'rendered', init: ResponseInit = {}) =>
  new Response(body, {
    ...init,
    headers: { 'Content-Type': 'text/html; charset=utf-8', ...init.headers },
  });

function setup(
  path = '/',
  options: { method?: string; headers?: HeadersInit; pattern?: string } = {}
) {
  const scheduled: Promise<unknown>[] = [];
  const request = new Request(`https://podcasts.highsignal.app${path}`, options);
  const context = {
    request,
    url: new URL(request.url),
    routePattern: options.pattern ?? '/',
    locals: { cfContext: { waitUntil: (promise: Promise<unknown>) => scheduled.push(promise) } },
  } as Parameters<typeof withEdgeCache>[0];
  const entries = new Map<string, Response>();
  const match = vi.fn(async (key: string) => entries.get(key)?.clone());
  const put = vi.fn(async (key: string, response: Response) => {
    entries.set(key, response);
  });
  vi.stubGlobal('caches', { default: { match, put } });
  const render = vi.fn(async () => html());
  return { context, scheduled, entries, match, put, render };
}

function apiRender(fetch: ApiFetcher['fetch']) {
  return async () => {
    try {
      const { body } = await apiGet<{ body: string }>('/api/search', { API: { fetch } });
      return html(body);
    } catch {
      return html('temporarily unavailable', { headers: { 'Cache-Control': 'no-store' } });
    }
  };
}

beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(NOW);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('public HTML edge cache', () => {
  it.each([
    ['/', '/'],
    ['/people', '/people'],
    ['/sources', '/sources'],
    ['/search', '/search'],
    ['/recommendations', '/recommendations'],
    ['/claims/123', '/claims/[id]'],
    ['/people/jane', '/people/[slug]'],
    ['/sources/123', '/sources/[id]'],
  ])('does not cache degraded HTTP 200 HTML at %s', async (path, pattern) => {
    const { context, scheduled, entries, put } = setup(path, { pattern });
    const render = apiRender(async () => new Response(null, { status: 503 }));
    const result = await withEdgeCache(context, render);
    expect(result.edgeCache).toBe('BYPASS');
    expect(result.response.status).toBe(200);
    expect(result.response.headers.get('Cache-Control')).toBe('no-store');
    expect(result.response.headers.has('X-Edge-Cache')).toBe(false);
    await expect(result.response.text()).resolves.toBe('temporarily unavailable');
    await Promise.all(scheduled);
    expect(put).not.toHaveBeenCalled();
    expect(entries.size).toBe(0);
  });

  it('keeps serving healthy stale HTML when a refresh catches an API failure', async () => {
    const { context, entries, scheduled, put } = setup();
    const stale = html('healthy');
    const cachedAt = String(NOW - 300_000);
    stale.headers.set('X-Edge-Cached-At', cachedAt);
    entries.set(context.request.url, stale);
    const render = apiRender(async () => {
      await Promise.resolve();
      throw new Error('API unavailable');
    });
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const result = await withEdgeCache(context, render);
      expect(result.edgeCache).toBe('STALE');
      await expect(result.response.text()).resolves.toBe('healthy');
      await Promise.all(scheduled);
      expect(entries.get(context.request.url)).toBe(stale);
      expect(stale.headers.get('X-Edge-Cached-At')).toBe(cachedAt);
    }
    expect(put).not.toHaveBeenCalled();
  });

  it('caches the next healthy render after an API failure', async () => {
    const { context, scheduled, put } = setup();
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('API unavailable'))
      .mockResolvedValue(Response.json({ body: 'recovered' }));
    const render = apiRender(fetch);
    expect((await withEdgeCache(context, render)).edgeCache).toBe('BYPASS');
    const recovered = await withEdgeCache(context, render);
    expect(recovered.edgeCache).toBe('MISS');
    expect(recovered.response.headers.get('Cache-Control')).toBe(POLICY);
    await Promise.all(scheduled);
    expect(put).toHaveBeenCalledTimes(1);
    const hit = await withEdgeCache(context, render);
    expect(hit.edgeCache).toBe('HIT');
    await expect(hit.response.text()).resolves.toBe('recovered');
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('stores a MISS in waitUntil and serves a HIT without rendering', async () => {
    const { context, scheduled, match, put, render } = setup();
    const miss = await withEdgeCache(context, render);
    expect(miss).toMatchObject({ edgeCache: 'MISS', renderMs: 0 });
    expect(miss.response.headers.get('X-Edge-Cache')).toBe('MISS');
    expect(miss.response.headers.get('Cache-Control')).toBe(POLICY);
    expect(scheduled).toHaveLength(1);
    await Promise.all(scheduled);
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.calls[0][1].headers.get('Cache-Control')).toBe(
      'public, max-age=0, s-maxage=3900'
    );
    const hit = await withEdgeCache(context, render);
    expect(hit.edgeCache).toBe('HIT');
    expect(hit.renderMs).toBeUndefined();
    expect(hit.response.headers.get('X-Edge-Cache')).toBe('HIT');
    expect(hit.response.headers.get('Cache-Control')).toBe(POLICY);
    expect(hit.response.headers.has('X-Edge-Cached-At')).toBe(false);
    await expect(hit.response.text()).resolves.toBe('rendered');
    expect(render).toHaveBeenCalledTimes(1);
    expect(match).toHaveBeenCalledWith('https://podcasts.highsignal.app/');
  });

  it('serves STALE immediately and refreshes through waitUntil', async () => {
    const { context, entries, scheduled, render } = setup();
    const stale = html('old');
    stale.headers.set('X-Edge-Cached-At', String(NOW - 300_000));
    entries.set(context.request.url, stale);
    let finish: (response: Response) => void = () => {
      throw new Error('refresh has not started');
    };
    render.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        })
    );
    const result = await withEdgeCache(context, render);
    expect(result.edgeCache).toBe('STALE');
    expect(result.renderMs).toBeUndefined();
    expect(result.response.headers.get('X-Edge-Cache')).toBe('STALE');
    await expect(result.response.text()).resolves.toBe('old');
    expect(scheduled).toHaveLength(1);
    finish(html('new'));
    await Promise.all(scheduled);
    const hit = await withEdgeCache(context, render);
    expect(hit.edgeCache).toBe('HIT');
    await expect(hit.response.text()).resolves.toBe('new');
  });

  it.each([3_900_000, -1])('renders again outside the retained age window: %s', async (age) => {
    const { context, entries, render } = setup();
    const cached = html('expired');
    cached.headers.set('X-Edge-Cached-At', String(NOW - age));
    entries.set(context.request.url, cached);
    expect((await withEdgeCache(context, render)).edgeCache).toBe('MISS');
    expect(render).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['/?q=private', {}],
    ['/?mode=agent', {}],
    ['/?', {}],
    ['/', { headers: { Cookie: '' } }],
    ['/', { headers: { Authorization: 'Bearer private' } }],
    ['/', { method: 'HEAD' }],
    ['/', { method: 'POST' }],
    ['/admin', { pattern: '/admin' }],
    ['/missing', { pattern: '/404' }],
  ])('bypasses ineligible request %s %j', async (path, options) => {
    const { context, match, put, render } = setup(path, options);
    const result = await withEdgeCache(context, render);
    expect(result.edgeCache).toBe('BYPASS');
    expect(match).not.toHaveBeenCalled();
    expect(put).not.toHaveBeenCalled();
    expect(render).toHaveBeenCalledTimes(1);
  });

  it.each([
    { status: 404 },
    { status: 500 },
    { status: 302 },
    { headers: { 'Set-Cookie': 'session=private' } },
    { headers: { Vary: 'Cookie' } },
    { headers: { Vary: 'Accept-Encoding, Accept' } },
    { headers: { Vary: '*' } },
    { headers: { 'Content-Type': 'application/json' } },
  ])('never stores unsafe response %j', async (init) => {
    const { context, put, render } = setup();
    render.mockResolvedValue(html('unsafe', init));
    const result = await withEdgeCache(context, render);
    expect(result.edgeCache).toBe('BYPASS');
    expect(result.response.headers.has('X-Edge-Cache')).toBe(false);
    expect(put).not.toHaveBeenCalled();
  });

  it('accepts Vary: Accept-Encoding and normalizes trailing slash keys', async () => {
    const { context, match, put, render, scheduled } = setup('/people/jane/', {
      pattern: '/people/[slug]/',
    });
    render.mockResolvedValue(html('public', { headers: { Vary: 'Accept-Encoding' } }));
    await withEdgeCache(context, render);
    await Promise.all(scheduled);
    expect(match).toHaveBeenCalledWith('https://podcasts.highsignal.app/people/jane');
    expect(put.mock.calls[0][0]).toBe('https://podcasts.highsignal.app/people/jane');
    const unslashed = { ...context, url: new URL('https://podcasts.highsignal.app/people/jane') };
    expect((await withEdgeCache(unslashed, render)).edgeCache).toBe('HIT');
  });

  it.each(['match', 'put', 'missing', 'schedule'])(
    'falls back safely on cache failure: %s',
    async (failure) => {
      const { context, scheduled, match, put, render } = setup();
      if (failure === 'match') {
        match.mockRejectedValue(new Error('read failed'));
      }
      if (failure === 'put') {
        put.mockRejectedValue(new Error('write failed'));
      }
      if (failure === 'missing') {
        vi.stubGlobal('caches', undefined);
      }
      if (failure === 'schedule') {
        context.locals.cfContext.waitUntil = () => {
          throw new Error('schedule failed');
        };
      }
      const result = await withEdgeCache(context, render);
      await expect(result.response.text()).resolves.toBe('rendered');
      await expect(Promise.all(scheduled)).resolves.toBeDefined();
      expect(render).toHaveBeenCalledTimes(1);
    }
  );

  it.each(['error', 'cookie', 'status'])(
    'keeps stale body when refresh is unsafe: %s',
    async (failure) => {
      const { context, entries, scheduled, render, put } = setup();
      const stale = html('old');
      stale.headers.set('X-Edge-Cached-At', String(NOW - 301_000));
      entries.set(context.request.url, stale);
      if (failure === 'error') {
        render.mockRejectedValue(new Error('render failed'));
      } else {
        render.mockResolvedValue(
          html(
            'unsafe',
            failure === 'cookie' ? { headers: { 'Set-Cookie': 'private=1' } } : { status: 500 }
          )
        );
      }
      const result = await withEdgeCache(context, render);
      await expect(result.response.text()).resolves.toBe('old');
      await Promise.all(scheduled);
      expect(put).not.toHaveBeenCalled();
    }
  );

  it('propagates render failures without storing them', async () => {
    const { context, render, put } = setup();
    render.mockRejectedValue(new Error('render failed'));
    await expect(withEdgeCache(context, render)).rejects.toThrow('render failed');
    expect(put).not.toHaveBeenCalled();
  });
});
