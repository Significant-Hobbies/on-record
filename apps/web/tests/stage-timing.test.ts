import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { observeStageTiming } from '../src/lib/stage-timing';

const { env } = vi.hoisted(() => ({ env: {} as Record<string, string | undefined> }));
vi.mock('../src/lib/runtime', () => ({ runtimeEnv: () => env }));

function setup(pattern = '/people/[slug]', colo: unknown = 'BOM') {
  const scheduled: Promise<unknown>[] = [];
  const request = new Request('https://podcasts.highsignal.app/people/private-name?q=secret');
  Object.defineProperty(request, 'cf', { value: { colo }, configurable: true });
  const context = {
    request,
    routePattern: pattern,
    locals: { cfContext: { waitUntil: (promise: Promise<unknown>) => scheduled.push(promise) } },
  } as Parameters<typeof observeStageTiming>[0];
  const fetch = vi.fn(
    async (_url: string, _init: RequestInit) => new Response(null, { status: 202 })
  );
  vi.stubGlobal('fetch', fetch);
  return { context, scheduled, fetch };
}

beforeEach(() => {
  env.APP_HEALTH_INGEST_KEY = 'test-key';
  env.APP_HEALTH_STAGE_SAMPLE_RATE = '1';
});
afterEach(() => {
  for (const key of Object.keys(env)) {
    delete env[key];
  }
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('fleet stage timing logs', () => {
  it('sends one template-only debug log with MISS render timing through waitUntil', async () => {
    const { context, scheduled, fetch } = setup();
    observeStageTiming(
      context,
      { response: new Response('html'), edgeCache: 'MISS', renderMs: 12 },
      25
    );
    expect(scheduled).toHaveLength(1);
    await Promise.all(scheduled);
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('https://ingest.sassmaker.com/v1/logs');
    expect(init.headers).toEqual({
      'content-type': 'application/json',
      authorization: 'Bearer test-key',
    });
    const batch = JSON.parse(String(init.body));
    expect(batch).toEqual({
      schema_version: 'v1',
      batch_id: expect.any(String),
      logs: [
        {
          log_id: expect.any(String),
          timestamp: expect.any(Number),
          event: 'api.stage_timing',
          level: 'debug',
          props: {
            route: '/people/:param',
            status: 200,
            total_ms: 25,
            edge_cache: 'MISS',
            inner_cache: 'NONE',
            colo: 'BOM',
            render_ms: 12,
          },
        },
      ],
    });
    expect(String(init.body)).not.toContain('private-name');
    expect(String(init.body)).not.toContain('secret');
    expect(String(init.body)).not.toContain('?');
  });

  it.each(['HIT', 'STALE', 'BYPASS'] as const)('omits render timing for %s', async (edgeCache) => {
    const { context, scheduled, fetch } = setup('/claims/[id]');
    observeStageTiming(
      context,
      { response: new Response(null, { status: 404 }), edgeCache, renderMs: 4 },
      9
    );
    await Promise.all(scheduled);
    const props = JSON.parse(String(fetch.mock.calls[0][1].body)).logs[0].props;
    expect(props).toMatchObject({ route: '/claims/:param', status: 404, edge_cache: edgeCache });
    expect(props).not.toHaveProperty('render_ms');
  });

  it.each(['bad-colo!', 'TOOLONG123', '', undefined])('sanitizes colo %s', (colo) => {
    const { context, fetch } = setup('/sources/[id]', colo);
    if (colo === undefined) {
      Object.defineProperty(context.request, 'cf', { value: undefined });
    }
    observeStageTiming(context, { response: new Response(), edgeCache: 'HIT' }, 1);
    expect(JSON.parse(String(fetch.mock.calls[0][1].body)).logs[0].props.colo).toBe('unknown');
  });

  it.each(['0', '-1'])('does not sample at rate %s', (rate) => {
    env.APP_HEALTH_STAGE_SAMPLE_RATE = rate;
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const { context, scheduled, fetch } = setup();
    observeStageTiming(context, { response: new Response(), edgeCache: 'MISS' }, 1);
    expect(fetch).not.toHaveBeenCalled();
    expect(scheduled).toHaveLength(0);
  });

  it('uses the default single 0.1 rate for both misses and stale requests', () => {
    env.APP_HEALTH_STAGE_SAMPLE_RATE = undefined;
    const random = vi.spyOn(Math, 'random').mockReturnValue(0.1);
    const { context, fetch } = setup();
    observeStageTiming(context, { response: new Response(), edgeCache: 'MISS' }, 1);
    observeStageTiming(context, { response: new Response(), edgeCache: 'STALE' }, 1);
    expect(fetch).not.toHaveBeenCalled();
    random.mockReturnValue(0.09);
    observeStageTiming(context, { response: new Response(), edgeCache: 'HIT' }, 1);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(['', '   '])('silently skips without an ingest key: %j', (key) => {
    env.APP_HEALTH_INGEST_KEY = key;
    const { context, scheduled, fetch } = setup();
    observeStageTiming(context, { response: new Response(), edgeCache: 'MISS' }, 1);
    expect(fetch).not.toHaveBeenCalled();
    expect(scheduled).toHaveLength(0);
  });

  it.each(['', '/people?q=secret', '/people#private', '/people private'])(
    'rejects invalid route template %j',
    (pattern) => {
      const { context, fetch } = setup(pattern);
      observeStageTiming(context, { response: new Response(), edgeCache: 'HIT' }, 1);
      expect(fetch).not.toHaveBeenCalled();
    }
  );

  it('bounds timing values to the fleet contract', () => {
    const { context, fetch } = setup();
    observeStageTiming(
      context,
      { response: new Response(), edgeCache: 'MISS', renderMs: 900_000 },
      -1
    );
    expect(JSON.parse(String(fetch.mock.calls[0][1].body)).logs[0].props).toMatchObject({
      total_ms: 0,
      render_ms: 600_000,
    });
  });

  it.each(['fetch', 'schedule'])(
    'cannot fail a request on telemetry failure: %s',
    async (failure) => {
      const { context, scheduled, fetch } = setup();
      if (failure === 'fetch') {
        fetch.mockRejectedValue(new Error('collector failed'));
      } else {
        context.locals.cfContext.waitUntil = () => {
          throw new Error('schedule failed');
        };
      }
      expect(() =>
        observeStageTiming(context, { response: new Response(), edgeCache: 'MISS' }, 1)
      ).not.toThrow();
      await expect(Promise.all(scheduled)).resolves.toBeDefined();
    }
  );
});
