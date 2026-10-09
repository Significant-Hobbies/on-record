import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { onRequest } from '../src/middleware';

const { env } = vi.hoisted(() => ({ env: {} as Record<string, string> }));
vi.mock('../src/lib/runtime', () => ({ runtimeEnv: () => env }));
vi.mock('astro:middleware', () => ({ defineMiddleware: (handler: unknown) => handler }));

beforeEach(() => {
  env.APP_HEALTH_INGEST_KEY = 'test-key';
  env.APP_HEALTH_STAGE_SAMPLE_RATE = '1';
  vi.spyOn(Date, 'now').mockReturnValue(1_800_000_000_000);
});
afterEach(() => {
  for (const key of Object.keys(env)) {
    delete env[key];
  }
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function setup(path = '/', pattern = '/') {
  const scheduled: Promise<unknown>[] = [];
  const request = new Request(`https://podcasts.highsignal.app${path}`);
  const context = {
    request,
    url: new URL(request.url),
    routePattern: pattern,
    locals: { cfContext: { waitUntil: (promise: Promise<unknown>) => scheduled.push(promise) } },
  } as Parameters<typeof onRequest>[0];
  const entries = new Map<string, Response>();
  const put = vi.fn(async (key: string, response: Response) => {
    entries.set(key, response);
  });
  vi.stubGlobal('caches', {
    default: { match: async (key: string) => entries.get(key)?.clone(), put },
  });
  const fetch = vi.fn(
    async (_url: string, _init: RequestInit) => new Response(null, { status: 202 })
  );
  vi.stubGlobal('fetch', fetch);
  const next = vi.fn(
    async () => new Response('HTML', { headers: { 'Content-Type': 'text/html' } })
  );
  return { context, entries, scheduled, fetch, next, put };
}

describe('HTML middleware integration', () => {
  it('reports MISS and HIT timings while preserving discovery and existing telemetry', async () => {
    const { context, next, fetch, scheduled } = setup();
    const miss = (await onRequest(context, next)) as Response;
    expect(miss.headers.get('Server-Timing')).toBe('total;dur=0, render;dur=0, cache;desc="MISS"');
    expect(miss.headers.get('Link')).toContain('</index.md>; rel="alternate"');
    await Promise.all(scheduled);
    const hit = (await onRequest(context, next)) as Response;
    expect(hit.headers.get('Server-Timing')).toBe('total;dur=0, cache;desc="HIT"');
    expect(hit.headers.get('Link')).toContain('</sitemap.xml>; rel="sitemap"');
    expect(next).toHaveBeenCalledTimes(1);
    await Promise.all(scheduled);
    const endpointCalls = fetch.mock.calls.filter(([url]) => url.endsWith('/v1/ingest'));
    const stageCalls = fetch.mock.calls.filter(([url]) => url.endsWith('/v1/logs'));
    expect(endpointCalls).toHaveLength(2);
    expect(stageCalls).toHaveLength(2);
    expect(JSON.parse(String(endpointCalls[1][1].body)).events[0]).toMatchObject({
      method: 'GET',
      route: '/',
      status_code: 200,
      duration_ms: 0,
    });
    expect(JSON.parse(String(stageCalls[1][1].body)).logs[0].props.edge_cache).toBe('HIT');
  });

  it('reports STALE without foreground render timing', async () => {
    const { context, entries, next, scheduled } = setup();
    const old = new Response('old HTML', {
      headers: { 'Content-Type': 'text/html', 'X-Edge-Cached-At': String(Date.now() - 300_000) },
    });
    entries.set(context.request.url, old);
    const response = (await onRequest(context, next)) as Response;
    expect(response.headers.get('Server-Timing')).toBe('total;dur=0, cache;desc="STALE"');
    await expect(response.text()).resolves.toBe('old HTML');
    await Promise.all(scheduled);
  });

  it('times bypassed HTML using only the route template in both telemetry formats', async () => {
    const { context, next, scheduled, fetch, put } = setup(
      '/people/private-person?q=secret',
      '/people/[slug]'
    );
    const response = (await onRequest(context, next)) as Response;
    expect(response.headers.get('Server-Timing')).toBe('total;dur=0, cache;desc="BYPASS"');
    expect(put).not.toHaveBeenCalled();
    await Promise.all(scheduled);
    expect(fetch).toHaveBeenCalledTimes(2);
    for (const [, init] of fetch.mock.calls) {
      expect(String(init.body)).toContain('/people/:param');
      expect(String(init.body)).not.toContain('private-person');
      expect(String(init.body)).not.toContain('secret');
    }
  });

  it('times non-200 HTML without caching it', async () => {
    const { context, next, put, scheduled } = setup();
    next.mockResolvedValue(
      new Response('error', { status: 500, headers: { 'Content-Type': 'text/html' } })
    );
    const response = (await onRequest(context, next)) as Response;
    expect(response.status).toBe(500);
    expect(response.headers.get('Server-Timing')).toBe('total;dur=0, cache;desc="BYPASS"');
    expect(put).not.toHaveBeenCalled();
    await Promise.all(scheduled);
  });

  it('leaves the query-selected agent JSON view intact', async () => {
    const { context, next, put, fetch } = setup('/?mode=agent');
    const response = (await onRequest(context, next)) as Response;
    expect(response.headers.get('Content-Type')).toContain('application/json');
    expect(response.headers.has('Server-Timing')).toBe(false);
    await expect(response.json()).resolves.toMatchObject({ name: 'High Signal Podcasts' });
    expect(next).not.toHaveBeenCalled();
    expect(put).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not send stage logs or HTML timing for non-HTML endpoints', async () => {
    const { context, next, fetch, scheduled } = setup('/openapi.json', '/openapi.json');
    next.mockResolvedValue(Response.json({ ok: true }));
    const response = (await onRequest(context, next)) as Response;
    expect(response.headers.has('Server-Timing')).toBe(false);
    await Promise.all(scheduled);
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      'https://ingest.sassmaker.com/v1/ingest',
    ]);
  });
});
