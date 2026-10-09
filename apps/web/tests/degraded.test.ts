import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiGet, homepageEvidence } from '../src/lib/api';
import { markDegraded, runWithDegradedTracking } from '../src/lib/degraded';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('request-scoped degradation tracking', () => {
  it('makes markDegraded outside a store a no-op', async () => {
    expect(markDegraded).not.toThrow();
    await expect(runWithDegradedTracking(() => 'healthy')).resolves.toEqual({
      result: 'healthy',
      degraded: false,
    });
  });

  it('marks the current render after an asynchronous boundary', async () => {
    const tracked = await runWithDegradedTracking(async () => {
      await Promise.resolve();
      markDegraded();
      return 'unavailable';
    });
    expect(tracked).toEqual({ result: 'unavailable', degraded: true });
    expect(markDegraded).not.toThrow();
    await expect(runWithDegradedTracking(() => 'healthy')).resolves.toEqual({
      result: 'healthy',
      degraded: false,
    });
  });

  it('isolates two interleaved renders', async () => {
    let resumeDegraded: () => void = () => undefined;
    let resumeHealthy: () => void = () => undefined;
    const degradedGate = new Promise<void>((resolve) => {
      resumeDegraded = resolve;
    });
    const healthyGate = new Promise<void>((resolve) => {
      resumeHealthy = resolve;
    });
    const degradedRender = runWithDegradedTracking(async () => {
      await degradedGate;
      markDegraded();
      return 'unavailable';
    });
    const healthyRender = runWithDegradedTracking(async () => {
      await healthyGate;
      return 'healthy';
    });
    resumeDegraded();
    await expect(degradedRender).resolves.toEqual({ result: 'unavailable', degraded: true });
    resumeHealthy();
    await expect(healthyRender).resolves.toEqual({ result: 'healthy', degraded: false });
  });

  it.each(['status', 'fetch', 'timeout', 'json'])(
    'tracks API failure without changing the thrown error: %s',
    async (failure) => {
      const error =
        failure === 'timeout'
          ? new DOMException('timed out', 'TimeoutError')
          : new Error('network failed');
      const fetch = vi.fn(async (_url: string, _init?: RequestInit) => {
        if (failure === 'status') {
          return new Response(null, { status: 503 });
        }
        if (failure === 'json') {
          return new Response('invalid JSON');
        }
        throw error;
      });
      const tracked = await runWithDegradedTracking(async () => {
        try {
          await apiGet('/api/search', { API: { fetch } }, { timeoutMs: 1000 });
        } catch (caught) {
          return caught;
        }
      });
      expect(tracked.degraded).toBe(true);
      if (failure === 'status') {
        expect(tracked.result).toEqual(new Error('/api/search failed: 503'));
      } else if (failure === 'json') {
        expect(tracked.result).toBeInstanceOf(SyntaxError);
      } else {
        expect(tracked.result).toBe(error);
      }
      expect(fetch.mock.calls[0][1]?.signal).toBeInstanceOf(AbortSignal);
    }
  );

  it('tracks failures from the unbound fetch path', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network failed')));
    const tracked = await runWithDegradedTracking(() => apiGet('/api/search').catch(() => null));
    expect(tracked).toEqual({ result: null, degraded: true });
  });

  it('keeps successful API results healthy', async () => {
    const payload = { claims: [] };
    const tracked = await runWithDegradedTracking(() =>
      apiGet('/api/search', { API: { fetch: async () => Response.json(payload) } })
    );
    expect(tracked).toEqual({ result: payload, degraded: false });
  });
});

describe('homepage fallbacks', () => {
  it('marks a 200 response with an invalid claim payload as degraded', async () => {
    const payload = { claims: [{ id: 'bad' }] };
    const env = {
      API: { fetch: async () => new Response(JSON.stringify(payload), { status: 200 }) },
    };
    const tracked = await runWithDegradedTracking(() => homepageEvidence(env));
    expect(tracked.result.status).toBe('unavailable');
    expect(tracked.degraded).toBe(true);
  });
});
