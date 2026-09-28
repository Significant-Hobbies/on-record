import { Hono } from 'hono';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Env } from './env';
import { endpointTelemetryMiddleware } from './telemetry';

afterEach(() => vi.unstubAllGlobals());

describe('App Health endpoint telemetry', () => {
  it('sends only a matched public route summary through waitUntil', async () => {
    const fetch = vi.fn(
      async (_input: string | URL | Request, _init?: RequestInit) =>
        new Response(null, { status: 202 })
    );
    vi.stubGlobal('fetch', fetch);

    const app = new Hono();
    app.use('/api/*', endpointTelemetryMiddleware);
    app.get('/api/people/:slug', (c) => c.json({ ok: true }, 201));
    const scheduled: Promise<unknown>[] = [];

    const response = await app.request(
      '/api/people/jane-doe?private=value',
      undefined,
      {
        APP_HEALTH_INGEST_KEY: 'ahk_test_0123456789abcdef',
        ENVIRONMENT: 'test',
      } as Env,
      {
        waitUntil: (promise: Promise<unknown>) => {
          scheduled.push(promise);
        },
      } as unknown as ExecutionContext
    );

    expect(response.status).toBe(201);
    expect(scheduled).toHaveLength(1);
    await Promise.all(scheduled);

    expect(fetch).toHaveBeenCalledTimes(1);
    const requestInit = fetch.mock.calls[0]?.[1];
    const batch = JSON.parse(String(requestInit?.body)) as {
      runtime: string;
      environment: string;
      events: Record<string, unknown>[];
    };
    expect(batch.runtime).toBe('worker');
    expect(batch.environment).toBe('test');
    expect(batch.events).toHaveLength(1);
    expect(batch.events[0]).toMatchObject({
      method: 'GET',
      route: '/api/people/:slug',
      status_code: 201,
      duration_ms: expect.any(Number),
    });
    expect(Object.keys(batch.events[0] ?? {}).sort()).toEqual(
      ['duration_ms', 'event_id', 'method', 'route', 'status_code', 'timestamp'].sort()
    );
    expect(requestInit?.body).not.toContain('jane-doe');
    expect(requestInit?.body).not.toContain('private');
  });

  it('does not collect when the ingest secret is absent', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const app = new Hono();
    app.use('/api/*', endpointTelemetryMiddleware);
    app.get('/api/stats', (c) => c.json({ ok: true }));
    const scheduled: Promise<unknown>[] = [];

    const response = await app.request(
      '/api/stats',
      undefined,
      {} as Env,
      {
        waitUntil: (promise: Promise<unknown>) => {
          scheduled.push(promise);
        },
      } as unknown as ExecutionContext
    );

    expect(response.status).toBe(200);
    expect(fetch).not.toHaveBeenCalled();
    expect(scheduled).toHaveLength(0);
  });

  it('does not collect unmatched, root, health, or admin requests', async () => {
    const fetch = vi.fn(async () => new Response(null, { status: 202 }));
    vi.stubGlobal('fetch', fetch);
    const app = new Hono();
    app.use('/api/*', endpointTelemetryMiddleware);
    app.get('/api/stats', (c) => c.json({ ok: true }));
    const env = {
      APP_HEALTH_INGEST_KEY: 'ahk_test_0123456789abcdef',
      ENVIRONMENT: 'test',
    } as Env;
    const scheduled: Promise<unknown>[] = [];
    const executionCtx = {
      waitUntil: (promise: Promise<unknown>) => {
        scheduled.push(promise);
      },
    } as unknown as ExecutionContext;

    for (const path of ['/', '/health', '/admin/jobs', '/api/not-a-route']) {
      await app.request(path, undefined, env, executionCtx);
    }
    await Promise.all(scheduled);

    expect(fetch).not.toHaveBeenCalled();
    expect(scheduled).toHaveLength(0);
  });

  it('does not change a response when the collector fails', async () => {
    const fetch = vi.fn(async () => {
      throw new Error('collector unavailable');
    });
    vi.stubGlobal('fetch', fetch);
    const app = new Hono();
    app.use('/api/*', endpointTelemetryMiddleware);
    app.get('/api/stats', (c) => c.json({ ok: true }));
    const scheduled: Promise<unknown>[] = [];

    const response = await app.request(
      '/api/stats',
      undefined,
      {
        APP_HEALTH_INGEST_KEY: 'ahk_test_0123456789abcdef',
        ENVIRONMENT: 'test',
      } as Env,
      {
        waitUntil: (promise: Promise<unknown>) => {
          scheduled.push(promise);
        },
      } as unknown as ExecutionContext
    );
    await Promise.all(scheduled);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledTimes(4);
  });
});
